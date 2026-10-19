import json
from dataclasses import replace
from uuid import uuid4

from alembic import command
from alembic.util import CommandError
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from core.imports import import_pdf
from core.parser import parse_pdf_bytes
from core.persistence.models import ImportRecord
from core.revisions import reparse_import
from core.statement_balance_capture import capture_printed_balance
from core.persistence.store import StoreError
from tests.import_fixture import ImportTestsBase
from tests.postgres_fixture import migration_config
from tests.test_statement_balance import bill_page
from tests.hdfc_fixture import pdf_bytes


class StatementBalancePostgresTests(ImportTestsBase):
    def test_existing_import_capture_is_previewed_verified_and_idempotent(self):
        from unittest.mock import patch
        original = pdf_bytes([bill_page()])
        self.path.write_bytes(original)
        parsed = parse_pdf_bytes(original, source_name="synthetic.pdf")
        with patch("core.imports._parse", return_value=replace(parsed, printed_balance=None)):
            saved = import_pdf(self.engine, self.owner, self.card, self.path)
        self.assertEqual(capture_printed_balance(self.engine, self.owner, saved.import_id, parsed, original)["status"], "ready")
        with self.engine.connect() as connection:
            self.assertIsNone(connection.scalar(select(ImportRecord.printed_balance).where(ImportRecord.id == saved.import_id)))
        with self.assertRaises(StoreError):
            capture_printed_balance(self.engine, self.owner, saved.import_id, parsed, original + b"different", apply=True)
        changed = replace(parsed, transactions=(replace(parsed.transactions[0], description="CHANGED"),))
        with self.assertRaises(StoreError):
            capture_printed_balance(self.engine, self.owner, saved.import_id, changed, original, apply=True)
        self.assertEqual(capture_printed_balance(self.engine, self.owner, saved.import_id, parsed, original, apply=True)["status"], "captured")
        self.assertEqual(capture_printed_balance(self.engine, self.owner, saved.import_id, parsed, original, apply=True)["status"], "unchanged")

    def test_import_and_reparse_retain_bill_without_selecting_candidate(self):
        self.path.write_bytes(pdf_bytes([bill_page()]))
        saved = import_pdf(self.engine, self.owner, self.card, self.path)
        revision = reparse_import(self.engine, self.owner, saved.import_id)
        with self.engine.connect() as connection:
            balances = connection.scalars(select(ImportRecord.printed_balance).where(ImportRecord.statement_id == saved.statement_id)).all()
            self.assertEqual(len(balances), 2)
            self.assertTrue(all(b["amount_due"] == "5216.00" for b in balances))
            bills = connection.execute(text("SELECT id,printed_balance FROM hisaab_api.statement_bills WHERE statement_id=:id"), {"id": saved.statement_id}).mappings().all()
            self.assertEqual([b["id"] for b in bills], [saved.import_id])
            self.assertEqual(bills[0]["printed_balance"]["amount_due"], "5216.00")

    def test_bill_view_obeys_owner_rls_and_browser_cannot_change_balance(self):
        with self.engine.connect() as connection:
            if not connection.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='authenticated')")):
                self.skipTest("Authenticated role requires the disposable Supabase stack")
        self.path.write_bytes(pdf_bytes([bill_page()]))
        saved = import_pdf(self.engine, self.owner, self.card, self.path)
        with self.engine.begin() as connection:
            subject = uuid4()
            connection.execute(text("UPDATE hisaab.owners SET auth_user_id=:subject WHERE id=:owner"), {"subject": subject, "owner": self.owner})
            for other, expected in ((uuid4(), 0), (subject, 1)):
                with connection.begin_nested():
                    connection.execute(text("SELECT set_config('request.jwt.claims',:claims,true)"), {"claims": json.dumps({"sub": str(other), "role": "authenticated"})})
                    connection.execute(text("SET LOCAL ROLE authenticated"))
                    self.assertEqual(connection.scalar(text("SELECT count(*) FROM hisaab_api.statement_bills WHERE id=:id"), {"id": saved.import_id}), expected)
                    if expected:
                        with self.assertRaises(DBAPIError), connection.begin_nested():
                            connection.execute(text("UPDATE hisaab.imports SET printed_balance=NULL WHERE id=:id"), {"id": saved.import_id})
                    connection.execute(text("RESET ROLE"))

    def test_downgrade_refuses_to_discard_captured_bill(self):
        # This transaction rolls back with the fixture; no real evidence involved.
        from tests.persistence_fixture import seed
        records = seed(self.session)
        records.imported.printed_balance = parse_pdf_bytes(pdf_bytes([bill_page()]), source_name="synthetic.pdf").printed_balance.to_dict()
        self.session.flush()
        with self.assertRaises(CommandError), self.connection.begin_nested():
            command.downgrade(migration_config(self.connection), "0013_auto_assignments")
