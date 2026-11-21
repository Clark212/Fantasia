from __future__ import annotations
import tempfile
import unittest
from pathlib import Path

from asm.engine import ASMEngine


def trust(engine, source='oracle'):
    for i in range(80):
        engine.observe_evidence_source(source, observation='A', resolved_hypothesis='A', temporal_index=i)


def activate_context(engine, mechanism, context, fn):
    for i, x in enumerate((0, 1, 2)):
        engine.observe_procedural_experience(
            mechanism, {'x': x}, fn(x), evidence_id=f'{mechanism}-{context}-fit-{i}',
            source_id='oracle', context=context,
        )
    for i, x in enumerate(range(10, 18)):
        engine.observe_procedural_experience(
            mechanism, {'x': x}, fn(x), evidence_id=f'{mechanism}-{context}-val-{i}',
            source_id='oracle', context=context,
        )
    assert engine.procedure_versions(mechanism, context=context)[-1]['state'] == 'active'


class Alpha75ParallelRoutingTests(unittest.TestCase):
    def make(self):
        td = tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup)
        e = ASMEngine(Path(td.name) / 'state.db'); self.addCleanup(e.close); trust(e); return e

    def test_two_context_routing_and_prediction(self):
        e = self.make(); activate_context(e, 'route', 'A', lambda x: x + 1); activate_context(e, 'route', 'B', lambda x: x - 1)
        for i in range(4):
            e.observe_procedure_route('route', {'mode': False}, 'A', evidence_id=f'ra-{i}', source_id='oracle')
            e.observe_procedure_route('route', {'mode': True}, 'B', evidence_id=f'rb-{i}', source_id='oracle')
        a = e.route_procedure_context('route', {'mode': False}); b = e.route_procedure_context('route', {'mode': True})
        self.assertEqual((a['status'], a['context']), ('routed', 'A')); self.assertEqual((b['status'], b['context']), ('routed', 'B'))
        self.assertEqual(e.predict_routed_procedure('route', {'x': 5}, {'mode': False})['value'], 6)
        self.assertEqual(e.predict_routed_procedure('route', {'x': 5}, {'mode': True})['value'], 4)

    def test_missing_context_requests_information_read_only(self):
        e = self.make(); activate_context(e, 'q', 'A', lambda x: x + 1); activate_context(e, 'q', 'B', lambda x: x - 1)
        for i in range(4):
            e.observe_procedure_route('q', {'mode': False}, 'A', evidence_id=f'qa-{i}', source_id='oracle')
            e.observe_procedure_route('q', {'mode': True}, 'B', evidence_id=f'qb-{i}', source_id='oracle')
        db=e.procedures.db
        before=db.execute('SELECT COUNT(*) FROM procedure_route_evidence').fetchone()[0]
        r=e.route_procedure_context('q', {})
        after=db.execute('SELECT COUNT(*) FROM procedure_route_evidence').fetchone()[0]
        self.assertEqual(r['status'], 'needs_information'); self.assertEqual(r['information_query']['feature'], 'mode')
        self.assertGreater(r['information_query']['expected_information_gain'], 0); self.assertTrue(r['information_query']['read_only'])
        self.assertEqual(before, after)

    def test_two_step_information_gathering(self):
        e=self.make(); patterns={'A':(False,False),'B':(False,True),'C':(True,False),'D':(True,True)}
        for idx,ctx in enumerate(patterns): activate_context(e,'seq',ctx,lambda x,d=idx+1:x+d)
        for ctx,(a,b) in patterns.items():
            for i in range(8):
                e.observe_procedure_route('seq', {'bit1':a,'bit2':b}, ctx, evidence_id=f'{ctx}-r-{i}', source_id='oracle')
        r0=e.route_procedure_context('seq',{}); self.assertEqual(r0['status'],'needs_information'); self.assertEqual(r0['information_query']['feature'],'bit1')
        r1=e.route_procedure_context('seq',{'bit1':False}); self.assertEqual(r1['status'],'needs_information'); self.assertEqual(r1['information_query']['feature'],'bit2')
        r2=e.route_procedure_context('seq',{'bit1':False,'bit2':True}); self.assertEqual((r2['status'],r2['context']),('routed','B'))

    def test_duplicate_root_never_multiplies_routing_support(self):
        e=self.make(); activate_context(e,'root','A',lambda x:x+1); activate_context(e,'root','B',lambda x:x-1)
        r=e.observe_procedure_route('root',{'mode':False},'A',evidence_id='r1',source_id='oracle',root_id='shared')
        d=e.observe_procedure_route('root',{'mode':False},'A',evidence_id='r2',source_id='oracle',root_id='shared')
        self.assertEqual(r['status'],'recorded'); self.assertEqual(d['status'],'duplicate_root')
        self.assertEqual(e.procedure_route_evidence_status('root')['total_records'],1)

    def test_target_requires_active_procedure(self):
        e=self.make()
        r=e.observe_procedure_route('missing',{'mode':True},'A',evidence_id='m1',source_id='oracle')
        self.assertEqual(r['status'],'blocked'); self.assertEqual(r['reason'],'target_context_has_no_active_procedure')

    def test_low_trust_route_evidence_is_blocked(self):
        e=self.make(); activate_context(e,'trust','A',lambda x:x+1)
        r=e.observe_procedure_route('trust',{'mode':True},'A',evidence_id='bad',source_id='unknown_source')
        self.assertEqual(r['status'],'blocked'); self.assertEqual(r['reason'],'routing_source_below_trust_floor')
        self.assertEqual(e.procedure_route_evidence_status('trust')['total_records'],0)

    def test_source_regime_change_invalidates_old_route_evidence(self):
        e=self.make(); activate_context(e,'drift','A',lambda x:x+1); activate_context(e,'drift','B',lambda x:x-1)
        for i in range(4):
            e.observe_procedure_route('drift',{'mode':False},'A',evidence_id=f'da-{i}',source_id='oracle')
            e.observe_procedure_route('drift',{'mode':True},'B',evidence_id=f'db-{i}',source_id='oracle')
        self.assertEqual(e.route_procedure_context('drift',{'mode':False})['status'],'routed')
        # Drive the source into a new reliability regime using externally resolved contradictions.
        for i in range(80, 160):
            e.observe_evidence_source('oracle', observation='A', resolved_hypothesis='B', temporal_index=i)
        status=e.procedure_route_evidence_status('drift')
        self.assertEqual(status['effective_records'],0)
        self.assertNotEqual(e.route_procedure_context('drift',{'mode':False}).get('status'),'routed')

    def test_temporal_routing_drift_and_full_reversal_preserve_history(self):
        e=self.make();activate_context(e,'rdrift','A',lambda x:x+1);activate_context(e,'rdrift','B',lambda x:x-1)
        t=0
        for i in range(6):
            e.observe_procedure_route('rdrift',{'signal':True},'A',evidence_id=f'ra0-{i}',source_id='oracle',temporal_index=t);t+=1
        self.assertEqual(e.route_procedure_context('rdrift',{'signal':True})['context'],'A')
        for i in range(4):
            e.observe_procedure_route('rdrift',{'signal':True},'B',evidence_id=f'rb1-{i}',source_id='oracle',temporal_index=t);t+=1
        mid=e.route_procedure_context('rdrift',{'signal':True})
        self.assertEqual((mid['status'],mid['context'],mid['reason']),('routed','B','recent_temporal_signature_regime'))
        for i in range(4):
            e.observe_procedure_route('rdrift',{'signal':True},'A',evidence_id=f'ra2-{i}',source_id='oracle',temporal_index=t);t+=1
        end=e.route_procedure_context('rdrift',{'signal':True})
        self.assertEqual((end['status'],end['context']),('routed','A'))
        self.assertEqual(e.procedure_route_evidence_status('rdrift')['total_records'],14)

    def test_bad_temporal_index_fails_without_partial_route_mutation(self):
        e=self.make();activate_context(e,'time','A',lambda x:x+1)
        e.observe_procedure_route('time',{'signal':True},'A',evidence_id='t1',source_id='oracle',temporal_index=10)
        before=e.procedure_route_evidence_status('time')['total_records']
        with self.assertRaises(ValueError):
            e.observe_procedure_route('time',{'signal':True},'A',evidence_id='t2',source_id='oracle',temporal_index=9)
        with self.assertRaises(ValueError):
            e.observe_procedure_route('time',{'signal':True},'A',evidence_id='t3',source_id='oracle',temporal_index=True)
        self.assertEqual(e.procedure_route_evidence_status('time')['total_records'],before)

    def test_random_no_pattern_context_abstains(self):
        e=self.make(); activate_context(e,'noise','A',lambda x:x+1); activate_context(e,'noise','B',lambda x:x-1)
        # Same observed context maps equally to both procedures: no stable applicability relation exists.
        for i in range(8):
            e.observe_procedure_route('noise',{'signal':True},'A' if i%2==0 else 'B',evidence_id=f'n-{i}',source_id='oracle')
        r=e.route_procedure_context('noise',{'signal':True})
        self.assertIn(r['status'],('abstain','needs_information')); self.assertNotEqual(r.get('status'),'routed')

    def test_route_state_persists_across_reopen(self):
        td=tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup); path=Path(td.name)/'state.db'
        e=ASMEngine(path); trust(e); activate_context(e,'persist','A',lambda x:x+1); activate_context(e,'persist','B',lambda x:x-1)
        for i in range(4):
            e.observe_procedure_route('persist',{'mode':False},'A',evidence_id=f'pa-{i}',source_id='oracle')
            e.observe_procedure_route('persist',{'mode':True},'B',evidence_id=f'pb-{i}',source_id='oracle')
        e.close(); e=ASMEngine(path); self.addCleanup(e.close)
        r=e.route_procedure_context('persist',{'mode':True})
        self.assertEqual((r['status'],r['context']),('routed','B'))

    def test_bounded_query_tree_resolves_four_contexts_without_mutation(self):
        e=self.make(); patterns={'A':(False,False),'B':(False,True),'C':(True,False),'D':(True,True)}
        for idx,ctx in enumerate(patterns): activate_context(e,'tree',ctx,lambda x,d=idx+1:x+d)
        for ctx,(a,b) in patterns.items():
            for i in range(8):
                e.observe_procedure_route('tree',{'bit1':a,'bit2':b},ctx,evidence_id=f't-{ctx}-{i}',source_id='oracle')
        db=e.procedures.db;before=db.execute('SELECT COUNT(*) FROM procedure_route_evidence').fetchone()[0]
        plan=e.plan_procedure_route_queries('tree',{},max_depth=2)
        after=db.execute('SELECT COUNT(*) FROM procedure_route_evidence').fetchone()[0]
        self.assertEqual(plan['status'],'planned');self.assertTrue(plan['read_only']);self.assertEqual(before,after)
        self.assertEqual(plan['tree']['information_query']['feature'],'bit1')
        leaves=[]
        for b1 in plan['tree']['branches']:
            self.assertEqual(b1['next']['information_query']['feature'],'bit2')
            leaves.extend(x['next'] for x in b1['next']['branches'])
        self.assertEqual({leaf.get('context') for leaf in leaves},{'A','B','C','D'})
        self.assertTrue(all(leaf['status']=='routed' for leaf in leaves))

    def test_route_feature_contract_fails_closed(self):
        e=self.make(); activate_context(e,'contract','A',lambda x:x+1)
        with self.assertRaises(ValueError): e.route_procedure_context('contract',{'bad key':True})
        with self.assertRaises(ValueError): e.route_procedure_context('contract',{'x':1.5})
        with self.assertRaises(ValueError): e.route_procedure_context('contract',{f'f{i}':True for i in range(17)})


if __name__=='__main__': unittest.main()
