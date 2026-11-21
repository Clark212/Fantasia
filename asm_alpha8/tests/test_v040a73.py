from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from asm.engine import ASMEngine


def trust_oracle(engine: ASMEngine, source: str = "oracle", start: int = 0, n: int = 80) -> None:
    for i in range(start, start + n):
        engine.observe_evidence_source(source, observation="A", resolved_hypothesis="A", temporal_index=i)


def observe(engine, mechanism, tag, rows, fn, *, source="oracle", root_id=None):
    out=[]
    for i, values in enumerate(rows):
        kwargs={}
        if root_id is not None:kwargs['root_id']=root_id
        out.append(engine.observe_procedural_experience(
            mechanism, values, fn(**values), evidence_id=f"{tag}-{i}", source_id=source, **kwargs
        ))
    return out


class MultiInputCompositionalProcedureTests(unittest.TestCase):
    def test_two_input_affine_autonomous_induction_and_validation(self):
        with tempfile.TemporaryDirectory() as d:
            e=ASMEngine(Path(d)/'state.db')
            try:
                trust_oracle(e)
                fit=[{'x':0,'y':0},{'x':1,'y':0},{'x':0,'y':1},{'x':2,'y':3}]
                rows=observe(e,'aff2','fit',fit,lambda x,y:2*x+3*y+5)
                auto=rows[-1]['auto_induction']
                self.assertEqual(auto['status'],'proposed')
                self.assertEqual(auto['origin'],'multi_affine')
                self.assertEqual(e.predict_procedure('aff2',{'x':9,'y':4})['status'],'abstained')
                val=[{'x':i,'y':2*i+1} for i in range(10,18)]
                observe(e,'aff2','val',val,lambda x,y:2*x+3*y+5)
                pred=e.predict_procedure('aff2',{'x':9,'y':4})
                self.assertEqual(pred['status'],'predicted');self.assertEqual(pred['value'],35)
            finally:e.close()

    def test_three_input_affine_requires_five_independent_roots(self):
        with tempfile.TemporaryDirectory() as d:
            e=ASMEngine(Path(d)/'state.db')
            try:
                trust_oracle(e)
                pts=[{'a':0,'b':0,'c':0},{'a':1,'b':0,'c':0},{'a':0,'b':1,'c':0},{'a':0,'b':0,'c':1},{'a':1,'b':1,'c':1}]
                rows=observe(e,'aff3','fit',pts[:4],lambda a,b,c:2*a-3*b+4*c+7)
                self.assertEqual(rows[-1]['auto_induction']['status'],'collecting')
                self.assertEqual(rows[-1]['auto_induction']['required'],5)
                row=observe(e,'aff3','fit5',pts[4:],lambda a,b,c:2*a-3*b+4*c+7)[-1]
                self.assertEqual(row['auto_induction']['status'],'proposed')
                self.assertEqual(row['auto_induction']['origin'],'multi_affine')
            finally:e.close()

    def test_four_input_affine_requires_six_roots(self):
        with tempfile.TemporaryDirectory() as d:
            e=ASMEngine(Path(d)/'state.db')
            try:
                trust_oracle(e)
                pts=[
                    {'a':0,'b':0,'c':0,'d':0},{'a':1,'b':0,'c':0,'d':0},
                    {'a':0,'b':1,'c':0,'d':0},{'a':0,'b':0,'c':1,'d':0},
                    {'a':0,'b':0,'c':0,'d':1},{'a':1,'b':1,'c':1,'d':1},
                ]
                rows=observe(e,'aff4','fit',pts[:5],lambda a,b,c,d:a+2*b+3*c+4*d-5)
                self.assertEqual(rows[-1]['auto_induction']['status'],'collecting')
                self.assertEqual(rows[-1]['auto_induction']['required'],6)
                row=observe(e,'aff4','fit6',pts[5:],lambda a,b,c,d:a+2*b+3*c+4*d-5)[-1]
                self.assertEqual(row['auto_induction']['status'],'proposed')
            finally:e.close()

    def test_product_is_found_by_bounded_composition_search(self):
        with tempfile.TemporaryDirectory() as d:
            e=ASMEngine(Path(d)/'state.db')
            try:
                trust_oracle(e)
                pts=[{'x':0,'y':2},{'x':1,'y':5},{'x':3,'y':-2},{'x':2,'y':4}]
                auto=observe(e,'prod','fit',pts,lambda x,y:x*y)[-1]['auto_induction']
                self.assertEqual(auto['status'],'proposed')
                self.assertTrue(auto['origin'].startswith('composition:'))
                self.assertLessEqual(auto['candidate_count'],512)
            finally:e.close()

    def test_validated_unary_procedure_can_donate_structure_without_authority(self):
        with tempfile.TemporaryDirectory() as d:
            e=ASMEngine(Path(d)/'state.db')
            try:
                trust_oracle(e)
                observe(e,'square','sqfit',[{'x':0},{'x':1},{'x':2}],lambda x:x*x)
                observe(e,'square','sqval',[{'x':i} for i in range(10,18)],lambda x:x*x)
                self.assertEqual(e.predict_procedure('square',{'x':9})['value'],81)
                pts=[{'x':0,'y':2},{'x':1,'y':5},{'x':2,'y':1},{'x':3,'y':4}]
                auto=observe(e,'square_plus','fit',pts,lambda x,y:x*x+y)[-1]['auto_induction']
                self.assertEqual(auto['status'],'proposed')
                self.assertIn('donor:square',auto['origin'])
                # New hypothesis is still untrusted until its own held-out evidence arrives.
                self.assertEqual(e.predict_procedure('square_plus',{'x':7,'y':3})['status'],'abstained')
                observe(e,'square_plus','val',[{'x':i,'y':2*i+1} for i in range(10,18)],lambda x,y:x*x+y)
                self.assertEqual(e.predict_procedure('square_plus',{'x':7,'y':3})['value'],52)
                v=e.procedure_versions('square_plus')[-1]
                self.assertEqual(v['support'],8);self.assertEqual(v['dependencies'],{'oracle':1})
            finally:e.close()

    def test_multi_input_drift_creates_new_version(self):
        with tempfile.TemporaryDirectory() as d:
            e=ASMEngine(Path(d)/'state.db')
            try:
                trust_oracle(e)
                fit=[{'x':0,'y':0},{'x':1,'y':0},{'x':0,'y':1},{'x':2,'y':3}]
                observe(e,'drift','a',fit,lambda x,y:2*x+y+3)
                observe(e,'drift','av',[{'x':i,'y':i+1} for i in range(10,18)],lambda x,y:2*x+y+3)
                fresh=[{'x':20,'y':2},{'x':21,'y':0},{'x':19,'y':3},{'x':22,'y':5}]
                rows=observe(e,'drift','b',fresh,lambda x,y:-x+4*y+2)
                self.assertEqual(rows[-1]['auto_induction']['status'],'proposed')
                self.assertEqual(rows[-1]['auto_induction']['version'],2)
                observe(e,'drift','bv',[{'x':i,'y':2*i-3} for i in range(30,38)],lambda x,y:-x+4*y+2)
                self.assertEqual(e.predict_procedure('drift',{'x':8,'y':2})['value'],2)
            finally:e.close()

    def test_multi_input_full_reversal_revalidates_old_structure(self):
        with tempfile.TemporaryDirectory() as d:
            e=ASMEngine(Path(d)/'state.db')
            try:
                trust_oracle(e)
                base=[{'x':0,'y':0},{'x':1,'y':0},{'x':0,'y':1}]
                observe(e,'rev','a',base,lambda x,y:2*x+y+3)
                observe(e,'rev','av',[{'x':i,'y':i+1} for i in range(10,18)],lambda x,y:2*x+y+3)
                observe(e,'rev','b',[{'x':20,'y':2},{'x':21,'y':0},{'x':19,'y':3},{'x':22,'y':5}],lambda x,y:-x+4*y+2)
                observe(e,'rev','bv',[{'x':i,'y':2*i-3} for i in range(30,38)],lambda x,y:-x+4*y+2)
                rows=observe(e,'rev','c',[{'x':40,'y':2},{'x':41,'y':0},{'x':39,'y':3},{'x':42,'y':5}],lambda x,y:2*x+y+3)
                auto=rows[-1]['auto_induction']
                self.assertEqual(auto['status'],'proposed');self.assertEqual(auto['mode'],'revalidation');self.assertEqual(auto['version'],3)
            finally:e.close()

    def test_duplicate_roots_still_do_not_trigger_multi_input_induction(self):
        with tempfile.TemporaryDirectory() as d:
            e=ASMEngine(Path(d)/'state.db')
            try:
                trust_oracle(e)
                pts=[{'x':i,'y':i+1} for i in range(10)]
                rows=observe(e,'dup','fit',pts,lambda x,y:x+y,root_id='same-root')
                self.assertEqual(rows[-1]['auto_induction']['status'],'collecting')
                self.assertEqual(rows[-1]['auto_induction']['trusted_independent_roots'],1)
                self.assertEqual(e.procedure_versions('dup'),[])
            finally:e.close()

    def test_low_trust_multi_input_evidence_cannot_trigger_hypothesis(self):
        with tempfile.TemporaryDirectory() as d:
            e=ASMEngine(Path(d)/'state.db')
            try:
                rows=observe(e,'low','fit',[{'x':0,'y':0},{'x':1,'y':0},{'x':0,'y':1},{'x':2,'y':3}],lambda x,y:x+y,source='unknown')
                self.assertEqual(rows[-1]['auto_induction']['status'],'collecting')
                self.assertEqual(rows[-1]['auto_induction']['trusted_independent_roots'],0)
                self.assertEqual(e.procedure_versions('low'),[])
            finally:e.close()

    def test_unary_alpha72_behavior_remains_available(self):
        with tempfile.TemporaryDirectory() as d:
            e=ASMEngine(Path(d)/'state.db')
            try:
                trust_oracle(e)
                auto=observe(e,'legacy','fit',[{'x':0},{'x':1},{'x':2}],lambda x:4*x-2)[-1]['auto_induction']
                self.assertEqual(auto['status'],'proposed');self.assertEqual(auto['origin'],'grammar')
            finally:e.close()


if __name__=='__main__':unittest.main()
