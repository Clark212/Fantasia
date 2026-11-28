from __future__ import annotations

import json
import time
from pathlib import Path

from asm import __version__
from asm.transition_mechanism import LocalRecurrentTransitionMechanism

ROOT = Path(__file__).resolve().parent
RESULT = ROOT / 'results' / 'elastic_mechanism_capacity_benchmark.json'
GROUPS = (tuple(range(0, 32)), tuple(range(32, 64)), tuple(range(64, 96)))
GATES = {
    'phase1_min': 30,
    'phase2_old_min': 30,
    'phase2_new_min': 30,
    'phase3_group_min': 29,
    'post_hammer_group_min': 30,
    'restart_group_min': 30,
    'known_outcomes': 96,
    'final_capacity': 128,
    'capacity_expansions': 2,
    'anchor_outcome_coverage_min': 96,
}


def case(i: int):
    before = {'kind': 'machine', 'mode': i, 'phase': 0, 'signal': f's{i % 9}'}
    after = {'kind': 'machine', 'mode': i, 'phase': 1, 'result': i}
    return before, 'advance', after


def build(*, capacity_limit: int = 128):
    return LocalRecurrentTransitionMechanism(
        'elastic_shared_machine', hidden_dim=48, train_steps=2, learning_rate=.008,
        seed=17, max_outcomes=32, outcome_capacity_limit=capacity_limit,
        retention_anchor_limit=96, retention_anchor_batch_limit=8,
    )


def train(mech, ids, reps: int, tag: str):
    for i in ids:
        state, action, after = case(i)
        for r in range(reps):
            mech.observe(
                entity_id=f'{tag}_{i}_{r}_{mech.total_observations}',
                state=state, action=action, after_state=after,
            )


def evaluate(mech, ids, tag: str):
    rows = []
    correct = 0
    for i in ids:
        state, action, after = case(i)
        pred = mech.predict(entity_id=f'{tag}_{i}', state=state, action=action)
        ok = pred.predicted_state == after
        correct += int(ok)
        rows.append({'id': i, 'correct': ok, 'confidence': pred.confidence})
    return correct, rows


started = time.perf_counter()
mech = build()
train(mech, GROUPS[0], 10, 'g0')
phase1, _ = evaluate(mech, GROUPS[0], 'phase1')
capacity_after_phase1 = mech.stats()['outcome_capacity']

train(mech, GROUPS[1], 10, 'g1')
phase2 = [evaluate(mech, GROUPS[j], f'phase2_{j}')[0] for j in range(2)]
capacity_after_phase2 = mech.stats()['outcome_capacity']

train(mech, GROUPS[2], 10, 'g2')
phase3 = [evaluate(mech, GROUPS[j], f'phase3_{j}')[0] for j in range(3)]
capacity_after_phase3 = mech.stats()['outcome_capacity']

# Late pressure on the newest outcomes checks that expansion plus continued
# learning does not erase the earlier rows the head copied forward.
train(mech, GROUPS[2], 15, 'hammer')
post_hammer = [evaluate(mech, GROUPS[j], f'hammer_{j}')[0] for j in range(3)]
detail = mech.stats()

blob = mech.export_blob()
restored = build()
restored.import_blob(blob)
restart = [evaluate(restored, GROUPS[j], f'restart_{j}')[0] for j in range(3)]
restart_detail = restored.stats()

# Frozen fixed-capacity ablation reproduces the actual alpha.6 wall: outcome #33
# cannot be represented. This is an exception-only control, not an accuracy score.
fixed = build(capacity_limit=32)
fixed_capacity_rejected_33rd = False
try:
    for i in range(33):
        state, action, after = case(i)
        fixed.observe(entity_id=f'fixed_{i}', state=state, action=action, after_state=after)
except RuntimeError:
    fixed_capacity_rejected_33rd = True

checks = []
def add(name, passed, **details):
    checks.append({'name': name, 'pass': bool(passed), 'details': details})

add('phase1_learns_initial_32', phase1 >= GATES['phase1_min'], value=phase1)
add('first_expansion_preserves_old_group', phase2[0] >= GATES['phase2_old_min'], value=phase2[0])
add('first_expansion_learns_new_group', phase2[1] >= GATES['phase2_new_min'], value=phase2[1])
add('second_expansion_retains_all_groups', min(phase3) >= GATES['phase3_group_min'], values=phase3)
add('late_stream_retains_all_groups', min(post_hammer) >= GATES['post_hammer_group_min'], values=post_hammer)
add('serialization_retains_all_groups', min(restart) >= GATES['restart_group_min'], values=restart)
add('all_96_outcomes_registered', restart_detail['known_outcomes'] == GATES['known_outcomes'], value=restart_detail['known_outcomes'])
add('capacity_grows_32_64_128', restart_detail['capacity_history'] == [32, 64, 128], value=restart_detail['capacity_history'])
add('two_expansions_recorded', restart_detail['capacity_expansions'] == GATES['capacity_expansions'], value=restart_detail['capacity_expansions'])
add('final_capacity_is_bounded', restart_detail['outcome_capacity'] == GATES['final_capacity'], value=restart_detail['outcome_capacity'])
add('retention_covers_all_outcomes', restart_detail['retention_anchor_outcomes'] >= GATES['anchor_outcome_coverage_min'], value=restart_detail['retention_anchor_outcomes'])
add('alpha6_fixed_head_rejects_33rd_outcome', fixed_capacity_rejected_33rd)

payload = {
    'benchmark': 'ASM v0.3.0-alpha.7 Elastic Mechanism Capacity',
    'version': __version__,
    'frozen_gates': GATES,
    'phase1': {'group0': phase1, 'capacity': capacity_after_phase1},
    'phase2': {'groups': phase2, 'capacity': capacity_after_phase2},
    'phase3': {'groups': phase3, 'capacity': capacity_after_phase3},
    'post_hammer': {'groups': post_hammer},
    'restart': {'groups': restart},
    'detail': detail,
    'restart_detail': restart_detail,
    'fixed_capacity_ablation': {'rejected_33rd': fixed_capacity_rejected_33rd},
    'checks': checks,
    'summary': {'passed': sum(int(x['pass']) for x in checks), 'total': len(checks)},
    'elapsed_seconds': time.perf_counter() - started,
    'notes': [
        'Controlled architecture benchmark; not a standardized intelligence benchmark.',
        'Ninety-six outcomes share one recurrent mechanism and force two output-head expansions.',
        'Old output rows are copied exactly and Adam moments are carried forward when capacity grows.',
        'The fixed-capacity control reproduces alpha.6 behavior by setting the capacity ceiling to 32.',
        'This demonstrates bounded elastic capacity, not unlimited world-model capacity or general reasoning.',
    ],
}
payload['summary']['accuracy_pct'] = 100.0 * payload['summary']['passed'] / payload['summary']['total']
RESULT.parent.mkdir(exist_ok=True)
RESULT.write_text(json.dumps(payload, indent=2), encoding='utf-8')
print(json.dumps({
    'version': __version__, 'summary': payload['summary'],
    'phase1': payload['phase1'], 'phase2': payload['phase2'],
    'phase3': payload['phase3'], 'post_hammer': payload['post_hammer'],
    'restart': payload['restart'],
    'capacity_history': restart_detail['capacity_history'],
    'known_outcomes': restart_detail['known_outcomes'],
    'anchors': restart_detail['retention_anchor_outcomes'],
    'fixed_capacity_rejected_33rd': fixed_capacity_rejected_33rd,
}, indent=2))
print('RESULT:', RESULT)
if payload['summary']['passed'] != payload['summary']['total']:
    raise SystemExit(1)
