"""Friendly descriptions with real browser, Auth and local synthetic data."""
import os
import unittest

from tests.supabase_fixture import SupabaseTests
from tests import test_browser_e2e as browser_fixture


@unittest.skipUnless(os.environ.get('HISAAB_BROWSER_TESTS') == '1', 'Browser test opt-in required')
class FriendlyDescriptionBrowserTests(SupabaseTests):
    run_frontend = browser_fixture.BrowserE2ETests.run_frontend

    def test_edit_reload_search_clear_desktop_and_mobile(self):
        self.run_frontend(('friendly-description-smoke.mjs',))
