"""Trusted operator training; historical rows are examples, never ledger entries."""

from collections import Counter, defaultdict
from pathlib import Path
import re
from uuid import UUID, uuid4

from sqlalchemy import select, text, func
from sqlalchemy.dialects.postgresql import insert

from core.assignment_history import read_history
from core.config import CONFIG_ROOT
from core.persistence.models import (
    AssignmentExample, Category, FundingAccount, Owner, Statement,
)
from core.persistence.store import StoreError, store_session


def merchant_key(description):
    without_references = re.sub("[0-9]{6,}", " ", description.lower())
    return re.sub("[^a-z0-9]+", " ", without_references).strip()


def load_examples(paths):
    examples = {}
    for path in paths:
        resolved = Path(path).resolve()
        if (
            not resolved.is_relative_to(CONFIG_ROOT / "data/reference")
            or not resolved.is_file()
            or resolved.suffix.lower() != ".xlsx"
        ):
            raise StoreError(
                "input_path_not_allowed", "Choose XLSX files inside data/reference."
            )
        for example in read_history(resolved):
            examples[example.source_key] = example
    return list(examples.values())


def history_summary(examples):
    groups = defaultdict(Counter)
    for example in examples:
        for kind in ("account", "category"):
            label = getattr(example, kind)
            if label:
                key = (kind, merchant_key(example.description), example.direction)
                groups[key][label.casefold()] += 1
    ready = Counter()
    for (kind, key, _direction), counts in groups.items():
        top = counts.most_common(1)[0][1]
        if len(key) >= 3 and top >= 2 and top / counts.total() >= 0.9:
            ready[kind] += 1
    return {
        "examples": len(examples),
        "account_patterns": ready["account"],
        "category_patterns": ready["category"],
    }


def train_assignments(engine, owner_id: UUID, examples):
    """Atomic, idempotent history load plus backfill of selected entries only."""
    with store_session(engine) as session:
        owner = session.scalar(
            select(Owner).where(Owner.id == owner_id).with_for_update()
        )
        if owner is None:
            raise StoreError("owner_not_found", "Selected owner does not exist.")
        statements = session.scalars(
            select(Statement.id)
            .where(Statement.owner_id == owner_id)
            .order_by(Statement.id)
            .with_for_update()
        ).all()
        labels = {}
        added = skipped = 0
        pending = []
        for example in examples:
            for kind, model in (("account", FundingAccount), ("category", Category)):
                name = getattr(example, kind)
                if not name or len(merchant_key(example.description)) < 3:
                    continue
                key = (kind, name.casefold())
                if key not in labels:
                    scope = str(owner_id) + ":" + model.__tablename__
                    session.execute(
                        text("SELECT pg_advisory_xact_lock(hashtextextended(:scope,0))"),
                        {"scope": scope},
                    )
                    label = session.scalar(
                        select(model).where(
                            model.owner_id == owner_id,
                            func.lower(model.name) == name.lower(),
                        )
                    )
                    if label is None:
                        label = model(owner_id=owner_id, name=name)
                        session.add(label)
                        session.flush()
                    labels[key] = label
                label = labels[key]
                if label.is_archived:
                    skipped += 1
                    continue
                values = dict(
                    id=uuid4(), owner_id=owner_id, source_key=example.source_key,
                    merchant_key=merchant_key(example.description),
                    direction=example.direction, kind=kind, is_manual=False,
                    account_id=label.id if kind == "account" else None,
                    category_id=label.id if kind == "category" else None,
                )
                pending.append(values)
        # Keep network round trips and PostgreSQL bind counts bounded for long histories.
        for start in range(0, len(pending), 200):
            result = session.execute(
                insert(AssignmentExample).values(pending[start:start + 200])
                .on_conflict_do_nothing(constraint="uq_assignment_examples_source")
                .returning(AssignmentExample.id)
            )
            added += len(result.scalars().all())
        entries = session.execute(
            text("""SELECT e.id FROM hisaab.entries e
                JOIN hisaab.imports i ON i.id=e.import_id AND i.owner_id=e.owner_id
                JOIN hisaab.statements s ON s.id=i.statement_id AND s.owner_id=i.owner_id
                WHERE e.owner_id=:owner AND s.active_import_id=i.id
                  AND s.id=ANY(:statements) ORDER BY s.id,e.id"""),
            {"owner": owner_id, "statements": statements},
        ).scalars().all()
        assigned = sum(
            bool(session.scalar(
                text("SELECT hisaab.apply_entry_assignments(:owner,:entry)"),
                {"owner": owner_id, "entry": entry},
            ))
            for entry in entries
        )
        return {
            **history_summary(examples), "added_examples": added,
            "skipped_archived_labels": skipped, "assigned_entries": assigned,
        }
