"""Explicit candidate reparsing; ordinary imports never reparse or replace facts."""

from dataclasses import asdict
from importlib.metadata import version

from sqlalchemy import bindparam, select, text
from sqlalchemy.dialects.postgresql import JSONB

from core.imports import _entry, _parse
from core.persistence.import_records import read_original
from core.persistence.models import ImportRecord, Statement
from core.persistence.store import StoreError, require_card, store_session


def reparse_import(engine, owner_id, import_id, *, password="", password_provider=None):
    with store_session(engine) as session:
        source = session.scalar(
            select(ImportRecord).where(
                ImportRecord.owner_id == owner_id, ImportRecord.id == import_id
            )
        )
        if source is None:
            raise StoreError(
                "import_not_found", "Import is not available for the selected owner."
            )
        card_id, statement_id = source.card_id, source.statement_id
        source_id = source.source_import_id or source.id
        name, digest, size = (
            source.source_filename,
            source.file_sha256,
            source.file_size_bytes,
        )
    data = read_original(engine, owner_id, import_id)
    parsed = _parse(data, name, password, password_provider)
    if parsed.source_sha256 != digest or parsed.input_kind != "pdf":
        raise StoreError(
            "snapshot_mismatch", "Reparse does not match the retained original."
        )
    with store_session(engine) as session:
        card = require_card(session, owner_id, card_id, lock=True)
        if parsed.bank != card.bank:
            raise StoreError(
                "bank_mismatch", "Reparse bank does not match the selected card."
            )
        statement = session.scalar(
            select(Statement)
            .where(Statement.owner_id == owner_id, Statement.id == statement_id)
            .with_for_update()
        )
        issues = [asdict(issue) for issue in parsed.issues]
        if parsed.statement_date != statement.statement_date:
            issues.append({"code": "statement_date_conflict", "page": None})
        candidate = ImportRecord(
            owner_id=owner_id,
            card_id=card_id,
            statement_id=statement_id,
            source_import_id=source_id,
            source_filename=name,
            file_sha256=digest,
            file_size_bytes=size,
            pdf_bytes=None,
            parsed_statement_date=parsed.statement_date,
            page_count=parsed.page_count,
            parser_version=parsed.parser_version,
            extractor_version="hisaab-extraction-1/pdfplumber-" + version("pdfplumber"),
            schema_version=parsed.schema_version,
            issues=issues,
        )
        session.add(candidate)
        session.flush()
        session.add_all(
            _entry(owner_id, candidate.id, row) for row in parsed.transactions
        )
        session.flush()
        return session.scalar(
            text("SELECT hisaab.prepare_revision_for_owner(:owner,:candidate)"),
            {"owner": owner_id, "candidate": candidate.id},
        )


def accept_revision(
    engine,
    owner_id,
    revision_id,
    *,
    mapping=None,
    removed=(),
    reason,
    ack_metadata=False,
):
    with store_session(engine) as session:
        query = text(
            "SELECT hisaab.accept_revision_for_owner(:owner,:revision,:mapping,:removed,:reason,:ack)"
        ).bindparams(
            bindparam("mapping", type_=JSONB), bindparam("removed", type_=JSONB)
        )
        return session.scalar(
            query,
            {
                "owner": owner_id,
                "revision": revision_id,
                "mapping": mapping or [],
                "removed": list(removed),
                "reason": reason,
                "ack": ack_metadata,
            },
        )
