"""Capture missing bill facts without reparsing or replacing selected entries."""

from hashlib import sha256
import json

from sqlalchemy import select

from core.imports import _entry
from core.persistence.models import Entry, ImportRecord
from core.persistence.store import StoreError, require_card, store_session


def capture_printed_balance(engine, owner_id, import_id, parsed, original_bytes, *, apply=False):
    """Preview by default; only fill absent bill evidence for a verified import.

    A cached local probe is accepted only when the original PDF fingerprint,
    statement metadata and every extracted transaction/source field agree with
    the retained immutable import. User decisions and source selection are not
    touched. Existing, different bill evidence is never overwritten.
    """
    if parsed.printed_balance is None:
        raise StoreError("bill_not_captured", "No supported printed bill summary was found.")
    digest = sha256(original_bytes).hexdigest()
    if parsed.input_kind == "pdf" and parsed.source_sha256 != digest:
        raise StoreError("snapshot_mismatch", "Parsed source does not match the original PDF.")
    with store_session(engine) as session:
        record = session.scalar(select(ImportRecord).where(
            ImportRecord.owner_id == owner_id, ImportRecord.id == import_id,
        ).with_for_update())
        if record is None:
            raise StoreError("import_not_found", "Import is unavailable for the selected owner.")
        card = require_card(session, owner_id, record.card_id)
        if (record.file_sha256, record.file_size_bytes, record.page_count,
            record.parsed_statement_date, card.bank) != (
            digest, len(original_bytes), parsed.page_count, parsed.statement_date, parsed.bank,
        ):
            raise StoreError("snapshot_mismatch", "Bill source does not match the retained import.")
        actual = session.scalars(select(Entry).where(
            Entry.owner_id == owner_id, Entry.import_id == import_id,
        ).order_by(Entry.sequence)).all()
        fields = ("sequence", "transaction_date", "transaction_time", "description",
                  "amount", "direction", "currency", "entry_type", "section",
                  "raw_date", "raw_time", "raw_amount", "source_page",
                  "source_bbox", "source_raw_text")
        expected = [_entry(owner_id, import_id, row) for row in parsed.transactions]
        if len(actual) != len(expected) or any(
            any(getattr(a, field) != getattr(b, field) for field in fields)
            for a, b in zip(actual, expected)
        ):
            raise StoreError("evidence_mismatch", "Cached extraction does not match retained transaction evidence.")
        value = parsed.printed_balance.to_dict()
        if record.printed_balance is not None:
            # JSON turns bbox tuples into lists on persistence.
            if record.printed_balance != json.loads(json.dumps(value)):
                raise StoreError("bill_conflict", "Different printed bill evidence is already captured.")
            return {"status": "unchanged", "import_id": str(import_id)}
        if apply:
            record.printed_balance = value
        return {"status": "captured" if apply else "ready", "import_id": str(import_id)}
