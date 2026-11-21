import unittest
from asm import __version__
from asm.transition_mechanism import LocalRecurrentTransitionMechanism

class Alpha11MechanismAbstractionTests(unittest.TestCase):
    def build(self, **kw):
        opts=dict(hidden_dim=12,train_steps=1,max_outcomes=16,outcome_capacity_limit=128,
                  retention_anchor_limit=32,abstraction_min_support=4,
                  abstraction_min_precision=.95,abstraction_min_diversity=3,
                  abstraction_max_dropped_features=2,abstraction_max_candidates=256,
                  abstraction_exception_limit=32,seed=41)
        opts.update(kw)
        m=LocalRecurrentTransitionMechanism('a11_unit',**opts);m.replay_limit=24;m.replay_batch_limit=4
        return m

    def test_version(self): self.assertEqual(__version__,'0.4.0-alpha.7.9')

    def test_visible_nuisance_features_can_be_abstracted(self):
        m=self.build()
        for v in range(8):
            m.observe(entity_id=f'e{v}',state={'mode':'on','token':f't{v}','batch':v%3},action='go',after_state={'r':'yes'})
        p=m.predict(entity_id='new',state={'mode':'on','token':'unseen','batch':99},action='go')
        self.assertEqual(p.predicted_state,{'r':'yes'})
        self.assertGreaterEqual(m.stats()['abstraction_promoted'],1)

    def test_random_contradictions_do_not_promote_rule(self):
        m=self.build(abstraction_min_support=6)
        for v in range(12):
            m.observe(entity_id=f'e{v}',state={'mode':'x','token':f't{v}','batch':v%3},action='go',after_state={'r':v%4})
        self.assertEqual(m.stats()['abstraction_promoted'],0)

    def test_rare_exception_overrides_but_does_not_destroy_rule(self):
        m=self.build()
        for v in range(8):
            m.observe(entity_id=f'e{v}',state={'mode':'on','token':f't{v}','batch':v%3},action='go',after_state={'r':'normal'})
        exc={'mode':'on','token':'exception','batch':77}
        for _ in range(3):m.observe(entity_id='exc',state=exc,action='go',after_state={'r':'exception'})
        self.assertEqual(m.predict(entity_id='exc2',state=exc,action='go').predicted_state,{'r':'exception'})
        self.assertEqual(m.predict(entity_id='fresh',state={'mode':'on','token':'new','batch':88},action='go').predicted_state,{'r':'normal'})

    def test_diverse_contradictions_demote_rule(self):
        m=self.build()
        for v in range(8):m.observe(entity_id=f'e{v}',state={'mode':'on','token':f't{v}','batch':v%3},action='go',after_state={'r':'normal'})
        for j in range(3):m.observe(entity_id=f'c{j}',state={'mode':'on','token':f'c{j}','batch':50+j},action='go',after_state={'r':'changed'})
        slot,_,_,_=m._query_abstraction({'mode':'on','token':'brandnew','batch':99},'go',None,1.0)
        self.assertIsNone(slot)

    def test_serialization_preserves_rules_and_exceptions(self):
        m=self.build()
        for v in range(8):m.observe(entity_id=f'e{v}',state={'mode':'on','token':f't{v}','batch':v%3},action='go',after_state={'r':'normal'})
        exc={'mode':'on','token':'exception','batch':77}
        for _ in range(2):m.observe(entity_id='exc',state=exc,action='go',after_state={'r':'exception'})
        r=self.build();r.import_blob(m.export_blob())
        self.assertEqual(r.predict(entity_id='new',state={'mode':'on','token':'unseen','batch':99},action='go').predicted_state,{'r':'normal'})
        self.assertEqual(r.predict(entity_id='exc2',state=exc,action='go').predicted_state,{'r':'exception'})

if __name__=='__main__':unittest.main()
