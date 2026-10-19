"""Friendly descriptions through real Auth/API, isolated from financial decisions."""
from sqlalchemy import text

from tests.decision_fixture import remove_decisions
from tests.supabase_fixture import SupabaseTests


class FriendlyDescriptionHTTPTests(SupabaseTests):
    def setUp(self):
        with self.engine.begin() as connection:
            remove_decisions(connection, self.owners)

    def save(self, description, version=0, index=0, entry=None):
        return self.call('/rpc/save_friendly_description', self.tokens[index], method='POST', data={
            'p_entry_id': str(entry or self.records[0].entry.id),
            'p_expected_version': version, 'p_description': description,
        })

    def row(self):
        code, rows = self.call('/entries?id=eq.' + str(self.records[0].entry.id), self.tokens[0])
        self.assertEqual(code, 200)
        return rows[0]

    def snapshot(self):
        with self.engine.connect() as c:
            return {
                name: c.execute(text(sql), {'owner': self.owners[0]}).all()
                for name, sql in {
                    'evidence': 'SELECT to_jsonb(e)::text FROM hisaab.entries e WHERE owner_id=:owner ORDER BY id',
                    'imports': 'SELECT to_jsonb(i)::text FROM hisaab.imports i WHERE owner_id=:owner ORDER BY id',
                    'decisions': 'SELECT to_jsonb(d)::text FROM hisaab.entry_decisions d WHERE owner_id=:owner ORDER BY id',
                    'learning': 'SELECT to_jsonb(x)::text FROM hisaab.assignment_examples x WHERE owner_id=:owner ORDER BY id',
                    'funding': 'SELECT evidence::text FROM hisaab.funding_rows WHERE owner_id=:owner ORDER BY id',
                    'obligations': 'SELECT fingerprint,net,blocked FROM hisaab.funding_obligations WHERE owner_id=:owner ORDER BY card_id,account_id',
                }.items()
            }

    def test_save_replace_clear_history_and_financial_invariance(self):
        before = self.snapshot()
        row = self.row()
        self.assertEqual((row['friendly_description'], row['friendly_description_version']), (None, 0))
        code, saved = self.save('  Desk lamp for study  ')
        self.assertEqual((code, saved), (200, {'friendly_description': 'Desk lamp for study', 'friendly_description_version': 1}))
        self.assertEqual(self.row()['friendly_description'], 'Desk lamp for study')
        self.assertEqual(self.save('Desk lamp for study', 1), (200, saved))
        code, saved = self.save('Gift from Amazon', 1)
        self.assertEqual((code, saved['friendly_description_version']), (200, 2))
        code, saved = self.save('   ', 2)
        self.assertEqual((code, saved['friendly_description'], saved['friendly_description_version']), (200, None, 3))
        self.assertEqual(self.row()['description'], row['description'])
        self.assertEqual(self.snapshot(), before)
        with self.engine.connect() as c:
            history = c.execute(text('SELECT description,actor_auth_user_id FROM hisaab.entry_descriptions WHERE owner_id=:owner ORDER BY version'), {'owner': self.owners[0]}).all()
        self.assertEqual([r[0] for r in history], ['Desk lamp for study', 'Gift from Amazon', None])
        self.assertTrue(all(str(r[1]) == self.users[0] for r in history))

    def test_conflicts_validation_and_owner_isolation(self):
        self.assertEqual(self.save('Allowed')[0], 200)
        self.assertEqual(self.save('Stale')[0], 409)
        self.assertEqual(self.row()['friendly_description'], 'Allowed')
        for description, version in [('x' * 501, 1), ('Valid', -1), ('Valid', None)]:
            self.assertEqual(self.save(description, version)[0], 422)
        for index in (1, 2):
            self.assertIn(self.save('Foreign', index=index)[0], (403, 404))
        code, _ = self.call('/rpc/save_friendly_description', method='POST', data={
            'p_entry_id': str(self.records[0].entry.id), 'p_expected_version': 1, 'p_description': 'Anonymous'})
        self.assertGreaterEqual(code, 400)
        self.assertEqual(self.row()['friendly_description'], 'Allowed')
        with self.engine.begin() as c:
            c.execute(text("SELECT set_config('request.jwt.claims',:claims,true)"), {'claims': '{"sub":"' + self.users[1] + '"}'})
            c.execute(text('SET LOCAL ROLE authenticated'))
            self.assertEqual(c.scalar(text('SELECT count(*) FROM hisaab.entry_descriptions')), 0)
            self.assertFalse(c.scalar(text("SELECT has_table_privilege(current_user,'hisaab.entry_descriptions','INSERT')")))
            self.assertFalse(c.scalar(text("SELECT has_table_privilege(current_user,'hisaab.entry_descriptions','UPDATE')")))

    def test_description_survives_verified_corrections_and_logical_identity(self):
        self.assertEqual(self.save('Friendly title')[0], 200)
        row = self.row()
        code, _ = self.call('/rpc/review_entry', self.tokens[0], method='POST', data={
            'p_entry_id': row['id'], 'p_expected_version': row['decision_version'],
            'p_overrides': {'description': 'Corrected merchant'}, 'p_acknowledged': [],
            'p_reason': 'Synthetic correction'})
        self.assertEqual(code, 200)
        self.assertEqual(self.row()['friendly_description'], 'Friendly title')
        self.assertEqual(self.row()['effective_description'], 'Corrected merchant')
        self.assertEqual(self.save('Still independent', 1)[0], 200)
        self.assertEqual(self.row()['decision_version'], row['decision_version'] + 1)

    def test_server_search_matches_both_original_and_friendly(self):
        self.assertEqual(self.save('Unique gift title')[0], 200)
        from urllib.parse import quote
        for value in ('Unique gift title', self.records[0].entry.description):
            query = '/entries?id=eq.' + str(self.records[0].entry.id) + '&or=' + quote('(description.ilike."%' + value + '%",friendly_description.ilike."%' + value + '%")')
            code, rows = self.call(query, self.tokens[0])
            self.assertEqual((code, len(rows)), (200, 1))

    def test_z_accepted_reparse_keeps_description_and_rejects_old_source_edits(self):
        from sqlalchemy.orm import Session
        from tests.persistence_fixture import PDF, new_entry, new_import
        self.assertEqual(self.save('Retained purchase title')[0], 200)
        original = self.records[0]
        with Session(self.engine) as session, session.begin():
            candidate = new_import(original, payload=PDF, pdf_bytes=None,
                source_import_id=original.imported.id, source_filename=original.imported.source_filename,
                parser_version='synthetic-friendly-reparse')
            session.add(candidate)
            session.flush()
            revised = new_entry(candidate)
            session.add(revised)
            session.flush()
            candidate_id, new_id = str(candidate.id), str(revised.id)
        self.assertEqual(self.save('Candidate edit', entry=new_id)[0], 409)
        code, plan = self.call('/rpc/prepare_revision', self.tokens[0], method='POST', data={'p_candidate_import_id': candidate_id})
        self.assertEqual(code, 200)
        code, _ = self.call('/rpc/accept_revision', self.tokens[0], method='POST', data={
            'p_revision_id': plan['id'], 'p_mapping': [], 'p_removed': [], 'p_reason': 'Synthetic reparse'})
        self.assertEqual(code, 200)
        code, rows = self.call('/entries?id=eq.' + new_id, self.tokens[0])
        self.assertEqual(code, 200)
        self.assertEqual(rows[0]['friendly_description'], 'Retained purchase title')
        self.assertEqual(rows[0]['friendly_description_version'], 1)
        self.assertEqual(self.save('Old source edit', 1)[0], 409)
        self.assertEqual(self.save('Revised purchase title', 1, entry=new_id)[0], 200)
