from __future__ import annotations
import unittest

from asm import __version__
from asm.planning import BeliefStateInternalPlanner, DiscreteBeliefState, StateGoal


class InvalidLikelihoodModel:
    def __call__(self, mechanism_type, *, entity_id, state, action, neighborhood=None,
                 dt=1.0, simulation_context=None, top_k=4, empirical_min_support=None):
        if state.get('loc') != 'start':
            outs=[]
        elif action == 'sense':
            outs=[
                {'predicted_state':{'loc':'start'}, 'observation':'x',
                 'hypothesis_likelihoods':{'A':.9,'B':.9}},
                {'predicted_state':{'loc':'start'}, 'observation':'y',
                 'hypothesis_likelihoods':{'A':.9,'B':.9}},
            ]
        elif action == 'chooseA':
            outs=[
                {'predicted_state':{'loc':'goal'}, 'hypothesis_likelihoods':{'A':1,'B':0}},
                {'predicted_state':{'loc':'hazard'}, 'hypothesis_likelihoods':{'A':0,'B':1}},
            ]
        elif action == 'chooseB':
            outs=[
                {'predicted_state':{'loc':'goal'}, 'hypothesis_likelihoods':{'A':0,'B':1}},
                {'predicted_state':{'loc':'hazard'}, 'hypothesis_likelihoods':{'A':1,'B':0}},
            ]
        else:
            outs=[]
        return {'outcomes':outs[:top_k], 'unknown_probability':0.0 if outs else 1.0,
                'calibrated':True, '_simulation_context':simulation_context,
                '_simulation_context_key':''}


class Alpha51BeliefHardeningTests(unittest.TestCase):
    def test_version(self):
        self.assertEqual(__version__, '0.4.0-alpha.7.9')

    def test_extreme_contradictory_evidence_can_resurrect_underflowed_hypothesis(self):
        b=DiscreteBeliefState.from_mapping({'A':.5,'B':.5})
        for _ in range(200):
            b=b.update({'A':.99,'B':.01})
        self.assertEqual(b.as_dict()['B'], 0.0)  # ordinary float view underflows
        self.assertLess(b.as_log_dict()['B'], -745.0)  # internal evidence remains
        for _ in range(200):
            b=b.update({'A':.01,'B':.99})
        self.assertAlmostEqual(b.as_dict()['A'], .5, 11)
        self.assertAlmostEqual(b.as_dict()['B'], .5, 11)

    def test_extreme_log_odds_get_distinct_memo_keys(self):
        a=DiscreteBeliefState.from_mapping({'A':.5,'B':.5})
        b=DiscreteBeliefState.from_mapping({'A':.5,'B':.5})
        for _ in range(170): a=a.update({'A':.99,'B':.01})
        for _ in range(200): b=b.update({'A':.99,'B':.01})
        self.assertEqual(a.as_dict()['B'], 0.0)
        self.assertEqual(b.as_dict()['B'], 0.0)
        self.assertNotEqual(a.key(), b.key())

    def test_tiny_prior_can_recover(self):
        b=DiscreteBeliefState.from_mapping({'A':1.0,'B':1e-300})
        for _ in range(200):
            b=b.update({'A':.01,'B':.99})
        self.assertEqual(b.most_likely()[0], 'B')

    def test_malformed_likelihood_matrix_fails_closed(self):
        planner=BeliefStateInternalPlanner(
            InvalidLikelihoodModel(), max_horizon=2, max_expansions=64,
            risk_aversion=0.0, unknown_risk_weight=0.0, cost_weight=0.0,
            proximity_weight=0.0, step_penalty=0.0, min_goal_probability=0.0,
            max_hazard_probability=1.0, max_unknown_probability=1.0,
        )
        r=planner.plan('bad',entity_id='x',initial_state={'loc':'start'},
            actions=('sense','chooseA','chooseB'),goal=StateGoal({'loc':'goal'},{'loc':'hazard'}),
            initial_belief={'A':.5,'B':.5},horizon=2)
        self.assertGreaterEqual(r['invalid_likelihood_models'],1)
        self.assertNotEqual(r['policy_graph'][r['root_node']]['action'],'sense')

    def test_exact_zero_likelihood_still_eliminates_by_design(self):
        b=DiscreteBeliefState.from_mapping({'A':.5,'B':.5}).update({'A':1.0,'B':0.0})
        self.assertEqual(b.as_dict(), {'A':1.0})
        with self.assertRaises(ValueError):
            b.update({'A':0.0,'B':1.0})


if __name__ == '__main__':
    unittest.main()
