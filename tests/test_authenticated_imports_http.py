"""Actual password Auth and atomic import RPCs on disposable Supabase only."""
import base64
import copy
import json
import tempfile
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from importlib.metadata import version
from uuid import uuid4

from sqlalchemy import text

from core.parser import parse_pdf_bytes
from core.cli import main
from tests.supabase_fixture import SupabaseTests
from tests.test_snapshot import encrypt, statement_bytes


def payload(data, name="statement.pdf", password=""):
    parsed = parse_pdf_bytes(data, source_name=name, password=password).to_dict()
    parsed["extractor_version"] = "hisaab-extraction-1/pdfplumber-" + version("pdfplumber")
    return {"p_statement": parsed, "p_pdf_base64": base64.b64encode(data).decode()}


class AuthenticatedImportsHTTPTests(SupabaseTests):
    def setUp(self):
        code, card = self.call("/rpc/save_card", self.tokens[0], method="POST", data={
            "p_expected_owner": str(self.owners[0]), "p_id": None,
            "p_expected_version": 0, "p_label": "Synthetic import " + uuid4().hex,
            "p_bank": "hdfc", "p_last_four": None})
        self.assertEqual(code, 200)
        self.card = card["id"]
        self.pdf = statement_bytes()
        self.body = {"p_card": self.card, **payload(self.pdf)}

    def submit(self, body=None, token=None):
        return self.call("/rpc/import_statement", token or self.tokens[0],
                         method="POST", data=body or self.body)

    def test_atomic_roundtrip_duplicate_and_candidate(self):
        code, saved = self.submit()
        self.assertEqual(code, 200, saved)
        self.assertEqual(saved["status"], "imported")
        self.assertTrue(saved["selected_source"])
        self.assertEqual(saved["transaction_count"], 2)
        code, original = self.call("/rpc/original_pdf", self.tokens[0], method="POST",
                                   data={"p_import_id": saved["import_id"]})
        self.assertEqual(code, 200)
        self.assertEqual(base64.b64decode(original["content_base64"]), self.pdf)
        renamed = copy.deepcopy(self.body)
        renamed["p_statement"]["source_name"] = "renamed.pdf"
        code, duplicate = self.submit(renamed)
        self.assertEqual((code, duplicate["status"], duplicate["import_id"]),
                         (200, "duplicate", saved["import_id"]))
        competing = {"p_card": self.card, **payload(statement_bytes("COMPETING"))}
        code, candidate = self.submit(competing)
        self.assertEqual((code, candidate["status"], candidate["selected_source"]),
                         (200, "review_candidate", False))
        self.assertEqual(candidate["statement_id"], saved["statement_id"])

    def test_no_owner_spoofing_foreign_card_or_anonymous_access(self):
        for token in (self.tokens[1], self.tokens[2]):
            code, _ = self.submit(token=token)
            self.assertIn(code, (403, 404))
        code, _ = self.call("/rpc/import_statement", method="POST", data=self.body)
        self.assertGreaterEqual(code, 400)
        tampered = {**self.body, "p_owner": str(self.owners[1])}
        self.assertGreaterEqual(self.submit(tampered)[0], 400)
        code, _ = self.call("/rpc/find_pdf_import", self.tokens[1], method="POST",
                            data={"p_card": self.card, "p_sha256": sha256(self.pdf).hexdigest()})
        self.assertEqual(code, 404)

    def test_invalid_evidence_rolls_back_everything(self):
        changes = [
            lambda b: b["p_statement"].update(source_sha256="0" * 64),
            lambda b: b["p_statement"].update(bank="sbi"),
            lambda b: b["p_statement"]["transactions"][1].update(amount="1.001"),
            lambda b: b["p_statement"]["transactions"][1].update(transaction_date="2026-02-31"),
            lambda b: b["p_statement"]["transactions"][1]["source"].update(page=9999),
            lambda b: b["p_statement"]["transactions"][1].update(sequence=1),
            lambda b: b.update(p_pdf_base64="invalid base64!"),
        ]
        for change in changes:
            with self.subTest(change=change):
                bad = copy.deepcopy(self.body)
                change(bad)
                code, result = self.submit(bad)
                self.assertEqual(code, 422, result)
                with self.engine.connect() as conn:
                    self.assertEqual(conn.scalar(text("SELECT count(*) FROM hisaab.statements WHERE card_id=:card"),
                                                 {"card": self.card}), 0)
        self.assertEqual(self.submit()[0], 200)

    def test_parallel_retries_have_one_original(self):
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: self.submit(), range(2)))
        self.assertEqual([code for code, _ in results], [200, 200], results)
        self.assertEqual({result["status"] for _, result in results}, {"imported", "duplicate"})
        self.assertEqual(len({result["import_id"] for _, result in results}), 1)

    def test_other_bank_layouts_keep_exact_entry_facts(self):
        from tests.bank_fixture import BankPage
        from tests.hdfc_fixture import pdf_bytes

        for bank in ("sbi", "yes_bank"):
            with self.subTest(bank=bank):
                code, card = self.call("/rpc/save_card", self.tokens[0], method="POST", data={
                    "p_expected_owner": str(self.owners[0]), "p_id": None,
                    "p_expected_version": 0, "p_label": "Synthetic " + bank,
                    "p_bank": bank, "p_last_four": None})
                self.assertEqual(code, 200)
                page = BankPage(bank)
                page.header()
                page.row(250, "SYNTHETIC SHOP", "123.45")
                page.footer(340)
                data = encrypt(pdf_bytes([page]))
                body = {"p_card": card["id"], **payload(data, password="synthetic-password")}
                code, saved = self.submit(body)
                self.assertEqual(code, 200, saved)
                with self.engine.connect() as connection:
                    actual = connection.execute(text("SELECT amount,description,source_raw_text FROM hisaab.entries WHERE import_id=:id ORDER BY sequence"),
                                                {"id": saved["import_id"]}).mappings().all()
                expected = body["p_statement"]["transactions"]
                self.assertEqual(len(actual), len(expected))
                for row, parsed in zip(actual, expected):
                    self.assertEqual(format(row["amount"], ".2f"), parsed["amount"])
                    self.assertEqual(row["source_raw_text"], parsed["source"]["raw_text"])

    def test_printed_balance_is_retained_and_malformed_amount_rejected(self):
        body = copy.deepcopy(self.body)
        balance = {name: "123.45" for name in (
            "previous_balance", "payments_and_credits", "charges", "finance_charges", "amount_due")}
        balance.update(currency="INR", source=body["p_statement"]["transactions"][0]["source"])
        body["p_statement"]["printed_balance"] = balance
        bad = copy.deepcopy(body)
        bad["p_statement"]["printed_balance"]["amount_due"] = "123.456"
        self.assertEqual(self.submit(bad)[0], 422)
        code, saved = self.submit(body)
        self.assertEqual(code, 200, saved)
        with self.engine.connect() as connection:
            stored = connection.scalar(text("SELECT printed_balance FROM hisaab.imports WHERE id=:id"),
                                       {"id": saved["import_id"]})
        self.assertEqual(stored, balance)

    def test_encrypted_bytes_and_unresolved_date(self):
        data = encrypt(self.pdf)
        body = {"p_card": self.card, **payload(data, password="synthetic-password")}
        body["p_statement"]["statement_date"] = None
        code, result = self.submit(body)
        self.assertEqual((code, result["status"], result["selected_source"]),
                         (200, "review_candidate", False))
        with self.engine.connect() as conn:
            self.assertEqual(conn.scalar(text("SELECT pdf_bytes FROM hisaab.imports WHERE id=:id"),
                                         {"id": result["import_id"]}), data)

    def test_cli_password_login_import_and_duplicate_without_database_credentials(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            public = root / "public.json"
            public.write_text(json.dumps({"url": self.api, "publishable_key": self.anon}))
            path = root / "encrypted.pdf"
            original = encrypt(self.pdf)
            path.write_bytes(original)
            results = []
            for duplicate in (False, True):
                output = StringIO()
                email, password = self.logins[0]
                with redirect_stdout(output), patch("sys.stdin.isatty", return_value=True), \
                        patch("core.imports.INPUT_ROOT", root), \
                        patch("builtins.input", return_value=email), \
                        patch("getpass.getpass", side_effect=[password] if duplicate else [password, "synthetic-password"]), \
                        patch("core.cli_store.load_config") as private_config, \
                        patch("core.cli_store.create_database_engine") as database:
                    code = main(["import-pdf", "--project-config", str(public),
                                 "--card", self.card, "--owner", str(self.owners[0]), str(path)])
                    private_config.assert_not_called()
                    database.assert_not_called()
                self.assertIn(code, (0, 3), output.getvalue())
                self.assertNotIn(password, output.getvalue())
                self.assertNotIn("synthetic-password", output.getvalue())
                results.append(json.loads(output.getvalue()))
            self.assertEqual([result["status"] for result in results], ["imported", "duplicate"])
            self.assertEqual(results[0]["import_id"], results[1]["import_id"])
            with self.engine.connect() as conn:
                self.assertEqual(conn.scalar(text("SELECT pdf_bytes FROM hisaab.imports WHERE id=:id"),
                                             {"id": results[0]["import_id"]}), original)
