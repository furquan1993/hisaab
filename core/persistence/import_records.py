"""Owner-scoped import summaries and explicit original-byte retrieval."""

from dataclasses import asdict, dataclass
from hashlib import sha256
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import undefer

from core.persistence.models import Entry, ImportRecord, Statement
from core.persistence.store import (
    StoreError,
    page,
    require_card,
    require_owner,
    store_session,
)


@dataclass(frozen=True)
class ImportResult:
    status: str
    owner_id: UUID
    card_id: UUID
    statement_id: UUID
    import_id: UUID
    transaction_count: int
    review_issue_count: int
    review_status: str
    selected_source: bool
    needs_review: bool

    def to_dict(self):
        return {
            key: str(value) if isinstance(value, UUID) else value
            for key, value in asdict(self).items()
        }


def result(session, record, status):
    selected = (
        session.scalar(
            select(Statement.active_import_id).where(
                Statement.owner_id == record.owner_id,
                Statement.id == record.statement_id,
            )
        )
        == record.id
    )
    issues = session.scalars(
        select(Entry.issues).where(
            Entry.owner_id == record.owner_id, Entry.import_id == record.id
        )
    ).all()
    count = len(record.issues) + sum(len(row) for row in issues)
    return ImportResult(
        status,
        record.owner_id,
        record.card_id,
        record.statement_id,
        record.id,
        len(issues),
        count,
        record.review_status,
        selected,
        bool(count or not selected or record.review_status == "rejected"),
    )


def duplicate(session, owner_id, card_id, digest):
    record = session.scalar(
        select(ImportRecord).where(
            ImportRecord.owner_id == owner_id,
            ImportRecord.card_id == card_id,
            ImportRecord.file_sha256 == digest,
        )
    )
    return result(session, record, "duplicate") if record is not None else None


def list_imports(engine, owner_id, *, card_id=None, limit=50, offset=0):
    page(limit, offset)
    with store_session(engine) as session:
        require_owner(session, owner_id)
        query = select(ImportRecord).where(ImportRecord.owner_id == owner_id)
        if card_id is not None:
            require_card(session, owner_id, card_id)
            query = query.where(ImportRecord.card_id == card_id)
        records = session.scalars(
            query.order_by(ImportRecord.created_at, ImportRecord.id)
            .limit(limit)
            .offset(offset)
        )
        return [result(session, record, "stored").to_dict() for record in records]


def read_original(engine, owner_id, import_id):
    with store_session(engine) as session:
        record = session.scalar(
            select(ImportRecord)
            .options(undefer(ImportRecord.pdf_bytes))
            .where(ImportRecord.owner_id == owner_id, ImportRecord.id == import_id)
        )
        if record is None:
            raise StoreError(
                "import_not_found", "Import is not available for the selected owner."
            )
        if record.pdf_bytes is None:
            raise StoreError("pdf_not_retained", "Original PDF is no longer retained.")
        data = record.pdf_bytes
        if (
            len(data) != record.file_size_bytes
            or sha256(data).hexdigest() != record.file_sha256
        ):
            raise StoreError(
                "pdf_integrity_failed", "Stored PDF failed fingerprint verification."
            )
        return data
