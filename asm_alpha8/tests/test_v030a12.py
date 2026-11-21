import unittest
from asm import __version__
from asm.transition_mechanism import LocalRecurrentTransitionMechanism

class Alpha12RobustAbstractionTests(unittest.TestCase):
    def build(self, **kw):
        opts=dict(hidden_dim=10,train_steps=1,max_outcomes=16,outcome_capacity_limit=128,
                  retention_anchor_limit=24,abstraction_min_support=5,
                  abstraction_min_precision=.95,abstraction_min_diversity=3,
                  abstraction_max_dropped_features=2,abstraction_sparse_enabled=True,
                  abstraction_sparse_max_retained_features=2,
                  abstraction_candidates_per_observation=48,
                  abstraction_max_candidates=256,abstraction_exception_limit=32,seed=1212)
        opts.update(kw)
        m=LocalRecurrentTransitionMechanism('a12_unit',**opts);m.replay_limit=24;m.replay_batch_limit=3
        return m

    def test_version(self):
        self.assertEqual(__version__,'0.4.0-alpha.7.9')

    def test_sparse_projection_reaches_rule_hidden_by_many_nuisance_features(self):
        m=self.build()
        for v in range(7):
            m.observe(entity_id=f'e{v}',state={'mode':'on','n1':f'a{v}','n2':f'b{v}','n3':v,'n4':v%3,'n5':f'q{v}'},
                      action='go',after_state={'r':'yes'})
        p=m.predict(entity_id='fresh',state={'mode':'on','n1':'new1','n2':'new2','n3':99,'n4':8,'n5':'new5','extra':'new'},action='go')
        self.assertEqual(p.predicted_state,{'r':'yes'})
        self.assertGreaterEqual(m.stats()['abstraction_promoted'],1)

    def test_drop_only_ablation_cannot_reach_five_nuisance_rule(self):
        m=self.build(abstraction_sparse_enabled=False)
        candidates=m._abstraction_candidates({'mode':'on','n1':'a','n2':'b','n3':1,'n4':2,'n5':'q'},'go',None,1.0)
        self.assertTrue(candidates)
        self.assertFalse(any(k.startswith('keep=') for k,_ in candidates))

    def test_sparse_candidate_work_is_bounded(self):
        m=self.build(abstraction_candidates_per_observation=24)
        state={'mode':'x', **{f'n{i}':i for i in range(12)}}
        self.assertLessEqual(len(m._abstraction_candidates(state,'go',None,1.0)),24)

    def test_random_outcomes_do_not_promote_sparse_rule(self):
        m=self.build(abstraction_min_support=6)
        for v in range(12):
            m.observe(entity_id=f'e{v}',state={'mode':'x','n1':f'a{v}','n2':f'b{v}','n3':v,'n4':v%4,'n5':f'q{v}'},
                      action='go',after_state={'r':v%6})
        self.assertEqual(m.stats()['abstraction_promoted'],0)

    def test_serialization_preserves_sparse_projection_settings_and_rule(self):
        m=self.build()
        for v in range(7):
            m.observe(entity_id=f'e{v}',state={'mode':'on','n1':f'a{v}','n2':f'b{v}','n3':v,'n4':v%3,'n5':f'q{v}'},
                      action='go',after_state={'r':'yes'})
        r=self.build(abstraction_sparse_enabled=False,abstraction_candidates_per_observation=16)
        r.import_blob(m.export_blob())
        self.assertTrue(r.abstraction_sparse_enabled)
        self.assertEqual(r.abstraction_candidates_per_observation,48)
        self.assertEqual(r.predict(entity_id='fresh',state={'mode':'on','n1':'u','n2':'v','n3':44,'n4':9,'n5':'w'},action='go').predicted_state,{'r':'yes'})

if __name__=='__main__': unittest.main()
