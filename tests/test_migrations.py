import unittest
from io import StringIO
from unittest.mock import patch

from alembic import command
from alembic.script import ScriptDirectory
from alembic.util import CommandError
from sqlalchemy import inspect, text

from tests.postgres_fixture import PostgresTests, migration_config, test_engine


class OfflineMigrationTests(unittest.TestCase):
    def test_upgrade_sql_does_not_read_private_settings_or_connect(self):
        output = StringIO()
        with patch(
            "core.config.load_config", side_effect=AssertionError("No private settings")
        ):
            command.upgrade(migration_config(output_buffer=output), "head", sql=True)
        sql = output.getvalue()
        for name in ("owners", "cards", "statements", "imports", "entries"):
            self.assertIn(f"CREATE TABLE hisaab.{name}", sql)
            self.assertIn(f"ALTER TABLE hisaab.{name} ENABLE ROW LEVEL SECURITY", sql)
        self.assertIn("BYTEA", sql)
        self.assertIn("NUMERIC(20, 2)", sql)
        self.assertIn("fk_statements_active_import", sql)
        self.assertNotIn("DROP TABLE", sql)

    def test_downgrade_removes_cycle_before_tables(self):
        output = StringIO()
        command.downgrade(
            migration_config(output_buffer=output), "0001_initial_schema:base", sql=True
        )
        sql = output.getvalue()
        self.assertLess(
            sql.index("DROP CONSTRAINT"), sql.index("DROP TABLE hisaab.imports")
        )
        self.assertNotIn("CASCADE", sql)

    def test_single_head_and_no_secret_in_configuration(self):
        config = migration_config()
        self.assertEqual(
            ScriptDirectory.from_config(config).get_heads(), ["0003_browser_queries"]
        )
        self.assertIsNone(config.get_main_option("sqlalchemy.url"))

    def test_online_failures_do_not_print_sensitive_driver_messages(self):
        with (
            patch("core.config.load_config"),
            patch(
                "core.database.create_database_engine",
                side_effect=RuntimeError(
                    "postgresql://synthetic-secret@example.invalid/test"
                ),
            ),
        ):
            with self.assertRaises(CommandError) as error:
                command.current(migration_config())
        self.assertNotIn("synthetic-secret", str(error.exception))

    def test_test_database_guard_rejects_hosted_and_non_test_databases(self):
        for url in (
            "postgresql+psycopg://user@db.example.invalid/hisaab_test",
            "postgresql+psycopg://user@127.0.0.1/postgres",
            "sqlite:///:memory:",
        ):
            with self.subTest(url=url), patch("tests.postgres_fixture.TEST_URL", url):
                with self.assertRaises(RuntimeError):
                    test_engine()


class MigrationPostgresTests(PostgresTests):
    def test_metadata_has_no_drift_after_upgrade(self):
        output = StringIO()
        config = migration_config(self.connection)
        config.stdout = output
        command.check(config)
        self.assertIn("No new upgrade operations", output.getvalue())

    def test_downgrade_upgrade_round_trip(self):
        config = migration_config(self.connection)
        command.downgrade(config, "base")
        self.assertFalse(inspect(self.connection).has_schema("hisaab"))
        command.upgrade(config, "head")
        self.assertEqual(
            set(inspect(self.connection).get_table_names(schema="hisaab")),
            {"owners", "cards", "statements", "imports", "entries"},
        )
        self.assertEqual(
            self.connection.scalar(
                text("SELECT version_num FROM public.hisaab_schema_version")
            ),
            "0003_browser_queries",
        )

    def test_upgrade_is_idempotent(self):
        command.upgrade(migration_config(self.connection), "head")
        command.upgrade(migration_config(self.connection), "head")
        self.assertEqual(
            len(inspect(self.connection).get_table_names(schema="hisaab")), 5
        )
