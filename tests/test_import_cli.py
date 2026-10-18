import json
import stat
from contextlib import redirect_stdout
from io import StringIO
from itertools import permutations
from pathlib import Path
from unittest.mock import patch

from core.cli import main
from core.config import DatabaseConfig
from core.imports import import_pdf
from core.persistence.import_records import list_imports
from tests.import_fixture import ImportTestsBase
from tests.postgres_fixture import test_engine
from tests.test_snapshot import encrypt, statement_bytes
from tests.test_transactions_postgres import remove_synthetic_owner


class ImportCliTests(ImportTestsBase):
    def invoke(self, *args):
        output = StringIO()
        with (
            redirect_stdout(output),
            patch(
                "core.cli_store.load_config", return_value=DatabaseConfig("sqlite://")
            ),
            patch(
                "core.cli_store.create_database_engine",
                side_effect=lambda settings: test_engine(),
            ),
            patch("core.private_files.CONFIG_ROOT", self.root),
        ):
            code = main(list(args))
        return code, [json.loads(line) for line in output.getvalue().splitlines()]

    def load_args(self, *paths):
        return (
            "import-pdf",
            "--owner",
            str(self.owner),
            "--card",
            str(self.card),
            *map(str, paths),
        )

    def test_register_list_card_and_import(self):
        code, output = self.invoke("owner-create", "Synthetic CLI owner")
        self.assertEqual(code, 0)
        from uuid import UUID

        owner = UUID(output[0]["owner_id"])
        self.addCleanup(remove_synthetic_owner, self.engine, owner)
        code, output = self.invoke(
            "card-create",
            "--owner",
            str(owner),
            "--bank",
            "hdfc",
            "--label",
            "Synthetic card",
        )
        self.assertEqual(code, 0)
        card = output[0]["card_id"]
        code, output = self.invoke("cards-list", "--owner", str(owner))
        self.assertEqual(code, 0)
        self.assertEqual(output[0]["items"][0]["id"], card)

    def test_cli_round_trip_exports_original_and_hides_rows(self):
        original = encrypt(self.path.read_bytes())
        self.path.write_bytes(original)
        with (
            patch("sys.stdin.isatty", return_value=True),
            patch("getpass.getpass", return_value="synthetic-password"),
        ):
            code, output = self.invoke(*self.load_args(self.path))
        self.assertIn(code, (0, 3))
        self.assertNotIn("SYNTHETIC SHOP", json.dumps(output))
        self.assertNotIn("synthetic-password", json.dumps(output))
        import_id = output[0]["import_id"]
        code, output = self.invoke(
            "original-export", "--owner", str(self.owner), "--import-id", import_id
        )
        self.assertEqual(code, 0)
        destination = Path(output[0]["output"])
        self.assertEqual(destination.read_bytes(), original)
        self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(destination.parent.stat().st_mode), 0o700)

    def test_list_is_paginated_and_does_not_expose_transactions(self):
        import_pdf(self.engine, self.owner, self.card, self.path)
        code, output = self.invoke(
            "imports-list", "--owner", str(self.owner), "--limit", "1"
        )
        self.assertEqual(code, 0)
        self.assertEqual(output[0]["count"], 1)
        self.assertEqual(output[0]["items"][0]["transaction_count"], 2)
        self.assertNotIn("SYNTHETIC SHOP", json.dumps(output))

    def test_explicit_reparse_creates_a_review_candidate_without_printing_rows(self):
        saved = import_pdf(self.engine, self.owner, self.card, self.path)
        code, output = self.invoke(
            "reparse-import",
            "--owner",
            str(self.owner),
            "--import-id",
            str(saved.import_id),
        )
        self.assertEqual(code, 3)
        self.assertEqual(output[0]["status"], "review_candidate")
        self.assertEqual(output[0]["matched_count"], 2)
        self.assertNotIn("SYNTHETIC SHOP", json.dumps(output))
        self.assertNotIn("matches", output[0])

    def test_noninteractive_encrypted_pdf_requires_hidden_input(self):
        self.path.write_bytes(encrypt(self.path.read_bytes()))
        with (
            patch("sys.stdin.isatty", return_value=False),
            patch("getpass.getpass") as prompt,
        ):
            code, output = self.invoke(*self.load_args(self.path))
        self.assertEqual(code, 1)
        self.assertEqual(output[0]["error"]["code"], "password_required")
        prompt.assert_not_called()
        self.assertEqual(list_imports(self.engine, self.owner), [])

    def test_failure_review_success_precedence_in_any_order(self):
        import_pdf(self.engine, self.owner, self.card, self.path)
        review = self.root / "competing.pdf"
        review.write_bytes(statement_bytes("COMPETING SYNTHETIC SHOP"))
        missing = self.root / "missing.pdf"
        for paths in permutations((self.path, review, missing)):
            code, output = self.invoke(*self.load_args(*paths))
            self.assertEqual(code, 1)
            self.assertEqual(len(output), 3)
        for paths in permutations((self.path, review)):
            code, output = self.invoke(*self.load_args(*paths))
            self.assertEqual(code, 3)

    def test_cancelled_batch_keeps_prior_import_and_stops(self):
        second = self.root / "encrypted.pdf"
        second.write_bytes(encrypt(statement_bytes("SECOND")))
        with (
            patch("sys.stdin.isatty", return_value=True),
            patch("getpass.getpass", side_effect=KeyboardInterrupt),
        ):
            code, output = self.invoke(*self.load_args(self.path, second, self.path))
        self.assertEqual(code, 130)
        self.assertEqual(len(output), 2)
        self.assertEqual(len(list_imports(self.engine, self.owner)), 1)

    def test_unknown_arguments_and_bad_ids_are_safe_usage_errors(self):
        for args in (
            (*self.load_args(self.path), "--password", "synthetic-secret"),
            ("imports-list", "--owner", "synthetic-secret"),
        ):
            code, output = self.invoke(*args)
            self.assertEqual(code, 2)
            self.assertNotIn("synthetic-secret", json.dumps(output))

    def test_raw_database_errors_are_not_printed(self):
        with patch(
            "core.cli_store.import_pdf",
            side_effect=RuntimeError("synthetic-secret SQL amount 999.99"),
        ):
            code, output = self.invoke(*self.load_args(self.path))
        self.assertEqual(code, 1)
        self.assertNotIn("synthetic-secret", json.dumps(output))
        self.assertNotIn("999.99", json.dumps(output))
