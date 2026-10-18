"""No mocked JWTs: GoTrue sessions exercised over actual PostgREST HTTP."""

import base64
import json
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import delete, text
from sqlalchemy.orm import Session

from core.persistence.models import Entry, ImportRecord
from core.persistence.store import link_owner_auth, unlink_owner_auth
from tests.persistence_fixture import new_entry, new_import
from tests.supabase_fixture import SupabaseTests, request


class BrowserHTTPTests(SupabaseTests):
    def test_operator_link_and_revoke_apply_to_existing_jwts(self):
        owner = self.records[0].owner.id
        subject = UUID(self.users[0])
        try:
            unlink_owner_auth(self.engine, owner)
            self.assertEqual(self.call("/entries", self.tokens[0]), (200, []))
        finally:
            link_owner_auth(self.engine, owner, subject)
        self.assertEqual(self.call("/profile", self.tokens[0])[1][0]["id"], str(owner))

    def test_public_signup_stays_disabled_while_password_login_works(self):
        code, _ = request(
            self.api + "/auth/v1/signup",
            method="POST",
            key=self.anon,
            schema=False,
            data={
                "email": f"not-created-{uuid4().hex}@example.invalid",
                "password": "Synthetic-test-only-password-42",
            },
        )
        self.assertGreaterEqual(code, 400)

    def test_date_modes_candidates_nulls_and_large_exact_money(self):
        records = self.records[0]
        extra_ids = []
        candidate_id = None
        try:
            with Session(self.engine) as session, session.begin():
                outside = new_entry(
                    records.imported, sequence=2, transaction_date=date(2025, 12, 29)
                )
                undated = new_entry(records.imported, sequence=3, transaction_date=None)
                candidate = new_import(records)
                session.add_all([outside, undated, candidate])
                session.flush()
                candidate_id = candidate.id
                copied = new_entry(candidate, amount=Decimal("999999999999999999.99"))
                session.add(copied)
                session.flush()
                extra_ids = [outside.id, undated.id, copied.id]
            code, rows = self.call(
                "/entries?is_selected=eq.true&statement_date=gte.2026-01-01&statement_date=lte.2026-01-31",
                self.tokens[0],
            )
            self.assertEqual(code, 200)
            self.assertEqual(len(rows), 3)
            code, rows = self.call(
                "/entries?is_selected=eq.true&transaction_date=gte.2026-01-01&transaction_date=lte.2026-01-31",
                self.tokens[0],
            )
            self.assertEqual(len(rows), 1)
            code, rows = self.call("/entries?is_selected=eq.false", self.tokens[0])
            self.assertEqual(rows[0]["amount"], "999999999999999999.99")
            code, rows = self.call("/entries?needs_review=eq.true", self.tokens[0])
            self.assertIn(str(extra_ids[1]), [row["id"] for row in rows])
        finally:
            with self.engine.begin() as connection:
                if extra_ids:
                    connection.execute(delete(Entry).where(Entry.id.in_(extra_ids)))
                if candidate_id:
                    connection.execute(
                        delete(ImportRecord).where(ImportRecord.id == candidate_id)
                    )

    def test_each_authenticated_user_sees_only_their_own_joined_rows(self):
        for index in range(2):
            code, rows = self.call("/entries", self.tokens[index])
            self.assertEqual(code, 200)
            self.assertEqual(
                [r["id"] for r in rows], [str(self.records[index].entry.id)]
            )
            self.assertEqual(rows[0]["amount"], "123.45")
            code, profile = self.call("/profile", self.tokens[index])
            self.assertEqual([p["id"] for p in profile], [str(self.owners[index])])

    def test_anonymous_unmapped_and_forged_claims_have_no_access(self):
        code, _ = self.call("/entries")
        self.assertIn(code, (401, 403))
        code, rows = self.call("/entries", self.tokens[2])
        self.assertEqual((code, rows), (200, []))
        header, payload, signature = self.tokens[0].split(".")
        claims = json.loads(
            base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
        )
        claims["sub"] = self.users[1]
        forged = (
            base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
        )
        code, _ = self.call("/entries", ".".join([header, forged, signature]))
        self.assertEqual(code, 401)

    def test_guessed_ids_and_original_download_cannot_cross_owners(self):
        foreign = self.records[1]
        code, rows = self.call(
            "/entries?id=eq." + str(foreign.entry.id), self.tokens[0]
        )
        self.assertEqual((code, rows), (200, []))
        code, rows = self.call(
            "/entry_evidence?id=eq." + str(foreign.entry.id), self.tokens[0]
        )
        self.assertEqual((code, rows), (200, []))
        code, original = self.call(
            "/rpc/original_pdf",
            self.tokens[0],
            method="POST",
            data={"p_import_id": str(foreign.imported.id)},
        )
        self.assertEqual((code, original), (200, None))
        code, original = self.call(
            "/rpc/original_pdf",
            self.tokens[0],
            method="POST",
            data={"p_import_id": str(self.records[0].imported.id)},
        )
        self.assertEqual(code, 200)
        self.assertEqual(original["sha256"], self.records[0].imported.file_sha256)

    def test_browser_cannot_edit_facts_claim_owners_or_expose_private_schema(self):
        for path, method, data in (
            (
                "/entries?id=eq." + str(self.records[0].entry.id),
                "PATCH",
                {"description": "forged"},
            ),
            (
                "/profile",
                "POST",
                {"id": str(self.owners[1]), "display_name": "claimed"},
            ),
            ("/entry_evidence?id=eq." + str(self.records[0].entry.id), "DELETE", None),
        ):
            code, _ = self.call(path, self.tokens[0], method=method, data=data)
            self.assertGreaterEqual(code, 400)
        code, _ = self.call("/imports?select=pdf_bytes", self.tokens[0])
        self.assertGreaterEqual(code, 400)

    def test_application_migration_ledger_is_not_a_browser_resource(self):
        with self.engine.connect() as connection:
            for role in ("anon", "authenticated"):
                for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"):
                    self.assertFalse(
                        connection.scalar(
                            text(
                                "SELECT has_table_privilege(:role, 'public.hisaab_schema_version', :privilege)"
                            ),
                            {"role": role, "privilege": privilege},
                        )
                    )

    def test_direct_base_grants_cannot_modify_or_read_pdf_or_identity(self):
        with self.engine.connect() as connection:
            for table in ("owners", "cards", "statements", "imports", "entries"):
                for privilege in ("INSERT", "UPDATE", "DELETE", "TRUNCATE"):
                    self.assertFalse(
                        connection.scalar(
                            text(
                                "SELECT has_table_privilege('authenticated', :table, :privilege)"
                            ),
                            {"table": "hisaab." + table, "privilege": privilege},
                        )
                    )
            for table, column in (("imports", "pdf_bytes"), ("owners", "auth_user_id")):
                self.assertFalse(
                    connection.scalar(
                        text(
                            "SELECT has_column_privilege('authenticated', :table, :column, 'SELECT')"
                        ),
                        {"table": "hisaab." + table, "column": column},
                    )
                )
