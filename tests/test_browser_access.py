"""Trusted linking and read-only RLS contract, using invented local data."""

import json
from uuid import uuid4

from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError

from tests.persistence_fixture import seed
from tests.postgres_fixture import PostgresTests


class BrowserAccessTests(PostgresTests):
    def test_optional_auth_subject_is_unique_and_not_financial_identity(self):
        columns = {
            c["name"]
            for c in inspect(self.connection).get_columns("owners", schema="hisaab")
        }
        self.assertIn("auth_user_id", columns)
        first, second = seed(self.session), seed(self.session)
        subject = uuid4()
        first.owner.auth_user_id = subject
        self.session.flush()
        self.assertNotEqual(first.owner.id, subject)
        with self.session.begin_nested():
            second.owner.auth_user_id = subject
            with self.assertRaises(DBAPIError):
                self.session.flush()

    def test_verified_claims_map_to_one_owner_not_a_client_owner_argument(self):
        records = seed(self.session)
        subject = uuid4()
        self.connection.execute(
            text("UPDATE hisaab.owners SET auth_user_id=:subject WHERE id=:owner"),
            {"subject": subject, "owner": records.owner.id},
        )
        self.assertIsNone(
            self.connection.scalar(text("SELECT hisaab.current_owner_id()"))
        )
        self.connection.execute(
            text("SELECT set_config('request.jwt.claims', :claims, true)"),
            {"claims": json.dumps({"sub": str(subject), "role": "authenticated"})},
        )
        self.assertEqual(
            self.connection.scalar(text("SELECT hisaab.current_owner_id()")),
            records.owner.id,
        )
        self.connection.execute(
            text("SELECT set_config('request.jwt.claims', :claims, true)"),
            {"claims": json.dumps({"sub": str(uuid4()), "role": "authenticated"})},
        )
        self.assertIsNone(
            self.connection.scalar(text("SELECT hisaab.current_owner_id()"))
        )

    def test_all_five_tables_have_only_read_policies(self):
        policies = self.connection.execute(
            text(
                "SELECT tablename, cmd FROM pg_policies WHERE schemaname='hisaab' ORDER BY tablename"
            )
        ).all()
        self.assertEqual(
            policies,
            [
                (name, "SELECT")
                for name in ("cards", "entries", "imports", "owners", "statements")
            ],
        )
