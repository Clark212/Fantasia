import tempfile
import unittest
from pathlib import Path

from asm import __version__
from asm.transition_mechanism import LocalRecurrentTransitionMechanism, TransitionMechanismBank


class Alpha8ConsolidationTests(unittest.TestCase):
    def test_version(self):
        self.assertEqual(__version__, '0.4.0-alpha.7.9')

    def build(self, **kw):
        m = LocalRecurrentTransitionMechanism(
            'a8_unit', hidden_dim=24, train_steps=1, learning_rate=.01,
            max_outcomes=8, outcome_capacity_limit=32,
            retention_anchor_limit=8, retention_anchor_batch_limit=2,
            consolidation_table_size=128, consolidation_hashes=3,
            consolidation_min_support=2, **kw,
        )
        m.replay_limit = 4
        return m

    def test_fixed_memory_does_not_grow_with_mappings(self):
        m = self.build()
        before = m.stats()['consolidation_bytes']
        for i in range(12):
            state={'kind':'u','mode':i}; out={'kind':'u','result':i}
            for r in range(3):
                m.observe(entity_id=f'e{i}_{r}', state=state, action='go', after_state=out)
        st=m.stats()
        self.assertEqual(before, st['consolidation_bytes'])
        self.assertEqual(st['consolidation_bytes'], 128*3*(8+4+2))
        self.assertLessEqual(st['retention_anchors'], 8)

    def test_stable_mapping_is_retrieved_from_consolidation(self):
        m=self.build()
        m.retention_anchor_limit=1
        for i in range(2):
            state={'kind':'u','mode':i}; out={'kind':'u','result':i}
            for r in range(4):
                m.observe(entity_id=f'e{i}_{r}', state=state, action='go', after_state=out)
        # Force neural head toward the wrong class; exact consolidation should
        # still retrieve the stable visible mapping after replay pressure begins.
        import torch
        with torch.no_grad():
            m.net.head.weight.zero_(); m.net.head.bias.zero_(); m.net.head.bias[1]=20.0
        p=m.predict(entity_id='fresh', state={'kind':'u','mode':0}, action='go')
        self.assertEqual(p.predicted_state, {'kind':'u','result':0})
        self.assertGreater(m.stats()['consolidation_hits'], 0)

    def test_ambiguous_visible_mapping_is_excluded(self):
        m=self.build()
        state={'kind':'u','mode':0}
        for r in range(3): m.observe(entity_id=f'a{r}', state=state, action='go', after_state={'r':0})
        for r in range(3): m.observe(entity_id=f'b{r}', state=state, action='go', after_state={'r':1})
        sig=m._input_signature(state,'go',None,1.0)
        self.assertIn(sig, m.retention_ambiguous_signatures)
        slot, conf, support=m._query_consolidation(sig)
        self.assertIsNone(slot)
        self.assertEqual(support,0)

    def test_consolidation_survives_serialization(self):
        m=self.build()
        m.retention_anchor_limit=1
        for i in range(5):
            for r in range(3):
                m.observe(entity_id=f'{i}_{r}', state={'k':i}, action='go', after_state={'r':i})
        blob=m.export_blob(); r=self.build(); r.import_blob(blob)
        self.assertEqual(r.stats()['consolidation_bytes'], m.stats()['consolidation_bytes'])
        for i in range(5):
            self.assertEqual(r.predict(entity_id=f'x{i}', state={'k':i}, action='go').predicted_state, {'r':i})

    def test_bank_wires_consolidation_config(self):
        with tempfile.TemporaryDirectory() as td:
            b=TransitionMechanismBank(Path(td)/'x.db', consolidation_table_size=256, consolidation_hashes=2, consolidation_min_support=3)
            m=b._new('x')
            self.assertEqual(m.consolidation_table_size,256)
            self.assertEqual(m.consolidation_hashes,2)
            self.assertEqual(m.consolidation_min_support,3)
            b.close()

if __name__ == '__main__': unittest.main()
