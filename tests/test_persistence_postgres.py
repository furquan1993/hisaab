"""Real PostgreSQL constraint tests, exclusively on disposable local databases."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError, InvalidRequestError
from sqlalchemy.orm import undefer

from core.persistence.models import Entry, ImportRecord, Statement
from tests.persistence_fixture import PDF, new_entry, new_import, seed
from tests.postgres_fixture import PostgresTests


class PersistencePostgresTests(PostgresTests):
    def test_exact_amount_uuid_evidence_and_pdf_round_trip(self):
        rows = seed(self.session)
        self.session.expunge_all()
        saved = self.session.scalar(select(Entry).where(Entry.id == rows.entry.id))
        self.assertEqual(saved.amount, Decimal("123.45"))
        self.assertEqual(saved.id, rows.entry.id)
        self.assertEqual(saved.source_bbox, [10.0, 20.0, 300.0, 40.0])
        imported = self.session.scalar(
            select(ImportRecord).options(undefer(ImportRecord.pdf_bytes))
        )
        self.assertEqual(imported.pdf_bytes, PDF)
        self.assertEqual(imported.created_at.utcoffset(), timedelta(0))

    def test_pdf_requires_explicit_loading(self):
        rows = seed(self.session)
        self.session.expunge_all()
        imported = self.session.get(ImportRecord, rows.imported.id)
        with self.assertRaises(InvalidRequestError):
            _ = imported.pdf_bytes
        self.assertEqual(imported.source_filename, "synthetic.pdf")

    def test_duplicate_bytes_with_a_new_filename_are_rejected_by_unique_key(self):
        rows = seed(self.session)
        with self.assertRaises(IntegrityError), self.session.begin_nested():
            self.session.add(
                new_import(rows, payload=PDF, source_filename="renamed.pdf")
            )
            self.session.flush()
        self.assertEqual(
            self.session.scalar(select(func.count()).select_from(ImportRecord)), 1
        )

    def test_identical_looking_entries_are_separate(self):
        rows = seed(self.session)
        other = new_entry(rows.imported, sequence=2)
        self.session.add(other)
        self.session.flush()
        self.assertNotEqual(other.id, rows.entry.id)
        self.assertEqual(
            self.session.scalar(select(func.count()).select_from(Entry)), 2
        )

    def test_duplicate_sequence_rejected(self):
        rows = seed(self.session)
        with self.assertRaises(IntegrityError), self.session.begin_nested():
            self.session.add(new_entry(rows.imported))
            self.session.flush()

    def test_competing_file_does_not_replace_selected_source(self):
        rows = seed(self.session)
        candidate = new_import(rows)
        self.session.add(candidate)
        self.session.flush()
        self.assertEqual(rows.statement.active_import_id, rows.imported.id)
        self.assertNotEqual(candidate.id, rows.statement.active_import_id)
        self.assertEqual(candidate.review_status, "pending")

    def test_unknown_facts_remain_null_with_review_evidence(self):
        rows = seed(self.session)
        entry = new_entry(
            rows.imported,
            sequence=2,
            amount=None,
            direction=None,
            currency=None,
            transaction_date=None,
            entry_type="unknown",
            raw_date="",
            raw_amount="",
            issues=[{"code": "amount_missing_or_invalid", "page": 1}],
        )
        self.session.add(entry)
        self.session.flush()
        self.session.expire(entry)
        self.assertIsNone(entry.amount)
        self.assertIsNone(entry.transaction_date)
        self.assertEqual(entry.issues[0]["code"], "amount_missing_or_invalid")

    def test_cross_owner_card_reference_rejected(self):
        first, second = seed(self.session), seed(self.session)
        with self.assertRaises(IntegrityError), self.session.begin_nested():
            self.session.add(
                Statement(id=uuid4(), owner_id=second.owner.id, card_id=first.card.id)
            )
            self.session.flush()

    def test_cross_owner_entry_reference_rejected(self):
        first, second = seed(self.session), seed(self.session)
        with self.assertRaises(IntegrityError), self.session.begin_nested():
            self.session.add(
                new_entry(first.imported, sequence=2, owner_id=second.owner.id)
            )
            self.session.flush()

    def test_import_cannot_reference_another_cards_statement(self):
        first, second = seed(self.session), seed(self.session)
        with self.assertRaises(IntegrityError), self.session.begin_nested():
            self.session.add(new_import(first, statement_id=second.statement.id))
            self.session.flush()

    def test_active_import_must_belong_to_same_statement(self):
        rows = seed(self.session)
        other = Statement(id=uuid4(), owner_id=rows.owner.id, card_id=rows.card.id)
        self.session.add(other)
        self.session.flush()
        candidate = new_import(rows, statement_id=other.id)
        self.session.add(candidate)
        self.session.flush()
        with self.assertRaises(IntegrityError), self.session.begin_nested():
            rows.statement.active_import_id = candidate.id
            self.session.flush()

    def test_pdf_removal_preserves_entries_and_fingerprint(self):
        rows = seed(self.session)
        fingerprint = rows.imported.file_sha256
        self.session.execute(
            update(ImportRecord)
            .where(ImportRecord.id == rows.imported.id)
            .values(pdf_bytes=None, pdf_deleted_at=datetime.now(timezone.utc))
        )
        self.session.expire_all()
        self.assertEqual(rows.imported.file_sha256, fingerprint)
        self.assertIsNotNone(rows.imported.pdf_deleted_at)
        self.assertEqual(
            self.session.scalar(select(func.count()).select_from(Entry)), 1
        )
        self.assertEqual(
            self.session.scalar(
                select(ImportRecord.pdf_bytes).where(
                    ImportRecord.id == rows.imported.id
                )
            ),
            None,
        )

    def test_pdf_size_must_match_original_bytes(self):
        rows = seed(self.session)
        with self.assertRaises(IntegrityError), self.session.begin_nested():
            self.session.add(new_import(rows, file_size_bytes=1))
            self.session.flush()

    def test_pdf_cannot_disappear_without_a_deletion_timestamp(self):
        rows = seed(self.session)
        with self.assertRaises(IntegrityError), self.session.begin_nested():
            self.session.execute(
                update(ImportRecord)
                .where(ImportRecord.id == rows.imported.id)
                .values(pdf_bytes=None)
            )

    def test_parent_deletion_is_not_a_retention_cascade(self):
        rows = seed(self.session)
        with self.assertRaises(IntegrityError), self.session.begin_nested():
            self.session.delete(rows.statement)
            self.session.flush()

    def test_database_rejects_invalid_enum_and_negative_amount(self):
        rows = seed(self.session)
        for values in (
            {"direction": "guess"},
            {"entry_type": "guess"},
            {"amount": Decimal("-1")},
        ):
            with (
                self.subTest(values=values),
                self.assertRaises(IntegrityError),
                self.session.begin_nested(),
            ):
                self.session.execute(
                    update(Entry).where(Entry.id == rows.entry.id).values(**values)
                )

    def test_migration_enables_default_deny_rls(self):
        flags = self.connection.execute(
            text(
                "SELECT c.relname, c.relrowsecurity FROM pg_class c "
                "JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname='hisaab' AND c.relkind='r'"
            )
        ).all()
        self.assertEqual(len(flags), 5)
        self.assertTrue(all(flag for _, flag in flags))

    def test_nonowner_role_cannot_read_even_with_table_grants(self):
        seed(self.session)
        self.connection.execute(text("CREATE ROLE hisaab_schema_probe NOLOGIN"))
        self.connection.execute(
            text("GRANT USAGE ON SCHEMA hisaab TO hisaab_schema_probe")
        )
        self.connection.execute(
            text("GRANT SELECT ON ALL TABLES IN SCHEMA hisaab TO hisaab_schema_probe")
        )
        self.connection.execute(text("SET LOCAL ROLE hisaab_schema_probe"))
        try:
            count = self.connection.scalar(text("SELECT count(*) FROM hisaab.entries"))
            self.assertEqual(count, 0)
        finally:
            self.connection.execute(text("RESET ROLE"))
