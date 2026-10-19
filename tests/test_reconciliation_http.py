"""Complete derived totals through real synthetic Auth, never production."""

from datetime import date
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from core.persistence.models import Card, Entry, ImportRecord, Statement
from tests.decision_fixture import remove_decisions
from tests.persistence_fixture import new_entry, new_import
from tests.supabase_fixture import SupabaseTests


class ReconciliationFixture(SupabaseTests):
    def setUp(self):
        base = self.records[0]
        with self.engine.begin() as c:
            remove_decisions(c, self.owners)
            c.execute(
                update(Statement)
                .where(
                    Statement.owner_id == base.owner.id,
                    Statement.id != base.statement.id,
                )
                .values(active_import_id=None)
            )
            c.execute(
                delete(Entry).where(
                    Entry.owner_id == base.owner.id, Entry.id != base.entry.id
                )
            )
            c.execute(
                delete(ImportRecord).where(
                    ImportRecord.owner_id == base.owner.id,
                    ImportRecord.id != base.imported.id,
                )
            )
            c.execute(
                delete(Statement).where(
                    Statement.owner_id == base.owner.id,
                    Statement.id != base.statement.id,
                )
            )
            c.execute(
                delete(Card).where(
                    Card.owner_id == base.owner.id, Card.id != base.card.id
                )
            )
            c.execute(
                update(ImportRecord)
                .where(ImportRecord.id == base.imported.id)
                .values(issues=[])
            )
            c.execute(
                update(Entry)
                .where(Entry.id == base.entry.id)
                .values(
                    amount=Decimal("100.00"),
                    direction="debit",
                    entry_type="purchase",
                    currency="INR",
                    transaction_date=date(2025, 12, 20),
                    issues=[],
                )
            )
        code, self.account = self.call(
            "/rpc/save_label",
            self.tokens[0],
            method="POST",
            data={"p_kind": "account", "p_name": "Synthetic household"},
        )
        self.assertEqual(code, 200)
        self.assign(base.entry.id)

    def assign(self, entry_id):
        _, rows = self.call("/entries?id=eq." + str(entry_id), self.tokens[0])
        code, _ = self.call(
            "/rpc/save_entry_decision",
            self.tokens[0],
            method="POST",
            data={
                "p_entry_id": str(entry_id),
                "p_expected_version": rows[0]["decision_version"],
                "p_patch": {"account_id": self.account["id"]},
            },
        )
        self.assertEqual(code, 200)

    def totals(self):
        code, rows = self.call(
            "/funding_totals?order=card_id,month,currency", self.tokens[0]
        )
        self.assertEqual(code, 200)
        return rows

    def add(self, **changes):
        with Session(self.engine) as s, s.begin():
            row = new_entry(self.records[0].imported, **changes)
            s.add(row)
            s.flush()
            identifier = row.id
        self.assign(identifier)
        return identifier


class ReconciliationHTTPTests(ReconciliationFixture):
    def test_reviewed_statement_month_is_independent_of_purchase_month(self):
        code, _ = self.call(
            "/rpc/review_import",
            self.tokens[0],
            method="POST",
            data={
                "p_import_id": str(self.records[0].imported.id),
                "p_expected_version": 0,
                "p_acknowledged": [],
                "p_reason": "Synthetic verified issue date",
                "p_statement_date": "2026-02-01",
            },
        )
        self.assertEqual(code, 200)
        self.assertEqual(self.totals()[0]["month"], "2026-02-01")

    def test_empty_selected_statement_coverage_is_visible(self):
        base = self.records[0]
        with Session(self.engine) as s, s.begin():
            statement = Statement(
                owner_id=base.owner.id,
                card_id=base.card.id,
                statement_date=date(2026, 2, 28),
            )
            s.add(statement)
            s.flush()
            imported = new_import(
                base,
                statement_id=statement.id,
                parsed_statement_date=date(2026, 2, 28),
                issues=[{"code": "synthetic_unreadable_page"}],
            )
            s.add(imported)
            s.flush()
            statement.active_import_id = imported.id
        code, rows = self.call("/funding_attention", self.tokens[0])
        self.assertEqual(code, 200)
        self.assertEqual(rows[0]["reason"], "Statement coverage needs review")

    def test_totals_include_all_entries_not_only_one_transaction_page(self):
        for sequence in range(2, 54):
            self.add(sequence=sequence, amount=Decimal("0.10"))
        row = self.totals()[0]
        self.assertEqual(Decimal(row["net"]), Decimal("105.20"))
        self.assertEqual(row["entry_count"], 53)
        code, entries = self.call("/funding_entries?limit=50&offset=50", self.tokens[0])
        self.assertEqual(code, 200)
        self.assertEqual(len(entries), 3)
        self.assertEqual(row["month"], "2026-01-01")
        self.assertFalse(row["blocked"])

    def test_refunds_cashback_repayments_and_currency_stay_distinct(self):
        self.add(
            sequence=2,
            amount=Decimal("150.00"),
            direction="credit",
            entry_type="refund",
        )
        self.add(
            sequence=3,
            amount=Decimal("1.00"),
            direction="credit",
            entry_type="cashback",
        )
        self.add(
            sequence=4,
            amount=Decimal("999.00"),
            direction="credit",
            entry_type="payment",
        )
        self.add(sequence=5, amount=Decimal("2.01"), currency="USD")
        totals = {r["currency"]: r for r in self.totals()}
        self.assertEqual(Decimal(totals["INR"]["net"]), Decimal("-51.00"))
        self.assertEqual(totals["INR"]["entry_count"], 3)
        self.assertEqual(Decimal(totals["USD"]["net"]), Decimal("2.01"))

    def test_other_cards_do_not_block_but_candidates_on_this_card_do(self):
        self.assertFalse(self.totals()[0]["blocked"])
        with Session(self.engine) as s, s.begin():
            s.add(new_import(self.records[0]))
        self.assertTrue(self.totals()[0]["blocked"])
        code, attention = self.call("/funding_attention", self.tokens[0])
        self.assertEqual(code, 200)
        self.assertEqual(len(attention), 1)

    def test_unassigned_and_unknown_currency_are_visible_and_blocked(self):
        with Session(self.engine) as s, s.begin():
            s.add(new_entry(self.records[0].imported, sequence=2, currency=None, description="UNSEEN SYNTHETIC MERCHANT"))
        rows = self.totals()
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r["blocked"] for r in rows))
        self.assertTrue(
            any(r["account_id"] is None and r["currency"] is None for r in rows)
        )

    def test_other_owners_and_anonymous_users_cannot_read_totals(self):
        code, rows = self.call("/funding_totals", self.tokens[1])
        self.assertEqual(code, 200)
        self.assertTrue(all(r["card_id"] != str(self.records[0].card.id) for r in rows))
        code, _ = self.call("/funding_totals")
        self.assertGreaterEqual(code, 400)

    def test_second_card_combines_only_in_summary_not_obligation_identity(self):
        base = self.records[0]
        with Session(self.engine) as s, s.begin():
            card = Card(
                id=uuid4(), owner_id=base.owner.id, bank="sbi", label=base.card.label
            )
            s.add(card)
            s.flush()
            statement = Statement(
                id=uuid4(),
                owner_id=base.owner.id,
                card_id=card.id,
                statement_date=date(2026, 1, 25),
            )
            s.add(statement)
            s.flush()
            imported = new_import(
                base,
                card_id=card.id,
                statement_id=statement.id,
                parsed_statement_date=date(2026, 1, 25),
            )
            s.add(imported)
            s.flush()
            statement.active_import_id = imported.id
            row = new_entry(imported, amount=Decimal("20.02"))
            s.add(row)
            s.flush()
            identifier = row.id
        self.assign(identifier)
        rows = self.totals()
        self.assertEqual(len(rows), 2)
        self.assertEqual(len({r["card_id"] for r in rows}), 2)
        self.assertEqual(sum(Decimal(r["net"]) for r in rows), Decimal("120.02"))
