import tempfile
import unittest
from pathlib import Path

from asm import __version__
from asm.planning import ProbabilisticInternalPlanner, StateGoal
from asm.transition_mechanism import LocalRecurrentTransitionMechanism


class TableDistributionPredictor:
    def __init__(self, table):
        self.table = table

    def __call__(self, mechanism_type, *, entity_id, state, action, neighborhood=None,
                 dt=1.0, simulation_context=None, top_k=4, empirical_min_support=None):
        rows = list(self.table.get((state.get('loc'), action), []))
        outcomes = [
            {'predicted_state': {'loc': loc}, 'probability': float(prob),
             'conditional_probability': float(prob), 'support': 100, 'outcome_slot': i}
            for i, (loc, prob) in enumerate(rows[:top_k])
        ]
        known = sum(x['probability'] for x in outcomes)
        return {
            'mechanism_type': mechanism_type, 'entity_id': entity_id,
            'outcomes': outcomes, 'unknown_probability': max(0.0, 1.0-known),
            'support': 100, 'probability_source': 'test_table', 'calibrated': True,
            '_simulation_context': simulation_context, '_simulation_context_key': '',
        }


class PlanningAlpha3Tests(unittest.TestCase):
    def test_version(self):
        self.assertEqual(__version__, '0.4.0-alpha.7.9')

    def test_empirical_distribution_exposes_80_20_and_unknown(self):
        m = LocalRecurrentTransitionMechanism('a3-dist', hidden_dim=8, train_steps=1,
                                               max_outcomes=8, outcome_capacity_limit=32, seed=31)
        for i in range(16):
            m.observe(entity_id=f'g{i}', state={'loc':'start'}, action='risky', after_state={'loc':'goal'})
        for i in range(4):
            m.observe(entity_id=f'h{i}', state={'loc':'start'}, action='risky', after_state={'loc':'hazard'})
        d = m.predict_distribution_simulated(entity_id='probe', state={'loc':'start'}, action='risky')
        self.assertTrue(d['calibrated'])
        probs = {x['predicted_state']['loc']: x['conditional_probability'] for x in d['outcomes']}
        self.assertAlmostEqual(probs['goal'], .8, places=6)
        self.assertAlmostEqual(probs['hazard'], .2, places=6)
        self.assertGreater(d['unknown_probability'], 0.0)
        self.assertLess(d['unknown_probability'], .06)

    def test_distribution_persists(self):
        m = LocalRecurrentTransitionMechanism('a3-persist', hidden_dim=8, train_steps=1,
                                               max_outcomes=8, outcome_capacity_limit=32, seed=32)
        for i in range(8):
            m.observe(entity_id=f'e{i}', state={'s':0}, action='a', after_state={'s':1 if i < 6 else 2})
        blob = m.export_blob()
        restored = LocalRecurrentTransitionMechanism('a3-persist', hidden_dim=8, train_steps=1,
                                                      max_outcomes=8, outcome_capacity_limit=32, seed=32)
        restored.import_blob(blob)
        d = restored.predict_distribution_simulated(entity_id='p', state={'s':0}, action='a')
        probs = {x['predicted_state']['s']: x['conditional_probability'] for x in d['outcomes']}
        self.assertAlmostEqual(probs[1], .75, places=6)
        self.assertAlmostEqual(probs[2], .25, places=6)

    def test_80_20_tail_risk_prefers_safe_route(self):
        table = {
            ('start','risky'):[('goal',.80),('hazard',.20)],
            ('start','safe'):[('mid',1.0)],
            ('mid','safe'):[('goal',1.0)],
            ('mid','risky'):[('hazard',1.0)],
        }
        planner = ProbabilisticInternalPlanner(TableDistributionPredictor(table), max_horizon=2,
                    beam_width=6, max_expansions=32, risk_aversion=2.0,
                    max_hazard_probability=.10, max_unknown_probability=.1)
        r = planner.plan('risk', entity_id='x', initial_state={'loc':'start'},
                         actions=('risky','safe'), goal=StateGoal({'loc':'goal'},{'loc':'hazard'}), horizon=2)
        self.assertEqual(r['status'], 'risk_aware_plan_found')
        self.assertEqual(r['best']['actions'], ['safe','safe'])
        self.assertAlmostEqual(r['best']['hazard_probability'], 0.0)

    def test_rare_five_percent_hazard_can_be_rejected(self):
        table = {
            ('start','risky'):[('goal',.95),('hazard',.05)],
            ('start','safe'):[('mid',1.0)],
            ('mid','safe'):[('goal',1.0)],
            ('mid','risky'):[('hazard',1.0)],
        }
        planner = ProbabilisticInternalPlanner(TableDistributionPredictor(table), max_horizon=2,
                    beam_width=6, max_expansions=32, risk_aversion=4.0,
                    max_hazard_probability=.02, max_unknown_probability=.1)
        r = planner.plan('risk', entity_id='x', initial_state={'loc':'start'},
                         actions=('risky','safe'), goal=StateGoal({'loc':'goal'},{'loc':'hazard'}), horizon=2)
        self.assertEqual(r['best']['actions'], ['safe','safe'])

    def test_action_costs_prefer_cheap_route(self):
        table = {
            ('start','jump'):[('goal',1.0)],
            ('start','step'):[('mid',1.0)],
            ('mid','step'):[('goal',1.0)],
            ('mid','jump'):[('goal',1.0)],
        }
        planner = ProbabilisticInternalPlanner(TableDistributionPredictor(table), max_horizon=2,
                    beam_width=6, max_expansions=32, risk_aversion=1.0, cost_weight=.03,
                    max_unknown_probability=.1)
        r = planner.plan('cost', entity_id='x', initial_state={'loc':'start'},
                         actions=('jump','step'), goal=StateGoal({'loc':'goal'}),
                         action_costs={'jump':100.0,'step':1.0}, horizon=2)
        self.assertEqual(r['best']['actions'], ['step','step'])
        self.assertEqual(r['best']['expected_cost'], 2.0)

    def test_multistep_probability_propagates(self):
        table = {
            ('start','go'):[('mid',.90),('hazard',.10)],
            ('mid','go'):[('goal',.90),('hazard',.10)],
        }
        planner = ProbabilisticInternalPlanner(TableDistributionPredictor(table), max_horizon=2,
                    beam_width=3, max_expansions=16, risk_aversion=.1,
                    min_goal_probability=.7, max_hazard_probability=.3, max_unknown_probability=.1)
        r = planner.plan('prob', entity_id='x', initial_state={'loc':'start'}, actions=('go',),
                         goal=StateGoal({'loc':'goal'},{'loc':'hazard'}), horizon=2)
        self.assertAlmostEqual(r['best']['goal_probability'], .81, places=6)
        self.assertAlmostEqual(r['best']['hazard_probability'], .19, places=6)

    def test_uncalibrated_neural_fallback_keeps_unknown_mass(self):
        m = LocalRecurrentTransitionMechanism('a3-unknown', hidden_dim=8, train_steps=1,
                                               max_outcomes=8, outcome_capacity_limit=32, seed=39)
        for i in range(3):
            m.observe(entity_id=f'e{i}',state={'x':0},action='a',after_state={'x':1})
        d=m.predict_distribution_simulated(entity_id='p',state={'x':99},action='a')
        self.assertFalse(d['calibrated'])
        self.assertGreaterEqual(d['unknown_probability'], .25)

    def test_distribution_prediction_is_read_only(self):
        m = LocalRecurrentTransitionMechanism('a3-pure', hidden_dim=8, train_steps=1,
                                               max_outcomes=8, outcome_capacity_limit=32, seed=41)
        for i in range(8):
            m.observe(entity_id=f'e{i}',state={'x':0},action='a',after_state={'x':1})
        before = (m.total_observations, m.abstraction_hits, m.abstraction_misses,
                  m.consolidation_hits, m.consolidation_misses,
                  {k:dict(v) for k,v in m.conditional_outcome_support.items()})
        m.predict_distribution_simulated(entity_id='probe',state={'x':0},action='a')
        after = (m.total_observations, m.abstraction_hits, m.abstraction_misses,
                 m.consolidation_hits, m.consolidation_misses,
                 {k:dict(v) for k,v in m.conditional_outcome_support.items()})
        self.assertEqual(before, after)


if __name__ == '__main__':
    unittest.main()
