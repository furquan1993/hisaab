from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError

from core.persistence.models import Card, Entry, ImportRecord, Owner, Statement
from core.persistence.session import transaction
from tests.decision_fixture import remove_decisions
from tests.persistence_fixture import new_entry, seed
from tests.postgres_fixture import PostgresTests, test_engine


def remove_synthetic_owner(engine, owner_id):
    with engine.begin() as connection:
        remove_decisions(connection, [owner_id])
        connection.execute(
            update(Statement)
            .where(Statement.owner_id == owner_id)
            .values(active_import_id=None)
        )
        for model in (Entry, ImportRecord, Statement, Card):
            connection.execute(delete(model).where(model.owner_id == owner_id))
        connection.execute(delete(Owner).where(Owner.id == owner_id))


class TransactionPostgresTests(PostgresTests):
    def test_commit_survives_new_engine_and_session(self):
        owner_id = None
        try:
            with transaction(self.engine) as session:
                rows = seed(session)
                owner_id, entry_id = rows.owner.id, rows.entry.id
            restarted = test_engine()
            try:
                with transaction(restarted) as session:
                    saved = session.get(Entry, entry_id)
                    self.assertEqual(saved.id, entry_id)
                    self.assertEqual(saved.amount, rows.entry.amount)
                    self.assertIsNotNone(session.get(Owner, owner_id))
            finally:
                restarted.dispose()
        finally:
            if owner_id is not None:
                remove_synthetic_owner(self.engine, owner_id)

    def test_late_integrity_failure_rolls_back_every_entity(self):
        with self.assertRaises(IntegrityError):
            with transaction(self.engine) as session:
                rows = seed(session)
                owner_id = rows.owner.id
                session.add(
                    new_entry(rows.imported)
                )  # Duplicate sequence fails on commit.
        with transaction(self.engine) as session:
            self.assertIsNone(session.get(Owner, owner_id))
            for model in (Card, Statement, ImportRecord, Entry):
                self.assertEqual(
                    session.scalars(
                        select(model).where(model.owner_id == owner_id)
                    ).all(),
                    [],
                )

    def test_runtime_exception_also_rolls_back(self):
        with self.assertRaisesRegex(RuntimeError, "synthetic failure"):
            with transaction(self.engine) as session:
                rows = seed(session)
                owner_id = rows.owner.id
                raise RuntimeError("synthetic failure")
        with transaction(self.engine) as session:
            self.assertIsNone(session.get(Owner, owner_id))
