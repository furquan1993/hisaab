"""Invented rows only. Safe for a disposable PostgreSQL test database."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from hashlib import sha256
from uuid import uuid4

from core.persistence.models import Card, Entry, ImportRecord, Owner, Statement

PDF = b"%PDF-1.4\nsynthetic fixture only\n%%EOF\n"


@dataclass
class Records:
    owner: Owner
    card: Card
    statement: Statement
    imported: ImportRecord
    entry: Entry


def seed(session):
    owner = Owner(id=uuid4(), display_name="Synthetic owner")
    session.add(owner)
    session.flush()
    card = Card(
        id=uuid4(),
        owner_id=owner.id,
        bank="hdfc",
        label="Invented card",
        last_four="1234",
    )
    session.add(card)
    session.flush()
    statement = Statement(
        id=uuid4(), owner_id=owner.id, card_id=card.id, statement_date=date(2026, 1, 31)
    )
    session.add(statement)
    session.flush()
    imported = ImportRecord(
        id=uuid4(),
        owner_id=owner.id,
        card_id=card.id,
        statement_id=statement.id,
        source_filename="synthetic.pdf",
        file_sha256=sha256(PDF).hexdigest(),
        file_size_bytes=len(PDF),
        pdf_bytes=PDF,
        page_count=1,
        parsed_statement_date=date(2026, 1, 31),
        parser_version="synthetic-1",
        extractor_version="synthetic-1",
        issues=[{"code": "synthetic_review"}],
    )
    session.add(imported)
    session.flush()
    entry = new_entry(imported)
    session.add(entry)
    statement.active_import_id = imported.id
    session.flush()
    return Records(owner, card, statement, imported, entry)


def new_import(records, payload=PDF + b"another download", **changes):
    values = dict(
        id=uuid4(),
        owner_id=records.owner.id,
        card_id=records.card.id,
        statement_id=records.statement.id,
        source_filename="another.pdf",
        file_sha256=sha256(payload).hexdigest(),
        file_size_bytes=len(payload),
        pdf_bytes=payload,
        page_count=1,
        parsed_statement_date=date(2026, 1, 31),
        parser_version="synthetic-1",
        extractor_version="synthetic-1",
        issues=[],
    )
    values.update(changes)
    return ImportRecord(**values)


def new_entry(imported, **changes):
    values = dict(
        id=uuid4(),
        owner_id=imported.owner_id,
        import_id=imported.id,
        sequence=1,
        transaction_date=date(2026, 1, 1),
        transaction_time=None,
        description="SYNTHETIC SHOP",
        amount=Decimal("123.45"),
        direction="debit",
        currency="INR",
        entry_type="purchase",
        section="domestic",
        raw_date="01/01/2026",
        raw_time="",
        raw_amount="123.45",
        source_page=1,
        source_bbox=[10.0, 20.0, 300.0, 40.0],
        source_raw_text="01/01/2026 SYNTHETIC SHOP 123.45",
        issues=[],
    )
    values.update(changes)
    return Entry(**values)
