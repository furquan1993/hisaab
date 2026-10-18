"""Exercise the actual frontend against isolated Supabase, never the live project."""

import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from urllib.request import urlopen

from tests.supabase_fixture import SupabaseTests

ROOT = Path(__file__).resolve().parent.parent


@unittest.skipUnless(
    os.environ.get("HISAAB_BROWSER_TESTS") == "1", "Browser test opt-in required"
)
class BrowserE2ETests(SupabaseTests):
    def test_real_password_login_reload_evidence_and_signout(self):
        environment = os.environ.copy()
        environment.update(
            VITE_SUPABASE_URL=self.api,
            VITE_SUPABASE_PUBLISHABLE_KEY=self.anon,
            HISAAB_E2E_EMAIL=self.logins[0][0],
            HISAAB_E2E_PASSWORD=self.logins[0][1],
        )
        with tempfile.TemporaryFile() as log:
            server = subprocess.Popen(
                ["npm", "run", "dev", "--", "--port", "5183", "--strictPort"],
                cwd=ROOT / "web",
                env=environment,
                stdout=log,
                stderr=log,
            )
            try:
                for _ in range(60):
                    if server.poll() is not None:
                        self.fail("Isolated frontend did not start.")
                    try:
                        with urlopen(
                            "http://127.0.0.1:5183/hisaab/", timeout=1
                        ) as response:
                            if response.status == 200:
                                break
                    except OSError:
                        time.sleep(0.2)
                else:
                    self.fail("Isolated frontend readiness timed out.")
                result = subprocess.run(
                    ["node", "e2e/auth-smoke.mjs"],
                    cwd=ROOT / "web",
                    env=environment,
                    capture_output=True,
                    timeout=60,
                )
                self.assertEqual(
                    result.returncode, 0, "Isolated Auth browser smoke failed."
                )
            finally:
                server.terminate()
                try:
                    server.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=5)
