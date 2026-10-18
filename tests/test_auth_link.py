"""Operator-only Auth subject binding; no application signup/claim endpoint."""

from uuid import uuid4

from sqlalchemy import text

from core.persistence.models import Owner
from core.persistence.store import StoreError, link_owner_auth, unlink_owner_auth
from tests.postgres_fixture import PostgresTests


class AuthLinkTests(PostgresTests):
    def setUp(self):
        super().setUp()
        # Synthetic auth directory only within this transaction/disposable database.
        self.connection.execute(text("CREATE SCHEMA auth"))
        self.connection.execute(text("CREATE TABLE auth.users (id uuid PRIMARY KEY)"))
        self.subject = uuid4()
        self.connection.execute(
            text("INSERT INTO auth.users VALUES (:id)"), {"id": self.subject}
        )
        self.owner = Owner(display_name="Synthetic owner")
        self.session.add(self.owner)
        self.session.flush()

    def test_link_is_verified_idempotent_and_explicitly_revocable(self):
        owner_id = self.owner.id
        link_owner_auth(self.connection, owner_id, self.subject)
        link_owner_auth(self.connection, owner_id, self.subject)
        self.session.expire_all()
        self.assertEqual(self.session.get(Owner, owner_id).auth_user_id, self.subject)
        unlink_owner_auth(self.connection, owner_id)
        self.session.expire_all()
        self.assertIsNone(self.session.get(Owner, owner_id).auth_user_id)

    def test_unknown_auth_subject_and_implicit_replacement_are_rejected(self):
        with self.assertRaises(StoreError):
            link_owner_auth(self.connection, self.owner.id, uuid4())
        link_owner_auth(self.connection, self.owner.id, self.subject)
        second = uuid4()
        self.connection.execute(
            text("INSERT INTO auth.users VALUES (:id)"), {"id": second}
        )
        with self.assertRaises(StoreError):
            link_owner_auth(self.connection, self.owner.id, second)
