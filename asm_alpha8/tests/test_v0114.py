import hashlib
import tempfile
import unittest
from pathlib import Path
from asm import ASMEngine, ASMConfig
from asm.parsing import StructuralParser
from benchmark_cases import CORE, DISTRACTORS, PARAPHRASE_PAIRS, TESTS
from migrate import copy_database

class ParserTests(unittest.TestCase):
    def setUp(self):self.p=StructuralParser()
    def test_active_paraphrases(self):
        for q,k in [('work boosts heat','INCREASE'),('work brought about motion','CAUSE'),('cooling diminishes heat','DECREASE'),('skill permits performance','ENABLE'),('shield inhibits interference','PREVENT'),('signal sets off alarm','TRIGGER'),('liquid turns into gas','BECOME')]:
            with self.subTest(q=q):
                f=self.p.parse(q);self.assertTrue(f.supported,f.warnings);self.assertEqual(f.signature(),(k,))
    def test_passive_direction(self):
        for active,passive in [('practice increases skill','skill is increased by practice'),('wind causes motion','motion was caused by wind'),('cooling reduces heat','heat is lowered by cooling')]:
            with self.subTest(active=active):
                a=self.p.parse(active);b=self.p.parse(passive)
                self.assertTrue(b.supported,b.warnings);self.assertEqual(a.relations,b.relations)
    def test_negation_scope(self):
        for q in ['practice does not increase skill',"practice doesn't boost skill",'practice never raises skill',"skill isn't increased by practice",'skill was never boosted by practice']:
            with self.subTest(q=q):
                f=self.p.parse(q);self.assertTrue(f.supported,f.warnings)
                self.assertEqual(f.signature(),('NOT:INCREASE',));self.assertEqual(f.relations[0].left,'practice')
                self.assertEqual(f.relations[0].right,'skill')
    def test_typographic_contraction(self):
        f=self.p.parse('practice doesn’t boost skill');self.assertTrue(f.supported);self.assertEqual(f.signature(),('NOT:INCREASE',))
    def test_clause_local_negation(self):
        f=self.p.parse('practice does not increase skill; study increases knowledge')
        self.assertTrue(f.supported);self.assertEqual(f.signature(),('NOT:INCREASE','INCREASE'))
    def test_not_prevent_is_not_enable(self):
        f=self.p.parse('shield does not prevent interference');self.assertTrue(f.supported);self.assertEqual(f.signature(),('NOT:PREVENT',))
    def test_threshold(self):
        for q in ['heat exceeds the threshold','heat crosses threshold, server fails']:
            f=self.p.parse(q);self.assertTrue(f.supported,f.warnings);self.assertEqual(f.signature(),('THRESHOLD',))
    def test_unsupported_scope(self):
        cases=['if practice increases skill, results improve','practice may increase skill','does practice increase skill?','practice does not only increase skill','practice no longer increases skill','practice increases no ability','no practice increases skill','practice frobnobulates skill','practice is not known to increase skill','practice causes skill to increase ability','', 'practice cannot increase skill', 'practice does not always increase skill', 'practice fails to increase skill']
        for q in cases:
            with self.subTest(q=q):self.assertFalse(self.p.parse(q).supported)

class EngineTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.path=Path(self.t.name)/'model.db';self.a=ASMEngine(self.path)
    def tearDown(self):
        self.a.close();self.t.cleanup()
    def train(self,lines):
        for s in lines:self.a.process(s,training=True)
    def pred(self,q):return self.a.expand_problem(q)['prediction']
    def test_original_and_audit_regression(self):
        self.train(CORE*3+DISTRACTORS*5)
        for q,expected in TESTS+[(q,k) for x,y,k in PARAPHRASE_PAIRS for q in (x,y)]:
            with self.subTest(q=q):self.assertEqual(self.pred(q)['relation'],expected)
    def test_unlearned_negative_abstains(self):
        self.train(CORE*3)
        for q in ["practice doesn't boost ability",'electrical input never increases voltage','wind does not cause motion']:
            with self.subTest(q=q):
                r=self.a.expand_problem(q);self.assertEqual(r['prediction']['status'],'no_evidence');self.assertEqual(r['hypotheses'],[]);self.assertEqual(r['analogies'],[])
    def test_learn_negative_without_overwriting_positive(self):
        self.train(['practice increases skill; skill enables performance']*3)
        self.train(['practice does not increase skill; instruction prevents confusion']*3)
        self.assertEqual(self.pred('practice boosts ability')['relation'],'ENABLE')
        self.assertEqual(self.pred("practice doesn't boost ability")['relation'],'PREVENT')
    def test_negative_outcome_retains_polarity(self):
        self.train(['practice increases skill; skill does not enable flight']*3)
        r=self.a.expand_problem('practice boosts ability')
        self.assertEqual(r['prediction']['relation'],'NOT:ENABLE')
        self.assertTrue(any(h['hypothesis']=='RELATION:NOT:ENABLE' for h in r['hypotheses']))
    def test_insufficient_support(self):
        self.train(['practice increases skill; skill enables performance'])
        self.assertEqual(self.pred('practice boosts ability')['status'],'no_evidence')
    def test_conflicting_continuations_abstain(self):
        self.train(['practice increases skill; skill enables performance','practice increases skill; skill triggers performance']*3)
        p=self.pred('practice boosts ability');self.assertEqual(p['status'],'ambiguous');self.assertEqual(p['relation'],None)
        self.assertAlmostEqual(p['margin'],0)
    def test_conflict_not_resolved_by_input_order(self):
        a=self.a
        lines=['practice increases skill; skill enables performance','practice increases skill; skill triggers performance']*3
        self.train(lines)
        other=ASMEngine(Path(self.t.name)/'other.db')
        try:
            for s in reversed(lines):other.process(s,training=True)
            self.assertEqual(self.pred('practice increases ability'),other.expand_problem('practice increases ability')['prediction'])
        finally:other.close()
    def test_unknown_does_not_generate_hypotheses(self):
        self.train(CORE*3)
        r=self.a.expand_problem('practice supercharges skill');self.assertEqual(r['prediction']['status'],'unsupported');self.assertEqual(r['hypotheses'],[])
    def test_unsupported_training_not_counted_as_assertion(self):
        self.train(['if practice increases skill, skill enables performance']*4)
        self.assertEqual(self.a.structural_memory.transition_counts,{})
    def test_duplicate_analogies_removed(self):
        self.train(CORE*5)
        r=self.a.expand_problem('practice boosts ability');texts=[x['text'] for x in r['analogies']]
        self.assertEqual(len(texts),len(set(texts)))
    def test_queries_do_not_learn(self):
        self.train(CORE*3);before=self.a.structural_memory.export_state();count=self.a.memory.count_events()
        for _ in range(4):self.pred('practice boosts ability')
        self.assertEqual(before,self.a.structural_memory.export_state());self.assertEqual(count,self.a.memory.count_events())
    def test_save_load(self):
        self.train(['practice does not increase skill; instruction prevents confusion']*3)
        old=self.pred('practice never boosts ability');self.a.close();self.a=ASMEngine(self.path)
        self.assertEqual(old,self.pred('practice never boosts ability'))
    def test_migration_reparses_all_events_and_preserves_source(self):
        # More than the 1,200-example cache cap. Corrupt old structure is ignored.
        for _ in range(1205):
            self.a.memory.add_event('practice does not increase skill; instruction prevents confusion',{},[],0,0)
        self.a.save();payload=self.a.memory.get_kv(self.a.SNAPSHOT_KEY)
        payload['version']='0.1.1.3';payload['structural_memory']={}
        self.a.memory.set_kv('asm_snapshot_v1_1_3',payload)
        self.a.memory.db.execute('DELETE FROM kv WHERE key=?',(self.a.SNAPSHOT_KEY,));self.a.memory.db.commit()
        # Close only SQLite here so close() does not recreate the new snapshot.
        self.a.close(save_snapshot=False)
        original=self.path.read_bytes();dest=Path(self.t.name)/'copy.db';copy_database(self.path,dest)
        new=ASMEngine(dest)
        try:
            self.assertEqual(new.structural_memory.transition_counts['NOT:INCREASE']['PREVENT'],1205)
            self.assertEqual(new.event_count,1205);self.assertEqual(new.memory.count_events(),1205)
            new.close();new=ASMEngine(dest)
            self.assertEqual(new.structural_memory.transition_counts['NOT:INCREASE']['PREVENT'],1205)
        finally:new.close()
        self.assertEqual(self.path.read_bytes(),original)
        self.a=ASMEngine(self.path)
    def test_copy_refuses_overwrite(self):
        self.a.save();self.assertRaises(FileExistsError,copy_database,self.path,self.path)
    def test_same_words_without_cues_abstain_on_tie(self):
        self.train(CORE*3);self.assertEqual(self.pred('input increases output')['status'],'ambiguous')

if __name__=='__main__':unittest.main()
