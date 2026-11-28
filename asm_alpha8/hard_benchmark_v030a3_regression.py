from __future__ import annotations

import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from asm import ASMEngine, __version__  # noqa: E402
from asm.config import ASMConfig  # noqa: E402


class Score:
    def __init__(self):
        self.rows = []

    def add(self, category, name, ok, details=None):
        self.rows.append({
            'category': category,
            'name': name,
            'pass': bool(ok),
            'details': details or {},
        })

    def summary(self):
        cats = {}
        for row in self.rows:
            rec = cats.setdefault(row['category'], {'passed': 0, 'total': 0})
            rec['total'] += 1
            rec['passed'] += int(row['pass'])
        for rec in cats.values():
            rec['accuracy_pct'] = round(100 * rec['passed'] / max(1, rec['total']), 2)
        passed = sum(int(r['pass']) for r in self.rows)
        total = len(self.rows)
        return {
            'passed': passed,
            'total': total,
            'accuracy_pct': round(100 * passed / max(1, total), 2),
            'categories': cats,
        }


def train(engine, texts):
    for text in texts:
        engine.process(text, training=True)


def top_id(engine, text):
    q = engine.infer_discovered_relation(text)
    return (q['relation_ids'][0] if q['supported'] and q['relation_ids'] else None), q


def relation_suite(score: Score, td: Path):
    asm = ASMEngine(td / 'relations.db')
    try:
        # Three hidden relation families. Connectors are invented and labels are
        # withheld from ASM.
        fam_a = [
            'box glarps item', 'crate glarps object', 'container glarps component',
            'box snarps item', 'crate snarps object', 'container snarps component',
        ]
        fam_b = [
            'alice traks coin', 'bob traks key', 'cara traks book',
            'alice vims coin', 'bob vims key', 'cara vims book',
        ]
        fam_c = [
            'signal frels alarm', 'pulse frels sensor', 'voltage frels relay',
            'signal quens alarm', 'pulse quens sensor', 'voltage quens relay',
        ]
        train(asm, fam_a + fam_b + fam_c)

        rid_a, qa = top_id(asm, 'vessel glarps module')
        rid_b, qb = top_id(asm, 'dana traks badge')
        rid_c, qc = top_id(asm, 'current frels actuator')
        score.add('relation_generalization', 'three_family_reuse',
                  all([rid_a, rid_b, rid_c]) and len({rid_a, rid_b, rid_c}) == 3,
                  {'ids': [rid_a, rid_b, rid_c], 'queries': [qa, qb, qc]})

        # Same hidden relation, unseen synonym connector with overlapping role
        # structure only after it is observed. This checks convergence.
        train(asm, [
            'box plens item', 'crate plens object', 'container plens component',
        ])
        rid_plens, q_plens = top_id(asm, 'vessel plens module')
        score.add('relation_generalization', 'third_paraphrase_convergence',
                  rid_plens == rid_a,
                  {'expected_id': rid_a, 'got_id': rid_plens, 'query': q_plens})

        # First-sighting distractor with familiar roles must not get a free label.
        _, q_unknown = top_id(asm, 'vessel zorbifies module')
        score.add('relation_robustness', 'unseen_connector_abstention',
                  not q_unknown['supported'], q_unknown)

        # Negation should preserve base relation while carrying polarity.
        d = asm.relation_discovery.infer_text('vessel does not glarp module')
        neg_ok = bool(d.frame.supported and d.relation_ids and d.relation_ids[0] == rid_a
                      and d.frame.relations and d.frame.relations[0].negated)
        score.add('relation_robustness', 'negation_preserves_relation_and_polarity',
                  neg_ok,
                  {'relation_ids': d.relation_ids,
                   'negated': d.frame.relations[0].negated if d.frame.relations else None,
                   'confidence': d.confidence})

        # Two known anonymous relations in one utterance.
        multi = asm.infer_discovered_relation('vessel glarps module; dana traks badge')
        score.add('relation_composition', 'two_clause_recovery',
                  multi['supported'] and len(multi['relation_ids']) == 2
                  and set(multi['relation_ids']) == {rid_a, rid_b}, multi)

        # Four-token relation phrase exceeds configured max connector span (3).
        # We train repeated clean examples and then require correct generalization.
        long_phrase_train = [
            'alpha moves all the way toward beta',
            'gamma moves all the way toward delta',
            'epsilon moves all the way toward zeta',
            'eta moves all the way toward theta',
        ]
        train(asm, long_phrase_train)
        long_dec = asm.infer_discovered_relation('iota moves all the way toward kappa')
        # Success here requires a promoted learned relation, irrespective of exact
        # textual span choice.
        score.add('relation_robustness', 'four_token_connector_generalization',
                  long_dec['supported'] and bool(long_dec['relation_ids']), long_dec)

        # Polysemy: same surface connector used for two deliberately different
        # latent families with disjoint role/context distributions. A robust
        # ontology should be able to split senses rather than connector-collapse.
        poly = ASMEngine(td / 'polysemy.db')
        try:
            train(poly, [
                'acid morks metal', 'heat morks vapor', 'pressure morks fracture',
                'acid morks alloy', 'heat morks steam', 'pressure morks crack',
                'box morks tool', 'bag morks coin', 'shelf morks book',
                'crate morks part', 'pocket morks key', 'drawer morks file',
            ])
            q_phys = poly.infer_discovered_relation('temperature morks gas')
            q_cont = poly.infer_discovered_relation('cabinet morks document')
            poly_ids = [
                q_phys['relation_ids'][0] if q_phys['supported'] and q_phys['relation_ids'] else None,
                q_cont['relation_ids'][0] if q_cont['supported'] and q_cont['relation_ids'] else None,
            ]
            score.add('relation_robustness', 'same_word_polysemy_separation',
                      all(poly_ids) and poly_ids[0] != poly_ids[1],
                      {'ids': poly_ids, 'relations': poly.discovered_relations(),
                       'physics_query': q_phys, 'container_query': q_cont})
        finally:
            poly.close()

        # Strong misleading surface overlap: known roles, brand new connector.
        adversarial = asm.infer_discovered_relation('box completely blenks item')
        score.add('relation_robustness', 'surface_overlap_does_not_hallucinate',
                  not adversarial['supported'], adversarial)

        # Safety abstention cases.
        safety_cases = [
            'if vessel glarps module',
            'could vessel glarps module',
            'maybe vessel glarps module',
            'does vessel glarp module?',
            'vessel does not always glarp module',
        ]
        for i, text in enumerate(safety_cases, 1):
            q = asm.infer_discovered_relation(text)
            score.add('relation_safety', f'safety_abstention_{i}', not q['supported'],
                      {'text': text, 'query': q})

        # Interference: original family should survive lots of unrelated normal events.
        for i in range(350):
            asm.process(f'noise{i} causes event{i}', training=True)
        after = asm.infer_discovered_relation('vessel glarps module')
        after_id = after['relation_ids'][0] if after['supported'] and after['relation_ids'] else None
        score.add('continual_learning', 'relation_retention_after_350_events',
                  after_id == rid_a,
                  {'before': rid_a, 'after': after_id, 'stats': asm.stats()})

        return {
            'core_relation_id': rid_a,
            'relation_stats': asm.relation_discovery.stats(),
        }
    finally:
        asm.close()


def mind_suite(score: Score, td: Path):
    asm = ASMEngine(td / 'mind.db')
    try:
        # Controlled nested forms should still work under conflicts.
        controlled = [
            ('Alice believes Bob believes that the box is full', ['Alice', 'Bob'], 'box is full', True),
            ('Mina thinks Theo believes that the lamp is not on', ['Mina', 'Theo'], 'lamp is on', False),
            ('Ava believes Ben thinks Cara believes that the gate is open', ['Ava', 'Ben', 'Cara'], 'gate is open', True),
        ]
        for idx, (text, path, prop, expected) in enumerate(controlled, 1):
            asm.process(text, training=True)
            got = asm.nested_belief(path, prop)
            score.add('theory_of_mind_controlled', f'controlled_nested_{idx}',
                      got['truth'] is expected,
                      {'text': text, 'query': got})

        # Contradict direct Bob belief without rewriting Alice's model of Bob.
        asm.process('Alice believes Bob believes that the door is locked', training=True)
        asm.process('Bob believes that the door is not locked', training=True)
        alice_bob = asm.nested_belief(['Alice', 'Bob'], 'door is locked')
        bob = asm.belief('Bob', 'door is locked')
        score.add('theory_of_mind_controlled', 'perspective_isolation_under_conflict',
                  alice_bob['truth'] is True and bob['truth'] is False,
                  {'alice_model_of_bob': alice_bob, 'bob_direct': bob})

        # Hard natural-language variants. These all express a nested belief but
        # avoid the narrow bootstrap grammar.
        paraphrases = [
            ('Alice suspects Bob thinks the key is hidden', ['Alice', 'Bob'], 'key is hidden', True),
            ('Mina is convinced Theo believes the lamp is on', ['Mina', 'Theo'], 'lamp is on', True),
            ('Ava has the impression Ben assumes the gate is closed', ['Ava', 'Ben'], 'gate is closed', True),
            ('Noah figures Lina expects the token is valid', ['Noah', 'Lina'], 'token is valid', True),
            ('Iris doubts Omar thinks the box is empty', ['Iris', 'Omar'], 'box is empty', False),
            ('Kai is sure Mia thinks Leo believes the route is safe', ['Kai', 'Mia', 'Leo'], 'route is safe', True),
        ]
        for idx, (text, path, prop, expected) in enumerate(paraphrases, 1):
            asm.process(text, training=True)
            got = asm.nested_belief(path, prop)
            score.add('theory_of_mind_free_language', f'free_nested_{idx}',
                      got['truth'] is expected,
                      {'text': text, 'path': path, 'query': got})

        # Controlled appraisal learning then transfer.
        teach = [
            'Alice wants that project succeeds',
            'Alice believes that project succeeds',
            'Alice felt proud because the project succeeded',
            'Ben wants that project succeeds',
            'Ben believes that project does not succeed',
            'Ben felt disappointed because the project failed',
            'Cara fears that danger continues',
            'Cara believes that danger continues',
            'Cara felt anxious because the danger continued',
            'Dan fears that danger continues',
            'Dan believes that danger does not continue',
            'Dan felt relieved because the danger ended',
        ]
        train(asm, teach)
        controlled_appraisal = [
            ('Eli wants that mission succeeds', 'Eli believes that mission does not succeed', 'Eli', 'disappointed'),
            ('Faye wants that mission succeeds', 'Faye believes that mission succeeds', 'Faye', 'proud'),
            ('Gus fears that storm continues', 'Gus believes that storm continues', 'Gus', 'anxious'),
            ('Hope fears that storm continues', 'Hope believes that storm does not continue', 'Hope', 'relieved'),
        ]
        for idx, (a, b, holder, expected) in enumerate(controlled_appraisal, 1):
            asm.process(a, training=True); asm.process(b, training=True)
            got = asm.infer_agent_emotion(holder)
            top = got[0]['emotion'] if got else None
            score.add('emotion_controlled', f'controlled_appraisal_{idx}', top == expected,
                      {'holder': holder, 'expected': expected, 'got': got})

        # Same mental states, natural wording not shaped like parser templates.
        free_emotion_cases = [
            ('Evan had been hoping the mission would succeed',
             'Evan learned that the mission had failed', 'Evan', 'disappointed'),
            ('Fiona desperately hoped for success',
             'Fiona discovered that she had succeeded', 'Fiona', 'proud'),
            ('Gina was scared the storm would continue',
             'Gina realized the storm was still going', 'Gina', 'anxious'),
            ('Hugo had been afraid the danger would remain',
             'Hugo found out the danger was gone', 'Hugo', 'relieved'),
        ]
        for idx, (a, b, holder, expected) in enumerate(free_emotion_cases, 1):
            asm.process(a, training=True); asm.process(b, training=True)
            got = asm.infer_agent_emotion(holder)
            top = got[0]['emotion'] if got else None
            score.add('emotion_free_language', f'free_appraisal_{idx}', top == expected,
                      {'holder': holder, 'expected': expected, 'got': got,
                       'state': asm.appraisal_state(holder)})

        # Persistence through unrelated events.
        before = asm.nested_belief(['Alice', 'Bob'], 'box is full')
        for i in range(350):
            asm.process(f'unrelated{i} increases variable{i}', training=True)
        after = asm.nested_belief(['Alice', 'Bob'], 'box is full')
        score.add('continual_learning', 'nested_belief_retention_after_350_events',
                  before['truth'] is True and after['truth'] is True,
                  {'before': before, 'after': after})

        return {'stats': asm.stats()}
    finally:
        asm.close()


def self_model_suite(score: Score, td: Path):
    asm = ASMEngine(td / 'self.db')
    try:
        # Direct outcome API: strategy reversal under nonstationarity.
        for _ in range(5):
            asm.report_strategy_outcome('search', 'strategy_a', True)
        for _ in range(3):
            asm.report_strategy_outcome('search', 'strategy_b', False)
        initial = asm.choose_strategy('search', ['strategy_a', 'strategy_b'])
        initial_ok = initial and initial[0]['strategy'] == 'strategy_a'
        score.add('self_model_api', 'initial_strategy_learning', initial_ok,
                  {'ranking': initial})

        # Environment flips.
        for _ in range(10):
            asm.report_strategy_outcome('search', 'strategy_a', False)
        for _ in range(7):
            asm.report_strategy_outcome('search', 'strategy_b', True)
        flipped = asm.choose_strategy('search', ['strategy_a', 'strategy_b'])
        score.add('self_model_api', 'nonstationary_strategy_reversal',
                  flipped and flipped[0]['strategy'] == 'strategy_b',
                  {'ranking': flipped})

        # Internal failure signal and recovery.
        fail_asm = ASMEngine(td / 'self_failure.db')
        try:
            for _ in range(5):
                fail_asm.report_strategy_outcome('reasoning', 'same_path', False)
            high = fail_asm.self_state()['internal']['frustration_like']
            for _ in range(4):
                fail_asm.report_strategy_outcome('reasoning', 'alternative', True)
            low = fail_asm.self_state()['internal']['frustration_like']
            score.add('self_model_api', 'failure_signal_then_recovery',
                      high > 0.4 and low < high,
                      {'after_failures': high, 'after_successes': low})
        finally:
            fail_asm.close()

        # Language-only outcome reporting should ideally update self-model if the
        # architecture truly understands its own experiences. Current API may not.
        before = asm.capability('reasoning')['attempts']
        language_events = [
            'I tried analogy and it failed',
            'I used analogy again and it failed',
            'my analogy strategy failed a third time',
            'simulation worked successfully',
        ]
        train(asm, language_events)
        after = asm.capability('reasoning')['attempts']
        score.add('self_model_language_integration', 'language_outcomes_update_self_model',
                  after > before,
                  {'attempts_before': before, 'attempts_after': after,
                   'self_state': asm.self_state()})

        return {'stats': asm.stats()}
    finally:
        asm.close()


def capacity_and_latency(score: Score, td: Path):
    # Baseline inference with 12 promoted relations.
    small = ASMEngine(td / 'small_scale.db')
    try:
        for i in range(12):
            for _ in range(3):
                small.process(f'left{i} connector{i} right{i}', training=True)
        query = 'left0 connector0 right0'
        # Warmup
        for _ in range(5):
            small.infer_discovered_relation(query)
        times = []
        for _ in range(60):
            t0 = time.perf_counter()
            small.infer_discovered_relation(query)
            times.append((time.perf_counter() - t0) * 1000)
        small_ms = statistics.median(times)
        small_rel = small.relation_discovery.stats()['relations']
    finally:
        small.close()

    scale_cfg = ASMConfig(relation_discovery_max_relations=48)
    large = ASMEngine(td / 'large_scale.db', config=scale_cfg)
    try:
        # 60 unique promoted families against a configured max of 48. Every family receives 3 identical
        # episodes so it should form one promoted relation.
        for i in range(60):
            text = f'leftx{i} connectorx{i} rightx{i}'
            for _ in range(3):
                large.process(text, training=True)
        st = large.relation_discovery.stats()
        relation_count = st['relations']
        max_cfg = large.cfg.relation_discovery_max_relations
        score.add('scaling_correctness', 'configured_relation_capacity_respected',
                  relation_count <= max_cfg,
                  {'configured_max': max_cfg, 'actual_relations': relation_count,
                   'stats': st})

        q = 'leftx0 connectorx0 rightx0'
        for _ in range(5):
            large.infer_discovered_relation(q)
        times = []
        for _ in range(60):
            t0 = time.perf_counter()
            large.infer_discovered_relation(q)
            times.append((time.perf_counter() - t0) * 1000)
        large_ms = statistics.median(times)

        # Original relation still queryable despite capacity pressure.
        retention = large.infer_discovered_relation(q)
        score.add('scaling_correctness', 'old_relation_survives_capacity_pressure',
                  retention['supported'], retention)

        return {
            'small_relation_count': small_rel,
            'large_relation_count': relation_count,
            'median_inference_ms_small': round(small_ms, 6),
            'median_inference_ms_large': round(large_ms, 6),
            'latency_ratio_large_over_small': round(large_ms / max(small_ms, 1e-9), 3),
            'large_stats': st,
        }
    finally:
        large.close()


def main():
    score = Score()
    started = time.perf_counter()
    with tempfile.TemporaryDirectory() as tmp:
        td = Path(tmp)
        relation_meta = relation_suite(score, td)
        mind_meta = mind_suite(score, td)
        self_meta = self_model_suite(score, td)
        scale_meta = capacity_and_latency(score, td)

    summary = score.summary()
    payload = {
        'benchmark': 'ASM v0.3.0-alpha.3 Inherited Hard Regression',
        'version': __version__,
        'elapsed_seconds': round(time.perf_counter() - started, 3),
        'summary': summary,
        'metrics': {
            'scaling': scale_meta,
            'relation_meta': relation_meta,
            'mind_meta': mind_meta,
            'self_meta': self_meta,
        },
        'cases': score.rows,
        'notes': [
            'This is an assistant-authored adversarial benchmark, not an external standardized benchmark.',
            'The aggregate pass rate is only a summary of these cases and is not an intelligence percentage.',
            'Scaling latency is measured on this execution environment and should be compared only within this run.',
        ],
    }

    out = Path(__file__).parent / 'results/hard_regression_v030a3.json'
    out.write_text(json.dumps(payload, indent=2), encoding='utf-8')

    print(json.dumps({
        'version': payload['version'],
        'elapsed_seconds': payload['elapsed_seconds'],
        'summary': summary,
        'scaling': scale_meta,
    }, indent=2))
    print('RESULT:', out)


if __name__ == '__main__':
    main()
