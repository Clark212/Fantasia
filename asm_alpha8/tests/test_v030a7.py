import io
import unittest

import torch

from asm import __version__
from asm.transition_mechanism import LocalRecurrentTransitionMechanism


class Alpha7ElasticCapacityTests(unittest.TestCase):
    def build(self, limit=128):
        return LocalRecurrentTransitionMechanism(
            'elastic_test', hidden_dim=16, train_steps=1, learning_rate=.01,
            seed=17, max_outcomes=32, outcome_capacity_limit=limit,
            retention_anchor_limit=128,
        )

    @staticmethod
    def case(i):
        return {'kind':'machine','mode':i}, 'advance', {'kind':'machine','result':i}

    def test_version(self):
        self.assertEqual(__version__, '0.4.0-alpha.7.9')

    def test_33rd_outcome_expands_head(self):
        m=self.build()
        for i in range(33):
            s,a,o=self.case(i); m.observe(entity_id=f'e{i}',state=s,action=a,after_state=o)
        d=m.stats()
        self.assertEqual(d['known_outcomes'],33)
        self.assertEqual(d['outcome_capacity'],64)
        self.assertEqual(d['capacity_history'],[32,64])

    def test_expansion_copies_old_output_rows_exactly(self):
        m=self.build()
        before_w=m.net.head.weight.detach().clone()
        before_b=m.net.head.bias.detach().clone()
        m._resize_output_head(64)
        self.assertTrue(torch.equal(m.net.head.weight[:32],before_w))
        self.assertTrue(torch.equal(m.net.head.bias[:32],before_b))

    def test_expanded_blob_reloads_into_initial_32_model(self):
        m=self.build()
        m._resize_output_head(64)
        blob=m.export_blob()
        r=self.build(); r.import_blob(blob)
        self.assertEqual(r.stats()['outcome_capacity'],64)
        self.assertEqual(r.stats()['capacity_history'],[32,64])

    def test_capacity_limit_is_enforced(self):
        m=self.build(limit=32)
        with self.assertRaises(RuntimeError):
            for i in range(33):
                s,a,o=self.case(i); m.observe(entity_id=f'e{i}',state=s,action=a,after_state=o)

    def test_alpha6_blob_without_elastic_fields_still_loads(self):
        m=self.build(); s,a,o=self.case(0); m.observe(entity_id='e',state=s,action=a,after_state=o)
        payload=torch.load(io.BytesIO(m.export_blob()),map_location='cpu',weights_only=False)
        for key in ('outcome_capacity_limit','outcome_growth_factor','capacity_expansions','capacity_history'):
            payload.pop(key,None)
        buf=io.BytesIO(); torch.save(payload,buf)
        r=self.build(); r.import_blob(buf.getvalue())
        self.assertEqual(r.stats()['known_outcomes'],1)
        self.assertEqual(r.stats()['outcome_capacity'],32)


if __name__=='__main__': unittest.main()
