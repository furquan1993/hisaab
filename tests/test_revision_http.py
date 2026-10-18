"""Actual Auth/API revision acceptance retains decisions without exposing another owner."""

from sqlalchemy.orm import Session

from core.persistence.models import Category, EntryDecision
from tests.persistence_fixture import PDF, new_entry, new_import
from tests.supabase_fixture import SupabaseTests


class RevisionHTTPTests(SupabaseTests):
    def test_reviewed_source_switch_is_atomic_owner_scoped_and_keeps_assignments(self):
        original = self.records[0]
        with Session(self.engine) as session:
            category = Category(
                owner_id=self.owners[0], name="Synthetic revision category"
            )
            session.add(category)
            session.flush()
            session.add(
                EntryDecision(
                    owner_id=self.owners[0],
                    entry_id=original.entry.id,
                    category_id=category.id,
                )
            )
            candidate = new_import(
                original,
                payload=PDF,
                pdf_bytes=None,
                source_import_id=original.imported.id,
                source_filename=original.imported.source_filename,
                parser_version="synthetic-2",
            )
            session.add(candidate)
            session.flush()
            revised_entry = new_entry(candidate)
            session.add(revised_entry)
            session.flush()
            candidate_id, new_id = str(candidate.id), str(revised_entry.id)
            session.commit()
        code, plan = self.call(
            "/rpc/prepare_revision",
            self.tokens[0],
            method="POST",
            data={"p_candidate_import_id": candidate_id},
        )
        self.assertEqual(code, 200)
        self.assertEqual(len(plan["plan"]["matches"]), 1)
        code, _ = self.call(
            "/rpc/prepare_revision",
            self.tokens[1],
            method="POST",
            data={"p_candidate_import_id": candidate_id},
        )
        self.assertEqual(code, 404)
        payload = {
            "p_revision_id": plan["id"],
            "p_mapping": [],
            "p_removed": [],
            "p_reason": "Synthetic reviewed replacement",
        }
        code, _ = self.call(
            "/rpc/accept_revision", self.tokens[1], method="POST", data=payload
        )
        self.assertEqual(code, 404)
        code, _ = self.call("/rpc/accept_revision", method="POST", data=payload)
        self.assertGreaterEqual(code, 400)
        code, accepted = self.call(
            "/rpc/accept_revision", self.tokens[0], method="POST", data=payload
        )
        self.assertEqual(code, 200)
        self.assertEqual(accepted["status"], "accepted")
        _, rows = self.call("/entries?id=eq." + new_id, self.tokens[0])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["logical_entry_id"], str(original.entry.id))
        self.assertEqual(rows[0]["category_name"], "Synthetic revision category")
        self.assertEqual(rows[0]["decision_version"], 1)
        _, old = self.call("/entries?id=eq." + str(original.entry.id), self.tokens[0])
        self.assertEqual(old, [])
        _, evidence = self.call(
            "/entry_evidence?id=eq." + str(original.entry.id), self.tokens[0]
        )
        self.assertEqual(len(evidence), 1)
        _, foreign = self.call("/revision_entries?id=eq." + new_id, self.tokens[1])
        self.assertEqual(foreign, [])
        code, pdf = self.call(
            "/rpc/original_pdf",
            self.tokens[0],
            method="POST",
            data={"p_import_id": candidate_id},
        )
        self.assertEqual(code, 200)
        self.assertEqual(pdf["sha256"], original.imported.file_sha256)
        code, _ = self.call(
            "/rpc/save_entry_decision",
            self.tokens[0],
            method="POST",
            data={
                "p_entry_id": str(original.entry.id),
                "p_expected_version": 1,
                "p_patch": {"category_id": None},
            },
        )
        self.assertEqual(code, 409)
