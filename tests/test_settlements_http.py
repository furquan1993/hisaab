"""Real owner-scoped contribution writes with exact original-month applications."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import update
from sqlalchemy.orm import Session

from core.persistence.models import Entry, Statement
from tests.persistence_fixture import new_entry, new_import
from tests.test_reconciliation_http import ReconciliationFixture


class SettlementHTTPTests(ReconciliationFixture):
    def scope(self, month="2026-01-01"):
        return {
            "p_card_id": str(self.records[0].card.id),
            "p_account_id": self.account["id"],
            "p_currency": "INR",
            "p_month": month,
            "p_expected_owner": str(self.owners[0]),
        }

    def preview(self, month="2026-01-01"):
        code, result = self.call(
            "/rpc/funding_preview",
            self.tokens[0],
            method="POST",
            data=self.scope(month),
        )
        self.assertEqual(code, 200)
        return result

    def payload(self, amount="60.00", month="2026-01-01"):
        return {
            **self.scope(month),
            "p_id": str(uuid4()),
            "p_amount": amount,
            "p_received_on": "2026-02-02",
            "p_note": "Synthetic contribution",
            "p_expected_token": self.preview(month)["token"],
        }

    def record(self, payload):
        return self.call(
            "/rpc/record_contribution", self.tokens[0], method="POST", data=payload
        )

    def february(self):
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
                base, statement_id=statement.id, parsed_statement_date=date(2026, 2, 28)
            )
            s.add(imported)
            s.flush()
            statement.active_import_id = imported.id
            row = new_entry(imported, amount=Decimal("50.00"))
            s.add(row)
            s.flush()
            identifier = row.id
        self.assign(identifier)

    def test_partial_full_and_oldest_first_preserve_january_attribution(self):
        code, receipt = self.record(self.payload())
        self.assertEqual(code, 200)
        self.assertEqual(receipt["amount"], "60.00")
        self.assertEqual(receipt["applications"][0]["month"], "2026-01-01")
        self.assertEqual(self.preview()["groups"][0]["outstanding"], "40.00")
        self.february()
        code, receipt = self.record(self.payload("65.00", "2026-02-01"))
        self.assertEqual(code, 200)
        self.assertEqual(
            [(a["month"], a["amount"]) for a in receipt["applications"]],
            [("2026-01-01", "40.00"), ("2026-02-01", "25.00")],
        )
        groups = self.preview("2026-02-01")["groups"]
        self.assertEqual([g["outstanding"] for g in groups], ["0.00", "25.00"])
        code, receipt = self.record(self.payload(None, "2026-02-01"))
        self.assertEqual(code, 200)
        self.assertEqual(receipt["amount"], "25.00")
        self.assertEqual(self.preview("2026-02-01")["groups"][0]["received"], "100.00")
        code, history = self.call("/contributions", self.tokens[0])
        self.assertEqual(code, 200)
        self.assertEqual(len(history), 3)

    def test_contributions_cannot_mix_currencies(self):
        self.add(sequence=2, amount=Decimal("2.01"), currency="USD")
        scope = {**self.scope(), "p_currency": "USD"}
        code, preview = self.call(
            "/rpc/funding_preview", self.tokens[0], method="POST", data=scope
        )
        self.assertEqual(code, 200)
        payload = {
            **self.payload("1.00"),
            **scope,
            "p_expected_token": preview["token"],
        }
        code, receipt = self.record(payload)
        self.assertEqual(code, 200)
        self.assertEqual(receipt["currency"], "USD")
        self.assertEqual(self.preview()["groups"][0]["outstanding"], "100.00")
        code, preview = self.call(
            "/rpc/funding_preview", self.tokens[0], method="POST", data=scope
        )
        self.assertEqual(preview["groups"][0]["outstanding"], "1.01")

    def test_reconfirm_older_month_uses_the_preview_through_month(self):
        self.february()
        code, _ = self.record(self.payload("60.00", "2026-02-01"))
        self.assertEqual(code, 200)
        with self.engine.begin() as c:
            c.execute(
                update(Entry)
                .where(Entry.id == self.records[0].entry.id)
                .values(amount=Decimal("120.00"))
            )
        preview = self.preview("2026-02-01")
        code, _ = self.call(
            "/rpc/confirm_funding",
            self.tokens[0],
            method="POST",
            data={
                **self.scope(),
                "p_reason": "Synthetic reviewed January in February",
                "p_expected_token": preview["token"],
                "p_through_month": "2026-02-01",
            },
        )
        self.assertEqual(code, 200)
        self.assertFalse(self.preview("2026-02-01")["groups"][0]["needs_review"])

    def test_lost_response_retry_is_idempotent_and_conflicting_retry_fails(self):
        payload = self.payload()
        code, first = self.record(payload)
        self.assertEqual(code, 200)
        code, again = self.record(payload)
        self.assertEqual(code, 200)
        self.assertEqual(first["id"], again["id"])
        code, _ = self.record({**payload, "p_amount": "10.00"})
        self.assertEqual(code, 409)
        self.assertEqual(self.preview()["groups"][0]["received"], "60.00")

    def test_stale_and_concurrent_requests_cannot_double_settle(self):
        first = self.payload("70.00")
        second = {**first, "p_id": str(uuid4())}
        with ThreadPoolExecutor(max_workers=2) as pool:
            codes = [result[0] for result in pool.map(self.record, [first, second])]
        self.assertEqual(sorted(codes), [200, 409])
        self.assertEqual(self.preview()["groups"][0]["outstanding"], "30.00")

    def test_corrections_keep_receipts_and_require_reasoned_reconfirmation(self):
        code, _ = self.record(self.payload("100.00"))
        self.assertEqual(code, 200)
        code, _ = self.call(
            "/rpc/review_entry",
            self.tokens[0],
            method="POST",
            data={
                "p_entry_id": str(self.records[0].entry.id),
                "p_expected_version": 1,
                "p_overrides": {"amount": "120.00"},
                "p_acknowledged": [],
                "p_reason": "Synthetic corrected amount",
                "p_confirm_source": False,
            },
        )
        self.assertEqual(code, 200)
        group = self.preview()["groups"][0]
        self.assertTrue(group["needs_review"])
        self.assertEqual(group["received"], "100.00")
        code, _ = self.record(self.payload("20.00"))
        self.assertEqual(code, 409)
        confirm = {
            **self.scope(),
            "p_reason": "Synthetic verified changed obligation",
            "p_expected_token": self.preview()["token"],
        }
        code, _ = self.call(
            "/rpc/confirm_funding", self.tokens[0], method="POST", data=confirm
        )
        self.assertEqual(code, 200)
        self.assertFalse(self.preview()["groups"][0]["needs_review"])
        code, _ = self.record(self.payload(None))
        self.assertEqual(code, 200)
        self.assertEqual(self.preview()["groups"][0]["received"], "120.00")

    def test_removed_group_retains_history_and_credit_in_original_month(self):
        code, _ = self.record(self.payload("100.00"))
        self.assertEqual(code, 200)
        code, _ = self.call(
            "/rpc/save_entry_decision",
            self.tokens[0],
            method="POST",
            data={
                "p_entry_id": str(self.records[0].entry.id),
                "p_expected_version": 1,
                "p_patch": {"account_id": None},
            },
        )
        self.assertEqual(code, 200)
        group = self.preview()["groups"][0]
        self.assertEqual(group["net"], "0.00")
        self.assertEqual(group["credit"], "100.00")
        self.assertTrue(group["needs_review"])

    def test_negative_month_never_offsets_previous_month_arrears(self):
        self.february()
        with self.engine.begin() as c:
            c.execute(
                update(Entry)
                .where(
                    Entry.owner_id == self.owners[0],
                    Entry.id != self.records[0].entry.id,
                )
                .values(direction="credit", entry_type="refund")
            )
        groups = self.preview("2026-02-01")["groups"]
        self.assertEqual([g["outstanding"] for g in groups], ["100.00", "0.00"])
        code, receipt = self.record(self.payload(None, "2026-02-01"))
        self.assertEqual(code, 200)
        self.assertEqual(receipt["amount"], "100.00")
        self.assertEqual(len(receipt["applications"]), 1)

    def test_invalid_amounts_foreign_owners_and_raw_table_writes_fail(self):
        for amount in ("0", "-1", "1.001", "NaN", "101.00", "1e2"):
            code, _ = self.record(self.payload(amount))
            self.assertEqual(code, 422, amount)
        payload = self.payload()
        code, _ = self.call(
            "/rpc/record_contribution", self.tokens[1], method="POST", data=payload
        )
        self.assertEqual(code, 409)
        code, _ = self.call("/rpc/record_contribution", method="POST", data=payload)
        self.assertGreaterEqual(code, 400)
        code, rows = self.call("/contributions", self.tokens[1])
        self.assertEqual(code, 200)
        self.assertEqual(rows, [])
        code, _ = self.call("/contributions", self.tokens[0], method="POST", data={})
        self.assertGreaterEqual(code, 400)
