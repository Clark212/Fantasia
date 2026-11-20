from __future__ import annotations
import json
from pathlib import Path

from asm import __version__
from asm.planning import BoundedInternalPlanner, StateGoal
from asm.transition_mechanism import LocalRecurrentTransitionMechanism

OUT=Path('results/planning_v040a1_benchmark.json')


def build_mechanism(seed=404):
    m=LocalRecurrentTransitionMechanism(
        'v040a1_movement', hidden_dim=16, train_steps=1, max_outcomes=8,
        outcome_capacity_limit=64, retention_anchor_limit=96, seed=seed,
        abstraction_min_support=8, abstraction_min_precision=.95,
        abstraction_min_diversity=4, abstraction_sparse_enabled=True,
        abstraction_sparse_max_retained_features=2,
    )
    m.replay_limit=64; m.replay_batch_limit=4
    for position in range(4):
        for action in ('left','right'):
            nxt=max(0,min(3,position+(1 if action=='right' else -1)))
            for variant in range(12):
                m.observe(
                    entity_id=f'train-{position}-{action}-{variant}',
                    state={'position':position,'token':f't{variant}','noise':variant%5},
                    action=action,
                    after_state={'position':nxt},
                )
    return m


def main():
    m=build_mechanism()
    planner=BoundedInternalPlanner(
        lambda mechanism_type, **kw: m.predict_simulated(**kw),
        max_horizon=5, beam_width=8, max_expansions=64,
        uncertainty_penalty=.35, step_penalty=.01,
    )
    initial={'position':0,'token':'unseen-start','noise':99}
    before_stats=m.stats().copy()
    result=planner.plan('v040a1_movement',entity_id='planning-probe',initial_state=initial,
                        actions=['left','right'],goal=StateGoal({'position':3}),horizon=3)
    after_stats=m.stats().copy()

    # A second, deliberately too-short horizon should not hallucinate success.
    short=planner.plan('v040a1_movement',entity_id='planning-short',initial_state=initial,
                       actions=['left','right'],goal=StateGoal({'position':3}),horizon=2)

    checks={
        'version_is_v040a1_capability_preserved': __version__=='0.4.0-alpha.7',
        'learned_mechanism_has_reusable_abstractions': before_stats['abstraction_promoted']>=8,
        'three_step_goal_reached': result['status']=='goal_reached',
        'correct_action_sequence': result['best']['actions']==['right','right','right'],
        'predicted_terminal_state_correct': result['best']['predicted_state']=={'position':3},
        'uncertainty_compounds': 0.0 < result['best']['path_confidence'] < result['best']['trace'][0]['confidence'] < 1.0,
        'simulation_is_explicitly_marked': result['simulated_only'] and result['best']['source']=='simulated',
        'planner_is_bounded': result['expansions']<=64,
        'short_horizon_does_not_claim_goal': short['status']!='goal_reached',
        'planning_does_not_add_observations': after_stats['observations']==before_stats['observations'],
    }
    payload={
        'version':__version__,
        'benchmark':'ASM v0.4.0-alpha.1 Planning & Internal Simulation (preservation gate)',
        'trained_mechanism_stats':before_stats,
        'plan':result,
        'short_horizon_control':short,
        'checks':checks,
        'passed':sum(checks.values()),
        'total':len(checks),
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(payload,indent=2,sort_keys=True))
    print(json.dumps(payload,indent=2,sort_keys=True))
    if not all(checks.values()):
        raise SystemExit(1)

if __name__=='__main__':
    main()
