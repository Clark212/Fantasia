from __future__ import annotations
import math, unittest
from asm.planning import DiscreteBeliefState, BeliefStateInternalPlanner, StateGoal

class MatrixModel:
    def __init__(self, rows): self.rows=rows
    def __call__(self, mechanism_type, *, entity_id,state,action,neighborhood=None,dt=1.0,simulation_context=None,top_k=64,empirical_min_support=None):
        if state.get('loc')!='start': outs=[]
        elif action=='sense': outs=self.rows
        elif action=='chooseA': outs=[
            {'predicted_state':{'loc':'goal'},'observation':'g','hypothesis_likelihoods':{'A':1.0,'B':0.0}},
            {'predicted_state':{'loc':'hazard'},'observation':'h','hypothesis_likelihoods':{'A':0.0,'B':1.0}}]
        elif action=='chooseB': outs=[
            {'predicted_state':{'loc':'goal'},'observation':'g','hypothesis_likelihoods':{'A':0.0,'B':1.0}},
            {'predicted_state':{'loc':'hazard'},'observation':'h','hypothesis_likelihoods':{'A':1.0,'B':0.0}}]
        else: outs=[]
        return {'outcomes':outs[:top_k],'unknown_probability':0.0 if outs else 1.0,'calibrated':True,'_simulation_context':simulation_context,'_simulation_context_key':''}

def plan_rows(rows):
    p=BeliefStateInternalPlanner(MatrixModel(rows),max_horizon=2,max_expansions=64,top_k_outcomes=64,
        risk_aversion=0,unknown_risk_weight=0,cost_weight=0,proximity_weight=0,step_penalty=0,
        min_goal_probability=0,max_hazard_probability=1,max_unknown_probability=1)
    return p.plan('contract',entity_id='x',initial_state={'loc':'start'},actions=('sense','chooseA','chooseB'),
        goal=StateGoal({'loc':'goal'},{'loc':'hazard'}),initial_belief={'A':.5,'B':.5},horizon=2)

class ContractTests(unittest.TestCase):
    def assertRejected(self, rows):
        r=plan_rows(rows)
        self.assertGreaterEqual(r['invalid_likelihood_models'],1)
        self.assertNotEqual(r['policy_graph'][r['root_node']]['action'],'sense')

    def test_invalid_matrix_forms_fail_closed(self):
        cases=[
            # sums > 1 / sums < 1
            [{'predicted_state':{'loc':'start'},'observation':'x','hypothesis_likelihoods':{'A':.9,'B':.9}}, {'predicted_state':{'loc':'start'},'observation':'y','hypothesis_likelihoods':{'A':.9,'B':.9}}],
            [{'predicted_state':{'loc':'start'},'observation':'x','hypothesis_likelihoods':{'A':.2,'B':.2}}, {'predicted_state':{'loc':'start'},'observation':'y','hypothesis_likelihoods':{'A':.2,'B':.2}}],
            [{'predicted_state':{'loc':'start'},'observation':'x','hypothesis_likelihoods':{'A':-.1,'B':.5}}, {'predicted_state':{'loc':'start'},'observation':'y','hypothesis_likelihoods':{'A':1.1,'B':.5}}],
            [{'predicted_state':{'loc':'start'},'observation':'x','hypothesis_likelihoods':{'A':float('nan'),'B':.5}}, {'predicted_state':{'loc':'start'},'observation':'y','hypothesis_likelihoods':{'A':.5,'B':.5}}],
            [{'predicted_state':{'loc':'start'},'observation':'x','hypothesis_likelihoods':{'A':float('inf'),'B':.5}}, {'predicted_state':{'loc':'start'},'observation':'y','hypothesis_likelihoods':{'A':0,'B':.5}}],
            [{'predicted_state':{'loc':'start'},'observation':'x','hypothesis_likelihoods':{'A':float('-inf'),'B':.5}}, {'predicted_state':{'loc':'start'},'observation':'y','hypothesis_likelihoods':{'A':1,'B':.5}}],
            [{'predicted_state':{'loc':'start'},'observation':'x','hypothesis_likelihoods':{}}, {'predicted_state':{'loc':'start'},'observation':'y','hypothesis_likelihoods':{}}],
            [{'predicted_state':{'loc':'start'},'observation':'x','hypothesis_likelihoods':{'A':.5}}, {'predicted_state':{'loc':'start'},'observation':'y','hypothesis_likelihoods':{'A':.5}}],
            [{'predicted_state':{'loc':'start'},'observation':'x','hypothesis_likelihoods':{'A':.5,'B':.5,'C':0}}, {'predicted_state':{'loc':'start'},'observation':'y','hypothesis_likelihoods':{'A':.5,'B':.5,'C':1}}],
            [{'predicted_state':{'loc':'start'},'observation':'x','hypothesis_likelihoods':{'A':0,'B':0}}, {'predicted_state':{'loc':'start'},'observation':'y','hypothesis_likelihoods':{'A':1,'B':1}}],
            # duplicate observation identity
            [{'predicted_state':{'loc':'start'},'observation':'x','hypothesis_likelihoods':{'A':.5,'B':.5}}, {'predicted_state':{'loc':'start'},'observation':'x','hypothesis_likelihoods':{'A':.5,'B':.5}}],
            # mixed likelihood/non-likelihood rows
            [{'predicted_state':{'loc':'start'},'observation':'x','hypothesis_likelihoods':{'A':.5,'B':.5}}, {'predicted_state':{'loc':'start'},'observation':'y'}],
        ]
        for rows in cases:
            with self.subTest(rows=rows): self.assertRejected(rows)

    def test_tiny_normalization_error_is_tolerated(self):
        eps=2e-10
        rows=[
            {'predicted_state':{'loc':'start'},'observation':'x','hypothesis_likelihoods':{'A':.7+eps,'B':.3-eps}},
            {'predicted_state':{'loc':'start'},'observation':'y','hypothesis_likelihoods':{'A':.3-eps,'B':.7+eps}},]
        r=plan_rows(rows)
        self.assertEqual(r['invalid_likelihood_models'],0)

    def test_direct_likelihood_api_rejects_bad_values_and_keys(self):
        b=DiscreteBeliefState.from_mapping({'A':.5,'B':.5})
        for bad in ({}, {'A':.5}, {'A':.5,'B':.5,'C':0}, {'A':-1,'B':1}, {'A':math.nan,'B':1}, {'A':math.inf,'B':1}, {'A':0,'B':0}):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError): b.update(bad)

    def test_structural_zero_stays_impossible_but_soft_zero_recovers(self):
        hard=DiscreteBeliefState.from_mapping({'A':1.0,'B':0.0})
        self.assertEqual(hard.structural_zero_hypotheses(),('B',))
        for _ in range(100): hard=hard.update({'A':.01,'B':.99})
        self.assertEqual(hard.as_dict(),{'A':1.0})
        self.assertEqual(hard.structural_zero_hypotheses(),('B',))
        soft=DiscreteBeliefState.from_mapping({'A':1.0,'B':1e-300})
        for _ in range(200): soft=soft.update({'A':.01,'B':.99})
        self.assertEqual(soft.most_likely()[0],'B')
        self.assertNotIn('B',soft.structural_zero_hypotheses())

if __name__=='__main__': unittest.main()
