import json
import os
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import MagicMock, patch

from core.cli import main
from core.config import ConfigurationError, DatabaseConfig, load_config
from core.database import DatabaseError, check_connection

URL = "postgresql://example:synthetic-secret@localhost/test"


class ConnectionTests(unittest.TestCase):
    def test_postgres_url_uses_psycopg_tls_and_bounded_connection_attempt(self):
        engine = MagicMock()
        connection = engine.connect.return_value.__enter__.return_value
        connection.execute.return_value.scalar_one.return_value = 1
        with patch("core.database.create_engine", return_value=engine) as create:
            check_connection(DatabaseConfig(URL, 5))
        url = create.call_args.args[0]
        options = create.call_args.kwargs
        self.assertEqual(url.drivername, "postgresql+psycopg")
        self.assertEqual(url.query["sslmode"], "require")
        self.assertEqual(options["connect_args"]["connect_timeout"], 5)
        self.assertIsNone(options["connect_args"]["prepare_threshold"])
        self.assertTrue(options["hide_parameters"])
        self.assertFalse(options["echo"])
        self.assertEqual(str(connection.execute.call_args.args[0]), "SELECT 1")
        engine.dispose.assert_called_once()

    def test_preserves_stronger_tls(self):
        with patch("core.database.create_engine") as create:
            create.return_value.connect.return_value.__enter__.return_value.execute.return_value.scalar_one.return_value = 1
            check_connection(DatabaseConfig(URL + "?sslmode=verify-full"))
        self.assertEqual(create.call_args.args[0].query["sslmode"], "verify-full")

    def test_rejects_invalid_urls_and_disabled_postgres_tls(self):
        for url in (
            "synthetic-secret",
            "postgresql://user:password@localhost:synthetic-secret/test",
            URL + "?sslmode=disable",
        ):
            with self.subTest(url=url), patch("core.database.create_engine") as create:
                with self.assertRaises(ConfigurationError) as error:
                    check_connection(DatabaseConfig(url))
                self.assertNotIn("synthetic-secret", str(error.exception))
                create.assert_not_called()

    def test_failure_is_sanitized_and_engine_disposed(self):
        engine = MagicMock()
        engine.connect.side_effect = RuntimeError(URL)
        with patch("core.database.create_engine", return_value=engine):
            with self.assertRaises(DatabaseError) as error:
                check_connection(DatabaseConfig(URL))
        self.assertNotIn("synthetic-secret", str(error.exception))
        self.assertEqual(error.exception.code, "database_unavailable")
        engine.dispose.assert_called_once()

    def test_unexpected_query_result_is_not_success(self):
        engine = MagicMock()
        engine.connect.return_value.__enter__.return_value.execute.return_value.scalar_one.return_value = 0
        with patch("core.database.create_engine", return_value=engine):
            with self.assertRaises(DatabaseError):
                check_connection(DatabaseConfig(URL))

    def test_real_in_memory_sql_connection_without_network_or_schema_changes(self):
        check_connection(DatabaseConfig("sqlite:///:memory:"))


class LiveConnectionTests(unittest.TestCase):
    @unittest.skipUnless(
        os.environ.get("HISAAB_DB_TESTS") == "1", "Private database opt-in"
    )
    def test_private_database_connection(self):
        check_connection(load_config())


class ConnectionCliTests(unittest.TestCase):
    def invoke(self, *args):
        output = StringIO()
        with redirect_stdout(output):
            code = main(list(args))
        return code, json.loads(output.getvalue())

    def test_success_reports_no_connection_details(self):
        with (
            patch("core.cli.load_config", return_value=DatabaseConfig(URL)),
            patch("core.cli.check_connection"),
        ):
            code, result = self.invoke("db-check")
        self.assertEqual((code, result), (0, {"status": "connected"}))

    def test_private_config_path_is_forwarded(self):
        with (
            patch("core.cli.load_config", return_value=DatabaseConfig(URL)) as load,
            patch("core.cli.check_connection"),
        ):
            self.invoke("db-check", "--config", "/private/example.toml")
        self.assertEqual(str(load.call_args.args[0]), "/private/example.toml")

    def test_config_errors_are_structured(self):
        with patch(
            "core.cli.load_config",
            side_effect=ConfigurationError(
                "config_incomplete", "Configure the database."
            ),
        ):
            code, result = self.invoke("db-check")
        self.assertEqual(code, 1)
        self.assertEqual(result["error"]["code"], "config_incomplete")

    def test_unknown_driver_errors_do_not_expose_secrets(self):
        with (
            patch("core.cli.load_config", return_value=DatabaseConfig(URL)),
            patch("core.cli.check_connection", side_effect=RuntimeError(URL)),
        ):
            code, result = self.invoke("db-check")
        self.assertEqual(code, 1)
        self.assertNotIn("synthetic-secret", json.dumps(result))

    def test_unknown_option_rejected(self):
        code, result = self.invoke("db-check", "--password", "synthetic-secret")
        self.assertEqual(code, 2)
        self.assertNotIn("synthetic-secret", json.dumps(result))

    def test_cancelled_check_has_safe_exit(self):
        with patch("core.cli.load_config", side_effect=KeyboardInterrupt):
            code, result = self.invoke("db-check")
        self.assertEqual(code, 130)
        self.assertEqual(result["error"]["code"], "cancelled")
