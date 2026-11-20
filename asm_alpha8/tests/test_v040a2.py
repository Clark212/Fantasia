import tempfile
import unittest
from pathlib import Path

from asm import __version__
from asm.planning import BoundedInternalPlanner, StateGoal
from asm.transition_mechanism import LocalRecurrentTransitionMechanism


class ContextPredictor:
    """Tiny history-dependent world with identical visible intermediate state."""
    def __call__(self, mechanism_type, *, entity_id, state, action, neighborhood=None,
                 dt=1.0, simulation_context=None):
        phase = int((simulation_context or {}).get('phase', 0))
        if action == 'prime':
            nxt = {'door': 'closed'}
            next_phase = 1
        elif action == 'open':
            nxt = {'door': 'open' if phase == 1 else 'jammed'}
            next_phase = 0
        elif action == 'wait':
            nxt = dict(state)
            next_phase = phase
        else:
            return {'mechanism_type': mechanism_type, 'predicted_state': None,
                    'confidence': 0.0, 'uncertainty': 1.0,
                    '_simulation_context': simulation_context,
                    '_simulation_context_key': f'p{phase}'}
        return {'mechanism_type': mechanism_type, 'predicted_state': nxt,
                'confidence': .97, 'uncertainty': .03,
                '_simulation_context': {'phase': next_phase},
                '_simulation_context_key': f'p{next_phase}'}


class GridPredictor:
    def __init__(self, walls=(), width=5, height=5):
        self.walls=set(walls); self.width=width; self.height=height
    def __call__(self, mechanism_type, *, entity_id, state, action, neighborhood=None,
                 dt=1.0, simulation_context=None):
        x,y=int(state['x']),int(state['y'])
        dx,dy={'U':(0,-1),'D':(0,1),'L':(-1,0),'R':(1,0)}[action]
        nx,ny=x+dx,y+dy
        if nx<0 or ny<0 or nx>=self.width or ny>=self.height or (nx,ny) in self.walls:
            nx,ny=x,y
        return {'mechanism_type':mechanism_type,'predicted_state':{'x':nx,'y':ny},
                'confidence':.99,'uncertainty':.01,
                '_simulation_context':simulation_context,'_simulation_context_key':''}


class PlanningAlpha2Tests(unittest.TestCase):
    def test_version(self):
        self.assertEqual(__version__, '0.4.0-alpha.7.9')

    def test_numeric_proximity_is_search_only_not_success(self):
        g=StateGoal({'x':4,'y':4})
        self.assertGreater(g.proximity({'x':3,'y':4}), g.proximity({'x':0,'y':0}))
        self.assertFalse(g.satisfied({'x':3,'y':4}))
        self.assertTrue(g.satisfied({'x':4,'y':4}))

    def test_branch_local_context_preserves_same_visible_state(self):
        planner=BoundedInternalPlanner(ContextPredictor(), max_horizon=2, beam_width=4,
                                       adaptive_beam_max=4, max_expansions=16)
        result=planner.plan('door',entity_id='sim',initial_state={'door':'closed'},
                            actions=['open','prime','wait'],goal=StateGoal({'door':'open'}),horizon=2)
        self.assertEqual(result['status'],'goal_reached')
        self.assertEqual(result['best']['actions'],['prime','open'])

    def test_loop_dominance_prunes_blocked_moves(self):
        planner=BoundedInternalPlanner(GridPredictor(walls={(1,0)}), max_horizon=8,
                                       beam_width=4, adaptive_beam_max=4, max_expansions=80)
        result=planner.plan('grid',entity_id='sim',initial_state={'x':0,'y':0},
                            actions=['R','D','L','U'],goal=StateGoal({'x':2,'y':0}),horizon=8)
        self.assertEqual(result['status'],'goal_reached')
        self.assertGreater(result['dominated_pruned'],0)

    def test_budget_exhausted_reason(self):
        planner=BoundedInternalPlanner(GridPredictor(),max_horizon=20,beam_width=2,
                                       adaptive_beam_max=2,max_expansions=1)
        result=planner.plan('grid',entity_id='sim',initial_state={'x':0,'y':0},
                            actions=['R','D'],goal=StateGoal({'x':4,'y':4}),horizon=20)
        self.assertEqual(result['status'],'budget_exhausted')
        self.assertEqual(result['reason'],'expansion_budget_reached_before_goal')

    def test_horizon_exhausted_reason(self):
        planner=BoundedInternalPlanner(GridPredictor(),max_horizon=1,beam_width=4,
                                       adaptive_beam_max=4,max_expansions=20)
        result=planner.plan('grid',entity_id='sim',initial_state={'x':0,'y':0},
                            actions=['R','D'],goal=StateGoal({'x':4,'y':4}),horizon=1)
        self.assertEqual(result['status'],'horizon_exhausted')

    def test_adaptive_widening_on_stall(self):
        # Goal x=2 is blocked directly, forcing a temporary move in y.
        planner=BoundedInternalPlanner(GridPredictor(walls={(1,0)}),max_horizon=8,
                                       beam_width=2,adaptive_beam_max=8,max_expansions=80,
                                       stall_patience=1)
        result=planner.plan('grid',entity_id='sim',initial_state={'x':0,'y':0},
                            actions=['R','D','L','U'],goal=StateGoal({'x':2,'y':0}),horizon=8)
        self.assertEqual(result['status'],'goal_reached')
        self.assertGreaterEqual(result['effective_beam_width_peak'],2)

    def test_simulated_prediction_does_not_touch_diagnostic_counters(self):
        m=LocalRecurrentTransitionMechanism(
            'v040a2_pure', hidden_dim=8, train_steps=1, max_outcomes=8,
            outcome_capacity_limit=32, seed=77,
            abstraction_min_support=2, abstraction_min_precision=.9,
            abstraction_min_diversity=2,
        )
        for i in range(8):
            m.observe(entity_id=f't{i}',state={'x':0,'noise':i},action='R',after_state={'x':1})
        before=(m.abstraction_hits,m.abstraction_misses,m.abstraction_exception_hits,
                m.trace_fallback_hits,m.consolidation_hits,m.consolidation_misses,
                m.total_observations)
        pred=m.predict_simulated(entity_id='probe',state={'x':0,'noise':99},action='R')
        after=(m.abstraction_hits,m.abstraction_misses,m.abstraction_exception_hits,
               m.trace_fallback_hits,m.consolidation_hits,m.consolidation_misses,
               m.total_observations)
        self.assertEqual(before,after)
        self.assertIsNotNone(pred['predicted_state'])
        self.assertIn('_simulation_context',pred)

    def test_simulated_context_advances_without_mutating_real_context(self):
        m=LocalRecurrentTransitionMechanism('v040a2_ctx',hidden_dim=8,train_steps=1,max_outcomes=8,
                                             outcome_capacity_limit=32,seed=91)
        for i in range(6):
            m.observe(entity_id=f't{i}',state={'s':0},action='a',after_state={'s':1})
        before_hidden=dict(m.context_hidden)
        p1=m.predict_simulated(entity_id='new',state={'s':0},action='a')
        p2=m.predict_simulated(entity_id='new',state={'s':1},action='a',
                               simulation_context=p1['_simulation_context'])
        self.assertNotEqual(p1['_simulation_context_key'],p2['_simulation_context_key'])
        self.assertEqual(set(before_hidden),set(m.context_hidden))
        self.assertNotIn('new',m.context_hidden)


if __name__=='__main__':
    unittest.main()
