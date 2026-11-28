import os
import tempfile
import unittest
from pathlib import Path

from asm import __version__
from asm.transition_mechanism import TransitionMechanismBank


class Alpha5CompetitiveRoutingTests(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        self.bank = TransitionMechanismBank(
            self.path,
            hidden_dim=8,
            train_steps=1,
            learning_rate=.012,
            seed=17,
            scheduler_max_calls=1,
            scheduler_medium_calls=3,
            scheduler_min_relevance=.45,
            scheduler_high_confidence=.74,
            scheduler_low_confidence=.46,
            scheduler_min_margin=.08,
            scheduler_calibration_min_support=4,
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

    def seed_variant(self, mechanism, variant, *, repeats=4):
        before = {'kind': 'valve', 'variant': variant, 'open': False}
        after = {'kind': 'valve', 'variant': variant, 'open': True}
        for i in range(repeats):
            self.bank.observe(
                mechanism,
                entity_id=f'{mechanism}_{i}',
                state=before,
                action='open',
                after_state=after,
            )
        return before, after

    def test_version(self):
        self.assertEqual(__version__, '0.4.0-alpha.7.9')

    def test_confident_competition_selects_top1(self):
        normal, _ = self.seed_variant('normal_valve', 'normal')
        self.seed_variant('safety_valve', 'safety')
        route = self.bank.route(state=normal, action='open', mode='seismic')
        self.assertEqual(route['reason'], 'seismic_confident_topk')
        self.assertEqual(route['selected'][0]['mechanism_type'], 'normal_valve')
        self.assertEqual(len(route['selected']), 1)
        self.assertGreaterEqual(route['margin'], .08)
        self.assertGreaterEqual(route['routing_confidence'], .74)

    def test_ambiguous_input_widens_instead_of_faking_confidence(self):
        base = {'kind': 'valve', 'open': False}
        for mechanism in ('a_valve', 'b_valve'):
            after = {'kind': 'valve', 'open': True, 'route': mechanism}
            for i in range(3):
                self.bank.observe(mechanism, entity_id=f'{mechanism}_{i}', state=base, action='open', after_state=after)
        route = self.bank.route(state=base, action='open', mode='seismic')
        self.assertEqual(route['reason'], 'seismic_competitive_topk')
        self.assertEqual(route['margin'], 0.0)
        self.assertEqual(len(route['selected']), 2)

    def test_prediction_error_teaches_negative_applicability(self):
        base = {'kind': 'valve', 'open': False}
        for mechanism in ('normal', 'safety'):
            after = {'kind': 'valve', 'open': True, 'route': mechanism}
            for i in range(3):
                self.bank.observe(mechanism, entity_id=f'{mechanism}_{i}', state=base, action='open', after_state=after)

        query = {'kind': 'valve', 'open': False, 'pressure_safe': False}
        before = self.bank.route(state=query, action='open', mode='seismic')
        normal_before = next(x['relevance'] for x in before['candidates'] if x['mechanism_type'] == 'normal')
        self.assertEqual(before['candidates'][0]['mechanism_type'], 'normal')

        routed = self.bank.predict_routed(entity_id='feedback_entity', state=query, action='open', mode='seismic', recover=False)
        self.assertIn('normal', [x['mechanism_type'] for x in routed['predictions']])
        learned = self.bank.observe(
            'safety', entity_id='feedback_entity', state=query, action='open',
            after_state={'kind': 'valve', 'open': False, 'route': 'safety'},
        )
        self.assertIsNotNone(learned['routing_feedback'])
        self.assertFalse(learned['routing_feedback']['top_correct'])
        self.assertIn('normal', learned['routing_feedback']['wrong_penalized'])

        after = self.bank.route(state=query, action='open', mode='seismic')
        normal_after = next(x for x in after['candidates'] if x['mechanism_type'] == 'normal')
        self.assertLess(normal_after['relevance'], normal_before)
        self.assertGreater(normal_after['negative_support'], 0)
        self.assertEqual(after['candidates'][0]['mechanism_type'], 'safety')

    def test_empirical_confidence_calibration_activates_after_feedback(self):
        state, after = self.seed_variant('door_like', 'main', repeats=3)
        # Repeated correct routed observations populate one confidence bucket.
        for i in range(5):
            entity = f'cal_{i}'
            self.bank.predict_routed(entity_id=entity, state=state, action='open', mode='seismic', recover=False)
            self.bank.observe('door_like', entity_id=entity, state=state, action='open', after_state=after)
        route = self.bank.route(state=state, action='open', mode='seismic')
        self.assertEqual(route['calibration_source'], 'empirical')
        self.assertGreaterEqual(route['calibration_support'], 4)
        self.assertGreaterEqual(self.bank.stats()['scheduler']['calibration_samples'], 4)

    def test_routing_evidence_and_calibration_persist(self):
        state, after = self.seed_variant('persist_mech', 'p', repeats=3)
        for i in range(4):
            entity = f'pcal_{i}'
            self.bank.predict_routed(entity_id=entity, state=state, action='open', mode='seismic', recover=False)
            self.bank.observe('persist_mech', entity_id=entity, state=state, action='open', after_state=after)
        self.bank.close()
        self.bank = TransitionMechanismBank(
            self.path, hidden_dim=8, train_steps=1, learning_rate=.012, seed=17,
            scheduler_calibration_min_support=4,
        )
        route = self.bank.route(state=state, action='open', mode='seismic')
        stats = self.bank.stats()['scheduler']
        self.assertEqual(route['selected'][0]['mechanism_type'], 'persist_mech')
        self.assertGreater(stats['routing_evidence_features'], 0)
        self.assertGreaterEqual(stats['calibration_samples'], 4)
        self.assertEqual(route['calibration_source'], 'empirical')

    def test_ood_still_falls_back_dense(self):
        state, _ = self.seed_variant('known_a', 'a')
        self.seed_variant('known_b', 'b')
        routed = self.bank.predict_routed(
            entity_id='ood', state={'kind': 'alien_device', 'phase': 7}, action='pulse', mode='seismic'
        )
        self.assertTrue(routed['fallback'])
        self.assertEqual(routed['calls'], routed['total_mechanisms'])
        self.assertIn(routed['reason'], {'low_relevance_dense_fallback', 'low_confidence_dense_fallback'})


if __name__ == '__main__':
    unittest.main()
