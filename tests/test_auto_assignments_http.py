"""Assignment learning through actual owner-scoped authenticated HTTP."""
from uuid import uuid4
from sqlalchemy import text

from tests.supabase_fixture import SupabaseTests


class AssignmentHTTPTests(SupabaseTests):
    def setUp(self):
        with self.engine.begin() as connection:
            for table in ('assignment_examples','decision_events','entry_decisions','categories','accounts'):
                connection.execute(text('DELETE FROM hisaab.'+table+' WHERE owner_id=ANY(:owners)'),{'owners':self.owners})

    def training(self):
        code,label=self.call('/rpc/save_label',self.tokens[0],method='POST',data={'p_kind':'account','p_name':'Synthetic history pot'})
        self.assertEqual(code,200)
        with self.engine.begin() as c:
            for _ in range(2):
                c.execute(text("INSERT INTO hisaab.assignment_examples(id,owner_id,source_key,merchant_key,direction,kind,is_manual,account_id) VALUES(:id,:owner,:key,'synthetic shop','debit','account',false,:label)"),{'id':uuid4(),'owner':self.owners[0],'key':str(uuid4()),'label':label['id']})
        return label

    def auto(self,index=0,**overrides):
        args={'p_entry_ids':[str(self.records[0].entry.id)],'p_expected_owner':str(self.owners[min(index,1)])}
        args.update(overrides)
        return self.call('/rpc/auto_assign_entries',self.tokens[index],method='POST',data=args)

    def test_assignments_persist_and_manual_corrections_are_learned(self):
        label=self.training()
        code,count=self.auto();self.assertEqual((code,count),(200,1))
        _,rows=self.call('/entries?id=eq.'+str(self.records[0].entry.id),self.tokens[0])
        self.assertEqual(rows[0]['account_id'],label['id'])
        code,saved=self.call('/rpc/save_entry_decision',self.tokens[0],method='POST',data={'p_entry_id':str(self.records[0].entry.id),'p_expected_version':rows[0]['decision_version'],'p_patch':{'account_id':None}})
        self.assertEqual(code,200)
        self.assertEqual(self.auto(),(200,0))
        _,events=self.call('/decision_history?entry_id=eq.'+str(self.records[0].entry.id),self.tokens[0])
        self.assertEqual(len(events),2)
        self.assertIsNone(events[0]['actor_auth_user_id'])
        self.assertIsNotNone(events[1]['actor_auth_user_id'])

    def test_owner_guards_foreign_entries_and_batch_limits(self):
        self.training()
        self.assertEqual(self.auto(1),(200,0))
        self.assertEqual(self.auto(p_expected_owner=str(self.owners[1]))[0],403)
        self.assertEqual(self.auto(2,p_expected_owner=str(self.owners[0]))[0],403)
        self.assertEqual(self.auto(p_entry_ids=[str(uuid4())]*51)[0],422)
        self.assertEqual(self.auto(p_entry_ids=[None])[0],422)
        code,_=self.call('/rpc/auto_assign_entries',method='POST',data={'p_entry_ids':[],'p_expected_owner':str(self.owners[0])})
        self.assertGreaterEqual(code,400)
        code,_=self.call('/assignment_examples',self.tokens[0])
        self.assertGreaterEqual(code,400)

    def test_private_helpers_cannot_bypass_learning(self):
        code,_=self.call('/rpc/save_entry_decision_without_learning',self.tokens[0],method='POST',data={'p_entry_id':str(self.records[0].entry.id),'p_expected_version':0,'p_patch':{}})
        self.assertGreaterEqual(code,400)
