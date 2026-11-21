from __future__ import annotations
import json
from pathlib import Path

from asm import __version__
from asm.planning import ContingentInternalPlanner, ProbabilisticInternalPlanner, StateGoal
from asm.transition_mechanism import LocalRecurrentTransitionMechanism

OUT = Path('results/planning_v040a4_benchmark.json')


class DistTable:
    def __init__(self, table): self.table = table
    def __call__(self, mechanism_type, *, entity_id, state, action, neighborhood=None,
                 dt=1.0, simulation_context=None, top_k=4, empirical_min_support=None):
        rows = list(self.table.get((state.get('loc'), action), []))
        outcomes = [
            {'predicted_state': {'loc': loc}, 'probability': float(prob),
             'conditional_probability': float(prob), 'support': 100, 'outcome_slot': i}
            for i, (loc, prob) in enumerate(rows[:top_k])
        ]
        mass = sum(x['probability'] for x in outcomes)
        return {
            'mechanism_type': mechanism_type, 'entity_id': entity_id, 'outcomes': outcomes,
            'unknown_probability': max(0.0, 1.0 - mass), 'support': 100,
            'probability_source': 'table', 'calibrated': True,
            '_simulation_context': simulation_context, '_simulation_context_key': '',
        }


def clue_table():
    return {
        ('start','sense'):[('clueA',.5),('clueB',.5)],
        ('start','chooseA'):[('goal',.5),('hazard',.5)],
        ('start','chooseB'):[('goal',.5),('hazard',.5)],
        ('clueA','chooseA'):[('goal',1.0)], ('clueA','chooseB'):[('hazard',1.0)],
        ('clueB','chooseA'):[('hazard',1.0)], ('clueB','chooseB'):[('goal',1.0)],
    }


def train_clue_mechanism(seed: int):
    m = LocalRecurrentTransitionMechanism(
        f'a4_clue_{seed}', hidden_dim=12, train_steps=1, max_outcomes=12,
        outcome_capacity_limit=32, retention_anchor_limit=64, seed=seed,
    )
    m.replay_limit = 64; m.replay_batch_limit = 4
    def obs(state, action, after, n):
        for i in range(n):
            m.observe(entity_id=f'{state}-{action}-{after}-{i}', state={'loc':state},
                      action=action, after_state={'loc':after})
    obs('start','sense','clueA',20); obs('start','sense','clueB',20)
    obs('start','chooseA','goal',20); obs('start','chooseA','hazard',20)
    obs('start','chooseB','goal',20); obs('start','chooseB','hazard',20)
    obs('clueA','chooseA','goal',30); obs('clueA','chooseB','hazard',30)
    obs('clueB','chooseA','hazard',30); obs('clueB','chooseB','goal',30)
    return m


def learned_case(seed: int):
    m = train_clue_mechanism(seed)
    predictor = lambda mechanism_type, **kw: m.predict_distribution_simulated(**kw)
    goal = StateGoal({'loc':'goal'},{'loc':'hazard'})
    before_state = (m.total_observations, m.abstraction_hits, m.abstraction_misses,
                    m.consolidation_hits, m.consolidation_misses,
                    {k:dict(v) for k,v in m.conditional_outcome_support.items()})
    before = ProbabilisticInternalPlanner(
        predictor, max_horizon=2, beam_width=8, max_expansions=64,
        min_goal_probability=.9, max_hazard_probability=.08,
        max_unknown_probability=.08, risk_aversion=4.0,
    ).plan('clue', entity_id='plan', initial_state={'loc':'start'},
           actions=('sense','chooseA','chooseB'), goal=goal, horizon=2)
    after = ContingentInternalPlanner(
        predictor, max_horizon=2, max_expansions=64,
        min_goal_probability=.9, max_hazard_probability=.08,
        max_unknown_probability=.08, risk_aversion=4.0,
    ).plan('clue', entity_id='plan', initial_state={'loc':'start'},
           actions=('sense','chooseA','chooseB'), goal=goal, horizon=2)
    after_state = (m.total_observations, m.abstraction_hits, m.abstraction_misses,
                   m.consolidation_hits, m.consolidation_misses,
                   {k:dict(v) for k,v in m.conditional_outcome_support.items()})
    branches = {b['observation']['loc']:b['policy']['action'] for b in after['best']['branches']}
    return {
        'seed':seed,
        'before_status':before['status'],
        'before_actions':before['best']['actions'],
        'before_goal_probability':before['best']['goal_probability'],
        'before_hazard_probability':before['best']['hazard_probability'],
        'after_status':after['status'],
        'after_root_action':after['best']['action'],
        'after_goal_probability':after['best']['goal_probability'],
        'after_hazard_probability':after['best']['hazard_probability'],
        'after_branch_actions':branches,
        'contingency_gain':after['contingency_gain'],
        'read_only':before_state == after_state,
    }


def controls():
    useful = clue_table()
    useless = {
        ('start','go'):[('goal',1.0)],
        ('start','inspect'):[('clueA',.5),('clueB',.5)],
        ('clueA','go'):[('goal',1.0)], ('clueB','go'):[('goal',1.0)],
    }
    three = {
        ('start','inspect'):[('A',1/3),('B',1/3),('C',1/3)],
        ('A','a'):[('goal',1.0)], ('A','b'):[('hazard',1.0)], ('A','c'):[('hazard',1.0)],
        ('B','a'):[('hazard',1.0)], ('B','b'):[('goal',1.0)], ('B','c'):[('hazard',1.0)],
        ('C','a'):[('hazard',1.0)], ('C','b'):[('hazard',1.0)], ('C','c'):[('goal',1.0)],
    }
    noisy = {
        ('start','inspect'):[('A',.45),('B',.45)],
        ('A','a'):[('goal',1.0)], ('A','b'):[('hazard',1.0)],
        ('B','a'):[('hazard',1.0)], ('B','b'):[('goal',1.0)],
    }
    risky = clue_table(); risky[('clueA','chooseA')] = [('goal',.95),('hazard',.05)]

    p_useless = ContingentInternalPlanner(DistTable(useless), max_horizon=2, max_expansions=64,
        min_goal_probability=.95,max_hazard_probability=.05,max_unknown_probability=.05,cost_weight=.1).plan(
        'u',entity_id='x',initial_state={'loc':'start'},actions=('inspect','go'),
        goal=StateGoal({'loc':'goal'}),action_costs={'inspect':1.0,'go':.1},horizon=2)
    p_three = ContingentInternalPlanner(DistTable(three),max_horizon=2,max_expansions=96,
        min_goal_probability=.95,max_hazard_probability=.05,max_unknown_probability=.05,risk_aversion=4.0).plan(
        't',entity_id='x',initial_state={'loc':'start'},actions=('inspect','a','b','c'),
        goal=StateGoal({'loc':'goal'},{'loc':'hazard'}),horizon=2)
    p_noisy = ContingentInternalPlanner(DistTable(noisy),max_horizon=2,max_expansions=64,
        min_goal_probability=.85,max_hazard_probability=.05,max_unknown_probability=.15,risk_aversion=3.0).plan(
        'n',entity_id='x',initial_state={'loc':'start'},actions=('inspect','a','b'),
        goal=StateGoal({'loc':'goal'},{'loc':'hazard'}),horizon=2)
    p_risky = ContingentInternalPlanner(DistTable(risky),max_horizon=2,max_expansions=64,
        min_goal_probability=.9,max_hazard_probability=.03,max_unknown_probability=.05,risk_aversion=4.0).plan(
        'r',entity_id='x',initial_state={'loc':'start'},actions=('sense','chooseA','chooseB'),
        goal=StateGoal({'loc':'goal'},{'loc':'hazard'}),horizon=2)
    return {
        'useless_information_choice':p_useless['best']['action'],
        'useless_contingency_gain':p_useless['contingency_gain'],
        'three_way_goal_probability':p_three['best']['goal_probability'],
        'three_way_branch_diversity':p_three['branch_action_diversity'],
        'noisy_goal_probability':p_noisy['best']['goal_probability'],
        'noisy_unknown_probability':p_noisy['best']['unknown_probability'],
        'risky_goal_probability':p_risky['best']['goal_probability'],
        'risky_hazard_probability':p_risky['best']['hazard_probability'],
    }


def main():
    learned = [learned_case(seed) for seed in (111,222,333)]
    c = controls()
    before_mean = sum(x['before_goal_probability'] for x in learned)/len(learned)
    after_mean = sum(x['after_goal_probability'] for x in learned)/len(learned)
    checks = {
        'version_is_v040a4': __version__ == '0.4.0-alpha.7',
        'alpha3_open_loop_learned_control_at_most_half': all(x['before_goal_probability'] <= .5 + 1e-9 for x in learned),
        'alpha4_learned_clue_world_is_near_certain': all(x['after_goal_probability'] >= .94 for x in learned),
        'alpha4_learned_uses_observation_conditioning': all(x['after_root_action']=='sense' and x['after_branch_actions']=={'clueA':'chooseA','clueB':'chooseB'} for x in learned),
        'alpha4_contingency_gain_positive': all((x['contingency_gain'] or 0) > .35 for x in learned),
        'planning_remains_read_only': all(x['read_only'] for x in learned),
        'useless_information_rejected': c['useless_information_choice']=='go' and abs(c['useless_contingency_gain']) < 1e-9,
        'three_way_contingency_succeeds': abs(c['three_way_goal_probability']-1.0)<1e-9 and c['three_way_branch_diversity']==3,
        'unknown_mass_survives_information_tree': abs(c['noisy_goal_probability']-.9)<1e-9 and abs(c['noisy_unknown_probability']-.1)<1e-9,
        'branch_tail_risk_is_aggregated': abs(c['risky_goal_probability']-.975)<1e-9 and abs(c['risky_hazard_probability']-.025)<1e-9,
    }
    payload = {
        'version':__version__,
        'benchmark':'ASM v0.4.0-alpha.5.1 Active Information Gathering & Contingent Planning',
        'before_alpha3_open_loop':{'learned_cases':learned,'mean_goal_probability':before_mean},
        'after_alpha4_contingent':{'learned_cases':learned,'mean_goal_probability':after_mean,'controls':c},
        'checks':checks,'passed':sum(checks.values()),'total':len(checks),
        'notes':[
            'Before and after use the same learned transition mechanisms and goal/risk thresholds.',
            'Alpha.4 policy trees may choose different future actions after different observed outcomes.',
            'This is an internal architecture benchmark, not a standardized AGI benchmark.',
        ],
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(payload,indent=2,sort_keys=True),encoding='utf-8')
    print(json.dumps({
        'version':__version__,'passed':payload['passed'],'total':payload['total'],
        'before_mean_goal_probability':before_mean,
        'after_mean_goal_probability':after_mean,
        'learned_before_successes':sum(x['before_goal_probability']>.9 for x in learned),
        'learned_after_successes':sum(x['after_goal_probability']>.9 for x in learned),
        'useless_information_choice':c['useless_information_choice'],
        'three_way_goal_probability':c['three_way_goal_probability'],
        'noisy_unknown_probability':c['noisy_unknown_probability'],
    },indent=2))
    if not all(checks.values()): raise SystemExit(1)

if __name__=='__main__': main()
