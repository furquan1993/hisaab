"""Authenticated monthly funding flow on the isolated Supabase stack."""

import os
import unittest
from datetime import date
from decimal import Decimal

from sqlalchemy import update
from sqlalchemy.orm import Session

from core.persistence.models import Entry, ImportRecord, Statement
from tests import test_browser_e2e as browser_fixture
from tests.persistence_fixture import new_entry, new_import
from tests.supabase_fixture import SupabaseTests


@unittest.skipUnless(
    os.environ.get("HISAAB_BROWSER_TESTS") == "1", "Browser test opt-in required"
)
class FundingBrowserE2ETests(SupabaseTests):
    run_frontend = browser_fixture.BrowserE2ETests.run_frontend

    def test_full_partial_reload_and_reasoned_reconfirmation(self):
        base = self.records[0]
        with self.engine.begin() as c:
            c.execute(
                update(ImportRecord)
                .where(ImportRecord.id == base.imported.id)
                .values(issues=[])
            )
            c.execute(
                update(Entry)
                .where(Entry.id == base.entry.id)
                .values(amount=Decimal("100.00"))
            )
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
            s.add(
                new_entry(
                    imported, description="SYNTHETIC FEB SHOP", amount=Decimal("50.00")
                )
            )
        self.run_frontend(("funding-smoke.mjs",))
