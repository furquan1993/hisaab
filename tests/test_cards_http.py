"""Card registration and editing through the actual authenticated Data API."""
from tests.supabase_fixture import SupabaseTests


class CardsHTTPTests(SupabaseTests):
    def save(self, index=0, **changes):
        data = dict(p_expected_owner=str(self.owners[0]), p_label="Synthetic travel card",
                    p_bank="hdfc", p_last_four="0042", p_id=None, p_expected_version=0)
        data.update(changes)
        return self.call('/rpc/save_card', self.tokens[index], method='POST', data=data)

    def test_create_edit_conflict_and_owner_isolation(self):
        code, card = self.save()
        self.assertEqual(code, 200)
        self.assertEqual(card['last_four'], '0042')
        code, rows = self.call('/cards?id=eq.' + card['id'], self.tokens[0])
        self.assertEqual((code, len(rows)), (200, 1))
        for index in (1, 2):
            code, rows = self.call('/cards?id=eq.' + card['id'], self.tokens[index])
            self.assertEqual((code, rows), (200, []))
            self.assertIn(self.save(index=index, p_id=card['id'], p_expected_version=1)[0], (403, 409))
        code, changed = self.save(p_id=card['id'], p_expected_version=1, p_label='Renamed', p_last_four=None)
        self.assertEqual((code, changed['version'], changed['label']), (200, 2, 'Renamed'))
        self.assertEqual(self.save(p_id=card['id'], p_expected_version=1)[0], 409)
        self.assertEqual(self.save(p_last_four='12345')[0], 422)
        self.assertGreaterEqual(self.call('/rpc/save_card', method='POST', data={
            'p_expected_owner': str(self.owners[0]), 'p_label': 'Anonymous',
            'p_bank': 'hdfc', 'p_last_four': None, 'p_id': None, 'p_expected_version': 0})[0], 400)
