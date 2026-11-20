import tempfile
import unittest
from pathlib import Path

from asm import ASMEngine, __version__


class TestASM0119(unittest.TestCase):
    def make_engine(self):
        td=tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup)
        asm=ASMEngine(Path(td.name)/'asm.db'); self.addCleanup(asm.close)
        return asm

    def test_version(self):
        self.assertEqual(__version__, '0.4.0-alpha.7.9')

    def test_new_relation_type_forms_without_human_label(self):
        asm=self.make_engine()
        for text in ['box glarps item','box glarps object','crate glarps item']:
            asm.process(text,training=True)
        rels=asm.discovered_relations()
        self.assertTrue(rels)
        self.assertTrue(rels[0]['id'].startswith('RELATION:'))
        self.assertNotIn(rels[0]['id'], {'CAUSE','INCREASE','DECREASE','ENABLE','PREVENT','TRIGGER','BECOME'})

    def test_new_relation_reuses_on_new_entities(self):
        asm=self.make_engine()
        for text in ['box glarps item','box glarps object','crate glarps item']:
            asm.process(text,training=True)
        rid=asm.discovered_relations()[0]['id']
        query=asm.infer_discovered_relation('container glarps component')
        self.assertTrue(query['supported'])
        self.assertEqual(query['relation_ids'][0],rid)

    def test_paraphrases_merge_from_distributional_context(self):
        asm=self.make_engine()
        for text in [
            'box glarps item','crate glarps object',
            'box snarps item','crate snarps object',
            'container glarps component','container snarps component',
        ]:
            asm.process(text,training=True)
        rels=asm.discovered_relations()
        self.assertEqual(len(rels),1)
        proto=set(rels[0]['prototype']['connector'])
        self.assertIn('glarp',proto)
        self.assertIn('snarp',proto)
        self.assertGreaterEqual(asm.relation_discovery.stats()['merges'],1)

    def test_different_relations_stay_separate(self):
        asm=self.make_engine()
        for text in [
            'box glarps item','crate glarps object','box snarps item','crate snarps object',
            'alice traks coin','bob traks key','alice vims coin','bob vims key',
        ]:
            asm.process(text,training=True)
        rels=asm.discovered_relations()
        self.assertEqual(len(rels),2)
        a=asm.infer_discovered_relation('container glarps component')['relation_ids'][0]
        b=asm.infer_discovered_relation('cara traks book')['relation_ids'][0]
        self.assertNotEqual(a,b)

    def test_machine_relation_can_be_used_as_structure(self):
        asm=self.make_engine()
        for text in ['box glarps item','crate glarps object','container glarps component']:
            asm.process(text,training=True)
        result=asm.process('vessel glarps module',training=True)
        self.assertTrue(result['structure']['supported'])
        self.assertTrue(result['structure']['signature'][0].startswith('RELATION:'))
        self.assertTrue(any(k.startswith('MREL:RELATION:') for k,_ in result['workspace']))

    def test_prediction_failure_can_split_overbroad_relation(self):
        asm=self.make_engine()
        for text in [
            'voltage links current','circuit links signal',
            'electrical signal links current','battery links power',
            'practice links skill','training links ability',
            'study links knowledge','practice links strength',
        ]:
            asm.process(text,training=True)
        self.assertEqual(asm.relation_discovery.stats()['relations'],1)
        rid=asm.discovered_relations()[0]['id']
        result=None
        for _ in range(3):
            result=asm.relation_feedback(rid,success=False,prediction_error=1.0)
        self.assertIsNotNone(result['split'])
        self.assertEqual(asm.relation_discovery.stats()['relations'],2)
        self.assertEqual(asm.relation_discovery.stats()['splits'],1)

    def test_relation_strength_weakens_on_failed_predictions(self):
        asm=self.make_engine()
        for text in ['box glarps item','crate glarps object','container glarps component']:
            asm.process(text,training=True)
        rid=asm.discovered_relations()[0]['id']
        before=asm.relation_discovery.inspect(rid)['strength']
        asm.relation_feedback(rid,success=False,prediction_error=1.0)
        after=asm.relation_discovery.inspect(rid)['strength']
        self.assertLess(after,before)

    def test_query_does_not_learn(self):
        asm=self.make_engine()
        before=asm.relation_discovery.stats()['episodes']
        asm.infer_discovered_relation('alpha zorps beta')
        self.assertEqual(asm.relation_discovery.stats()['episodes'],before)

    def test_persistence(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/'persist.db'
            asm=ASMEngine(db)
            for text in ['box glarps item','crate glarps object','container glarps component']:
                asm.process(text,training=True)
            rid=asm.discovered_relations()[0]['id']
            asm.close()
            asm2=ASMEngine(db)
            try:
                self.assertEqual(asm2.infer_discovered_relation('vessel glarps module')['relation_ids'][0],rid)
            finally:
                asm2.close()


if __name__=='__main__':
    unittest.main()
