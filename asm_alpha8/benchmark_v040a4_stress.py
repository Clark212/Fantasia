from __future__ import annotations
import json, random
from pathlib import Path
from asm.planning import ContingentInternalPlanner, ProbabilisticInternalPlanner, StateGoal
from benchmark_v040a4 import DistTable

OUT=Path('results/planning_v040a4_stress.json')

def random_clue_world(seed):
    r=random.Random(seed); n=r.randint(2,4)
    clues=[f'c{i}' for i in range(n)]; acts=[f'a{i}' for i in range(n)]
    weights=[r.uniform(.7,1.3) for _ in range(n)]; z=sum(weights); probs=[w/z for w in weights]
    t={('start','sense'):list(zip(clues,probs))}
    for i,a in enumerate(acts): t[('start',a)]=[('goal',probs[i]),('hazard',1-probs[i])]
    for i,c in enumerate(clues):
        for j,a in enumerate(acts): t[(c,a)]=[('goal',1.0)] if i==j else [('hazard',1.0)]
    return t, ('sense',*acts)

def run_random(seed):
    t,actions=random_clue_world(seed); pred=DistTable(t); goal=StateGoal({'loc':'goal'},{'loc':'hazard'})
    before=ProbabilisticInternalPlanner(pred,max_horizon=2,beam_width=8,max_expansions=96,
        min_goal_probability=.95,max_hazard_probability=.05,max_unknown_probability=.05,risk_aversion=4.0).plan(
        'r',entity_id='x',initial_state={'loc':'start'},actions=actions,goal=goal,horizon=2)
    after=ContingentInternalPlanner(pred,max_horizon=2,max_expansions=96,
        min_goal_probability=.95,max_hazard_probability=.05,max_unknown_probability=.05,risk_aversion=4.0).plan(
        'r',entity_id='x',initial_state={'loc':'start'},actions=actions,goal=goal,horizon=2)
    return {'before_ok':before['status']=='risk_aware_plan_found','before_goal':before['best']['goal_probability'],
            'after_ok':after['status']=='contingent_plan_found','after_goal':after['best']['goal_probability'],
            'after_action':after['best']['action'],'gain':after['contingency_gain'],'expansions':after['expansions']}

def run_useless(seed):
    r=random.Random(seed)
    p=r.uniform(.2,.8)
    t={('start','go'):[('goal',1.0)],('start','sense'):[('x',p),('y',1-p)],
       ('x','go'):[('goal',1.0)],('y','go'):[('goal',1.0)]}
    plan=ContingentInternalPlanner(DistTable(t),max_horizon=2,max_expansions=32,
        min_goal_probability=.95,max_hazard_probability=.05,max_unknown_probability=.05,
        cost_weight=.1).plan('u',entity_id='x',initial_state={'loc':'start'},actions=('sense','go'),
        goal=StateGoal({'loc':'goal'}),action_costs={'sense':1.0,'go':.1},horizon=2)
    return plan['best']['action']=='go' and abs(plan['contingency_gain'])<1e-9

def deep_case():
    t={('start','sense1'):[('red',.5),('blue',.5)],('red','sense2'):[('redA',.5),('redB',.5)],
       ('blue','sense2'):[('blueA',.5),('blueB',.5)]}
    mapping={'redA':'a','redB':'b','blueA':'c','blueB':'d'}; acts=('sense1','sense2','a','b','c','d')
    for s,correct in mapping.items():
        for a in ('a','b','c','d'): t[(s,a)]=[('goal',1.0)] if a==correct else [('hazard',1.0)]
    goal=StateGoal({'loc':'goal'},{'loc':'hazard'}); pred=DistTable(t)
    before=ProbabilisticInternalPlanner(pred,max_horizon=3,beam_width=12,max_expansions=160,
        min_goal_probability=.95,max_hazard_probability=.05,max_unknown_probability=.05,risk_aversion=4.0).plan(
        'd',entity_id='x',initial_state={'loc':'start'},actions=acts,goal=goal,horizon=3)
    after=ContingentInternalPlanner(pred,max_horizon=3,max_expansions=160,
        min_goal_probability=.95,max_hazard_probability=.05,max_unknown_probability=.05,risk_aversion=4.0).plan(
        'd',entity_id='x',initial_state={'loc':'start'},actions=acts,goal=goal,horizon=3)
    return {'before_goal':before['best']['goal_probability'],'before_status':before['status'],
            'after_goal':after['best']['goal_probability'],'after_status':after['status'],
            'after_root':after['best']['action'],'contingent':after['contingent_branching_used'],
            'policy_nodes':after['policy_nodes'],'expansions':after['expansions']}

def main():
    cases=[run_random(1000+i) for i in range(300)]
    useless=[run_useless(5000+i) for i in range(200)]
    deep=deep_case()
    payload={'random_cases':300,'alpha3_acceptable':sum(x['before_ok'] for x in cases),
             'alpha4_acceptable':sum(x['after_ok'] for x in cases),
             'alpha4_sense_first':sum(x['after_action']=='sense' for x in cases),
             'alpha4_mean_goal':sum(x['after_goal'] for x in cases)/len(cases),
             'alpha4_max_expansions':max(x['expansions'] for x in cases),
             'useless_sensing_rejected':sum(useless),'useless_cases':len(useless),'deep':deep}
    checks={'random_300_all_solved':payload['alpha4_acceptable']==300 and payload['alpha4_sense_first']==300,
            'random_alpha3_control_not_solved':payload['alpha3_acceptable']==0,
            'useless_200_all_rejected':payload['useless_sensing_rejected']==200,
            'deep_three_step_policy_solved':deep['after_status']=='contingent_plan_found' and abs(deep['after_goal']-1.0)<1e-9 and deep['contingent'],
            'deep_alpha3_control_not_solved':deep['before_status']!='risk_aware_plan_found'}
    payload['checks']=checks; payload['passed']=sum(checks.values()); payload['total']=len(checks)
    OUT.parent.mkdir(exist_ok=True); OUT.write_text(json.dumps(payload,indent=2,sort_keys=True))
    print(json.dumps(payload,indent=2))
    if not all(checks.values()): raise SystemExit(1)
if __name__=='__main__': main()
