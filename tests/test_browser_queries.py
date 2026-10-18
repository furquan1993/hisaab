"""Exact read-model contract in disposable PostgreSQL."""

from sqlalchemy import inspect, text

from tests.persistence_fixture import seed
from tests.postgres_fixture import PostgresTests


class BrowserQueryTests(PostgresTests):
    def test_list_strings_money_and_keeps_pdf_out(self):
        records = seed(self.session)
        row = (
            self.connection.execute(
                text("SELECT * FROM hisaab_api.entries WHERE id=:id"),
                {"id": records.entry.id},
            )
            .mappings()
            .one()
        )
        self.assertEqual(row["amount"], "123.45")
        self.assertIs(row["is_selected"], True)
        self.assertNotIn("pdf_bytes", row)
        self.assertNotIn("source_raw_text", row)
        evidence = (
            self.connection.execute(
                text("SELECT * FROM hisaab_api.entry_evidence WHERE id=:id"),
                {"id": records.entry.id},
            )
            .mappings()
            .one()
        )
        self.assertEqual(evidence["source_raw_text"], records.entry.source_raw_text)

    def test_invoker_views_and_no_implicit_pdf_columns(self):
        options = self.connection.execute(
            text(
                "SELECT relname, reloptions FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname='hisaab_api' AND c.relkind='v'"
            )
        ).all()
        self.assertTrue(options)
        for name, flags in options:
            self.assertIn("security_invoker=true", flags)
        columns = inspect(self.connection).get_columns("entries", schema="hisaab_api")
        self.assertNotIn("pdf_bytes", [c["name"] for c in columns])
