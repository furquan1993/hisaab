"""Real browser automatic assignment and explicit removal, using synthetic records."""
import os
import unittest
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from core.persistence.models import AssignmentExample, Entry, EntryDecision, FundingAccount
from tests.supabase_fixture import SupabaseTests
from tests import test_browser_e2e as browser_fixture


@unittest.skipUnless(os.environ.get('HISAAB_BROWSER_TESTS') == '1', 'Browser test opt-in required')
class AssignmentBrowserTests(SupabaseTests):
    run_frontend = browser_fixture.BrowserE2ETests.run_frontend

    def test_auto_assign_reload_and_explicit_removal(self):
        with Session(self.engine) as session, session.begin():
            session.execute(update(Entry).where(Entry.id==self.records[0].entry.id).values(description='SWIGGY INSTAMART'))
            account=FundingAccount(owner_id=self.owners[0],name='Synthetic history account')
            session.add(account);session.flush()
            for index in range(2):
                session.add(AssignmentExample(owner_id=self.owners[0],source_key=str(index),merchant_key='swiggy instamart',direction='debit',kind='account',is_manual=False,account_id=account.id))
        self.run_frontend(('auto-assign-smoke.mjs',))
        with Session(self.engine) as session:
            decision=session.scalar(select(EntryDecision).where(EntryDecision.entry_id==self.records[0].entry.id))
            self.assertIsNone(decision.account_id)
            self.assertIsNotNone(decision.category_id)
            self.assertEqual(decision.version,2)
