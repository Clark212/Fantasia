import os
import tempfile
import unittest

from asm import ASMConfig, ASMEngine, __version__
from asm.transition_mechanism import TransitionMechanismBank


BASE = [
    ({"mode": "closed"}, "open", {"mode": "open"}),
    ({"mode": "open"}, "close", {"mode": "closed"}),
    ({"mode": "closed"}, "lock", {"mode": "locked"}),
    ({"mode": "locked"}, "unlock", {"mode": "closed"}),
    ({"mode": "locked"}, "open", {"mode": "locked"}),
]


class TransitionMechanismTests(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        self.bank = TransitionMechanismBank(
            self.path, hidden_dim=32, train_steps=5, learning_rate=0.012, seed=7
        )

    def tearDown(self):
        try:
            self.bank.close()
        except Exception:
            pass
        for suffix in ('', '-wal', '-shm'):
            try:
                os.remove(self.path + suffix)
            except FileNotFoundError:
                pass

    def train_base(self, epochs=8):
        for _ in range(epochs):
            for entity in ('door_a', 'door_b', 'door_c'):
                for state, action, after in BASE:
                    self.bank.observe(
                        'door_state', entity_id=entity, state=state,
                        action=action, after_state=after,
                    )

    def test_version(self):
        self.assertEqual(__version__, '0.4.0-alpha.7.9')

    def test_cold_mechanism_abstains(self):
        out = self.bank.predict(
            'door_state', entity_id='door_x', state={'mode': 'closed'}, action='open'
        )
        self.assertIsNone(out['predicted_state'])
        self.assertEqual(out['uncertainty'], 1.0)

    def test_shared_weights_transfer_to_unseen_entity(self):
        self.train_base()
        correct = 0
        for state, action, after in BASE:
            out = self.bank.predict(
                'door_state', entity_id='door_d', state=state, action=action
            )
            correct += out['predicted_state'] == after
        self.assertEqual(correct, len(BASE))

    def test_surprise_raises_uncertainty_then_adaptation_reduces_it(self):
        self.train_base()
        state = {'mode': 'closed', 'jammed': True}
        before = self.bank.predict('door_state', entity_id='door_j', state=state, action='open')
        first = self.bank.observe(
            'door_state', entity_id='door_j', state=state, action='open',
            after_state={'mode': 'closed', 'jammed': True},
        )
        shocked = first['after_training_prediction']
        self.assertGreater(shocked['uncertainty'], before['uncertainty'] + 0.25)
        for _ in range(10):
            self.bank.observe(
                'door_state', entity_id='door_j', state=state, action='open',
                after_state={'mode': 'closed', 'jammed': True},
            )
        adapted = self.bank.predict('door_state', entity_id='door_j', state=state, action='open')
        self.assertEqual(adapted['predicted_state'], {'mode': 'closed', 'jammed': True})
        self.assertLess(adapted['uncertainty'], shocked['uncertainty'])

    def test_exception_learning_does_not_erase_general_rule(self):
        self.train_base()
        jammed = {'mode': 'closed', 'jammed': True}
        for _ in range(12):
            self.bank.observe(
                'door_state', entity_id='door_j', state=jammed, action='open',
                after_state={'mode': 'closed', 'jammed': True},
            )
        ordinary = self.bank.predict(
            'door_state', entity_id='door_new', state={'mode': 'closed'}, action='open'
        )
        self.assertEqual(ordinary['predicted_state'], {'mode': 'open'})

    def test_learned_mechanism_survives_reload(self):
        self.train_base(epochs=5)
        self.bank.close()
        self.bank = TransitionMechanismBank(
            self.path, hidden_dim=32, train_steps=5, learning_rate=0.012, seed=7
        )
        out = self.bank.predict(
            'door_state', entity_id='door_new', state={'mode': 'locked'}, action='unlock'
        )
        self.assertEqual(out['predicted_state'], {'mode': 'closed'})
        self.assertGreater(out['support'], 0)


class EngineTransitionIntegrationTests(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        cfg = ASMConfig(
            snapshot_every_events=999999,
            transition_hidden_dim=24,
            transition_train_steps=3,
        )
        self.engine = ASMEngine(self.path, config=cfg)

    def tearDown(self):
        self.engine.close()
        for suffix in ('', '-wal', '-shm'):
            try:
                os.remove(self.path + suffix)
            except FileNotFoundError:
                pass

    def test_engine_exposes_learning_and_prediction_api(self):
        learned = self.engine.learn_world_transition(
            'switch_state', entity_id='switch_a', state={'on': False},
            action='toggle', after_state={'on': True},
        )
        self.assertTrue(learned['learned'])
        pred = self.engine.predict_world_transition(
            'switch_state', entity_id='switch_b', state={'on': False}, action='toggle'
        )
        self.assertIsNotNone(pred['predicted_state'])

    def test_status_reports_transition_bank(self):
        self.engine.learn_world_transition(
            'switch_state', entity_id='switch_a', state={'on': False},
            action='toggle', after_state={'on': True},
        )
        status = self.engine.language_core_status()
        self.assertIn('transition_mechanisms', status)
        self.assertGreaterEqual(status['transition_mechanisms']['mechanisms'], 1)


if __name__ == '__main__':
    unittest.main()
