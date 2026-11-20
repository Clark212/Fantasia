import os
import tempfile
import unittest
from pathlib import Path

from asm import __version__
from asm.transition_mechanism import TransitionMechanismBank


class Alpha4SchedulerTests(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix='.db'); os.close(fd)
        self.bank = TransitionMechanismBank(
            self.path, hidden_dim=16, train_steps=2, learning_rate=.012, seed=17,
            scheduler_max_calls=1, scheduler_min_relevance=.45,
        )

    def tearDown(self):
        try: self.bank.close()
        except Exception: pass
        for suffix in ('','-wal','-shm'):
            try: os.remove(self.path+suffix)
            except FileNotFoundError: pass

    def seed(self, kind, mechanism, action='step'):
        before={'kind':kind,'value':0}; after={'kind':kind,'value':1}
        for i in range(3):
            self.bank.observe(mechanism, entity_id=f'{kind}{i}', state=before, action=action, after_state=after)
        return before, after

    def test_version(self):
        self.assertEqual(__version__, '0.4.0-alpha.7.9')

    def test_learned_applicability_selects_matching_mechanism(self):
        door,_=self.seed('door','door_dyn','open')
        self.seed('switch','switch_dyn','toggle')
        route=self.bank.route(state=door,action='open',mode='seismic')
        self.assertEqual(route['selected'][0]['mechanism_type'],'door_dyn')
        self.assertGreaterEqual(route['selected'][0]['relevance'],.99)
        self.assertEqual(len(route['selected']),1)

    def test_low_relevance_falls_back_dense(self):
        self.seed('door','door_dyn','open'); self.seed('switch','switch_dyn','toggle')
        routed=self.bank.predict_routed(entity_id='u',state={'kind':'unknown','value':9},action='zap',mode='seismic')
        self.assertTrue(routed['fallback'])
        self.assertEqual(routed['calls'],2)
        self.assertEqual(routed['reason'],'low_relevance_dense_fallback')

    def test_seismic_reduces_calls_vs_dense(self):
        door,_=self.seed('door','door_dyn','open')
        self.seed('switch','switch_dyn','toggle'); self.seed('container','container_dyn','insert')
        dense=self.bank.predict_routed(entity_id='d',state=door,action='open',mode='dense')
        seismic=self.bank.predict_routed(entity_id='s',state=door,action='open',mode='seismic')
        self.assertEqual(dense['calls'],3)
        self.assertEqual(seismic['calls'],1)
        self.assertGreaterEqual(seismic['call_reduction'],2/3)
        self.assertEqual(seismic['chosen']['mechanism_type'],'door_dyn')

    def test_applicability_survives_reload(self):
        door,_=self.seed('door','door_dyn','open')
        self.seed('switch','switch_dyn','toggle')
        self.bank.close()
        self.bank=TransitionMechanismBank(self.path,hidden_dim=16,train_steps=2,learning_rate=.012,seed=17)
        route=self.bank.route(state=door,action='open',mode='seismic')
        self.assertEqual(route['selected'][0]['mechanism_type'],'door_dyn')
        self.assertGreater(route['selected'][0]['relevance'],.9)

if __name__=='__main__': unittest.main()
