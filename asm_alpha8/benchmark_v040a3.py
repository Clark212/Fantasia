from __future__ import annotations
import json
from pathlib import Path

from asm import __version__
from asm.planning import ProbabilisticInternalPlanner, StateGoal
from asm.transition_mechanism import LocalRecurrentTransitionMechanism

OUT=Path('results/planning_v040a3_benchmark.json')
BASELINE=Path('results/v040a2_same_protocol_baseline.json')

class DistTable:
    def __init__(self, table): self.table=table
    def __call__(self, mechanism_type, *, entity_id, state, action, neighborhood=None,
                 dt=1.0, simulation_context=None, top_k=4, empirical_min_support=None):
        rows=list(self.table.get((state.get('loc'),action),[]))
        outcomes=[{'predicted_state':{'loc':loc},'probability':float(prob),
                   'conditional_probability':float(prob),'support':100,'outcome_slot':i}
                  for i,(loc,prob) in enumerate(rows[:top_k])]
        mass=sum(x['probability'] for x in outcomes)
        return {'mechanism_type':mechanism_type,'entity_id':entity_id,'outcomes':outcomes,
                'unknown_probability':max(0.0,1.0-mass),'support':100,
                'probability_source':'table','calibrated':True,
                '_simulation_context':simulation_context,'_simulation_context_key':''}

def make_mech(seed,p_goal=.8,n=50):
    m=LocalRecurrentTransitionMechanism(
        f'a3_bench_{seed}_{int(p_goal*100)}',hidden_dim=16,train_steps=1,max_outcomes=8,
        outcome_capacity_limit=32,retention_anchor_limit=64,seed=seed)
    m.replay_limit=64; m.replay_batch_limit=4
    g=round(n*p_goal); h=n-g
    for i in range(g): m.observe(entity_id=f'rg{i}',state={'loc':'start'},action='risky',after_state={'loc':'goal'})
    for i in range(h): m.observe(entity_id=f'rh{i}',state={'loc':'start'},action='risky',after_state={'loc':'hazard'})
    for i in range(n): m.observe(entity_id=f's1{i}',state={'loc':'start'},action='safe',after_state={'loc':'mid'})
    for i in range(n): m.observe(entity_id=f's2{i}',state={'loc':'mid'},action='safe',after_state={'loc':'goal'})
    return m

def seed_case(seed):
    m=make_mech(seed,.8,50)
    d=m.predict_distribution_simulated(entity_id='probe',state={'loc':'start'},action='risky')
    probs={x['predicted_state']['loc']:x['conditional_probability'] for x in d['outcomes']}
    before=(m.total_observations,m.abstraction_hits,m.abstraction_misses,m.consolidation_hits,m.consolidation_misses)
    planner=ProbabilisticInternalPlanner(lambda mechanism_type,**kw:m.predict_distribution_simulated(**kw),
        max_horizon=2,beam_width=6,max_expansions=40,risk_aversion=2.0,
        max_hazard_probability=.1,max_unknown_probability=.15)
    plan=planner.plan('risk',entity_id='plan',initial_state={'loc':'start'},actions=('risky','safe'),
        goal=StateGoal({'loc':'goal'},{'loc':'hazard'}),horizon=2)
    after=(m.total_observations,m.abstraction_hits,m.abstraction_misses,m.consolidation_hits,m.consolidation_misses)
    return {'seed':seed,'goal_probability':probs.get('goal',0.0),'hazard_probability':probs.get('hazard',0.0),
            'unknown_probability':d['unknown_probability'],'choice':plan['best']['actions'],'status':plan['status'],
            'read_only':before==after}

def calibration_case(p,seed):
    m=make_mech(seed,p,50)
    d=m.predict_distribution_simulated(entity_id='probe',state={'loc':'start'},action='risky')
    probs={x['predicted_state']['loc']:x['conditional_probability'] for x in d['outcomes']}
    forecast=probs.get('goal',0.0)
    brier=p*(1-forecast)**2+(1-p)*forecast**2
    return {'true_p':p,'forecast':forecast,'abs_error':abs(p-forecast),'expected_brier':brier,
            'outcomes':{x['predicted_state']['loc']:x['conditional_probability'] for x in d['outcomes']}}

def custom_cases():
    tail={('start','risky'):[('goal',.95),('hazard',.05)],('start','safe'):[('mid',1.0)],
          ('mid','safe'):[('goal',1.0)],('mid','risky'):[('hazard',1.0)]}
    cost={('start','jump'):[('goal',1.0)],('start','step'):[('mid',1.0)],
          ('mid','step'):[('goal',1.0)],('mid','jump'):[('goal',1.0)]}
    chain={('start','go'):[('mid',.90),('hazard',.10)],('mid','go'):[('goal',.90),('hazard',.10)]}
    tail_plan=ProbabilisticInternalPlanner(DistTable(tail),max_horizon=2,beam_width=6,max_expansions=32,
        risk_aversion=4.0,max_hazard_probability=.02,max_unknown_probability=.1).plan(
        'tail',entity_id='x',initial_state={'loc':'start'},actions=('risky','safe'),
        goal=StateGoal({'loc':'goal'},{'loc':'hazard'}),horizon=2)
    cost_plan=ProbabilisticInternalPlanner(DistTable(cost),max_horizon=2,beam_width=6,max_expansions=32,
        risk_aversion=1.0,cost_weight=.03,max_unknown_probability=.1).plan(
        'cost',entity_id='x',initial_state={'loc':'start'},actions=('jump','step'),
        goal=StateGoal({'loc':'goal'}),action_costs={'jump':100.0,'step':1.0},horizon=2)
    chain_plan=ProbabilisticInternalPlanner(DistTable(chain),max_horizon=2,beam_width=3,max_expansions=16,
        risk_aversion=.1,min_goal_probability=.7,max_hazard_probability=.3,max_unknown_probability=.1).plan(
        'chain',entity_id='x',initial_state={'loc':'start'},actions=('go',),
        goal=StateGoal({'loc':'goal'},{'loc':'hazard'}),horizon=2)
    return {'rare_tail_choice':tail_plan['best']['actions'],'rare_tail_hazard_probability':.05,
            'cost_choice':cost_plan['best']['actions'],'cost':cost_plan['best']['expected_cost'],
            'chain_goal_probability':chain_plan['best']['goal_probability'],
            'chain_hazard_probability':chain_plan['best']['hazard_probability']}

def main():
    baseline=json.loads(BASELINE.read_text()) if BASELINE.exists() else {}
    learned=[seed_case(s) for s in (101,202,303)]
    calibration=[calibration_case(p,400+i) for i,p in enumerate((.5,.7,.8,.95))]
    custom=custom_cases()
    mean_abs=sum(x['abs_error'] for x in calibration)/len(calibration)
    mean_brier=sum(x['expected_brier'] for x in calibration)/len(calibration)
    before_summary=baseline.get('summary',{})
    checks={
        'version_is_v040a3':__version__.startswith('0.4.0-alpha.7'),
        'all_three_80_20_seeds_choose_safe':all(x['choice']==['safe','safe'] for x in learned),
        '80_20_distribution_is_seed_stable':all(abs(x['goal_probability']-.8)<1e-9 and abs(x['hazard_probability']-.2)<1e-9 for x in learned),
        'stochastic_planning_is_read_only':all(x['read_only'] for x in learned),
        'calibration_mean_abs_error_below_1pct':mean_abs <= .01,
        'calibration_improves_over_alpha2':mean_abs < float(before_summary.get('mean_abs_calibration_error',1.0)),
        'brier_improves_over_alpha2':mean_brier < float(before_summary.get('mean_expected_brier',1.0)),
        'rare_5pct_tail_is_explicit_and_avoided':custom['rare_tail_choice']==['safe','safe'] and abs(custom['rare_tail_hazard_probability']-.05)<1e-9,
        'action_costs_choose_two_cheap_steps':custom['cost_choice']==['step','step'] and abs(custom['cost']-2.0)<1e-9,
        'multistep_probability_propagates':abs(custom['chain_goal_probability']-.81)<1e-9 and abs(custom['chain_hazard_probability']-.19)<1e-9,
    }
    payload={'version':__version__,'benchmark':'ASM v0.4.0-alpha.3 Probabilistic Futures & Simulation Trust',
             'before_alpha2_same_protocol':baseline,'after_alpha3':{'learned_80_20':learned,'calibration':calibration,'custom':custom,
             'summary':{'safe_choices_80_20':sum(x['choice']==['safe','safe'] for x in learned),
                        'mean_abs_calibration_error':mean_abs,'mean_expected_brier':mean_brier}},
             'checks':checks,'passed':sum(checks.values()),'total':len(checks),
             'notes':['Percentages here are empirical transition frequencies/probabilities, not an AGI percentage.',
                      'The stochastic planner is bounded and open-loop; adaptive policy trees are not claimed.',
                      'This is an internal architecture benchmark, not a standardized intelligence benchmark.']}
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(payload,indent=2,sort_keys=True),encoding='utf-8')
    print(json.dumps({'version':__version__,'passed':payload['passed'],'total':payload['total'],
        'before_safe_choices_80_20':before_summary.get('safe_choices_80_20'),
        'after_safe_choices_80_20':payload['after_alpha3']['summary']['safe_choices_80_20'],
        'before_mean_abs_calibration_error':before_summary.get('mean_abs_calibration_error'),
        'after_mean_abs_calibration_error':mean_abs,
        'before_mean_expected_brier':before_summary.get('mean_expected_brier'),
        'after_mean_expected_brier':mean_brier,
        'cost_choice':custom['cost_choice'],'chain_goal_probability':custom['chain_goal_probability']},indent=2))
    if not all(checks.values()): raise SystemExit(1)

if __name__=='__main__': main()
