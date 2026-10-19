"""Atomic account deletion against a disposable database, with real views and audit."""
import json
from decimal import Decimal
from uuid import uuid4

from alembic import command
from alembic.util import CommandError
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from core.persistence.models import Category, Contribution, DecisionEvent, EntryDecision, FundingAccount
from tests.persistence_fixture import seed, new_entry, new_import
from tests.postgres_fixture import PostgresTests, migration_config


class AccountDeletionTests(PostgresTests):
    def setUp(self):
        super().setUp()
        self.rows = seed(self.session)
        self.owner = self.rows.owner.id
        self.rows.owner.auth_user_id = uuid4()
        self.account = FundingAccount(owner_id=self.owner, name="Synthetic home")
        self.category = Category(owner_id=self.owner, name="Synthetic category")
        self.session.add_all([self.account, self.category])
        self.session.flush()
        self.session.execute(text("SELECT set_config('request.jwt.claims',:claims,true)"), {
            "claims": json.dumps({"role": "authenticated", "sub": str(self.rows.owner.auth_user_id)})})
        self.save(self.rows.entry.id)

    def save(self, entry_id):
        return self.session.scalar(text("SELECT hisaab_api.save_entry_decision(:e,coalesce((SELECT version FROM hisaab.entry_decisions WHERE owner_id=:o AND entry_id=:e),0),cast(:patch AS jsonb))"), {
            "e": entry_id, "o": self.owner, "patch": json.dumps({"account_id": str(self.account.id), "category_id": str(self.category.id)})})

    def preview(self, account=None, owner=None):
        return self.session.scalar(text("SELECT hisaab_api.preview_account_deletion(:a,:o)"), {
            "a": account or self.account.id, "o": owner or self.owner})

    def delete(self, preview):
        return self.session.scalar(text("SELECT hisaab_api.delete_account(:a,:token,:o)"), {
            "a": self.account.id, "token": preview["token"], "o": self.owner})

    def test_preview_and_delete_preserve_transactions_categories_and_audit(self):
        candidate = new_import(self.rows)
        self.session.add(candidate)
        self.session.flush()
        historical = new_entry(candidate)
        self.session.add(historical)
        self.session.flush()
        self.session.add(EntryDecision(owner_id=self.owner, entry_id=historical.id, account_id=self.account.id, version=1))
        self.session.flush()
        preview = self.preview()
        self.assertEqual({r["id"] for r in preview["entries"]}, {str(self.rows.entry.id), str(historical.id)})
        self.assertTrue(all(row["amount"] == "123.45" for row in preview["entries"]))
        self.assertEqual(self.delete(preview)["unassigned_count"], 2)
        self.session.expire_all()
        decision = self.session.scalar(select(EntryDecision).where(EntryDecision.entry_id == self.rows.entry.id))
        self.assertIsNone(decision.account_id)
        self.assertEqual(decision.category_id, self.category.id)
        self.assertEqual(decision.version, 2)
        self.assertEqual(str(self.rows.entry.amount), "123.45")
        labels = self.session.execute(text("SELECT * FROM hisaab_api.labels WHERE id=:id"), {"id": self.account.id}).all()
        self.assertEqual(labels, [])
        event = self.session.scalar(select(DecisionEvent).where(DecisionEvent.entry_id == self.rows.entry.id, DecisionEvent.version == 2))
        self.assertEqual(event.before["account_id"], str(self.account.id))
        self.assertIsNone(event.after["account_id"])
        self.assertFalse(self.session.scalar(text("SELECT hisaab.apply_entry_assignments(:o,:e)"), {"o": self.owner, "e": self.rows.entry.id}))
        with self.assertRaises(DBAPIError), self.session.begin_nested():
            self.session.execute(text("UPDATE hisaab.accounts SET is_archived=false WHERE id=:a"), {"a": self.account.id})

    def test_automatically_assigned_transactions_stay_unassigned_after_deletion(self):
        automatic = new_entry(self.rows.imported, sequence=2)
        self.session.add(automatic)
        self.session.flush()
        self.assertEqual(self.session.scalar(select(EntryDecision.account_id).where(EntryDecision.entry_id == automatic.id)), self.account.id)
        self.delete(self.preview())
        other = FundingAccount(owner_id=self.owner, name="Another pot")
        self.session.add(other)
        self.session.flush()
        # A later manual correction must not silently reassign the cleared entry.
        self.session.execute(text("SELECT hisaab_api.save_entry_decision(:e,2,cast(:patch AS jsonb))"), {
            "e": self.rows.entry.id, "patch": json.dumps({"account_id": str(other.id)})})
        self.assertFalse(self.session.scalar(text("SELECT hisaab.apply_entry_assignments(:o,:e)"), {"o": self.owner, "e": automatic.id}))
        self.session.expire_all()
        self.assertIsNone(self.session.scalar(select(EntryDecision.account_id).where(EntryDecision.entry_id == automatic.id)))

    def test_changed_transactions_reject_deletion_without_partial_writes(self):
        preview = self.preview()
        self.session.execute(text("SELECT hisaab_api.save_entry_decision(:e,1,cast(:patch AS jsonb))"), {"e": self.rows.entry.id, "patch": json.dumps({"account_id": None})})
        with self.assertRaises(DBAPIError) as error, self.session.begin_nested():
            self.delete(preview)
        self.assertEqual(error.exception.orig.sqlstate, "PT409")
        self.assertIsNone(self.session.get(FundingAccount, self.account.id).deleted_at)

    def test_preview_is_not_limited_to_first_page_or_date_range(self):
        for sequence in range(2, 107):
            entry = new_entry(self.rows.imported, sequence=sequence)
            self.session.add(entry)
        self.session.flush()
        entries = self.session.execute(text("SELECT id FROM hisaab.entries WHERE import_id=:i AND id<>:e"), {"i": self.rows.imported.id, "e": self.rows.entry.id}).scalars().all()
        for entry in entries:
            self.save(entry)
        self.assertEqual(len(self.preview()["entries"]), 106)

    def test_owner_checks_and_no_assignments(self):
        foreign = seed(self.session)
        account = FundingAccount(owner_id=foreign.owner.id, name="Foreign pot")
        empty = FundingAccount(owner_id=self.owner, name="Empty pot")
        self.session.add_all([account, empty])
        self.session.flush()
        for identifier, owner in ((account.id, self.owner), (self.account.id, foreign.owner.id)):
            with self.assertRaises(DBAPIError), self.session.begin_nested():
                self.preview(identifier, owner)
        preview = self.preview(empty.id)
        self.assertEqual(preview["entries"], [])
        result = self.session.scalar(text("SELECT hisaab_api.delete_account(:a,:t,:o)"), {"a": empty.id, "t": preview["token"], "o": self.owner})
        self.assertEqual(result["unassigned_count"], 0)

    def test_receipts_remain_intact_and_downgrade_cannot_resurrect_account(self):
        receipt = Contribution(owner_id=self.owner, card_id=self.rows.card.id, account_id=self.account.id,
            currency="INR", month=self.rows.statement.statement_date.replace(day=1), amount=Decimal("10.00"),
            received_on=self.rows.statement.statement_date, note="Synthetic receipt", request=[],
            actor_auth_user_id=self.rows.owner.auth_user_id,
            applications=[{"month": "2026-01-01", "amount": "10.00", "fingerprint": "synthetic"}])
        self.session.add(receipt)
        self.session.flush()
        self.delete(self.preview())
        self.session.expire_all()
        self.assertEqual(self.session.get(Contribution, receipt.id).amount, 10)
        with self.assertRaises(CommandError), self.connection.begin_nested():
            command.downgrade(migration_config(self.connection), "0016_friendly_descriptions")
