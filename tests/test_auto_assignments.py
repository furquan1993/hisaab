"""Real PostgreSQL matching, learning, audit and selected-source boundaries."""
from uuid import uuid4
from sqlalchemy import text, select

from core.persistence.models import AssignmentExample, EntryDecision, FundingAccount, Category, DecisionEvent
from tests.persistence_fixture import seed, new_entry, new_import
from tests.postgres_fixture import PostgresTests


class AssignmentTests(PostgresTests):
    def setUp(self):
        super().setUp()
        self.rows = seed(self.session)
        self.owner = self.rows.owner.id
        self.rows.owner.auth_user_id = uuid4()
        self.session.flush()
        self.session.execute(text("SELECT set_config('request.jwt.claims',:claims,true)"), {'claims':'{"role":"authenticated","sub":"'+str(self.rows.owner.auth_user_id)+'"}'})
        self.a = FundingAccount(owner_id=self.owner,name='Synthetic home')
        self.b = FundingAccount(owner_id=self.owner,name='Synthetic travel')
        self.session.add_all([self.a,self.b]); self.session.flush()

    def example(self, label, source=None, kind='account', direction='debit'):
        self.session.add(AssignmentExample(owner_id=self.owner,source_key=source or str(uuid4()),merchant_key='synthetic shop',direction=direction,kind=kind,is_manual=False,account_id=label if kind=='account' else None,category_id=label if kind=='category' else None))
        self.session.flush()

    def apply(self, entry=None):
        self.session.flush()
        return self.session.scalar(text('SELECT hisaab.apply_entry_assignments(:o,:e)'),{'o':self.owner,'e':entry or self.rows.entry.id})

    def decision(self, entry=None):
        self.session.expire_all()
        return self.session.scalar(select(EntryDecision).where(EntryDecision.entry_id==(entry or self.rows.entry.id)))

    def save(self, patch, entry=None):
        import json
        d=self.decision(entry)
        return self.session.scalar(text('SELECT hisaab_api.save_entry_decision(:e,:v,CAST(:p AS jsonb))'),{'e':entry or self.rows.entry.id,'v':d.version if d else 0,'p':json.dumps(patch)})

    def test_history_requires_consensus_and_preserves_facts(self):
        self.example(self.a.id)
        self.assertFalse(self.apply())
        self.example(self.a.id)
        self.assertTrue(self.apply())
        self.assertEqual(self.decision().account_id,self.a.id)
        self.assertFalse(self.apply())
        self.assertEqual(self.session.scalar(select(DecisionEvent).where(DecisionEvent.entry_id==self.rows.entry.id)).reason,'Automatically assigned from history, corrections or starter category rules')
        self.assertEqual(self.rows.entry.description,'SYNTHETIC SHOP')
        self.assertEqual(len(self.session.scalars(select(DecisionEvent).where(DecisionEvent.entry_id==self.rows.entry.id)).all()),1)

    def test_ambiguity_and_direction_are_independent(self):
        self.example(self.a.id);self.example(self.a.id);self.example(self.b.id)
        self.assertFalse(self.apply())
        self.session.add_all([new_entry(self.rows.imported,sequence=2,direction='credit'),new_entry(self.rows.imported,sequence=3,entry_type='payment',direction='credit')])
        self.session.flush()
        self.assertIsNone(self.decision())

    def test_latest_manual_correction_teaches_and_explicit_clear_is_protected(self):
        self.example(self.a.id);self.example(self.a.id);self.apply()
        self.save({'account_id':str(self.b.id)})
        entry=new_entry(self.rows.imported,sequence=2);self.session.add(entry);self.session.flush()
        self.assertEqual(self.decision(entry.id).account_id,self.b.id)
        self.save({'account_id':None},entry.id)
        self.assertFalse(self.apply(entry.id))
        third=new_entry(self.rows.imported,sequence=3);self.session.add(third);self.session.flush()
        self.assertIsNone(self.decision(third.id))

    def test_categories_work_without_history_and_manual_category_is_independent(self):
        entry=new_entry(self.rows.imported,sequence=2,description='SWIGGY INSTAMART BANGALORE');self.session.add(entry);self.session.flush()
        d=self.decision(entry.id)
        self.assertIsNone(d.account_id)
        self.assertEqual(self.session.get(Category,d.category_id).name,'Groceries')
        self.save({'category_id':None},entry.id)
        self.assertFalse(self.apply(entry.id))
        self.assertIsNone(self.decision(entry.id).category_id)

    def test_archived_labels_and_foreign_history_do_not_assign(self):
        self.example(self.a.id);self.example(self.a.id);self.a.is_archived=True
        self.assertFalse(self.apply())
        foreign=seed(self.session)
        self.assertFalse(self.session.scalar(text('SELECT hisaab.apply_entry_assignments(:o,:e)'),{'o':foreign.owner.id,'e':self.rows.entry.id}))

    def test_candidate_is_not_assigned_until_selected(self):
        self.example(self.a.id);self.example(self.a.id)
        candidate=new_import(self.rows);self.session.add(candidate);self.session.flush()
        entry=new_entry(candidate);self.session.add(entry);self.session.flush()
        self.assertIsNone(self.decision(entry.id))
        self.rows.statement.active_import_id=candidate.id;self.session.flush()
        self.assertEqual(self.decision(entry.id).account_id,self.a.id)

    def test_normalization_keeps_merchant_identity_and_removes_reference_noise(self):
        key=lambda s:self.session.scalar(text('SELECT hisaab.merchant_key(:s)'),{'s':s})
        self.assertEqual(key('SHOP*TEST 123456789'),'shop test')
        self.assertNotEqual(key('SHOP ONE'),key('SHOP TWO'))
        self.assertEqual(key('7-Eleven'),'7 eleven')

    def test_training_is_idempotent_and_does_not_create_ledger_entries(self):
        from core.assignment_history import HistoryExample
        from core.assignments import train_assignments
        from core.persistence.models import Entry
        examples=[HistoryExample(str(i),'SYNTHETIC SHOP','debit','Saved household',None) for i in range(2)]
        first=train_assignments(self.connection,self.owner,examples)
        self.assertEqual(first['added_examples'],2)
        self.assertEqual(first['assigned_entries'],1)
        second=train_assignments(self.connection,self.owner,examples)
        self.assertEqual(second['added_examples'],0)
        self.assertEqual(second['assigned_entries'],0)
        self.assertEqual(len(self.session.scalars(select(Entry).where(Entry.owner_id==self.owner)).all()),1)

    def test_review_corrections_survive_auto_assignment(self):
        self.example(self.a.id);self.example(self.a.id)
        self.session.add(EntryDecision(owner_id=self.owner,entry_id=self.rows.entry.id,overrides={'description':'Corrected source'},acknowledged=['issue'],version=1))
        self.session.flush()
        self.assertTrue(self.apply())
        decision=self.decision()
        self.assertEqual(decision.overrides,{'description':'Corrected source'})
        self.assertEqual(decision.acknowledged,['issue'])

    def test_manual_removal_with_unknown_direction_remains_protected_after_review(self):
        self.rows.entry.direction=None;self.session.flush()
        self.save({'account_id':None})
        self.rows.entry.direction='debit';self.session.flush()
        self.example(self.a.id);self.example(self.a.id)
        self.assertFalse(self.apply())
        self.assertIsNone(self.decision().account_id)

    def test_effective_description_drives_matching_without_losing_corrections(self):
        self.example(self.a.id);self.example(self.a.id)
        fingerprint=self.session.scalar(text('SELECT hisaab.entry_fingerprint(e) FROM hisaab.entries e WHERE id=:id'),{'id':self.rows.entry.id})
        self.session.add(EntryDecision(owner_id=self.owner,entry_id=self.rows.entry.id,overrides={'description':'SWIGGY INSTAMART'},source_fingerprint=fingerprint,version=1))
        self.session.flush()
        self.assertTrue(self.apply())
        d=self.decision()
        self.assertIsNone(d.account_id)
        self.assertEqual(self.session.get(Category,d.category_id).name,'Groceries')
        self.assertEqual(d.overrides,{'description':'SWIGGY INSTAMART'})

    def test_debit_credit_and_repayments_do_not_share_account_learning(self):
        self.example(self.a.id);self.example(self.a.id)
        self.example(self.b.id,direction='credit');self.example(self.b.id,direction='credit')
        self.assertTrue(self.apply())
        credit=new_entry(self.rows.imported,sequence=2,direction='credit',entry_type='refund')
        payment=new_entry(self.rows.imported,sequence=3,direction='credit',entry_type='payment')
        self.session.add_all([credit,payment]);self.session.flush()
        self.assertEqual(self.decision().account_id,self.a.id)
        self.assertEqual(self.decision(credit.id).account_id,self.b.id)
        self.assertIsNone(self.decision(payment.id))

    def test_concurrent_assignment_is_one_audited_decision(self):
        from concurrent.futures import ThreadPoolExecutor
        from core.persistence.session import transaction
        from tests.test_transactions_postgres import remove_synthetic_owner
        with transaction(self.engine) as session:
            rows=seed(session)
            rows.entry.description='SWIGGY INSTAMART'
        try:
            def apply():
                with self.engine.begin() as c:
                    return c.scalar(text('SELECT hisaab.apply_entry_assignments(:o,:e)'),{'o':rows.owner.id,'e':rows.entry.id})
            with ThreadPoolExecutor(2) as pool:
                results=list(pool.map(lambda _:apply(),range(2)))
            self.assertEqual(sorted(results),[False,True])
            with self.engine.connect() as c:
                self.assertEqual(c.scalar(text('SELECT count(*) FROM hisaab.decision_events WHERE entry_id=:e'),{'e':rows.entry.id}),1)
        finally:
            remove_synthetic_owner(self.engine,rows.owner.id)

    def test_training_keeps_account_and_category_examples_independent(self):
        from core.assignment_history import HistoryExample
        from core.assignments import train_assignments
        examples=[HistoryExample(str(i),'SYNTHETIC SHOP','debit','Historical account','Historical category') for i in range(2)]
        result=train_assignments(self.connection,self.owner,examples)
        self.assertEqual(result['added_examples'],4)
        d=self.decision()
        self.assertEqual(self.session.get(FundingAccount,d.account_id).name,'Historical account')
        self.assertEqual(self.session.get(Category,d.category_id).name,'Historical category')
