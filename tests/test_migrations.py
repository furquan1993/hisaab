import unittest
from io import StringIO
from datetime import date
from decimal import Decimal
from uuid import uuid4
from unittest.mock import patch

from alembic import command
from alembic.script import ScriptDirectory
from alembic.util import CommandError
from sqlalchemy import inspect, text

from core.persistence.models import Base, Contribution, FundingAccount, SpendingGroup
from tests.persistence_fixture import seed
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
            ScriptDirectory.from_config(config).get_heads(), ["0018_card_management"]
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
    def test_downgrade_refuses_to_discard_spending_groups(self):
        records = seed(self.session)
        self.session.add(SpendingGroup(owner_id=records.owner.id, name="Synthetic retained trip"))
        self.session.flush()
        before = self.connection.scalar(text("SELECT version_num FROM public.hisaab_schema_version"))
        with self.assertRaises(CommandError), self.connection.begin_nested():
            command.downgrade(migration_config(self.connection), "0014_statement_balances")
        self.assertEqual(self.connection.scalar(text("SELECT version_num FROM public.hisaab_schema_version")), before)
        self.assertEqual(self.connection.scalar(text("SELECT count(*) FROM hisaab.spending_groups")), 1)

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
            {table.name for table in Base.metadata.tables.values()},
        )
        self.assertEqual(
            self.connection.scalar(
                text("SELECT version_num FROM public.hisaab_schema_version")
            ),
            "0018_card_management",
        )

    def test_downgrade_refuses_to_discard_contribution_history(self):
        records = seed(self.session)
        account = FundingAccount(
            owner_id=records.owner.id, name="Synthetic retained pot"
        )
        self.session.add(account)
        self.session.flush()
        self.session.add(
            Contribution(
                owner_id=records.owner.id,
                card_id=records.card.id,
                account_id=account.id,
                currency="INR",
                month=date(2026, 1, 1),
                amount=Decimal("1.00"),
                received_on=date(2026, 2, 1),
                note="",
                request=[],
                actor_auth_user_id=uuid4(),
                applications=[
                    {
                        "month": "2026-01-01",
                        "amount": "1.00",
                        "fingerprint": "synthetic",
                    }
                ],
            )
        )
        self.session.flush()
        with self.assertRaises(CommandError), self.connection.begin_nested():
            command.downgrade(migration_config(self.connection), "0010_funding_totals")
        self.assertEqual(
            self.connection.scalar(
                text("SELECT version_num FROM public.hisaab_schema_version")
            ),
            "0018_card_management",
        )
        self.assertEqual(
            self.connection.scalar(text("SELECT count(*) FROM hisaab.contributions")), 1
        )

    def test_upgrade_is_idempotent(self):
        command.upgrade(migration_config(self.connection), "head")
        command.upgrade(migration_config(self.connection), "head")
        self.assertEqual(
            len(inspect(self.connection).get_table_names(schema="hisaab")),
            len(Base.metadata.tables),
        )
