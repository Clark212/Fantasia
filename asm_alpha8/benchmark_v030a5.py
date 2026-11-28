from __future__ import annotations

import json
import statistics
import tempfile
import time
from pathlib import Path

from asm import __version__
from asm.transition_mechanism import TransitionMechanismBank

ROOT = Path(__file__).resolve().parent
RESULT = ROOT / 'results' / 'competitive_seismic_routing_benchmark.json'

# Frozen before execution. Ten small domains x five competing mechanisms = 50.
KINDS = [
    'door', 'valve', 'container', 'switch', 'heater',
    'fan', 'elevator', 'lock', 'timer', 'inventory',
]
ACTIONS = ['open', 'activate', 'toggle', 'start', 'advance']
VARIANTS = ['a', 'b', 'c', 'd', 'e']
CASES = []
for ki, kind in enumerate(KINDS):
    action = ACTIONS[ki % len(ACTIONS)]
    for vi, variant in enumerate(VARIANTS):
        mechanism = f'{kind}_{variant}_dyn'
        before = {'kind': kind, 'variant': variant, 'phase': 0}
        after = {'kind': kind, 'variant': variant, 'phase': 1}
        CASES.append((mechanism, before, action, after))

GATES = {
    'dense_accuracy': 1.0,
    'seismic_accuracy': 1.0,
    'topk_recall_min': 0.98,
    'call_reduction_min': 0.90,
    'ambiguous_widen_fraction_min': 1.0,
    'ood_dense_fallback': True,
    'negative_feedback_must_reduce_wrong_relevance': True,
    'negative_feedback_must_promote_correct_route': True,
    'calibration_support_min': 4,
    'retention_after_feedback': True,
}


def median_ms(values):
    return statistics.median(values) if values else 0.0


def train_case(bank, mechanism, before, action, after, repeats=3):
    for i in range(repeats):
        bank.observe(
            mechanism,
            entity_id=f'{mechanism}_train_{i}',
            state=before,
            action=action,
            after_state=after,
        )


with tempfile.TemporaryDirectory() as td:
    db = Path(td) / 'alpha5.db'
    bank = TransitionMechanismBank(
        db,
        hidden_dim=8,
        train_steps=1,
        learning_rate=.012,
        seed=17,
        scheduler_max_calls=1,
        scheduler_medium_calls=3,
        scheduler_min_relevance=.45,
        scheduler_high_confidence=.74,
        scheduler_low_confidence=.46,
        scheduler_min_margin=.08,
        scheduler_calibration_min_support=4,
    )

    t0 = time.perf_counter()
    for case in CASES:
        train_case(bank, *case)
    training_seconds = time.perf_counter() - t0

    dense_correct = seismic_correct = 0
    dense_calls = seismic_calls = 0
    topk_hits = 0
    rows = []
    dense_times, seismic_times = [], []

    for i, (mechanism, before, action, after) in enumerate(CASES):
        t = time.perf_counter_ns()
        dense = bank.predict_routed(
            entity_id=f'dense_{i}', state=before, action=action, mode='dense', recover=False
        )
        dense_times.append((time.perf_counter_ns() - t) / 1e6)
        t = time.perf_counter_ns()
        seismic = bank.predict_routed(
            entity_id=f'seismic_{i}', state=before, action=action, mode='seismic', recover=False
        )
        seismic_times.append((time.perf_counter_ns() - t) / 1e6)

        dp = dense['chosen']['prediction']['predicted_state'] if dense['chosen'] else None
        sp = seismic['chosen']['prediction']['predicted_state'] if seismic['chosen'] else None
        selected_types = [x['mechanism_type'] for x in seismic['selected']]
        dense_correct += int(dp == after)
        seismic_correct += int(sp == after)
        dense_calls += dense['calls']
        seismic_calls += seismic['calls']
        topk_hits += int(mechanism in selected_types)
        rows.append({
            'mechanism': mechanism,
            'reason': seismic['reason'],
            'routing_confidence': seismic['routing_confidence'],
            'margin': seismic['margin'],
            'selected': selected_types,
            'calls': seismic['calls'],
            'correct': sp == after,
        })

    # Remove variant information. Five mechanisms now have equally plausible broad
    # evidence inside each domain; alpha.5 should widen rather than claim a top-1.
    ambiguous = []
    for i, kind in enumerate(KINDS):
        action = ACTIONS[i % len(ACTIONS)]
        route = bank.route(state={'kind': kind, 'phase': 0}, action=action, mode='seismic')
        ambiguous.append({
            'kind': kind,
            'reason': route['reason'],
            'breadth': len(route['selected']),
            'margin': route['margin'],
            'confidence': route['routing_confidence'],
        })

    # Completely unknown structured input must not be starved.
    ood = bank.predict_routed(
        entity_id='ood',
        state={'kind': 'unknown_machine', 'phase': 9, 'novel': True},
        action='pulse_unknown',
        mode='seismic',
        recover=False,
    )

    # Prediction-error routing feedback probe. Both mechanisms initially share the
    # same visible profile; a new context first ties, then observing the true
    # mechanism should penalize the actually attempted wrong route.
    fb_db = Path(td) / 'feedback.db'
    feedback_bank = TransitionMechanismBank(
        fb_db,
        hidden_dim=8,
        train_steps=1,
        learning_rate=.012,
        seed=17,
        scheduler_medium_calls=2,
        scheduler_calibration_min_support=4,
    )
    base = {'kind': 'valve', 'open': False}
    for mechanism in ('normal', 'safety'):
        for j in range(3):
            feedback_bank.observe(
                mechanism,
                entity_id=f'{mechanism}_{j}',
                state=base,
                action='open',
                after_state={'kind': 'valve', 'open': True, 'route': mechanism},
            )
    query = {'kind': 'valve', 'open': False, 'pressure_safe': False}
    before_route = feedback_bank.route(state=query, action='open', mode='seismic')
    wrong_before = next(x['relevance'] for x in before_route['candidates'] if x['mechanism_type'] == 'normal')
    feedback_bank.predict_routed(
        entity_id='feedback', state=query, action='open', mode='seismic', recover=False
    )
    feedback_result = feedback_bank.observe(
        'safety',
        entity_id='feedback',
        state=query,
        action='open',
        after_state={'kind': 'valve', 'open': False, 'route': 'safety'},
    )
    after_route = feedback_bank.route(state=query, action='open', mode='seismic')
    wrong_after_row = next(x for x in after_route['candidates'] if x['mechanism_type'] == 'normal')
    normal_known = feedback_bank.route(state=base, action='open', mode='seismic')

    # Separate clean route feedback populates empirical confidence correction.
    cal_state = {'kind': 'calibrator', 'variant': 'main', 'phase': 0}
    cal_after = {'kind': 'calibrator', 'variant': 'main', 'phase': 1}
    for j in range(3):
        feedback_bank.observe('calibrator_dyn', entity_id=f'ct_{j}', state=cal_state, action='advance', after_state=cal_after)
    for j in range(5):
        entity = f'cal_{j}'
        feedback_bank.predict_routed(entity_id=entity, state=cal_state, action='advance', mode='seismic', recover=False)
        feedback_bank.observe('calibrator_dyn', entity_id=entity, state=cal_state, action='advance', after_state=cal_after)
    calibrated = feedback_bank.route(state=cal_state, action='advance', mode='seismic')
    feedback_stats = feedback_bank.stats()['scheduler']
    feedback_bank.close()

    # Persistence audit for alpha.5-specific SQLite state.
    feedback_bank = TransitionMechanismBank(
        fb_db, hidden_dim=8, train_steps=1, learning_rate=.012, seed=17,
        scheduler_calibration_min_support=4,
    )
    persisted = feedback_bank.route(state=cal_state, action='advance', mode='seismic')
    persisted_stats = feedback_bank.stats()['scheduler']
    feedback_bank.close()

    bank_stats = bank.stats()['scheduler']
    bank.close()

n = len(CASES)
dense_acc = dense_correct / n
seismic_acc = seismic_correct / n
topk_recall = topk_hits / n
call_reduction = 1.0 - seismic_calls / max(1, dense_calls)
ambiguous_widen_fraction = sum(int(x['breadth'] > 1 and x['margin'] < .08) for x in ambiguous) / len(ambiguous)
negative_reduced = wrong_after_row['relevance'] < wrong_before and wrong_after_row['negative_support'] > 0
correct_promoted = after_route['candidates'][0]['mechanism_type'] == 'safety'
retained = any(x['mechanism_type'] == 'normal' for x in normal_known['selected'])

checks = []
def add(name, passed, **details):
    checks.append({'name': name, 'pass': bool(passed), 'details': details})

add('dense_accuracy_frozen_100pct', dense_acc >= GATES['dense_accuracy'], correct=dense_correct, total=n)
add('seismic_accuracy_matches_dense_100pct', seismic_acc >= GATES['seismic_accuracy'] and seismic_correct == dense_correct, correct=seismic_correct, total=n)
add('scheduler_topk_recall_at_least_98pct', topk_recall >= GATES['topk_recall_min'], recall=topk_recall, hits=topk_hits, total=n)
add('mechanism_call_reduction_at_least_90pct', call_reduction >= GATES['call_reduction_min'], dense_calls=dense_calls, seismic_calls=seismic_calls, reduction=call_reduction)
add('ambiguous_inputs_widen_instead_of_fake_top1', ambiguous_widen_fraction >= GATES['ambiguous_widen_fraction_min'], fraction=ambiguous_widen_fraction, rows=ambiguous)
add('ood_falls_back_dense', ood['fallback'] and ood['calls'] == ood['total_mechanisms'], calls=ood['calls'], total=ood['total_mechanisms'], reason=ood['reason'])
add('prediction_error_reduces_wrong_route_relevance', negative_reduced, before=wrong_before, after=wrong_after_row)
add('prediction_error_promotes_correct_route', correct_promoted, before_top=before_route['candidates'][0]['mechanism_type'], after_top=after_route['candidates'][0]['mechanism_type'], feedback=feedback_result.get('routing_feedback'))
add('feedback_does_not_erase_prior_normal_route', retained, route=normal_known)
add('empirical_confidence_correction_activates', calibrated['calibration_source'] == 'empirical' and calibrated['calibration_support'] >= GATES['calibration_support_min'], route=calibrated)
add('routing_evidence_and_calibration_persist', persisted['calibration_source'] == 'empirical' and persisted_stats['routing_evidence_features'] > 0 and persisted_stats['calibration_samples'] >= GATES['calibration_support_min'], route=persisted, stats=persisted_stats)

payload = {
    'benchmark': 'ASM v0.3.0-alpha.5 Competitive Seismic Routing',
    'version': __version__,
    'frozen_gates': GATES,
    'mechanisms': n,
    'domains': len(KINDS),
    'training_seconds': training_seconds,
    'dense': {'correct': dense_correct, 'total': n, 'mechanism_calls': dense_calls, 'median_ms': median_ms(dense_times)},
    'seismic': {'correct': seismic_correct, 'total': n, 'mechanism_calls': seismic_calls, 'call_reduction': call_reduction, 'median_ms': median_ms(seismic_times)},
    'topk_recall': topk_recall,
    'ambiguous': ambiguous,
    'ood': {'reason': ood['reason'], 'calls': ood['calls'], 'total_mechanisms': ood['total_mechanisms'], 'fallback': ood['fallback']},
    'negative_feedback': {
        'wrong_relevance_before': wrong_before,
        'wrong_relevance_after': wrong_after_row['relevance'],
        'wrong_negative_support_after': wrong_after_row['negative_support'],
        'top_before': before_route['candidates'][0]['mechanism_type'],
        'top_after': after_route['candidates'][0]['mechanism_type'],
        'feedback': feedback_result.get('routing_feedback'),
        'prior_route_retained': retained,
    },
    'calibration': {
        'source': calibrated['calibration_source'],
        'support': calibrated['calibration_support'],
        'confidence': calibrated['routing_confidence'],
        'persisted_source': persisted['calibration_source'],
        'persisted_support': persisted['calibration_support'],
        'samples': persisted_stats['calibration_samples'],
    },
    'scheduler_stats': bank_stats,
    'feedback_scheduler_stats': feedback_stats,
    'rows': rows,
    'checks': checks,
    'summary': {'passed': sum(int(x['pass']) for x in checks), 'total': len(checks)},
    'notes': [
        'Controlled architecture benchmark; not a standardized intelligence benchmark.',
        'Mechanism identities remain supplied. Alpha.5 tests competition among learned applicability profiles, not mechanism discovery.',
        'Confidence is heuristic until enough routed outcomes populate a confidence bucket; then empirical correction is applied.',
        'Negative routing evidence is added only to wrong mechanisms that were actually executed before the true transition was observed.',
        'The 50-mechanism scale test uses intentionally simple one-outcome local mechanisms to isolate scheduler behavior.',
    ],
}
payload['summary']['accuracy_pct'] = 100.0 * payload['summary']['passed'] / payload['summary']['total']
RESULT.write_text(json.dumps(payload, indent=2), encoding='utf-8')
print(json.dumps({
    'version': __version__,
    'summary': payload['summary'],
    'dense': payload['dense'],
    'seismic': payload['seismic'],
    'topk_recall': topk_recall,
    'ambiguous_widen_fraction': ambiguous_widen_fraction,
    'negative_feedback': payload['negative_feedback'],
    'calibration': payload['calibration'],
}, indent=2))
print('RESULT:', RESULT)
if payload['summary']['passed'] != payload['summary']['total']:
    raise SystemExit(1)
