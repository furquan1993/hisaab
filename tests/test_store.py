from uuid import uuid4

from core.persistence.store import (
    StoreError,
    list_cards,
    list_owners,
    register_card,
    register_owner,
)
from tests.postgres_fixture import PostgresTests
from tests.test_transactions_postgres import remove_synthetic_owner


class StoreTests(PostgresTests):
    def owner(self):
        owner_id = register_owner(self.engine, "Synthetic owner")
        self.addCleanup(remove_synthetic_owner, self.engine, owner_id)
        return owner_id

    def test_owner_and_card_survive_new_calls(self):
        owner = self.owner()
        card = register_card(
            self.engine, owner, bank="sbi", label="Synthetic card", last_four="1234"
        )
        self.assertIn(str(owner), [row["id"] for row in list_owners(self.engine)])
        self.assertEqual(list_cards(self.engine, owner)[0]["id"], str(card))

    def test_cards_are_owner_scoped(self):
        first, second = self.owner(), self.owner()
        register_card(self.engine, first, bank="hdfc", label="Synthetic")
        self.assertEqual(list_cards(self.engine, second), [])

    def test_unknown_owner_is_rejected(self):
        with self.assertRaises(StoreError):
            register_card(self.engine, uuid4(), bank="hdfc", label="Synthetic")

    def test_invalid_fields_are_not_saved_or_echoed(self):
        owner = self.owner()
        for options in (
            dict(bank="invented", label="synthetic-secret"),
            dict(bank="hdfc", label=""),
            dict(bank="hdfc", label="Synthetic", last_four="12345"),
        ):
            with self.assertRaises(StoreError) as error:
                register_card(self.engine, owner, **options)
            self.assertNotIn("synthetic-secret", str(error.exception))
        self.assertEqual(list_cards(self.engine, owner), [])
