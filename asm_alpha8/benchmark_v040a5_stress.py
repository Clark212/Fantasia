from __future__ import annotations
import json, math, random
from pathlib import Path

from asm.planning import BeliefStateInternalPlanner, DiscreteBeliefState, StateGoal
from benchmark_v040a5 import BinarySensorModel

OUT=Path('results/planning_v040a5_stress.json')


def majority_accuracy(p:float,n:int)->float:
    return sum(math.comb(n,k)*(p**k)*((1-p)**(n-k)) for k in range(n//2+1,n+1))


def binary_plan(acc:float,n:int):
    planner=BeliefStateInternalPlanner(
        BinarySensorModel(acc),max_horizon=n+1,max_expansions=256,top_k_outcomes=4,
        risk_aversion=0.0,unknown_risk_weight=0.0,cost_weight=0.0,proximity_weight=0.0,
        step_penalty=0.00001,min_goal_probability=0.0,max_hazard_probability=1.0,max_unknown_probability=1.0)
    return planner.plan('binary',entity_id='x',initial_state={'loc':'start'},
        actions=('sense','chooseA','chooseB'),goal=StateGoal({'loc':'goal'},{'loc':'hazard'}),
        initial_belief={'A':.5,'B':.5},horizon=n+1)


class TernarySensorModel:
    def __init__(self,accuracy=.7): self.a=float(accuracy)
    def likes(self,obs):
        spill=(1-self.a)/2
        return {h:(self.a if h==obs else spill) for h in 'ABC'}
    def __call__(self, mechanism_type, *, entity_id, state, action, neighborhood=None,
                 dt=1.0, simulation_context=None, top_k=6, empirical_min_support=None):
        if state.get('loc')!='start': outs=[]
        elif action=='sense':
            outs=[{'predicted_state':{'loc':'start'},'observation':o,'probability':1/3,
                   'hypothesis_likelihoods':self.likes(o)} for o in 'ABC']
        elif action in {'chooseA','chooseB','chooseC'}:
            chosen=action[-1]
            outs=[
                {'predicted_state':{'loc':'goal'},'observation':'goal','probability':1/3,
                 'hypothesis_likelihoods':{h:(1.0 if h==chosen else 0.0) for h in 'ABC'}},
                {'predicted_state':{'loc':'hazard'},'observation':'hazard','probability':2/3,
                 'hypothesis_likelihoods':{h:(0.0 if h==chosen else 1.0) for h in 'ABC'}},
            ]
        else: outs=[]
        return {'outcomes':outs[:top_k],'unknown_probability':0.0 if outs else 1.0,'calibrated':True,
                '_simulation_context':simulation_context,'_simulation_context_key':''}


def ternary_oracle(acc=.7,n=3):
    model=TernarySensorModel(acc)
    total=0.0
    # enumerate ordered observations; prior is uniform and MAP decision is optimal
    def rec(prefix):
        nonlocal total
        if len(prefix)==n:
            joint={h:1/3 for h in 'ABC'}
            for obs in prefix:
                likes=model.likes(obs)
                for h in 'ABC': joint[h]*=likes[h]
            total += max(joint.values())
            return
        for o in 'ABC': rec(prefix+(o,))
    rec(tuple())
    return total


def ternary_plan(acc=.7,n=3):
    planner=BeliefStateInternalPlanner(
        TernarySensorModel(acc),max_horizon=n+1,max_expansions=512,top_k_outcomes=6,
        risk_aversion=0.0,unknown_risk_weight=0.0,cost_weight=0.0,proximity_weight=0.0,
        step_penalty=0.00001,min_goal_probability=0.0,max_hazard_probability=1.0,max_unknown_probability=1.0,
        max_hypotheses=8)
    return planner.plan('ternary',entity_id='x',initial_state={'loc':'start'},
        actions=('sense','chooseA','chooseB','chooseC'),goal=StateGoal({'loc':'goal'},{'loc':'hazard'}),
        initial_belief={'A':1/3,'B':1/3,'C':1/3},horizon=n+1)


def random_posterior_consistency(seed):
    r=random.Random(seed)
    prior={'A':r.uniform(.05,.95),'B':0.0}; prior['B']=1-prior['A']
    acc=r.uniform(.55,.9)
    seq=[r.choice('AB') for _ in range(12)]
    b=DiscreteBeliefState.from_mapping(prior)
    wa,wb=prior['A'],prior['B']
    for obs in seq:
        likes={'A':acc if obs=='A' else 1-acc,'B':acc if obs=='B' else 1-acc}
        b=b.update(likes); wa*=likes['A']; wb*=likes['B']; z=wa+wb; wa/=z; wb/=z
        # reset unnormalized weights to the normalized posterior for stable recurrence
    return abs(b.as_dict()['A']-wa)<1e-12 and abs(b.as_dict()['B']-wb)<1e-12


def main():
    random.seed(4045)
    cases=[]
    for i in range(80):
        acc=random.uniform(.51,.90)
        n=random.choice((1,3,5,7))
        r=binary_plan(acc,n); target=majority_accuracy(acc,n)
        cases.append({'accuracy':acc,'clues':n,'actual':r['best']['goal_probability'],'target':target,
                      'error':abs(r['best']['goal_probability']-target),'expansions':r['expansions'],
                      'merges':r['belief_merge_hits'],'nodes':r['policy_nodes']})
    tern=ternary_plan(.7,3); tern_target=ternary_oracle(.7,3)
    posterior=[random_posterior_consistency(8000+i) for i in range(200)]
    payload={
        'binary_random_cases':len(cases),
        'binary_max_abs_error':max(x['error'] for x in cases),
        'binary_all_within_budget':all(x['expansions']<=256 for x in cases),
        'binary_cases_with_belief_merges':sum(x['merges']>0 for x in cases),
        'binary_max_policy_nodes':max(x['nodes'] for x in cases),
        'ternary_three_clue':{'actual':tern['best']['goal_probability'],'oracle':tern_target,
                              'abs_error':abs(tern['best']['goal_probability']-tern_target),
                              'expansions':tern['expansions'],'belief_merges':tern['belief_merge_hits'],
                              'unique_belief_states':tern['unique_belief_states'],'policy_nodes':tern['policy_nodes']},
        'posterior_consistency':{'passed':sum(posterior),'total':len(posterior)},
    }
    checks={
        'binary_80_match_closed_form':payload['binary_max_abs_error']<1e-10,
        'binary_all_bounded':payload['binary_all_within_budget'],
        'binary_merging_exercised':payload['binary_cases_with_belief_merges']>0,
        'ternary_matches_exact_enumeration':payload['ternary_three_clue']['abs_error']<1e-10,
        'ternary_is_not_binary_special_case':tern['unique_belief_states']>3 and tern['belief_merge_hits']>0,
        'random_posterior_200_match_direct_bayes':payload['posterior_consistency']['passed']==200,
    }
    payload['checks']=checks; payload['passed']=sum(checks.values()); payload['total']=len(checks)
    OUT.parent.mkdir(exist_ok=True); OUT.write_text(json.dumps(payload,indent=2,sort_keys=True),encoding='utf-8')
    print(json.dumps(payload,indent=2,sort_keys=True))
    if not all(checks.values()): raise SystemExit(1)

if __name__=='__main__': main()
