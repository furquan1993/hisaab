"""Sign-in, credential privacy and CLI routing without a database connection."""
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import BytesIO, StringIO
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from uuid import uuid4

from core.cli import main
from core.persistence.store import StoreError
from core.user_api import NoRedirect, UserAPI, public_config
from tests.test_snapshot import encrypt, statement_bytes


class UserAPITests(unittest.TestCase):
    def test_public_config_rejects_secrets_and_unsafe_urls(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "public.json"
            for url, key in [
                ("https://project.supabase.co/", "sb_secret_PRIVATE"),
                ("http://project.supabase.co/", "sb_publishable_public"),
                ("https://user:password@project.supabase.co/", "sb_publishable_public"),
                ("https://project.supabase.co/subpath", "sb_publishable_public"),
            ]:
                path.write_text(json.dumps({"url": url, "publishable_key": key}))
                with self.assertRaises(StoreError):
                    public_config(path)
            path.write_text(json.dumps({"url": "https://project.supabase.co/", "publishable_key": "sb_publishable_public"}))
            self.assertEqual(public_config(path), ("https://project.supabase.co", "sb_publishable_public"))

    def test_password_grant_refresh_and_local_logout_do_not_persist_tokens(self):
        api = UserAPI("https://example.supabase.co", "sb_publishable_public")
        response = {"access_token": "private-token", "refresh_token": "private-refresh", "expires_in": 3600}
        with patch.object(api, "_request", side_effect=[response, response, [], None]) as request:
            api.sign_in("user@example.invalid", "private-password")
            self.assertEqual(request.call_args.args[0], "/auth/v1/token?grant_type=password")
            api.expires_at = 0
            self.assertEqual(api.request("/cards"), [])
            self.assertEqual(request.call_args_list[1].args[0], "/auth/v1/token?grant_type=refresh_token")
            api.close()
            self.assertEqual(request.call_args.args[0], "/auth/v1/logout?scope=local")
        self.assertIsNone(api.access_token)
        self.assertIsNone(api.refresh_token)

    def test_auth_and_rpc_errors_do_not_leak_response_or_token(self):
        api = UserAPI("https://example.supabase.co", "sb_publishable_public")
        for auth, status in [(True, 400), (False, 422), (False, 500), (False, 401)]:
            api.access_token = "private-token"
            error = HTTPError(api.url, status, "private-password", {}, BytesIO(b'{"message":"private SQL PDF data", "code":"whatever"}'))
            with patch.object(api.opener, "open", side_effect=error), self.assertRaises(StoreError) as raised:
                api._request("/test", auth=auth)
            self.assertNotIn("private", str(raised.exception))
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.invalid"))

    def test_rpc_request_sends_session_and_public_key(self):
        api = UserAPI("https://example.supabase.co", "sb_publishable_public")
        api.access_token = "session-token"
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'null'
        with patch.object(api.opener, "open", return_value=response) as opened:
            api._request("/rest/v1/rpc/find_pdf_import", {"p_card": "card"})
        request = opened.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer session-token")
        self.assertEqual(request.get_header("Apikey"), "sb_publishable_public")
        self.assertEqual(request.get_header("Content-profile"), "hisaab_api")


class UserImportCLITests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.path = self.root / "statement.pdf"
        self.path.write_bytes(statement_bytes())
        self.owner, self.card = uuid4(), uuid4()
        self.api = Mock()
        self.saved = dict(status="imported", owner_id=str(self.owner), card_id=str(self.card),
                          statement_id=str(uuid4()), import_id=str(uuid4()), transaction_count=2,
                          review_issue_count=0, review_status="pending", selected_source=True, needs_review=False)
        self.api.request.side_effect = lambda path, data=None: (
            [{"id": str(self.owner), "display_name": "User"}] if path.startswith("/profile") else
            [{"id": str(self.card), "label": "My card", "bank": "hdfc"}] if path.startswith("/cards?") else
            None if path == "/rpc/find_pdf_import" else self.saved)

    def invoke(self, *paths, extra=(), password="UI-password", choose_card=False):
        output = StringIO()
        with redirect_stdout(output), patch("core.user_imports.UserAPI", return_value=self.api), \
                patch("core.cli_store.load_config") as database_config, \
                patch("core.cli_store.create_database_engine") as database, \
                patch("sys.stdin.isatty", return_value=True), \
                patch("core.imports.INPUT_ROOT", self.root), \
                patch("getpass.getpass", return_value=password), \
                patch("builtins.input", side_effect=["user@example.invalid", "1"]):
            card_args = [] if choose_card else ["--card", str(self.card)]
            code = main(["import-pdf", *card_args, *extra, *map(str, paths or [self.path])])
            database.assert_not_called()
            database_config.assert_not_called()
        return code, output.getvalue()

    def test_import_uses_ui_login_and_atomic_api_without_database_config(self):
        code, output = self.invoke()
        self.assertEqual(code, 0, output)
        self.api.sign_in.assert_called_once_with("user@example.invalid", "UI-password")
        self.api.close.assert_called_once()
        payload = self.api.request.call_args.args[1]
        self.assertNotIn("p_owner", payload)
        self.assertEqual(payload["p_statement"]["transactions"][0]["amount"], "123.45")
        self.assertEqual(json.loads(output)["import_id"], self.saved["import_id"])
        for private in ("UI-password", "SYNTHETIC SHOP", "p_pdf_base64"):
            self.assertNotIn(private, output)

    def test_owner_mismatch_stops_before_reading_pdf(self):
        code, output = self.invoke(extra=("--owner", str(uuid4())))
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output)["error"]["code"], "owner_mismatch")
        self.assertEqual(self.api.request.call_count, 1)

    def test_minimal_command_prompts_for_saved_card(self):
        code, output = self.invoke(choose_card=True)
        self.assertEqual(code, 0, output)
        self.assertEqual(json.loads(output)["card_id"], str(self.card))

    def test_cancelling_a_batch_keeps_prior_summary_and_stops(self):
        with patch("core.user_imports.import_one", side_effect=[self.saved, KeyboardInterrupt]) as imported:
            code, output = self.invoke(self.path, self.path, self.path)
        self.assertEqual(code, 130)
        self.assertEqual(imported.call_count, 2)
        summaries = [json.loads(line) for line in output.splitlines()]
        self.assertEqual(summaries[0]["status"], "imported")
        self.assertEqual(summaries[1]["error"]["code"], "cancelled")

    def test_duplicate_does_not_parse_or_request_pdf_password(self):
        self.path.write_bytes(encrypt(self.path.read_bytes()))
        self.api.request.side_effect = [
            [{"id": str(self.owner)}],
            [{"id": str(self.card), "label": "My card", "bank": "hdfc"}],
            {**self.saved, "status": "duplicate"}]
        with patch("core.user_imports._parse") as parse:
            code, output = self.invoke()
        self.assertEqual(code, 0, output)
        parse.assert_not_called()
        self.assertEqual(json.loads(output)["status"], "duplicate")

    def test_batch_continues_after_failure_and_preserves_exit_precedence(self):
        self.saved["needs_review"] = True
        missing = self.root / "missing.pdf"
        code, output = self.invoke(missing, self.path)
        self.assertEqual(code, 1)
        self.assertEqual(len(output.splitlines()), 2)
        code, _ = self.invoke(self.path)
        self.assertEqual(code, 3)

    def test_noninteractive_login_and_password_flags_fail_without_network(self):
        for extra, expected in [([], 1), (["--password", "private-value"], 2)]:
            output = StringIO()
            with redirect_stdout(output), patch("sys.stdin.isatty", return_value=False), \
                    patch("core.user_imports.UserAPI") as api:
                code = main(["import-pdf", *extra, str(self.path)])
            self.assertEqual(code, expected)
            self.assertNotIn("private-value", output.getvalue())
            api.assert_not_called()
