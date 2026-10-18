"""Integration tests never read config.local.toml or connect to Supabase."""

import os
import unittest
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parent.parent
TEST_URL = os.environ.get("HISAAB_TEST_DATABASE_URL")


def migration_config(connection=None, output_buffer=None):
    config = Config(str(ROOT / "alembic.ini"), output_buffer=output_buffer)
    if connection is not None:
        config.attributes["connection"] = connection
    return config


def test_engine():
    url = make_url(TEST_URL)
    if (
        url.get_backend_name() != "postgresql"
        or url.host not in ("localhost", "127.0.0.1", "::1")
        or not (url.database or "").startswith("hisaab_test")
    ):
        raise RuntimeError(
            "Integration tests require a disposable local hisaab_test database."
        )
    return create_engine(url, hide_parameters=True)


@unittest.skipUnless(
    TEST_URL, "Set HISAAB_TEST_DATABASE_URL for disposable PostgreSQL tests"
)
class PostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = test_engine()
        cls.addClassCleanup(cls.engine.dispose)
        with cls.engine.begin() as connection:
            command.upgrade(migration_config(connection), "head")

    def setUp(self):
        self.connection = self.engine.connect()
        outer = self.connection.begin()
        self.session = Session(
            bind=self.connection, join_transaction_mode="create_savepoint"
        )
        self.addCleanup(self.connection.close)
        self.addCleanup(outer.rollback)
        self.addCleanup(self.session.close)
