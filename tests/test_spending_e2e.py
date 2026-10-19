"""Saved spending groups across cards, dates and browser reloads."""

import os
import unittest
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from core.persistence.models import Card, Statement
from tests.persistence_fixture import new_entry, new_import
from tests.supabase_fixture import SupabaseTests
from tests import test_browser_e2e as browser_fixture


@unittest.skipUnless(os.environ.get("HISAAB_BROWSER_TESTS") == "1", "Browser opt-in required")
class SpendingBrowserTests(SupabaseTests):
    run_frontend = browser_fixture.BrowserE2ETests.run_frontend

    def test_grouping_refunds_reload_and_responsive_layout(self):
        base = self.records[0]
        with Session(self.engine) as session, session.begin():
            session.add(new_entry(base.imported, sequence=2, description="SYNTHETIC TRIP REFUND", direction="credit", entry_type="refund", amount=Decimal("23.45"), transaction_date=date(2026, 1, 2)))
            card = Card(owner_id=base.owner.id, bank="sbi", label="Invented travel card")
            session.add(card)
            session.flush()
            statement = Statement(owner_id=base.owner.id, card_id=card.id, statement_date=date(2026, 2, 28))
            session.add(statement)
            session.flush()
            imported = new_import(base, card_id=card.id, statement_id=statement.id, parsed_statement_date=date(2026, 2, 28))
            session.add(imported)
            session.flush()
            statement.active_import_id = imported.id
            session.add(new_entry(imported, description="SYNTHETIC TRIP HOTEL", transaction_date=date(2026, 2, 2), amount=Decimal("200.00")))
        self.run_frontend(("spending-smoke.mjs",), port=5185)
