from __future__ import annotations

import json
import time
from pathlib import Path

from asm import __version__
from asm.transition_mechanism import LocalRecurrentTransitionMechanism

ROOT = Path(__file__).resolve().parent
RESULT = ROOT / 'results' / 'continual_retention_benchmark.json'

OLD_IDS = tuple(range(16))
NEW_IDS = tuple(range(16, 32))
GATES = {
    'phase1_old_min': 15,
    'post_new_old_min': 14,
    'post_new_new_min': 15,
    'post_hammer_old_min': 14,
    'post_hammer_new_min': 15,
    'restart_old_min': 14,
    'restart_new_min': 15,
    'anchor_outcome_coverage_min': 32,
    'anchor_bound_max': 96,
    'ablation_old_retention_max': 8,
    'protected_gain_over_ablation_min': 6,
}


def case(i: int):
    before = {'kind': 'machine', 'mode': i, 'phase': 0, 'signal': f's{i % 5}'}
    after = {'kind': 'machine', 'mode': i, 'phase': 1, 'result': i}
    return before, 'advance', after


def build(batch_limit: int):
    return LocalRecurrentTransitionMechanism(
        'shared_machine', hidden_dim=32, train_steps=2, learning_rate=.008,
        seed=17, max_outcomes=32, retention_anchor_limit=96,
        retention_anchor_batch_limit=batch_limit,
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
    correct = 0
    rows = []
    for i in ids:
        state, action, after = case(i)
        pred = mech.predict(entity_id=f'{tag}_{i}', state=state, action=action)
        ok = pred.predicted_state == after
        correct += int(ok)
        rows.append({'id': i, 'correct': ok, 'confidence': pred.confidence})
    return correct, rows


def curriculum(batch_limit: int):
    mech = build(batch_limit)
    started = time.perf_counter()
    train(mech, OLD_IDS, 20, 'old')
    phase1_old, _ = evaluate(mech, OLD_IDS, 'phase1')

    train(mech, NEW_IDS, 20, 'new')
    post_new_old, _ = evaluate(mech, OLD_IDS, 'post_new_old')
    post_new_new, _ = evaluate(mech, NEW_IDS, 'post_new_new')

    # Long later stream with the same structural schema. In alpha.5 this floods
    # the 256-item recency buffer and removes rehearsal evidence for old classes.
    train(mech, NEW_IDS, 30, 'hammer')
    post_hammer_old, old_rows = evaluate(mech, OLD_IDS, 'post_hammer_old')
    post_hammer_new, new_rows = evaluate(mech, NEW_IDS, 'post_hammer_new')
    detail = mech.stats()

    blob = mech.export_blob()
    restored = build(batch_limit)
    restored.import_blob(blob)
    restart_old, _ = evaluate(restored, OLD_IDS, 'restart_old')
    restart_new, _ = evaluate(restored, NEW_IDS, 'restart_new')
    restart_detail = restored.stats()

    return {
        'phase1_old': phase1_old,
        'post_new_old': post_new_old,
        'post_new_new': post_new_new,
        'post_hammer_old': post_hammer_old,
        'post_hammer_new': post_hammer_new,
        'restart_old': restart_old,
        'restart_new': restart_new,
        'detail': detail,
        'restart_detail': restart_detail,
        'old_rows': old_rows,
        'new_rows': new_rows,
        'elapsed_seconds': time.perf_counter() - started,
    }


protected = curriculum(6)
ablation = curriculum(0)

checks = []
def add(name, passed, **details):
    checks.append({'name': name, 'pass': bool(passed), 'details': details})

add('old_skills_learn_before_interference', protected['phase1_old'] >= GATES['phase1_old_min'], value=protected['phase1_old'])
add('old_skills_survive_new_half', protected['post_new_old'] >= GATES['post_new_old_min'], value=protected['post_new_old'])
add('new_half_learns', protected['post_new_new'] >= GATES['post_new_new_min'], value=protected['post_new_new'])
add('old_skills_survive_late_stream', protected['post_hammer_old'] >= GATES['post_hammer_old_min'], value=protected['post_hammer_old'])
add('new_skills_survive_late_stream', protected['post_hammer_new'] >= GATES['post_hammer_new_min'], value=protected['post_hammer_new'])
add('retention_survives_serialization_old', protected['restart_old'] >= GATES['restart_old_min'], value=protected['restart_old'])
add('retention_survives_serialization_new', protected['restart_new'] >= GATES['restart_new_min'], value=protected['restart_new'])
add('anchors_cover_all_outcomes', protected['restart_detail']['retention_anchor_outcomes'] >= GATES['anchor_outcome_coverage_min'], detail=protected['restart_detail'])
add('anchors_remain_bounded', protected['restart_detail']['retention_anchors'] <= GATES['anchor_bound_max'], detail=protected['restart_detail'])
add('alpha5_replay_ablation_reproduces_forgetting', ablation['post_hammer_old'] <= GATES['ablation_old_retention_max'], value=ablation['post_hammer_old'])
add('anchors_materially_improve_retention', protected['post_hammer_old'] - ablation['post_hammer_old'] >= GATES['protected_gain_over_ablation_min'], protected=protected['post_hammer_old'], ablation=ablation['post_hammer_old'])

payload = {
    'benchmark': 'ASM v0.3.0-alpha.6 Continual Retention Stress',
    'version': __version__,
    'frozen_gates': GATES,
    'protected': protected,
    'alpha5_replay_ablation': ablation,
    'checks': checks,
    'summary': {'passed': sum(int(x['pass']) for x in checks), 'total': len(checks)},
    'notes': [
        'Controlled architecture benchmark; not a standardized intelligence benchmark.',
        'Thirty-two outcomes share one recurrent mechanism, so this targets shared-parameter interference.',
        'The ablation uses alpha.5 replay selection by setting the new anchor rehearsal budget to zero; network, seed, optimizer, and curriculum remain the same.',
        'Retention anchors are bounded representatives, not a growing archive and not hardcoded domain rules.',
        'Serialization uses the same model blob path persisted by the mechanism bank.',
        'This does not establish broad continual learning; it fixes one measured local-transition forgetting mode.',
    ],
}
payload['summary']['accuracy_pct'] = 100.0 * payload['summary']['passed'] / payload['summary']['total']
RESULT.parent.mkdir(exist_ok=True)
RESULT.write_text(json.dumps(payload, indent=2), encoding='utf-8')
print(json.dumps({
    'version': __version__,
    'summary': payload['summary'],
    'protected': {k: protected[k] for k in ('phase1_old','post_new_old','post_new_new','post_hammer_old','post_hammer_new','restart_old','restart_new')},
    'alpha5_replay_ablation': {k: ablation[k] for k in ('phase1_old','post_new_old','post_new_new','post_hammer_old','post_hammer_new','restart_old','restart_new')},
    'anchors': protected['restart_detail']['retention_anchors'],
    'anchor_outcomes': protected['restart_detail']['retention_anchor_outcomes'],
}, indent=2))
print('RESULT:', RESULT)
if payload['summary']['passed'] != payload['summary']['total']:
    raise SystemExit(1)
