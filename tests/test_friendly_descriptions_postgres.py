"""Migration retention and view contracts in disposable PostgreSQL."""
from alembic import command
from alembic.util import CommandError
from sqlalchemy import inspect

from core.persistence.models import EntryDescription
from tests.persistence_fixture import seed
from tests.postgres_fixture import PostgresTests, migration_config


class FriendlyDescriptionPostgresTests(PostgresTests):
    def test_downgrade_refuses_to_discard_description_history_even_when_cleared(self):
        records = seed(self.session)
        self.session.add(EntryDescription(owner_id=records.owner.id,
            entry_id=records.entry.id, version=1, description=None))
        self.session.flush()
        with self.assertRaises(CommandError), self.connection.begin_nested():
            command.downgrade(migration_config(self.connection), '0015_spending_groups')
        self.assertTrue(inspect(self.connection).has_table('entry_descriptions', schema='hisaab'))

    def test_all_transaction_views_expose_friendly_description(self):
        for view in ('entries', 'funding_entries', 'spending_entries'):
            self.assertIn('friendly_description', {column['name'] for column in inspect(self.connection).get_columns(view, schema='hisaab_api')})
