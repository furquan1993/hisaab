"""Reasoned review through real synthetic Auth; imported facts remain immutable."""

from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from core.persistence.models import Entry, ImportRecord, Statement
from tests.decision_fixture import remove_decisions
from tests.persistence_fixture import PDF, new_entry, new_import
from tests.supabase_fixture import SupabaseTests


class ReviewHTTPTests(SupabaseTests):
    def set_entry(self, **values):
        with self.engine.begin() as c:
            c.execute(
                update(Entry)
                .where(Entry.id == self.records[0].entry.id)
                .values(**values)
            )

    def setUp(self):
        with self.engine.begin() as c:
            remove_decisions(c, self.owners)
            c.execute(
                update(Statement)
                .where(Statement.id == self.records[0].statement.id)
                .values(active_import_id=self.records[0].imported.id)
            )
            c.execute(
                delete(Entry).where(
                    Entry.owner_id == self.owners[0],
                    Entry.import_id != self.records[0].imported.id,
                )
            )
            c.execute(
                delete(ImportRecord).where(
                    ImportRecord.owner_id == self.owners[0],
                    ImportRecord.id != self.records[0].imported.id,
                )
            )
            c.execute(
                update(ImportRecord)
                .where(ImportRecord.id == self.records[0].imported.id)
                .values(issues=[{"code": "synthetic_coverage", "page": 1}])
            )
        from datetime import date

        self.set_entry(
            entry_type="purchase",
            direction="debit",
            transaction_date=date(2026, 1, 1),
            issues=[],
        )

    def review(
        self,
        overrides,
        *,
        version=0,
        reason="Synthetic verified correction",
        acknowledged=None,
        index=0,
    ):
        return self.call(
            "/rpc/review_entry",
            self.tokens[index],
            method="POST",
            data={
                "p_entry_id": str(self.records[0].entry.id),
                "p_expected_version": version,
                "p_overrides": overrides,
                "p_acknowledged": acknowledged or [],
                "p_reason": reason,
            },
        )

    def row(self):
        code, rows = self.call(
            "/entries?id=eq." + str(self.records[0].entry.id), self.tokens[0]
        )
        self.assertEqual(code, 200)
        return rows[0]

    def test_type_correction_does_not_acknowledge_unrelated_coverage(self):
        self.set_entry(
            entry_type="unknown",
            direction="credit",
            issues=[{"code": "entry_type_unknown", "page": 1}],
        )
        code, _ = self.review({"entry_type": "refund"})
        self.assertEqual(code, 200)
        row = self.row()
        self.assertEqual(row["entry_type"], "unknown")
        self.assertEqual(row["effective_entry_type"], "refund")
        self.assertTrue(row["needs_review"])
        self.assertEqual(row["unresolved_entry_issues"], [])
        self.assertEqual(len(row["unresolved_import_issues"]), 1)
        code, _ = self.call(
            "/rpc/review_import",
            self.tokens[0],
            method="POST",
            data={
                "p_import_id": str(self.records[0].imported.id),
                "p_expected_version": 0,
                "p_acknowledged": ["synthetic_coverage:1"],
                "p_reason": "Synthetic manually inspected coverage page",
            },
        )
        self.assertEqual(code, 200)
        self.assertFalse(self.row()["needs_review"])
        self.assertEqual(self.row()["entry_issues"][0]["code"], "entry_type_unknown")

    def test_missing_date_correction_survives_reload_without_rewriting_source(self):
        self.set_entry(
            transaction_date=None,
            issues=[{"code": "date_missing_or_invalid", "page": 1}],
        )
        code, saved = self.review({"transaction_date": "2026-01-12"})
        self.assertEqual(code, 200)
        self.assertEqual(saved["version"], 1)
        row = self.row()
        self.assertIsNone(row["transaction_date"])
        self.assertEqual(row["effective_transaction_date"], "2026-01-12")
        self.assertEqual(row["unresolved_entry_issues"], [])
        code, _ = self.review({"transaction_date": "2026-01-13"}, version=0)
        self.assertEqual(code, 409)
        self.assertEqual(self.row()["effective_transaction_date"], "2026-01-12")

    def test_invalid_or_unreasoned_values_and_critical_acknowledgements_are_rejected(
        self,
    ):
        for overrides in (
            {"amount": 0.1},
            {"amount": "1.001"},
            {"transaction_date": "2026-02-31"},
            {"entry_type": "invented"},
            {"currency": "RS"},
            {"owner_id": str(self.owners[1])},
        ):
            with self.subTest(fields=list(overrides)):
                code, _ = self.review(overrides)
                self.assertEqual(code, 422)
        code, _ = self.review(
            {"description": "Synthetic corrected description"}, reason=" "
        )
        self.assertEqual(code, 422)
        self.set_entry(issues=[{"code": "date_missing_or_invalid", "page": 1}])
        code, _ = self.review({}, acknowledged=["date_missing_or_invalid:1"])
        self.assertEqual(code, 422)
        _, events = self.call(
            "/decision_history?entry_id=eq." + str(self.records[0].entry.id),
            self.tokens[0],
        )
        self.assertEqual(events, [])

    def accept_clone(self, **changes):
        original = self.records[0]
        with Session(self.engine) as session:
            source = session.get(ImportRecord, original.imported.id)
            old = session.get(Entry, original.entry.id)
            candidate = new_import(
                original,
                payload=PDF,
                pdf_bytes=None,
                source_import_id=source.id,
                source_filename=source.source_filename,
                issues=source.issues,
                parser_version="synthetic-review-2",
            )
            session.add(candidate)
            session.flush()
            values = {
                column.name: getattr(old, column.name)
                for column in Entry.__table__.columns
                if column.name not in ("id", "import_id")
            }
            values.update(changes)
            new = new_entry(candidate, **values)
            session.add(new)
            session.flush()
            candidate_id, new_id = str(candidate.id), str(new.id)
            session.commit()
        code, revision = self.call(
            "/rpc/prepare_revision",
            self.tokens[0],
            method="POST",
            data={"p_candidate_import_id": candidate_id},
        )
        self.assertEqual(code, 200)
        mapping = (
            []
            if revision["plan"]["matches"]
            else [{"new_entry_id": new_id, "previous_entry_id": str(original.entry.id)}]
        )
        code, _ = self.call(
            "/rpc/accept_revision",
            self.tokens[0],
            method="POST",
            data={
                "p_revision_id": revision["id"],
                "p_mapping": mapping,
                "p_removed": [],
                "p_reason": "Synthetic explicitly reviewed identity",
            },
        )
        self.assertEqual(code, 200)
        _, rows = self.call("/entries?id=eq." + new_id, self.tokens[0])
        return new_id, rows[0]

    def test_unchanged_reparse_retains_corrections_and_coverage_acknowledgements(self):
        code, _ = self.review({"description": "Synthetic retained correction"})
        self.assertEqual(code, 200)
        code, _ = self.call(
            "/rpc/review_import",
            self.tokens[0],
            method="POST",
            data={
                "p_import_id": str(self.records[0].imported.id),
                "p_expected_version": 0,
                "p_acknowledged": ["synthetic_coverage:1"],
                "p_reason": "Synthetic checked page coverage",
            },
        )
        self.assertEqual(code, 200)
        _, row = self.accept_clone()
        self.assertEqual(row["effective_description"], "Synthetic retained correction")
        self.assertFalse(row["review_stale"])
        self.assertFalse(row["import_review_stale"])
        self.assertFalse(row["needs_review"])

    def test_changed_evidence_preserves_but_does_not_apply_stale_corrections(self):
        code, _ = self.review({"description": "Synthetic old correction"})
        self.assertEqual(code, 200)
        new_id, row = self.accept_clone(description="SYNTHETIC NEW PARSER DESCRIPTION")
        self.assertTrue(row["review_stale"])
        self.assertEqual(
            row["effective_description"], "SYNTHETIC NEW PARSER DESCRIPTION"
        )
        self.assertEqual(row["overrides"]["description"], "Synthetic old correction")
        payload = {
            "p_entry_id": new_id,
            "p_expected_version": 1,
            "p_overrides": {"description": "Synthetic reviewed new source"},
            "p_acknowledged": [],
            "p_reason": "Synthetic checked revised evidence",
        }
        code, _ = self.call(
            "/rpc/review_entry", self.tokens[0], method="POST", data=payload
        )
        self.assertEqual(code, 409)
        code, _ = self.call(
            "/rpc/review_entry",
            self.tokens[0],
            method="POST",
            data={**payload, "p_confirm_source": True},
        )
        self.assertEqual(code, 200)

    def test_amounts_remain_decimal_strings_and_originals_do_not_change(self):
        code, _ = self.review({"amount": "0.10"})
        self.assertEqual(code, 200)
        self.assertEqual(self.row()["amount"], "123.45")
        self.assertEqual(self.row()["effective_amount"], "0.10")
        code, _ = self.review({"transaction_date": "2026-01-02"}, version=1)
        self.assertEqual(code, 200)
        self.assertEqual(self.row()["effective_amount"], "0.10")

    def test_statement_date_review_is_separate_versioned_and_immutable(self):
        payload = {
            "p_import_id": str(self.records[0].imported.id),
            "p_expected_version": 0,
            "p_acknowledged": ["synthetic_coverage:1"],
            "p_reason": "Synthetic verified corrected bill date",
            "p_statement_date": "2026-02-01",
        }
        code, _ = self.call(
            "/rpc/review_import", self.tokens[0], method="POST", data=payload
        )
        self.assertEqual(code, 200)
        row = self.row()
        self.assertEqual(row["statement_date"], "2026-01-31")
        self.assertEqual(row["effective_statement_date"], "2026-02-01")
        code, _ = self.call(
            "/rpc/review_import", self.tokens[0], method="POST", data=payload
        )
        self.assertEqual(code, 409)
        _, history = self.call("/import_review_history", self.tokens[0])
        self.assertEqual(len(history), 1)
        _, foreign = self.call("/import_review_history", self.tokens[1])
        self.assertEqual(foreign, [])

    def test_review_is_owner_scoped_and_does_not_accept_unmapped_users(self):
        for index in (1, 2):
            code, _ = self.review(
                {"description": "Synthetic forbidden correction"}, index=index
            )
            self.assertIn(code, (403, 404))
