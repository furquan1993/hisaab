"""Synthetic revisions must never replace published evidence or move decisions silently."""

from dataclasses import replace
from unittest.mock import patch

from sqlalchemy import func, select, text

from core.imports import import_pdf
from core.parser import parse_pdf_bytes
from core.persistence.import_records import read_original
from core.persistence.models import (
    Category,
    Entry,
    EntryDecision,
    ImportRecord,
    Statement,
)
from core.persistence.store import StoreError, store_session
from core.revisions import accept_revision, reparse_import
from tests.import_fixture import ImportTestsBase


class RevisionTests(ImportTestsBase):
    def load(self):
        return import_pdf(self.engine, self.owner, self.card, self.path)

    def selected(self, statement):
        with self.engine.connect() as c:
            return c.scalar(
                select(Statement.active_import_id).where(Statement.id == statement)
            )

    def decide(self, import_id, sequence=1):
        with store_session(self.engine) as session:
            entry = session.scalars(
                select(Entry)
                .where(Entry.import_id == import_id, Entry.sequence == sequence)
                .order_by(Entry.sequence)
            ).first()
            category = Category(owner_id=self.owner, name="Synthetic retained category")
            session.add(category)
            session.flush()
            decision = EntryDecision(
                owner_id=self.owner, entry_id=entry.id, category_id=category.id
            )
            session.add(decision)
            session.flush()
            return entry.id, decision.id, category.id

    def test_unaccepted_then_accepted_unchanged_revision_preserves_decision_identity(
        self,
    ):
        original = self.load()
        entry, decision_id, category_id = self.decide(original.import_id)
        revision = reparse_import(self.engine, self.owner, original.import_id)
        self.assertEqual(revision["status"], "pending")
        self.assertEqual(self.selected(original.statement_id), original.import_id)
        self.assertEqual(len(revision["plan"]["matches"]), 2)
        self.assertEqual(revision["plan"]["unmatched_new"], [])
        accepted = accept_revision(
            self.engine,
            self.owner,
            revision["id"],
            reason="Synthetic reviewed unchanged evidence",
        )
        self.assertEqual(accepted["status"], "accepted")
        with store_session(self.engine) as session:
            decision = session.get(EntryDecision, decision_id)
            self.assertEqual(decision.entry_id, entry)
            self.assertEqual(decision.category_id, category_id)
            self.assertEqual(
                session.scalar(select(func.count()).select_from(EntryDecision)), 1
            )
            self.assertEqual(session.scalar(select(func.count()).select_from(Entry)), 4)
            self.assertEqual(
                session.scalar(
                    select(func.count())
                    .select_from(ImportRecord)
                    .where(ImportRecord.pdf_bytes.is_not(None))
                ),
                1,
            )
            logical = list(
                session.scalars(
                    text(
                        "SELECT logical_entry_id FROM hisaab_api.entries WHERE import_id=:id"
                    ),
                    {"id": revision["candidate_import_id"]},
                )
            )
            self.assertIn(entry, logical)
        self.assertEqual(
            read_original(self.engine, self.owner, revision["candidate_import_id"]),
            self.path.read_bytes(),
        )
        self.assertEqual(
            read_original(self.engine, self.owner, original.import_id),
            self.path.read_bytes(),
        )

    def test_reordering_is_not_a_match_and_cannot_publish_without_explicit_decisions(
        self,
    ):
        original = self.load()
        self.decide(original.import_id)
        parsed = parse_pdf_bytes(self.path.read_bytes(), source_name=self.path.name)
        reordered = replace(
            parsed,
            parser_version="synthetic-revision-2",
            transactions=tuple(
                replace(row, sequence=index + 1)
                for index, row in enumerate(reversed(parsed.transactions))
            ),
        )
        with patch("core.revisions._parse", return_value=reordered):
            revision = reparse_import(self.engine, self.owner, original.import_id)
        self.assertEqual(revision["plan"]["matches"], [])
        self.assertEqual(len(revision["plan"]["unmatched_new"]), 2)
        with self.assertRaises(StoreError):
            accept_revision(
                self.engine,
                self.owner,
                revision["id"],
                reason="Synthetic unresolved reorder",
            )
        self.assertEqual(self.selected(original.statement_id), original.import_id)
        with self.engine.connect() as c:
            pairs = c.execute(
                text("""SELECT n.id,b.id FROM hisaab.entries n JOIN hisaab.entries b
                ON hisaab.entry_fingerprint(n)=hisaab.entry_fingerprint(b)
                WHERE n.import_id=:candidate AND b.import_id=:base"""),
                {
                    "candidate": revision["candidate_import_id"],
                    "base": original.import_id,
                },
            ).all()
        mapping = [
            {"new_entry_id": str(n), "previous_entry_id": str(b)} for n, b in pairs
        ]
        accepted = accept_revision(
            self.engine,
            self.owner,
            revision["id"],
            mapping=mapping,
            reason="Synthetic explicitly reviewed reordered identities",
        )
        self.assertEqual(accepted["status"], "accepted")
        self.assertEqual(
            str(self.selected(original.statement_id)), revision["candidate_import_id"]
        )

    def test_failed_parse_leaves_every_published_record_untouched(self):
        original = self.load()
        with patch(
            "core.revisions._parse", side_effect=RuntimeError("Synthetic failed parser")
        ):
            with self.assertRaises(RuntimeError):
                reparse_import(self.engine, self.owner, original.import_id)
        self.assertEqual(self.selected(original.statement_id), original.import_id)
        with self.engine.connect() as c:
            self.assertEqual(
                c.scalar(select(func.count()).select_from(ImportRecord)), 1
            )
            self.assertEqual(c.scalar(select(func.count()).select_from(Entry)), 2)

    def test_changed_candidate_metadata_invalidates_comparison(self):
        original = self.load()
        revision = reparse_import(self.engine, self.owner, original.import_id)
        with self.engine.begin() as c:
            c.execute(
                text("UPDATE hisaab.imports SET page_count=page_count+1 WHERE id=:id"),
                {"id": revision["candidate_import_id"]},
            )
        with self.assertRaises(StoreError):
            accept_revision(
                self.engine,
                self.owner,
                revision["id"],
                reason="Synthetic stale comparison",
            )
        self.assertEqual(self.selected(original.statement_id), original.import_id)

    def test_two_prepared_revisions_cannot_replace_each_other_silently(self):
        original = self.load()
        self.decide(original.import_id)
        first = reparse_import(self.engine, self.owner, original.import_id)
        second = reparse_import(self.engine, self.owner, original.import_id)
        accept_revision(
            self.engine,
            self.owner,
            first["id"],
            reason="Synthetic first reviewed revision",
        )
        with self.assertRaises(StoreError):
            accept_revision(
                self.engine,
                self.owner,
                second["id"],
                reason="Synthetic stale second revision",
            )
        self.assertEqual(
            str(self.selected(original.statement_id)), first["candidate_import_id"]
        )

    def test_other_owner_cannot_accept_a_revision(self):
        original = self.load()
        revision = reparse_import(self.engine, self.owner, original.import_id)
        with self.assertRaises(StoreError):
            accept_revision(
                self.engine,
                self.other_owner(),
                revision["id"],
                reason="Synthetic forbidden action",
            )
        self.assertEqual(self.selected(original.statement_id), original.import_id)

    def test_removed_entries_require_acknowledgement_and_keep_their_decisions(self):
        original = self.load()
        entry, decision_id, category = self.decide(original.import_id, sequence=2)
        parsed = parse_pdf_bytes(self.path.read_bytes(), source_name=self.path.name)
        with patch(
            "core.revisions._parse",
            return_value=replace(parsed, transactions=parsed.transactions[:1]),
        ):
            revision = reparse_import(self.engine, self.owner, original.import_id)
        with self.assertRaises(StoreError):
            accept_revision(
                self.engine,
                self.owner,
                revision["id"],
                reason="Synthetic missing removal acknowledgement",
            )
        accepted = accept_revision(
            self.engine,
            self.owner,
            revision["id"],
            removed=[str(entry)],
            reason="Synthetic explicit removed-row acknowledgement",
        )
        self.assertEqual(accepted["status"], "accepted")
        with store_session(self.engine) as session:
            self.assertEqual(session.get(EntryDecision, decision_id).entry_id, entry)
            self.assertIsNotNone(session.get(Entry, entry))

    def test_late_acceptance_failure_does_not_publish_partial_identity_links(self):
        original = self.load()
        self.decide(original.import_id)
        revision = reparse_import(self.engine, self.owner, original.import_id)
        with self.engine.begin() as c:
            c.execute(
                text(
                    "ALTER TABLE hisaab.entry_links ADD CONSTRAINT ck_synthetic_revision_failure CHECK(false) NOT VALID"
                )
            )
        try:
            with self.assertRaises(StoreError):
                accept_revision(
                    self.engine,
                    self.owner,
                    revision["id"],
                    reason="Synthetic injected late failure",
                )
            self.assertEqual(self.selected(original.statement_id), original.import_id)
            with self.engine.connect() as c:
                self.assertEqual(
                    c.scalar(text("SELECT count(*) FROM hisaab.entry_links")), 0
                )
                self.assertEqual(
                    c.scalar(
                        text("SELECT status FROM hisaab.parser_revisions WHERE id=:id"),
                        {"id": revision["id"]},
                    ),
                    "pending",
                )
        finally:
            with self.engine.begin() as c:
                c.execute(
                    text(
                        "ALTER TABLE hisaab.entry_links DROP CONSTRAINT ck_synthetic_revision_failure"
                    )
                )
        self.assertEqual(
            accept_revision(
                self.engine,
                self.owner,
                revision["id"],
                reason="Synthetic successful retry",
            )["status"],
            "accepted",
        )

    def test_ordinary_reimport_after_acceptance_is_still_a_no_parse_duplicate(self):
        original = self.load()
        revision = reparse_import(self.engine, self.owner, original.import_id)
        accept_revision(
            self.engine,
            self.owner,
            revision["id"],
            reason="Synthetic accepted parser revision",
        )
        with patch(
            "core.imports._parse", side_effect=AssertionError("No implicit reparse")
        ):
            duplicate = self.load()
        self.assertEqual(duplicate.status, "duplicate")
        self.assertEqual(str(duplicate.import_id), revision["candidate_import_id"])
        self.assertTrue(duplicate.selected_source)
