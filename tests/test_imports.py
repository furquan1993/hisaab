from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import func, select, update

from core.imports import import_pdf
from core.parser import parse_pdf_bytes
from core.persistence.import_records import list_imports, read_original
from core.persistence.models import Entry, ImportRecord, Statement
from core.persistence.store import StoreError, register_card
from tests.import_fixture import ImportTestsBase
from tests.test_snapshot import encrypt, statement_bytes


class ImportTests(ImportTestsBase):
    def load(self, path=None, **kwargs):
        return import_pdf(
            self.engine, self.owner, self.card, path or self.path, **kwargs
        )

    def test_complete_pdf_round_trip_exact_rows_and_source(self):
        data = self.path.read_bytes()
        parsed = parse_pdf_bytes(data, source_name=self.path.name)
        saved = self.load()
        self.assertEqual(saved.status, "imported")
        self.assertEqual(saved.transaction_count, 2)
        self.assertTrue(saved.selected_source)
        self.assertEqual(read_original(self.engine, self.owner, saved.import_id), data)
        with self.engine.connect() as connection:
            rows = (
                connection.execute(
                    select(Entry.__table__)
                    .where(Entry.import_id == saved.import_id)
                    .order_by(Entry.sequence)
                )
                .mappings()
                .all()
            )
            for actual, expected in zip(rows, parsed.transactions, strict=True):
                self.assertEqual(actual["amount"], expected.amount)
                self.assertEqual(actual["transaction_date"], expected.transaction_date)
                self.assertEqual(actual["description"], expected.description)
                self.assertEqual(actual["source_raw_text"], expected.source.raw_text)
                self.assertEqual(actual["source_bbox"], list(expected.source.bbox))
            self.assertEqual(
                connection.scalar(select(ImportRecord.file_sha256)),
                sha256(data).hexdigest(),
            )

    def test_sbi_and_yesbank_encrypted_originals_keep_all_fields(self):
        from dataclasses import asdict

        from tests.bank_fixture import BankPage
        from tests.hdfc_fixture import pdf_bytes

        for bank in ("sbi", "yes_bank"):
            with self.subTest(bank=bank):
                card = register_card(
                    self.engine, self.owner, bank=bank, label="Synthetic"
                )
                page = BankPage(bank)
                page.header()
                page.row(250, "SYNTHETIC SHOP", "123.45")
                page.row(
                    275,
                    "UNKNOWN SYNTHETIC CREDIT",
                    "7.00",
                    marker="C" if bank == "sbi" else "Cr",
                )
                if bank == "sbi":
                    page.row(300, "IGST", "18.00", day="", marker="C")
                page.footer(340)
                original = encrypt(pdf_bytes([page]))
                path = self.root / (bank + ".pdf")
                path.write_bytes(original)
                parsed = parse_pdf_bytes(
                    original, source_name=path.name, password="synthetic-password"
                )
                saved = import_pdf(
                    self.engine, self.owner, card, path, password="synthetic-password"
                )
                self.assertTrue(saved.needs_review)
                self.assertEqual(
                    read_original(self.engine, self.owner, saved.import_id), original
                )
                with self.engine.connect() as connection:
                    rows = (
                        connection.execute(
                            select(Entry.__table__)
                            .where(Entry.import_id == saved.import_id)
                            .order_by(Entry.sequence)
                        )
                        .mappings()
                        .all()
                    )
                for actual, expected in zip(rows, parsed.transactions, strict=True):
                    for key in (
                        "transaction_date",
                        "transaction_time",
                        "description",
                        "amount",
                        "currency",
                        "entry_type",
                        "raw_date",
                        "raw_time",
                        "raw_amount",
                    ):
                        self.assertEqual(actual[key], getattr(expected, key))
                    self.assertEqual(
                        actual["issues"], [asdict(issue) for issue in expected.issues]
                    )
                    self.assertEqual(
                        actual["source_raw_text"], expected.source.raw_text
                    )

    def test_renamed_reimport_returns_same_ids_without_parsing(self):
        first = self.load()
        other = self.root / "renamed.anything"
        other.write_bytes(self.path.read_bytes())
        with patch(
            "core.imports.parse_pdf_bytes", side_effect=AssertionError("No reparse")
        ):
            second = self.load(other)
        self.assertEqual(second.status, "duplicate")
        self.assertEqual(second.import_id, first.import_id)
        self.assertEqual(second.statement_id, first.statement_id)
        self.assertEqual(len(list_imports(self.engine, self.owner)), 1)

    def test_changed_bytes_become_candidate_without_overwrite(self):
        first = self.load()
        self.path.write_bytes(statement_bytes("ANOTHER SYNTHETIC SHOP"))
        second = self.load()
        self.assertEqual(second.status, "review_candidate")
        self.assertEqual(second.statement_id, first.statement_id)
        self.assertFalse(second.selected_source)
        self.assertTrue(second.needs_review)
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(select(Statement.active_import_id)), first.import_id
            )
            self.assertEqual(
                connection.scalar(select(func.count()).select_from(Entry)), 4
            )

    def test_password_stays_in_memory_and_duplicate_does_not_prompt(self):
        self.path.write_bytes(encrypt(self.path.read_bytes()))
        result = self.load(password_provider=lambda: "synthetic-password")
        with patch(
            "core.imports.parse_pdf_bytes", side_effect=AssertionError("No decrypt")
        ):
            self.assertEqual(self.load().import_id, result.import_id)

    def test_wrong_password_and_corrupt_input_leave_database_empty(self):
        for data in (encrypt(statement_bytes()), b'{"source":"probe.pdf"}'):
            self.path.write_bytes(data)
            with self.assertRaises(Exception):
                self.load(password="wrong")
        self.assertEqual(list_imports(self.engine, self.owner), [])

    def test_late_entry_failure_rolls_back_statement_and_import(self):
        from sqlalchemy import event

        def fail(mapper, connection, target):
            raise RuntimeError("synthetic-sensitive-value")

        event.listen(Entry, "before_insert", fail)
        try:
            with self.assertRaises(RuntimeError):
                self.load()
        finally:
            event.remove(Entry, "before_insert", fail)
        self.assertEqual(list_imports(self.engine, self.owner), [])
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(select(func.count()).select_from(Statement)), 0
            )

    def test_cross_owner_and_bank_mismatch_are_rejected(self):
        other = self.other_owner()
        with self.assertRaises(StoreError):
            import_pdf(self.engine, other, self.card, self.path)
        sbi = register_card(self.engine, self.owner, bank="sbi", label="Synthetic")
        with self.assertRaises(StoreError) as error:
            import_pdf(self.engine, self.owner, sbi, self.path)
        self.assertEqual(error.exception.code, "bank_mismatch")

    def test_missing_statement_date_is_not_guessed_or_selected(self):
        parsed = replace(
            parse_pdf_bytes(self.path.read_bytes(), source_name=self.path.name),
            statement_date=None,
        )
        with patch("core.imports.parse_pdf_bytes", return_value=parsed):
            result = self.load()
        self.assertFalse(result.selected_source)
        self.assertTrue(result.needs_review)
        with self.engine.connect() as connection:
            self.assertIsNone(connection.scalar(select(Statement.statement_date)))

    def test_duplicate_after_pdf_deletion_does_not_restore_bytes(self):
        first = self.load()
        with self.engine.begin() as connection:
            connection.execute(
                update(ImportRecord).values(
                    pdf_bytes=None, pdf_deleted_at=datetime.now(timezone.utc)
                )
            )
        second = self.load()
        self.assertEqual(second.status, "duplicate")
        self.assertEqual(first.import_id, second.import_id)
        with self.assertRaises(StoreError):
            read_original(self.engine, self.owner, second.import_id)

    def test_path_snapshot_is_not_reopened_after_parsing(self):
        original = self.path.read_bytes()

        def changing(data, **kwargs):
            self.path.write_bytes(b"changed while parsing")
            return parse_pdf_bytes(data, **kwargs)

        with patch("core.imports.parse_pdf_bytes", side_effect=changing):
            result = self.load()
        self.assertEqual(
            read_original(self.engine, self.owner, result.import_id), original
        )

    def test_cannot_read_original_for_another_owner(self):
        result = self.load()
        with self.assertRaises(StoreError):
            read_original(self.engine, self.other_owner(), result.import_id)

    def test_unknown_owner_or_card_is_rejected(self):
        with self.assertRaises(StoreError):
            import_pdf(self.engine, uuid4(), uuid4(), self.path)
