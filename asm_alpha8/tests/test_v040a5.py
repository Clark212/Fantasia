from __future__ import annotations
import unittest
import tempfile
from pathlib import Path

from asm import ASMEngine
from asm.planning import BeliefStateInternalPlanner, DiscreteBeliefState, StateGoal


class HiddenBinary:
    def __init__(self, accuracy=.7):
        self.a=float(accuracy); self.calls=0
    def __call__(self, mechanism_type, *, entity_id, state, action, neighborhood=None,
                 dt=1.0, simulation_context=None, top_k=4, empirical_min_support=None):
        self.calls += 1; a=self.a
        if action=='sense' and state.get('loc')=='start':
            outs=[
                {'predicted_state':{'loc':'start'},'observation':'A','probability':.5,
                 'hypothesis_likelihoods':{'A':a,'B':1-a}},
                {'predicted_state':{'loc':'start'},'observation':'B','probability':.5,
                 'hypothesis_likelihoods':{'A':1-a,'B':a}},
            ]
        elif action=='chooseA' and state.get('loc')=='start':
            outs=[
                {'predicted_state':{'loc':'goal'},'probability':.5,'hypothesis_likelihoods':{'A':1,'B':0}},
                {'predicted_state':{'loc':'hazard'},'probability':.5,'hypothesis_likelihoods':{'A':0,'B':1}},
            ]
        elif action=='chooseB' and state.get('loc')=='start':
            outs=[
                {'predicted_state':{'loc':'goal'},'probability':.5,'hypothesis_likelihoods':{'A':0,'B':1}},
                {'predicted_state':{'loc':'hazard'},'probability':.5,'hypothesis_likelihoods':{'A':1,'B':0}},
            ]
        else: outs=[]
        return {'outcomes':outs[:top_k],'unknown_probability':0.0 if outs else 1.0,'calibrated':True,
                '_simulation_context':simulation_context,'_simulation_context_key':''}


def make_planner(model=None, **kw):
    opts=dict(max_horizon=8,max_expansions=256,risk_aversion=0.0,unknown_risk_weight=0.0,
              cost_weight=0.0,proximity_weight=0.0,step_penalty=.0001,
              min_goal_probability=0.0,max_hazard_probability=1.0,max_unknown_probability=1.0)
    opts.update(kw)
    return BeliefStateInternalPlanner(model or HiddenBinary(),**opts)


class BeliefStateTests(unittest.TestCase):
    def test_normalizes_prior(self):
        b=DiscreteBeliefState.from_mapping({'A':2,'B':2})
        self.assertEqual(b.as_dict(),{'A':.5,'B':.5})

    def test_one_observation_updates_to_point_seven(self):
        b=DiscreteBeliefState.from_mapping({'A':.5,'B':.5}).update({'A':.7,'B':.3})
        self.assertAlmostEqual(b.as_dict()['A'],.7,12)
        self.assertEqual(b.evidence_count,1)

    def test_contradictory_evidence_returns_to_prior(self):
        b=DiscreteBeliefState.from_mapping({'A':.5,'B':.5})
        b=b.update({'A':.7,'B':.3}).update({'A':.3,'B':.7})
        self.assertAlmostEqual(b.as_dict()['A'],.5,12)
        self.assertAlmostEqual(b.as_dict()['B'],.5,12)

    def test_consistent_evidence_reduces_entropy(self):
        b=DiscreteBeliefState.from_mapping({'A':.5,'B':.5}); h0=b.entropy_bits()
        for _ in range(3): b=b.update({'A':.7,'B':.3})
        self.assertLess(b.entropy_bits(),h0)

    def test_zero_probability_evidence_rejected(self):
        b=DiscreteBeliefState.from_mapping({'A':1.0})
        with self.assertRaises(ValueError): b.update({'A':0.0})


class BeliefPlannerTests(unittest.TestCase):
    def plan(self,horizon):
        return make_planner().plan('h',entity_id='x',initial_state={'loc':'start'},
            actions=('sense','chooseA','chooseB'),goal=StateGoal({'loc':'goal'},{'loc':'hazard'}),
            initial_belief={'A':.5,'B':.5},horizon=horizon)

    def test_three_clue_expected_accuracy(self):
        r=self.plan(4)
        self.assertAlmostEqual(r['best']['goal_probability'],.784,12)
        self.assertEqual(r['status'],'belief_contingent_plan_found')

    def test_seven_clue_expected_accuracy_and_merging(self):
        r=self.plan(8)
        self.assertAlmostEqual(r['best']['goal_probability'],.873964,12)
        self.assertGreater(r['belief_merge_hits'],0)
        self.assertLessEqual(r['expansions'],256)
        self.assertLess(r['policy_nodes'],431)

    def test_hypothesis_limit_is_bounded(self):
        planner=make_planner(max_hypotheses=2)
        with self.assertRaises(ValueError):
            planner.plan('h',entity_id='x',initial_state={'loc':'start'},actions=('sense',),
                goal=StateGoal({'loc':'goal'}),initial_belief={'a':1,'b':1,'c':1},horizon=1)

    def test_initial_belief_is_not_mutated(self):
        prior={'A':.5,'B':.5}
        _=make_planner().plan('h',entity_id='x',initial_state={'loc':'start'},
            actions=('sense','chooseA','chooseB'),goal=StateGoal({'loc':'goal'},{'loc':'hazard'}),
            initial_belief=prior,horizon=4)
        self.assertEqual(prior,{'A':.5,'B':.5})

    def test_likelihood_provider_can_supply_evidence(self):
        class ProviderModel:
            def __call__(self, mechanism_type, *, entity_id, state, action, neighborhood=None,
                         dt=1.0, simulation_context=None, top_k=4, empirical_min_support=None):
                if action=='sense': outs=[{'predicted_state':{'loc':'start'},'observation':'A','probability':.5},
                                          {'predicted_state':{'loc':'start'},'observation':'B','probability':.5}]
                elif action=='chooseA': outs=[{'predicted_state':{'loc':'goal'},'observation':'goal','probability':.5},
                                              {'predicted_state':{'loc':'hazard'},'observation':'hazard','probability':.5}]
                elif action=='chooseB': outs=[{'predicted_state':{'loc':'goal'},'observation':'goal','probability':.5},
                                              {'predicted_state':{'loc':'hazard'},'observation':'hazard','probability':.5}]
                else: outs=[]
                return {'outcomes':outs,'unknown_probability':0.0 if outs else 1.0,'calibrated':True,
                        '_simulation_context':simulation_context,'_simulation_context_key':''}
        def provider(belief,state,action,observation,predicted):
            if action=='sense': return {'A':.7,'B':.3} if observation=='A' else {'A':.3,'B':.7}
            if action=='chooseA': return {'A':1,'B':0} if predicted.get('loc')=='goal' else {'A':0,'B':1}
            if action=='chooseB': return {'A':0,'B':1} if predicted.get('loc')=='goal' else {'A':1,'B':0}
            return None
        r=make_planner(ProviderModel()).plan('p',entity_id='x',initial_state={'loc':'start'},
            actions=('sense','chooseA','chooseB'),goal=StateGoal({'loc':'goal'},{'loc':'hazard'}),
            initial_belief={'A':.5,'B':.5},likelihood_provider=provider,horizon=4)
        self.assertAlmostEqual(r['best']['goal_probability'],.784,12)

    def test_engine_belief_planning_api(self):
        with tempfile.TemporaryDirectory() as td:
            engine=ASMEngine(Path(td)/'a5.db')
            try:
                engine.belief_planner=make_planner(HiddenBinary())
                r=engine.plan_world_actions_belief(
                    'h',entity_id='x',initial_state={'loc':'start'},
                    actions=('sense','chooseA','chooseB'),goal={'loc':'goal'},avoid={'loc':'hazard'},
                    initial_belief={'A':.5,'B':.5},horizon=4,
                )
                self.assertAlmostEqual(r['best']['goal_probability'],.784,12)
                self.assertTrue(r['belief_state_planning'])
                self.assertTrue(r['simulated_only'])
            finally:
                engine.close(save_snapshot=False)

    def test_outcome_specific_simulation_context(self):
        class ContextModel:
            def __call__(self, mechanism_type, *, entity_id, state, action, neighborhood=None,
                         dt=1.0, simulation_context=None, top_k=4, empirical_min_support=None):
                if state.get('loc')=='start' and action=='sense':
                    outs=[{'predicted_state':{'loc':'mid'},'observation':'L','probability':.5,
                           '_simulation_context':{'x':'L'},'_simulation_context_key':'L'},
                          {'predicted_state':{'loc':'mid'},'observation':'R','probability':.5,
                           '_simulation_context':{'x':'R'},'_simulation_context_key':'R'}]
                elif state.get('loc')=='mid' and action in {'L','R'}:
                    ok=(simulation_context or {}).get('x')==action
                    outs=[{'predicted_state':{'loc':'goal' if ok else 'hazard'},'probability':1.0}]
                else: outs=[]
                return {'outcomes':outs,'unknown_probability':0.0 if outs else 1.0,'calibrated':True,
                        '_simulation_context':simulation_context,
                        '_simulation_context_key':str((simulation_context or {}).get('x',''))}
        r=make_planner(ContextModel(),max_horizon=2,max_expansions=32,step_penalty=0.0,
                       min_goal_probability=.99,max_hazard_probability=.01,max_unknown_probability=.01).plan(
            'c',entity_id='x',initial_state={'loc':'start'},actions=('sense','L','R'),
            goal=StateGoal({'loc':'goal'},{'loc':'hazard'}),initial_belief={'only':1.0},horizon=2)
        self.assertAlmostEqual(r['best']['goal_probability'],1.0,12)
        root=r['policy_graph'][r['root_node']]
        acts={b['observation']:r['policy_graph'][b['next_node']]['action'] for b in root['branches']}
        self.assertEqual(acts,{'L':'L','R':'R'})


if __name__=='__main__': unittest.main()
