"""Regression for the real API query budget with several funding accounts."""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from core.persistence.models import EntryDecision, FundingAccount
from tests.persistence_fixture import new_entry
from tests.test_reconciliation_http import ReconciliationFixture


class ReconciliationPerformanceTests(ReconciliationFixture):
    def test_expensive_evidence_is_materialized_before_account_joins(self):
        with self.engine.connect() as connection:
            for view in ("hisaab.funding_obligations", "hisaab.funding_balances"):
                definition = connection.scalar(
                    text("SELECT pg_get_viewdef(CAST(:view AS regclass),true)"),
                    {"view": view},
                )
                self.assertIn("MATERIALIZED", definition)
                self.assertIn("current_owner_id()", definition)

    def test_multi_account_summary_fits_managed_api_timeout(self):
        base = self.records[0]
        with Session(self.engine) as session, session.begin():
            accounts = [UUID(self.account["id"])]
            for index in range(7):
                account = FundingAccount(
                    owner_id=base.owner.id, name=f"Synthetic performance pot {index}"
                )
                session.add(account)
                session.flush()
                accounts.append(account.id)
            for index in range(64):
                entry = new_entry(
                    base.imported, sequence=index + 2, amount=Decimal("10.01"),
                    description=f"SYNTHETIC PERFORMANCE SHOP {index}"
                )
                session.add(entry)
                session.flush()
                session.add(
                    EntryDecision(
                        owner_id=base.owner.id,
                        entry_id=entry.id,
                        account_id=accounts[index % len(accounts)],
                    )
                )
        with self.engine.begin() as connection:
            connection.execute(
                text("ANALYZE hisaab.entries, hisaab.entry_decisions, hisaab.accounts")
            )
        code, rows = self.call(
            "/funding_groups?or=(month.lte.2026-01-01,month.is.null)&order=card_id,account_id,currency,month&offset=0&limit=100",
            self.tokens[0],
        )
        self.assertEqual(
            code,
            200,
            "Multi-account reconciliation exceeded the real managed API query budget",
        )
        self.assertEqual(len(rows), len(accounts))
        self.assertEqual(sum(Decimal(row["net"]) for row in rows), Decimal("740.64"))
        self.assertFalse(any(row["blocked"] for row in rows))
