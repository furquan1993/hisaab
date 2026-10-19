"""Card mutation validation, isolation and stale-write protection on disposable PG."""
import json
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.persistence_fixture import seed
from tests.postgres_fixture import PostgresTests


class CardManagementTests(PostgresTests):
    def setUp(self):
        super().setUp()
        self.rows = seed(self.session)
        self.owner = self.rows.owner.id
        self.subject = uuid4()
        self.rows.owner.auth_user_id = self.subject
        self.session.flush()
        self.claims(self.subject)

    def claims(self, subject, role="authenticated"):
        self.session.execute(text("SELECT set_config('request.jwt.claims',:claims,true)"), {
            "claims": json.dumps({"role": role, "sub": str(subject)})})

    def save(self, **overrides):
        args = dict(owner=self.owner, label="Travel card", bank="hdfc", digits="0042", id=None, version=0)
        args.update(overrides)
        return self.session.scalar(text("SELECT hisaab_api.save_card(:owner,:label,:bank,:digits,:id,:version)"), args)

    def rejects(self, code, **fields):
        with self.assertRaises(DBAPIError) as error, self.session.begin_nested():
            self.save(**fields)
        self.assertEqual(error.exception.orig.sqlstate, code)

    def test_create_edit_and_stale_save(self):
        card = self.save(label="  Travel card  ")
        self.assertEqual(card["label"], "Travel card")
        self.assertEqual(card["last_four"], "0042")
        self.assertEqual(card["version"], 1)
        self.assertFalse(card["has_statements"])
        changed = self.save(id=card["id"], version=1, bank="sbi", digits=None)
        self.assertEqual(changed["bank"], "sbi")
        self.assertIsNone(changed["last_four"])
        self.assertEqual(changed["version"], 2)
        self.rejects("PT409", id=card["id"], version=1)
        self.rejects("PT409", version=None)

    def test_used_card_can_be_renamed_but_bank_cannot_change(self):
        card = self.save(id=self.rows.card.id, version=1, label="Updated name", digits=None)
        self.assertTrue(card["has_statements"])
        self.assertEqual(self.session.scalar(text("SELECT card_label FROM hisaab_api.entries WHERE id=:id"), {"id": self.rows.entry.id}), "Updated name")
        self.rejects("PT409", id=self.rows.card.id, version=2, bank="sbi")

    def test_validation(self):
        for fields in [dict(label=" "), dict(label="a" * 121), dict(label=None),
                       dict(bank="other"), dict(bank=None), dict(digits="123"),
                       dict(digits="１２３４"), dict(digits="12345"), dict(digits="12a4")]:
            with self.subTest(fields=fields):
                self.rejects("PT422", **fields)

    def test_owner_scope_and_no_direct_table_writes(self):
        card = self.save()
        self.claims(uuid4())
        self.rejects("42501", id=card["id"], version=1)
        self.claims(self.subject)
        self.rejects("PT409", owner=uuid4())
        self.rejects("PT404", id=uuid4(), version=1)

    def test_browser_role_permissions(self):
        if not self.session.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='authenticated')")):
            self.skipTest("Authenticated role requires the disposable Supabase stack")
        card = self.save()
        self.session.execute(text("SET LOCAL ROLE authenticated"))
        self.assertIn(card["id"], [str(row) for row in self.session.scalars(text("SELECT id FROM hisaab_api.cards"))])
        with self.assertRaises(DBAPIError), self.session.begin_nested():
            self.session.execute(text("UPDATE hisaab.cards SET label='untrusted'"))
        self.claims(uuid4())
        self.assertEqual(self.session.execute(text("SELECT * FROM hisaab_api.cards")).all(), [])
        self.session.execute(text("RESET ROLE"))
        self.assertFalse(self.session.scalar(text("SELECT has_function_privilege('anon','hisaab_api.save_card(uuid,text,text,text,uuid,integer)','EXECUTE')")))
