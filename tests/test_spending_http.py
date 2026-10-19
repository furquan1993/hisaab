"""Spending groups through real disposable Auth and owner-scoped REST."""

from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.persistence_fixture import new_entry, new_import
from tests.supabase_fixture import SupabaseTests


class SpendingHTTPTests(SupabaseTests):
    def setUp(self):
        with self.engine.begin() as connection:
            for table in ("spending_events", "spending_assignments", "spending_groups"):
                connection.execute(text(f"DELETE FROM hisaab.{table} WHERE owner_id=ANY(:owners)"), {"owners": self.owners})

    def group(self, name="Goa trip", index=0, **changes):
        args = {"p_name": name, "p_expected_owner": str(self.owners[min(index, 1)])}
        args.update(changes)
        return self.call("/rpc/save_spending_group", self.tokens[index], method="POST", data=args)

    def assign(self, group, version=0, index=0, **changes):
        args = {"p_group_id": group, "p_expected_owner": str(self.owners[min(index, 1)]), "p_entries": [{"id": str(self.records[0].entry.id), "version": version}]}
        args.update(changes)
        return self.call("/rpc/assign_spending_group", self.tokens[index], method="POST", data=args)

    def test_group_membership_persists_and_leaves_financial_decisions_unchanged(self):
        code, group = self.group()
        self.assertEqual(code, 200)
        _, before = self.call("/entries?id=eq." + str(self.records[0].entry.id), self.tokens[0])
        code, saved = self.assign(group["id"])
        self.assertEqual(code, 200, saved)
        self.assertEqual(saved[0]["version"], 1)
        _, rows = self.call("/spending_entries?id=eq." + str(self.records[0].entry.id), self.tokens[0])
        self.assertEqual(rows[0]["group_name"], "Goa trip")
        self.assertEqual(rows[0]["group_version"], 1)
        self.assertEqual({key: rows[0][key] for key in rows[0] if key in before[0]}, {key: before[0][key] for key in rows[0] if key in before[0]})
        self.assertEqual(self.assign(group["id"])[0], 409)
        self.assertEqual(self.assign(None, 1)[0], 200)
        self.assertEqual(self.assign(group["id"], 1)[0], 409)
        self.assertEqual(self.assign(group["id"], 2)[0], 200)
        with self.engine.connect() as connection:
            self.assertEqual(connection.scalar(text("SELECT count(*) FROM hisaab.spending_events WHERE owner_id=:owner"), {"owner": self.owners[0]}), 3)

    def test_owner_isolation_and_direct_mutations_are_denied(self):
        _, group = self.group()
        self.assertEqual(self.call("/spending_groups", self.tokens[1]), (200, []))
        self.assertEqual(self.assign(group["id"], index=1)[0], 422)
        self.assertEqual(self.assign(None, index=1)[0], 404)
        self.assertEqual(self.assign(group["id"], p_expected_owner=str(self.owners[1]))[0], 403)
        self.assertEqual(self.group(index=2)[0], 403)
        self.assertGreaterEqual(self.call("/spending_entries")[0], 400)
        self.assertGreaterEqual(self.call("/spending_groups", self.tokens[0], method="POST", data={"name": "Bypass"})[0], 400)
        self.assertGreaterEqual(self.call("/rpc/assign_spending_group", method="POST", data={"p_group_id": group["id"], "p_entries": [], "p_expected_owner": str(self.owners[0])})[0], 400)

    def test_batch_is_atomic_and_input_is_validated(self):
        _, group = self.group()
        entry = {"id": str(self.records[0].entry.id), "version": 0}
        self.assertEqual(self.assign(group["id"], p_entries=[entry, {"id": str(uuid4()), "version": 0}])[0], 404)
        _, rows = self.call("/spending_entries?id=eq." + entry["id"], self.tokens[0])
        self.assertIsNone(rows[0]["group_id"])
        for entries in ([], [entry] * 51, [entry, entry], [{"id": entry["id"], "version": -1}], [None], [{"id": "invalid", "version": 0}], [{"id": entry["id"], "version": None}]):
            with self.subTest(entries=entries[:2]):
                self.assertEqual(self.assign(group["id"], p_entries=entries)[0], 422)

    def test_names_archival_and_versions(self):
        _, group = self.group()
        self.assertEqual(self.group("goa TRIP")[0], 409)
        self.assertEqual(self.group("\n")[0], 422)
        self.assertEqual(self.assign(group["id"])[0], 200)
        code, archived = self.group("Goa holiday", p_id=group["id"], p_expected_version=1, p_archived=True)
        self.assertEqual(code, 200)
        self.assertEqual(archived["version"], 2)
        _, rows = self.call("/spending_entries?id=eq." + str(self.records[0].entry.id), self.tokens[0])
        self.assertEqual(rows[0]["group_name"], "Goa holiday")
        self.assertEqual(self.assign(group["id"], 1)[0], 422)
        self.assertEqual(self.group(p_id=group["id"], p_expected_version=1)[0], 409)
        self.assertEqual(self.assign(None, 1)[0], 200)

    def test_repayments_are_not_grouped(self):
        _, group = self.group()
        with Session(self.engine) as session, session.begin():
            payment = new_entry(self.records[0].imported, sequence=100, direction="credit", entry_type="payment")
            session.add(payment)
            session.flush()
            payment_id = str(payment.id)
        self.assertEqual(self.assign(group["id"], p_entries=[{"id": payment_id, "version": 0}])[0], 422)

    def test_z_group_follows_logical_identity_after_source_replacement(self):
        _, group = self.group()
        self.assertEqual(self.assign(group["id"])[0], 200)
        original = self.records[0]
        with Session(self.engine) as session, session.begin():
            candidate = new_import(original, payload=original.imported.pdf_bytes, pdf_bytes=None, file_sha256=original.imported.file_sha256, source_import_id=original.imported.id, parser_version="synthetic-spending-2")
            session.add(candidate)
            session.flush()
            revised = new_entry(candidate)
            session.add(revised)
            session.flush()
            candidate_id, new_id = str(candidate.id), str(revised.id)
        code, plan = self.call("/rpc/prepare_revision", self.tokens[0], method="POST", data={"p_candidate_import_id": candidate_id})
        self.assertEqual(code, 200)
        code, result = self.call("/rpc/accept_revision", self.tokens[0], method="POST", data={"p_revision_id": plan["id"], "p_mapping": [], "p_removed": [str(payment["id"]) for payment in self.call("/spending_entries?effective_entry_type=eq.payment", self.tokens[0])[1]], "p_reason": "Synthetic spending identity check"})
        self.assertEqual(code, 200, result)
        _, rows = self.call("/spending_entries?id=eq."+new_id, self.tokens[0])
        self.assertEqual(rows[0]["group_id"], group["id"])
        self.assertEqual(rows[0]["group_version"], 1)
        self.assertEqual(self.assign(None, 1)[0], 409)
