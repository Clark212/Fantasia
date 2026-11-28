from __future__ import annotations
import tempfile
import unittest
from pathlib import Path

from asm import __version__
from asm.engine import ASMEngine
from asm.procedure_program import Program


def trust(engine, source='oracle'):
    for i in range(80):
        engine.observe_evidence_source(source, observation='A', resolved_hypothesis='A', temporal_index=i)


def feed(engine, mechanism, rows, fn, tag, source='oracle'):
    out=[]
    for i, values in enumerate(rows):
        out.append(engine.observe_procedural_experience(
            mechanism, values, fn(**values), evidence_id=f'{mechanism}-{tag}-{i}', source_id=source
        ))
    return out



def resolve_queries(engine, mechanism, auto, fn, tag, max_steps=8):
    asked=[]
    for step in range(max_steps):
        q=auto.get('information_query') if isinstance(auto,dict) else None
        if not q or q.get('status')!='query_suggested':break
        values=q['input'];asked.append(dict(values))
        row=engine.observe_procedural_experience(
            mechanism, values, fn(**values), evidence_id=f'{mechanism}-{tag}-query-{step}', source_id='oracle'
        )
        auto=row['auto_induction']
    return auto,asked

class Alpha74ConditionalProcedureTests(unittest.TestCase):
    def make(self):
        td=tempfile.TemporaryDirectory();self.addCleanup(td.cleanup)
        e=ASMEngine(Path(td.name)/'state.db');self.addCleanup(e.close);trust(e);return e

    def test_version(self):
        self.assertEqual(__version__, '0.4.0-alpha.7.9')

    def test_typed_conditional_program_is_total_and_bounded(self):
        p=Program({'flag':'bool','x':'int'},('if','flag',('add','x',1),('sub','x',1)))
        self.assertEqual(p.run({'flag':True,'x':4}),5)
        self.assertEqual(p.run({'flag':False,'x':4}),3)
        with self.assertRaises(ValueError):p.run({'flag':1,'x':4})

    def test_xor_collecting_suggests_missing_discriminating_input(self):
        e=self.make();f=lambda a,b:a^b
        rows=[{'a':False,'b':False},{'a':False,'b':True},{'a':True,'b':False}]
        last=feed(e,'xor_query',rows,f,'fit')[-1]['auto_induction']
        self.assertEqual(last['status'],'collecting')
        q=last['information_query']
        self.assertEqual(q['status'],'query_suggested')
        self.assertEqual(q['input'],{'a':True,'b':True})
        self.assertGreaterEqual(q['distinct_predictions'],2)
        self.assertTrue(q['read_only'])

    def test_xor_autonomously_learns_then_validates(self):
        e=self.make();f=lambda a,b:a^b
        fit=[{'a':False,'b':False},{'a':False,'b':True},{'a':True,'b':False},{'a':True,'b':True}]
        auto=feed(e,'xor',fit,f,'fit')[-1]['auto_induction']
        self.assertEqual(auto['status'],'proposed')
        self.assertIn('boolean:',auto['origin'])
        feed(e,'xor',fit,f,'val')
        pred=e.predict_procedure('xor',{'a':True,'b':False})
        self.assertEqual(pred['status'],'predicted');self.assertIs(pred['value'],True)
        self.assertEqual(e.procedure_versions('xor')[-1]['state'],'active')

    def test_integer_predicate_boolean_learning(self):
        e=self.make();f=lambda x:x<0
        fit=[{'x':-3},{'x':-1},{'x':2}]
        auto=feed(e,'negative',fit,f,'fit')[-1]['auto_induction']
        self.assertEqual(auto['status'],'needs_information')
        auto,asked=resolve_queries(e,'negative',auto,f,'resolve')
        self.assertEqual(auto['status'],'proposed');self.assertLessEqual(len(asked),3)
        val=[{'x':x} for x in (-10,-8,-6,-4,3,5,7,9)]
        feed(e,'negative',val,f,'val')
        self.assertIs(e.predict_procedure('negative',{'x':-2})['value'],True)
        self.assertIs(e.predict_procedure('negative',{'x':4})['value'],False)

    def test_unary_piecewise_affine_learning(self):
        e=self.make();f=lambda x:2*x+1 if x<0 else -x+3
        fit=[{'x':-3},{'x':-1},{'x':1},{'x':3}]
        auto=feed(e,'piece',fit,f,'fit')[-1]['auto_induction']
        self.assertEqual(auto['status'],'needs_information')
        auto,asked=resolve_queries(e,'piece',auto,f,'resolve')
        self.assertEqual(auto['status'],'proposed');self.assertEqual(auto['origin'],'conditional');self.assertLessEqual(len(asked),2)
        val=[{'x':x} for x in (-10,-8,-6,-4,2,4,6,8)]
        feed(e,'piece',val,f,'val')
        self.assertEqual(e.predict_procedure('piece',{'x':-5})['value'],-9)
        self.assertEqual(e.predict_procedure('piece',{'x':5})['value'],-2)

    def test_bool_selector_piecewise_affine_learning(self):
        e=self.make();f=lambda flag,x:x+1 if flag else x-1
        fit=[{'flag':False,'x':0},{'flag':False,'x':2},{'flag':True,'x':0},{'flag':True,'x':2}]
        auto=feed(e,'selector',fit,f,'fit')[-1]['auto_induction']
        self.assertEqual(auto['status'],'proposed');self.assertEqual(auto['origin'],'conditional')
        val=[]
        for x in range(10,14):
            val.extend([{'flag':False,'x':x},{'flag':True,'x':x}])
        feed(e,'selector',val,f,'val')
        self.assertEqual(e.predict_procedure('selector',{'flag':True,'x':7})['value'],8)
        self.assertEqual(e.predict_procedure('selector',{'flag':False,'x':7})['value'],6)

    def test_information_query_is_read_only(self):
        e=self.make();f=lambda a,b:a^b
        rows=[{'a':False,'b':False},{'a':False,'b':True},{'a':True,'b':False}]
        # Manual observation avoids any autonomous proposal side effect.
        for i,v in enumerate(rows):
            e.observe_procedure('qro',v,f(**v),evidence_id=f'qro-{i}',source_id='oracle')
        db=e.procedures.db
        before={
            'evidence':db.execute('SELECT COUNT(*) FROM procedure_evidence').fetchone()[0],
            'versions':db.execute('SELECT COUNT(*) FROM procedure_versions').fetchone()[0],
            'audit':db.execute('SELECT COUNT(*) FROM procedure_audit').fetchone()[0],
            'auto':db.execute('SELECT COUNT(*) FROM procedure_auto_state').fetchone()[0],
        }
        q=e.procedure_information_query('qro')
        after={
            'evidence':db.execute('SELECT COUNT(*) FROM procedure_evidence').fetchone()[0],
            'versions':db.execute('SELECT COUNT(*) FROM procedure_versions').fetchone()[0],
            'audit':db.execute('SELECT COUNT(*) FROM procedure_audit').fetchone()[0],
            'auto':db.execute('SELECT COUNT(*) FROM procedure_auto_state').fetchone()[0],
        }
        self.assertEqual(q['status'],'query_suggested');self.assertEqual(before,after)

    def test_information_query_candidate_pool_contract(self):
        e=self.make();f=lambda a,b:a^b
        rows=[{'a':False,'b':False},{'a':False,'b':True},{'a':True,'b':False}]
        for i,v in enumerate(rows):e.observe_procedure('pool',v,f(**v),evidence_id=f'pool-{i}',source_id='oracle')
        q=e.procedure_information_query('pool',candidate_inputs=[{'a':True,'b':True}])
        self.assertEqual(q['input'],{'a':True,'b':True})
        with self.assertRaises(ValueError):
            e.procedure_information_query('pool',candidate_inputs=[{'a':1,'b':True}])

    def test_conditional_drift_and_reversal_are_versioned(self):
        e=self.make()
        f1=lambda x:2*x+1 if x<0 else -x+3
        f2=lambda x:-x+5 if x<0 else 3*x-2
        fit1=[{'x':-3},{'x':-1},{'x':1},{'x':3}]
        a=feed(e,'driftpiece',fit1,f1,'a-fit')[-1]['auto_induction'];a,_=resolve_queries(e,'driftpiece',a,f1,'a-resolve')
        self.assertEqual(a['status'],'proposed')
        feed(e,'driftpiece',[{'x':x} for x in (-10,-8,-6,-4,2,4,6,8)],f1,'a-val')
        fit2=[{'x':-9},{'x':-7},{'x':5},{'x':7}]
        r2=feed(e,'driftpiece',fit2,f2,'b-fit')[-1]['auto_induction'];r2,_=resolve_queries(e,'driftpiece',r2,f2,'b-resolve')
        self.assertEqual(r2['status'],'proposed');self.assertEqual(r2['version'],2)
        feed(e,'driftpiece',[{'x':x} for x in (-20,-18,-16,-14,10,12,14,16)],f2,'b-val')
        self.assertEqual(e.predict_procedure('driftpiece',{'x':6})['value'],16)
        # Old validated structure may be re-proposed, but it must earn held-out support again.
        rev=feed(e,'driftpiece',[{'x':-13},{'x':-11},{'x':9}],f1,'c-fit')[-1]['auto_induction'];rev,_=resolve_queries(e,'driftpiece',rev,f1,'c-resolve')
        self.assertEqual(rev['mode'],'revalidation');self.assertEqual(rev['version'],3)
        feed(e,'driftpiece',[{'x':x} for x in (-30,-28,-26,-24,20,22,24,26)],f1,'c-val')
        self.assertEqual(e.predict_procedure('driftpiece',{'x':6})['value'],-3)

    def test_boolean_search_budget_is_hard_bounded(self):
        e=self.make();f=lambda a,b:a^b
        rows=[{'a':False,'b':False},{'a':False,'b':True},{'a':True,'b':False},{'a':True,'b':True}]
        for i,v in enumerate(rows):e.observe_procedure('budget',v,f(**v),evidence_id=f'bg-{i}',source_id='oracle')
        r=e.induce_procedure('budget',budget=1,training_ids=[f'bg-{i}' for i in range(4)])
        self.assertLessEqual(r.get('candidate_count',0),1)

    def test_inference_never_records_query_answer(self):
        e=self.make();f=lambda a,b:a^b
        rows=[{'a':False,'b':False},{'a':False,'b':True},{'a':True,'b':False}]
        for i,v in enumerate(rows):e.observe_procedure('no_self_train',v,f(**v),evidence_id=f'nst-{i}',source_id='oracle')
        q=e.procedure_information_query('no_self_train')
        self.assertEqual(q['status'],'query_suggested')
        self.assertEqual(len(e.procedures.training('no_self_train')),3)
        self.assertEqual(len(e.procedure_versions('no_self_train')),0)


if __name__=='__main__':unittest.main()
