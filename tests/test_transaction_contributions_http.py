"""Whole-transaction allocations through the disposable authenticated API."""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import update
from sqlalchemy.orm import Session
from core.persistence.models import Statement
from tests.persistence_fixture import PDF, new_entry, new_import
from tests import test_settlements_http as settlements


class TransactionContributionHTTPTests(settlements.SettlementHTTPTests):
    def selected_payload(self, ids, month="2026-01-01"):
        payload = self.payload(None, month)
        payload.pop("p_amount")
        return {**payload, "p_entry_ids": [str(identifier) for identifier in ids]}

    def record_selected(self, payload, token=None):
        return self.call("/rpc/record_transaction_contribution", token or self.tokens[0], method="POST", data=payload)

    def transaction_rows(self):
        code, rows = self.call("/funding_transaction_entries?order=month,id", self.tokens[0])
        self.assertEqual(code, 200)
        return rows

    def test_selected_transaction_is_full_and_does_not_fund_older_month(self):
        self.february()
        feb = next(row for row in self.transaction_rows() if row["month"] == "2026-02-01")
        payload = self.selected_payload([feb["id"]], "2026-02-01")
        code, receipt = self.record_selected(payload)
        self.assertEqual(code, 200, receipt)
        self.assertEqual(receipt["amount"], "50.00")
        self.assertEqual([a["month"] for a in receipt["applications"]], ["2026-02-01"])
        self.assertEqual(receipt["applications"][0]["entries"][0]["entry_id"], feb["id"])
        self.assertEqual([g["outstanding"] for g in self.preview("2026-02-01")["groups"]], ["100.00", "0.00"])
        code, again = self.record_selected(payload)
        self.assertEqual(code, 200)
        self.assertEqual(receipt, again)
        code, _ = self.record_selected(self.selected_payload([feb["id"]], "2026-02-01"))
        self.assertEqual(code, 409)
        self.assertTrue(next(e for e in self.transaction_rows() if e["id"] == feb["id"])["settled"])

    def test_multiple_transactions_and_retry_set_order(self):
        extra = self.add(sequence=2, amount=Decimal("20.01"))
        payload = self.selected_payload([self.records[0].entry.id, extra])
        code, receipt = self.record_selected(payload)
        self.assertEqual(code, 200, receipt)
        self.assertEqual(receipt["amount"], "120.01")
        self.assertEqual(len(receipt["applications"][0]["entries"]), 2)
        code, again = self.record_selected({**payload, "p_entry_ids": list(reversed(payload["p_entry_ids"]))})
        self.assertEqual(code, 200)
        self.assertEqual(receipt["id"], again["id"])
        code, _ = self.record_selected({**payload, "p_entry_ids": [str(extra)]})
        self.assertEqual(code, 409)

    def test_scope_invalid_duplicates_and_legacy_history(self):
        entry = self.records[0].entry.id
        for ids, expected in (([], 422), ([entry, entry], 422), ([uuid4()], 409), ([self.records[1].entry.id], 409)):
            code, _ = self.record_selected(self.selected_payload(ids))
            self.assertEqual(code, expected)
        code, _ = self.record_selected({**self.selected_payload([entry]), "p_account_id": str(uuid4())})
        self.assertEqual(code, 404)
        code, _ = self.record_selected(self.selected_payload([entry]), self.tokens[1])
        self.assertEqual(code, 409)
        code, rows = self.call("/funding_transaction_entries", self.tokens[1])
        self.assertEqual(code, 200)
        self.assertEqual(rows, [])
        code, _ = self.call("/rpc/record_transaction_contribution", method="POST", data=self.selected_payload([entry]))
        self.assertGreaterEqual(code, 400)
        self.assertEqual(self.record(self.payload("10.00"))[0], 200)
        self.assertTrue(self.transaction_rows()[0]["legacy_funded"])
        self.assertEqual(self.record_selected(self.selected_payload([entry]))[0], 409)

    def test_concurrent_selections_cannot_settle_twice(self):
        payload = self.selected_payload([self.records[0].entry.id])
        with ThreadPoolExecutor(max_workers=2) as pool:
            codes = [result[0] for result in pool.map(self.record_selected, [payload, {**payload, "p_id": str(uuid4())}])]
        self.assertEqual(sorted(codes), [200, 409])

    def test_refunds_do_not_partially_settle_selected_debits(self):
        self.add(sequence=2, amount=Decimal("25.00"), direction="credit", entry_type="refund")
        code, receipt = self.record_selected(self.selected_payload([self.records[0].entry.id]))
        self.assertEqual(code, 200, receipt)
        self.assertEqual(receipt["amount"], "100.00")
        self.assertEqual(self.preview()["groups"][0]["credit"], "25.00")
        self.assertTrue(self.transaction_rows()[0]["settled"])

    def test_revision_keeps_logical_transaction_settled(self):
        self.assertEqual(self.record_selected(self.selected_payload([self.records[0].entry.id]))[0], 200)
        with Session(self.engine) as session, session.begin():
            candidate = new_import(self.records[0], payload=PDF, pdf_bytes=None,
                source_import_id=self.records[0].imported.id, parser_version="synthetic-settlement-2")
            session.add(candidate)
            session.flush()
            revised = new_entry(candidate, amount=Decimal("100.00"))
            session.add(revised)
            session.flush()
            candidate_id, revised_id = str(candidate.id), str(revised.id)
        def restore_active_source():
            with self.engine.begin() as connection:
                connection.execute(update(Statement).where(Statement.id == self.records[0].statement.id).values(active_import_id=self.records[0].imported.id))
        self.addCleanup(restore_active_source)
        code, plan = self.call("/rpc/prepare_revision", self.tokens[0], method="POST",
            data={"p_candidate_import_id": candidate_id})
        self.assertEqual(code, 200, plan)
        code, result = self.call("/rpc/accept_revision", self.tokens[0], method="POST",
            data={"p_revision_id": plan["id"], "p_mapping": [{"new_entry_id": new, "previous_entry_id": str(self.records[0].entry.id)} for new in plan["plan"]["unmatched_new"]], "p_removed": [], "p_reason": "Synthetic verified source revision"})
        self.assertEqual(code, 200, result)
        revised = next(e for e in self.transaction_rows() if e["id"] == revised_id)
        self.assertTrue(revised["settled"])
        self.assertEqual(revised["logical_entry_id"], str(self.records[0].entry.id))
        self.assertEqual(self.record_selected(self.selected_payload([revised_id]))[0], 409)
