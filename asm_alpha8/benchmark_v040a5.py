from __future__ import annotations
import json
from pathlib import Path

from asm import __version__
from asm.planning import (
    BeliefStateInternalPlanner, ContingentInternalPlanner,
    DiscreteBeliefState, StateGoal,
)

OUT = Path('results/planning_v040a5_benchmark.json')


class BinarySensorModel:
    """Controlled hidden-mode world: sensor is 70% reliable."""
    def __init__(self, accuracy: float = 0.7):
        self.accuracy = float(accuracy)
        self.calls = 0

    def __call__(self, mechanism_type, *, entity_id, state, action, neighborhood=None,
                 dt=1.0, simulation_context=None, top_k=4, empirical_min_support=None):
        self.calls += 1
        a = self.accuracy
        if state.get('loc') in {'goal', 'hazard'}:
            return {'outcomes': [], 'unknown_probability': 0.0, 'calibrated': True,
                    '_simulation_context': simulation_context, '_simulation_context_key': ''}
        if action == 'sense':
            rows = [
                {'predicted_state': {'loc': 'start'}, 'observation': 'A',
                 'probability': .5, 'hypothesis_likelihoods': {'A': a, 'B': 1-a},
                 'support': 100, '_simulation_context': simulation_context,
                 '_simulation_context_key': ''},
                {'predicted_state': {'loc': 'start'}, 'observation': 'B',
                 'probability': .5, 'hypothesis_likelihoods': {'A': 1-a, 'B': a},
                 'support': 100, '_simulation_context': simulation_context,
                 '_simulation_context_key': ''},
            ]
        elif action == 'chooseA':
            rows = [
                {'predicted_state': {'loc': 'goal'}, 'observation': 'goal',
                 'probability': .5, 'hypothesis_likelihoods': {'A': 1.0, 'B': 0.0}, 'support': 100},
                {'predicted_state': {'loc': 'hazard'}, 'observation': 'hazard',
                 'probability': .5, 'hypothesis_likelihoods': {'A': 0.0, 'B': 1.0}, 'support': 100},
            ]
        elif action == 'chooseB':
            rows = [
                {'predicted_state': {'loc': 'goal'}, 'observation': 'goal',
                 'probability': .5, 'hypothesis_likelihoods': {'A': 0.0, 'B': 1.0}, 'support': 100},
                {'predicted_state': {'loc': 'hazard'}, 'observation': 'hazard',
                 'probability': .5, 'hypothesis_likelihoods': {'A': 1.0, 'B': 0.0}, 'support': 100},
            ]
        else:
            rows = []
        return {
            'mechanism_type': mechanism_type, 'entity_id': entity_id,
            'outcomes': rows[:top_k], 'unknown_probability': 0.0 if rows else 1.0,
            'support': 100, 'probability_source': 'controlled_hidden_mode', 'calibrated': True,
            '_simulation_context': simulation_context, '_simulation_context_key': '',
        }


class LastObservationCompressedModel:
    """Alpha.4-style control: only the latest clue is visible."""
    def __init__(self, accuracy=.7): self.a=float(accuracy)
    def __call__(self, mechanism_type, *, entity_id, state, action, neighborhood=None,
                 dt=1.0, simulation_context=None, top_k=4, empirical_min_support=None):
        loc=state.get('loc'); a=self.a
        rows=[]
        if action=='sense' and loc not in {'goal','hazard'}:
            rows=[('clueA',.5),('clueB',.5)]
        elif action in {'chooseA','chooseB'} and loc not in {'goal','hazard'}:
            if loc=='clueA': correct='chooseA'
            elif loc=='clueB': correct='chooseB'
            else: correct=None
            p=.5 if correct is None else (a if action==correct else 1-a)
            rows=[('goal',p),('hazard',1-p)]
        outcomes=[{'predicted_state':{'loc':s},'probability':p,'support':100,'outcome_slot':i}
                  for i,(s,p) in enumerate(rows[:top_k])]
        return {'outcomes':outcomes,'unknown_probability':max(0.0,1-sum(x['probability'] for x in outcomes)),
                'support':100,'probability_source':'last_observation_only','calibrated':True,
                '_simulation_context':simulation_context,'_simulation_context_key':''}


class BranchContextModel:
    """Probe that requires a distinct simulation context for sibling outcomes."""
    def __call__(self, mechanism_type, *, entity_id, state, action, neighborhood=None,
                 dt=1.0, simulation_context=None, top_k=4, empirical_min_support=None):
        loc=state.get('loc')
        if loc=='start' and action=='sense':
            outs=[
                {'predicted_state':{'loc':'mid'},'observation':'left','probability':.5,
                 '_simulation_context':{'branch':'left'},'_simulation_context_key':'left'},
                {'predicted_state':{'loc':'mid'},'observation':'right','probability':.5,
                 '_simulation_context':{'branch':'right'},'_simulation_context_key':'right'},
            ]
        elif loc=='mid' and action in {'left','right'}:
            branch=(simulation_context or {}).get('branch')
            success=branch==action
            outs=[{'predicted_state':{'loc':'goal' if success else 'hazard'},'probability':1.0}]
        else: outs=[]
        return {'outcomes':outs[:top_k], 'unknown_probability':0.0 if outs else 1.0,
                'support':10,'probability_source':'branch_context_probe','calibrated':True,
                '_simulation_context':simulation_context,'_simulation_context_key':str((simulation_context or {}).get('branch',''))}


def posterior_checks():
    prior=DiscreteBeliefState.from_mapping({'A':.5,'B':.5})
    A={'A':.7,'B':.3}; B={'A':.3,'B':.7}
    after_a=prior.update(A)
    after_ab=after_a.update(B)
    after_aaa=after_a.update(A).update(A)
    return {
        'prior':prior.as_dict(), 'after_A':after_a.as_dict(), 'after_AB':after_ab.as_dict(),
        'after_AAA':after_aaa.as_dict(), 'entropy_prior':prior.entropy_bits(),
        'entropy_after_AAA':after_aaa.entropy_bits(),
    }


def run_belief(horizon:int):
    model=BinarySensorModel(.7)
    planner=BeliefStateInternalPlanner(
        model, max_horizon=8, max_expansions=256, top_k_outcomes=4,
        risk_aversion=0.0, unknown_risk_weight=0.0, cost_weight=0.0,
        proximity_weight=0.0, step_penalty=.0001,
        min_goal_probability=0.0, max_hazard_probability=1.0, max_unknown_probability=1.0,
    )
    result=planner.plan(
        'binary_hidden',entity_id='probe',initial_state={'loc':'start'},
        actions=('sense','chooseA','chooseB'),goal=StateGoal({'loc':'goal'},{'loc':'hazard'}),
        initial_belief={'A':.5,'B':.5},horizon=horizon,
    )
    return result


def run_alpha4_compressed(horizon:int):
    planner=ContingentInternalPlanner(
        LastObservationCompressedModel(.7),max_horizon=8,max_expansions=768,top_k_outcomes=4,
        risk_aversion=0.0,unknown_risk_weight=0.0,cost_weight=0.0,proximity_weight=0.0,
        step_penalty=.0001,min_goal_probability=0.0,max_hazard_probability=1.0,max_unknown_probability=1.0,
        compute_open_loop_reference=False,
    )
    return planner.plan('compressed',entity_id='probe',initial_state={'loc':'start'},
        actions=('sense','chooseA','chooseB'),goal=StateGoal({'loc':'goal'},{'loc':'hazard'}),horizon=horizon)


def branch_context_probe():
    planner=BeliefStateInternalPlanner(
        BranchContextModel(),max_horizon=2,max_expansions=32,risk_aversion=0.0,
        cost_weight=0.0,proximity_weight=0.0,step_penalty=0.0,
        min_goal_probability=.99,max_hazard_probability=.01,max_unknown_probability=.01,
    )
    r=planner.plan('ctx',entity_id='x',initial_state={'loc':'start'},
        actions=('sense','left','right'),goal=StateGoal({'loc':'goal'},{'loc':'hazard'}),
        initial_belief={'only':1.0},horizon=2)
    root=r['policy_graph'][r['root_node']]
    branch_actions={b['observation']:r['policy_graph'][b['next_node']]['action'] for b in root['branches']}
    return {'goal_probability':r['best']['goal_probability'],'status':r['status'],
            'branch_actions':branch_actions,'policy_nodes':r['policy_nodes']}


def main():
    p=posterior_checks()
    one=run_belief(2); three=run_belief(4); five=run_belief(6); seven=run_belief(8)
    compressed=run_alpha4_compressed(8)
    ctx=branch_context_probe()
    targets={1:.7,3:.784,5:.83692,7:.873964}
    actual={1:one['best']['goal_probability'],3:three['best']['goal_probability'],
            5:five['best']['goal_probability'],7:seven['best']['goal_probability']}
    checks={
        'version_is_current_release':__version__=='0.4.0-alpha.7.9',
        'single_clue_matches_bayes':abs(actual[1]-targets[1])<1e-12,
        'three_clue_expected_accuracy_matches_bayes':abs(actual[3]-targets[3])<1e-12,
        'five_clue_expected_accuracy_matches_bayes':abs(actual[5]-targets[5])<1e-12,
        'seven_clue_expected_accuracy_matches_bayes':abs(actual[7]-targets[7])<1e-12,
        'repeated_evidence_improves_policy':actual[7]>actual[5]>actual[3]>actual[1],
        'contradictory_AB_returns_to_prior':abs(p['after_AB']['A']-.5)<1e-12 and abs(p['after_AB']['B']-.5)<1e-12,
        'consistent_evidence_reduces_entropy':p['entropy_after_AAA']<p['entropy_prior'],
        'alpha4_last_observation_control_stays_at_70pct':abs(compressed['best']['goal_probability']-.7)<1e-12,
        'belief_memo_merges_equivalent_posteriors':seven['belief_merge_hits']>0,
        'seven_clue_search_within_256_expansions':seven['expansions']<=256 and seven['status']!='budget_exhausted',
        'policy_representation_is_compact_dag':seven['policy_nodes']<431,
        'outcome_specific_branch_context_works':ctx['status']=='belief_contingent_plan_found' and abs(ctx['goal_probability']-1.0)<1e-12 and ctx['branch_actions']=={'left':'left','right':'right'},
    }
    payload={
        'version':__version__,
        'benchmark':'ASM v0.4.0-alpha.5.1 Belief-State Planning & Partial Observability',
        'before_alpha4_last_observation':{
            'seven_clue_goal_probability':compressed['best']['goal_probability'],
            'status':compressed['status'],'expansions':compressed['expansions'],
            'prior_external_history_control_from_alpha4_hard_feed':{
                'seven_clue_goal_probability':.873964,'expansions':765,'policy_nodes':431,
                'note':'Recorded alpha.4 hard-feed control; history was externally supplied, not an ASM capability.'
            },
        },
        'after_alpha5_belief_state':{
            'goal_probability_by_clues':{str(k):actual[k] for k in (1,3,5,7)},
            'targets':{str(k):targets[k] for k in (1,3,5,7)},
            'seven_clue':{
                'status':seven['status'],'expansions':seven['expansions'],
                'policy_nodes':seven['policy_nodes'],'unique_belief_states':seven['unique_belief_states'],
                'belief_merge_hits':seven['belief_merge_hits'],'belief_updates':seven['belief_updates'],
                'max_evidence_count':seven['max_evidence_count'],
            },
            'posterior_checks':p,'outcome_specific_context':ctx,
        },
        'checks':checks,'passed':sum(checks.values()),'total':len(checks),
        'claim_boundary':(
            'Controlled discrete latent-state planning. This does not establish broad Bayesian reasoning, '
            'automatic latent-variable discovery, general causality, AGI, or RSI.'
        ),
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(payload,indent=2,sort_keys=True),encoding='utf-8')
    print(json.dumps(payload,indent=2,sort_keys=True))
    if not all(checks.values()): raise SystemExit(1)

if __name__=='__main__': main()
