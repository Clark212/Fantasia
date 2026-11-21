import json
import random
import tempfile
from pathlib import Path

from asm import ASMEngine, __version__


FAMILY_A = [
    'box glarps item',
    'crate glarps object',
    'box snarps item',
    'crate snarps object',
    'container glarps component',
    'container snarps component',
]

FAMILY_B = [
    'alice traks coin',
    'bob traks key',
    'alice vims coin',
    'bob vims key',
    'cara traks book',
    'cara vims book',
]

SPLIT_TRAIN = [
    'voltage links current',
    'circuit links signal',
    'electrical signal links current',
    'battery links power',
    'practice links skill',
    'training links ability',
    'study links knowledge',
    'practice links strength',
]

INTERFERENCE = [
    'wind causes branch motion',
    'practice increases skill',
    'cooling reduces temperature',
    'signal triggers alarm',
    'firewall prevents intrusion',
    'training enables lifting',
    'water becomes vapor',
]


def run(seed: int):
    rng = random.Random(seed)
    with tempfile.TemporaryDirectory() as td:
        asm = ASMEngine(Path(td) / 'bench.db')

        # First sighting must not assert a relation.
        first = asm.infer_discovered_relation('box glarps item')
        first_abstain = not first['supported']

        # Keep within-family exposure order stable so the benchmark tests the
        # architecture rather than accidental ordering. Seed variation is used
        # later for unrelated interference.
        for text in FAMILY_A:
            asm.process(text, training=True)
        for text in FAMILY_B:
            asm.process(text, training=True)

        promoted = asm.discovered_relations()
        machine_ids = {r['id'] for r in promoted}
        anonymous_ids = all(x.startswith('RELATION:') for x in machine_ids)

        qa = asm.infer_discovered_relation('vessel glarps module')
        qb = asm.infer_discovered_relation('dana traks badge')
        reuse_a = qa['supported'] and bool(qa['relation_ids'])
        reuse_b = qb['supported'] and bool(qb['relation_ids'])
        separation = (
            reuse_a and reuse_b
            and qa['relation_ids'][0] != qb['relation_ids'][0]
        )

        # Both invented surface connectors in FAMILY_A should converge to one
        # internal relation through shared distributional context.
        rid_a = qa['relation_ids'][0] if reuse_a else None
        proto_a = asm.relation_discovery.inspect(rid_a) if rid_a else None
        paraphrase_convergence = bool(
            proto_a
            and {'glarp', 'snarp'}.issubset(
                set(proto_a['prototype']['connector'])
            )
        )

        # Explicit merge-mechanics check: create two early candidates, then give
        # enough shared distributional context for them to become aliases.
        merge_asm = ASMEngine(Path(td) / 'merge.db')
        try:
            for text in [
                'box glarps item',
                'crate glarps object',
                'box snarps item',
                'crate snarps object',
                'container glarps component',
                'container snarps component',
            ]:
                merge_asm.process(text, training=True)
            explicit_merge = (
                merge_asm.relation_discovery.stats()['merges'] >= 1
                and len(merge_asm.discovered_relations()) == 1
            )
        finally:
            merge_asm.close()

        # Machine relation should be a real structural signature when older
        # language perception cannot supply a named relation.
        structured = asm.process('vessel glarps module', training=True)
        structural_use = (
            structured['structure']['supported']
            and structured['structure']['signature']
            and structured['structure']['signature'][0].startswith('RELATION:')
        )

        # Interference retention.
        for _ in range(8):
            seq = INTERFERENCE[:]
            rng.shuffle(seq)
            for text in seq:
                asm.process(text, training=True)
        qa_after = asm.infer_discovered_relation('vessel glarps module')
        retention = (
            qa_after['supported']
            and qa_after['relation_ids'][0] == rid_a
        )

        # Strength weakening / dormancy from repeated failed prediction feedback.
        current_rid = (
            qa_after['relation_ids'][0]
            if qa_after['supported'] and qa_after['relation_ids']
            else rid_a
        )
        current_state = asm.relation_discovery.inspect(current_rid)
        weak_before = current_state['strength'] if current_state else 0.0
        for _ in range(20):
            asm.relation_feedback(
                current_rid,
                success=False,
                prediction_error=1.0,
            )
        weak_state = asm.relation_discovery.inspect(current_rid)
        weakening = weak_state['strength'] < weak_before
        dormancy = weak_state['dormant']

        # Separate engine for split benchmark so dormancy above does not pollute it.
        split_db = Path(td) / 'split.db'
        split_asm = ASMEngine(split_db)
        try:
            for text in SPLIT_TRAIN:
                split_asm.process(text, training=True)
            before_split = split_asm.relation_discovery.stats()['relations']
            split_rel = split_asm.discovered_relations()[0]['id']
            split_result = None
            for _ in range(3):
                split_result = split_asm.relation_feedback(
                    split_rel,
                    success=False,
                    prediction_error=1.0,
                )
            after_split = split_asm.relation_discovery.stats()['relations']
            split_ok = (
                before_split == 1
                and after_split == 2
                and split_result is not None
                and split_result.get('split') is not None
            )
        finally:
            split_asm.close()

        result = {
            'seed': seed,
            'first_sighting_abstention': first_abstain,
            'anonymous_relation_creation': len(promoted) >= 2 and anonymous_ids,
            'paraphrase_convergence': paraphrase_convergence,
            'explicit_merge_mechanics': explicit_merge,
            'cross_entity_reuse': reuse_a and reuse_b,
            'relation_separation': separation,
            'structural_integration': structural_use,
            'post_interference_retention': retention,
            'prediction_error_weakening': weakening,
            'dormancy_after_repeated_failure': dormancy,
            'prediction_error_split': split_ok,
            'stats': asm.stats(),
        }
        asm.close()
        return result


runs = [run(seed) for seed in range(10)]
keys = [
    'first_sighting_abstention',
    'anonymous_relation_creation',
    'paraphrase_convergence',
    'explicit_merge_mechanics',
    'cross_entity_reuse',
    'relation_separation',
    'structural_integration',
    'post_interference_retention',
    'prediction_error_weakening',
    'dormancy_after_repeated_failure',
    'prediction_error_split',
]
summary = {
    'version': __version__,
    'runs': len(runs),
}
for key in keys:
    summary[key + '_pct'] = round(
        100 * sum(bool(r[key]) for r in runs) / len(runs),
        2,
    )
summary['runs_detail'] = runs

out = Path('/mnt/data/ASM_v0.1.1.9_benchmark_summary.json')
out.write_text(json.dumps(summary, indent=2), encoding='utf-8')
print(json.dumps({k:v for k,v in summary.items() if k != 'runs_detail'}, indent=2))
print('saved:', out)
