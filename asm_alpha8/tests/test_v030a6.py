import os
import tempfile
import unittest

from asm import __version__
from asm.transition_mechanism import TransitionMechanismBank


class Alpha6ContinualRetentionTests(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix='.db'); os.close(fd)
        self.bank = TransitionMechanismBank(
            self.path, hidden_dim=16, train_steps=1, learning_rate=.01,
            seed=17, max_outcomes=32,
        )

    def tearDown(self):
        try: self.bank.close()
        except Exception: pass
        for suffix in ('', '-wal', '-shm'):
            try: os.remove(self.path + suffix)
            except FileNotFoundError: pass

    @staticmethod
    def case(i):
        return (
            {'kind':'machine','mode':i,'phase':0}, 'advance',
            {'kind':'machine','mode':i,'phase':1,'result':i},
        )

    def teach(self, ids, reps=3):
        for i in ids:
            s,a,o=self.case(i)
            for r in range(reps):
                self.bank.observe('shared', entity_id=f'e_{i}_{r}', state=s, action=a, after_state=o)

    def test_version(self):
        self.assertEqual(__version__, '0.4.0-alpha.7.9')

    def test_retention_anchors_created_per_visible_outcome(self):
        self.teach(range(6), reps=2)
        d=self.bank.stats()['detail'][0]
        self.assertEqual(d['retention_anchor_outcomes'], 6)
        self.assertGreaterEqual(d['retention_anchors'], 6)

    def test_retention_anchors_are_bounded(self):
        # Reuse one outcome while varying visible inputs, so the anchor table can
        # hit its cap without exceeding max_outcomes.
        out={'kind':'machine','phase':1,'result':'same'}
        for i in range(110):
            self.bank.observe('shared', entity_id=f'b{i}', state={'kind':'machine','mode':i}, action='advance', after_state=out)
        d=self.bank.stats()['detail'][0]
        self.assertLessEqual(d['retention_anchors'], d['retention_anchor_limit'])
        self.assertEqual(d['retention_anchor_limit'], 96)

    def test_retention_anchors_persist_restart(self):
        self.teach(range(5), reps=2)
        before=self.bank.stats()['detail'][0]
        self.bank.close()
        self.bank=TransitionMechanismBank(self.path, hidden_dim=16, train_steps=1, learning_rate=.01, seed=17, max_outcomes=32)
        after=self.bank.stats()['detail'][0]
        self.assertEqual(after['retention_anchors'], before['retention_anchors'])
        self.assertEqual(after['retention_anchor_outcomes'], before['retention_anchor_outcomes'])

    def test_alpha5_blob_without_anchors_backfills_from_replay(self):
        self.teach(range(4), reps=2)
        mech=self.bank._get('shared', create=False)
        payload=mech.export_blob()
        # Simulate alpha.5 by loading then clearing the new fields before persistence.
        import io, torch
        obj=torch.load(io.BytesIO(payload), map_location='cpu', weights_only=False)
        for key in ('retention_anchors','retention_ambiguous_signatures','retention_anchor_limit','retention_anchor_batch_limit','retention_anchor_cursor'):
            obj.pop(key, None)
        buf=io.BytesIO(); torch.save(obj, buf)
        self.bank.db.execute('UPDATE world_mechanism_models SET model_blob=? WHERE mechanism_type=?',(buf.getvalue(),'shared'))
        self.bank.db.commit(); self.bank.mechanisms.clear()
        loaded=self.bank._get('shared', create=False)
        self.assertGreater(len(loaded.retention_anchors), 0)
        self.assertGreaterEqual(len({int(v['slot']) for v in loaded.retention_anchors.values()}), 4)


if __name__ == '__main__': unittest.main()
