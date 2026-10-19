"""Original-PDF to SQL import orchestration; never infer ownership from a file."""

import os
import stat
from dataclasses import asdict
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path

from sqlalchemy import select

from core.config import CONFIG_ROOT
from core.extraction import ParseError
from core.parser import parse_pdf_bytes
from core.persistence.import_records import duplicate, result
from core.persistence.models import Entry, ImportRecord, Statement
from core.persistence.store import StoreError, require_card, store_session

INPUT_ROOT = CONFIG_ROOT / "data"


def _snapshot(path):
    try:
        resolved = Path(path).resolve()
        if not resolved.is_relative_to(INPUT_ROOT):
            raise StoreError(
                "input_path_not_allowed",
                "Import files must be inside the project's data directory.",
            )
        flags = (
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        )
        with os.fdopen(os.open(resolved, flags), "rb") as source:
            if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                raise StoreError(
                    "input_unreadable", "Import input must be a regular file."
                )
            return source.read()
    except (OSError, RuntimeError):
        raise StoreError("input_unreadable", "Cannot read the original PDF.") from None


def _parse(data, source_name, password, provider):
    try:
        return parse_pdf_bytes(data, source_name=source_name, password=password)
    except ParseError as error:
        if error.code != "incorrect_password" or provider is None:
            raise
    password = provider()
    try:
        return parse_pdf_bytes(data, source_name=source_name, password=password)
    finally:
        password = None


def _target(session, owner_id, card_id, parsed):
    matches = []
    if parsed.statement_date is not None:
        matches = session.scalars(
            select(Statement).where(
                Statement.owner_id == owner_id,
                Statement.card_id == card_id,
                Statement.statement_date == parsed.statement_date,
            )
        ).all()
    if len(matches) == 1:
        return matches[0], False, [{"code": "competing_statement_file", "page": None}]
    statement = Statement(
        owner_id=owner_id, card_id=card_id, statement_date=parsed.statement_date
    )
    session.add(statement)
    session.flush()
    if matches:
        return (
            statement,
            False,
            [
                {
                    "code": "ambiguous_statement_match",
                    "page": None,
                    "candidate_statement_ids": [str(row.id) for row in matches],
                }
            ],
        )
    if parsed.statement_date is None:
        return statement, False, [{"code": "statement_match_unresolved", "page": None}]
    return statement, True, []


def _entry(owner_id, import_id, row):
    return Entry(
        owner_id=owner_id,
        import_id=import_id,
        sequence=row.sequence,
        transaction_date=row.transaction_date,
        transaction_time=row.transaction_time,
        description=row.description,
        amount=row.amount,
        direction=row.direction.value if row.direction is not None else None,
        currency=row.currency,
        entry_type=row.entry_type.value,
        section=row.section,
        raw_date=row.raw_date,
        raw_time=row.raw_time,
        raw_amount=row.raw_amount,
        source_page=row.source.page,
        source_bbox=list(row.source.bbox),
        source_raw_text=row.source.raw_text,
        issues=[asdict(issue) for issue in row.issues],
    )


def _persist(session, owner_id, card_id, data, parsed):
    statement, selected, extra_issues = _target(session, owner_id, card_id, parsed)
    imported = ImportRecord(
        owner_id=owner_id,
        card_id=card_id,
        statement_id=statement.id,
        source_filename=parsed.source_name,
        file_sha256=parsed.source_sha256,
        file_size_bytes=len(data),
        pdf_bytes=data,
        parsed_statement_date=parsed.statement_date,
        page_count=parsed.page_count,
        parser_version=parsed.parser_version,
        extractor_version="hisaab-extraction-1/pdfplumber-" + version("pdfplumber"),
        schema_version=parsed.schema_version,
        printed_balance=(
            parsed.printed_balance.to_dict() if parsed.printed_balance else None
        ),
        issues=[asdict(issue) for issue in parsed.issues] + extra_issues,
    )
    session.add(imported)
    session.flush()
    session.add_all(_entry(owner_id, imported.id, row) for row in parsed.transactions)
    if selected:
        statement.active_import_id = imported.id
    session.flush()
    return result(session, imported, "imported" if selected else "review_candidate")


def import_pdf(engine, owner_id, card_id, path, *, password="", password_provider=None):
    """One file, one transaction. Existing fingerprints return without decrypting.

    Card row locks serialize same-card classification and retries. Parsing/password
    entry happen before acquiring that lock; the final duplicate check is inside it.
    https://docs.sqlalchemy.org/en/21/core/selectable.html#sqlalchemy.sql.expression.GenerativeSelect.with_for_update
    """
    with store_session(engine) as session:
        bank = require_card(session, owner_id, card_id).bank
    data = _snapshot(path)
    digest = sha256(data).hexdigest()
    with store_session(engine) as session:
        existing = duplicate(session, owner_id, card_id, digest)
        if existing is not None:
            return existing
    parsed = _parse(data, Path(path).name, password, password_provider)
    if parsed.source_sha256 != digest or parsed.input_kind != "pdf":
        raise StoreError(
            "snapshot_mismatch",
            "Parser evidence does not match the original PDF snapshot.",
        )
    if parsed.bank != bank:
        raise StoreError(
            "bank_mismatch", "Statement bank does not match the selected card."
        )
    with store_session(engine) as session:
        card = require_card(session, owner_id, card_id, lock=True)
        if parsed.bank != card.bank:
            raise StoreError(
                "bank_mismatch", "Statement bank does not match the selected card."
            )
        existing = duplicate(session, owner_id, card_id, digest)
        if existing is not None:
            return existing
        return _persist(session, owner_id, card_id, data, parsed)
