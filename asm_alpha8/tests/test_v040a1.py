import unittest

from asm import __version__
from asm.planning import BoundedInternalPlanner, StateGoal


class FakePredictor:
    def __init__(self):
        self.calls = 0

    def __call__(self, mechanism_type, *, entity_id, state, action, neighborhood=None, dt=1.0, simulation_context=None):
        self.calls += 1
        pos = int(state.get('position', 0))
        if action == 'right':
            nxt = min(3, pos + 1)
            conf = 0.90
        elif action == 'left':
            nxt = max(0, pos - 1)
            conf = 0.90
        elif action == 'risky':
            nxt = 3
            conf = 0.25
        else:
            return {'mechanism_type': mechanism_type, 'predicted_state': None, 'confidence': 0.0, 'uncertainty': 1.0, '_simulation_context': simulation_context, '_simulation_context_key': ''}
        return {'mechanism_type': mechanism_type, 'predicted_state': {'position': nxt}, 'confidence': conf, 'uncertainty': 1.0-conf, '_simulation_context': simulation_context, '_simulation_context_key': ''}


class PlanningAlpha1Tests(unittest.TestCase):
    def build(self, **kw):
        opts=dict(max_horizon=5, beam_width=8, max_expansions=64,
                  uncertainty_penalty=.35, step_penalty=.01)
        opts.update(kw)
        predictor=FakePredictor()
        return BoundedInternalPlanner(predictor, **opts), predictor

    def test_version(self):
        self.assertEqual(__version__, '0.4.0-alpha.7.9')

    def test_finds_three_step_plan(self):
        p,_=self.build()
        result=p.plan('movement', entity_id='sim', initial_state={'position':0},
                      actions=['left','right'], goal=StateGoal({'position':3}), horizon=3)
        self.assertEqual(result['status'],'goal_reached')
        self.assertEqual(result['best']['actions'],['right','right','right'])
        self.assertEqual(result['best']['predicted_state'],{'position':3})

    def test_uncertainty_compounds_with_depth(self):
        p,_=self.build()
        result=p.plan('movement', entity_id='sim', initial_state={'position':0},
                      actions=['right'], goal=StateGoal({'position':3}), horizon=3)
        trace=result['best']['trace']
        self.assertEqual(len(trace),3)
        self.assertAlmostEqual(result['best']['path_confidence'], .9**3, places=7)
        self.assertAlmostEqual(result['best']['uncertainty'], 1-(.9**3), places=7)

    def test_prefers_reliable_multi_step_plan_over_risky_shortcut(self):
        p,_=self.build(uncertainty_penalty=1.0)
        result=p.plan('movement', entity_id='sim', initial_state={'position':0},
                      actions=['right','risky'], goal=StateGoal({'position':3}), horizon=3)
        self.assertEqual(result['best']['actions'],['right','right','right'])

    def test_avoid_state_blocks_candidate(self):
        p,_=self.build()
        result=p.plan('movement', entity_id='sim', initial_state={'position':0},
                      actions=['right'], goal=StateGoal({'position':3}, avoid={'position':2}), horizon=3)
        self.assertNotEqual(result['status'],'goal_reached')
        self.assertLess(result['best']['goal_score'],1.0)

    def test_goal_already_satisfied_uses_zero_predictions(self):
        p,pred=self.build()
        result=p.plan('movement', entity_id='sim', initial_state={'position':3},
                      actions=['left','right'], goal=StateGoal({'position':3}))
        self.assertEqual(result['status'],'goal_already_satisfied')
        self.assertEqual(pred.calls,0)

    def test_simulation_marker_and_no_observation_api(self):
        p,_=self.build()
        result=p.plan('movement', entity_id='sim', initial_state={'position':0},
                      actions=['right'], goal=StateGoal({'position':1}), horizon=1)
        self.assertTrue(result['simulated_only'])
        self.assertEqual(result['best']['source'],'simulated')

    def test_bounded_expansion_budget(self):
        p,pred=self.build(max_expansions=3, beam_width=8)
        result=p.plan('movement', entity_id='sim', initial_state={'position':0},
                      actions=['left','right','risky'], goal=StateGoal({'position':99}), horizon=5)
        self.assertLessEqual(result['expansions'],3)
        self.assertLessEqual(pred.calls,3)

    def test_state_goal_requires_explicit_target(self):
        with self.assertRaises(ValueError):
            StateGoal({})


if __name__ == '__main__':
    unittest.main()
