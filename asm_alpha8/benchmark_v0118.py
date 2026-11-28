import json
import random
import tempfile
from pathlib import Path

from asm import ASMEngine, __version__

CANON = [
    "practice increases skill",
    "study increases knowledge",
    "training increases ability",
    "charging increases battery heat",
    "traffic increases road pressure",
    "rendering increases component temperature",
    "filtering reduces signal noise",
    "maintenance reduces system error",
    "cooling reduces component temperature",
    "compression reduces processing delay",
    "rest reduces muscle fatigue",
    "optimization reduces latency",
    "wind causes branch motion",
    "sound causes membrane motion",
    "vibration causes machine motion",
    "pressure causes membrane movement",
    "force causes object motion",
    "heat causes material expansion",
    "signal triggers alarm",
    "motion triggers detector response",
    "voltage triggers protection",
    "current triggers breaker",
    "pulse triggers reaction",
    "movement triggers sensor response",
    "practice enables accurate performance",
    "training enables lifting",
    "knowledge enables problem solving",
    "permission enables access",
    "power enables operation",
    "preparation enables success",
    "filter prevents contamination",
    "firewall prevents intrusion",
    "brake prevents motion",
    "shield prevents damage",
    "cooling prevents overheating",
    "validation prevents error",
    "water becomes vapor",
    "material becomes brittle",
    "signal becomes stable",
    "ice becomes liquid",
    "seed becomes plant",
    "system becomes ready",
]

# Each teaching sentence contains a connector never listed in StructuralParser.
# The transfer sentence then uses the same learned connector with different nouns.
ADAPTIVE = [
    ("practice sharpens ability", "exercise sharpens capability", "INCREASE"),
    ("study deepens knowledge", "research deepens understanding", "INCREASE"),
    ("sustained rendering drives temperature higher", "heavy_compute drives heat upward", "INCREASE"),
    ("optimization trims system error", "new_method trims overhead", "DECREASE"),
    ("cooling eases component temperature", "new_process eases load", "DECREASE"),
    ("wind induces branch motion", "unknown_force induces unknown_effect", "CAUSE"),
    ("heat engenders material expansion", "alpha engenders beta", "CAUSE"),
    ("electrical pulse provokes alarm", "novel_input provokes novel_output", "TRIGGER"),
    ("movement elicits sensor response", "alpha elicits beta", "TRIGGER"),
    ("practice unlocks performance", "new_key unlocks new_state", "ENABLE"),
    ("permission empowers access", "alpha empowers beta", "ENABLE"),
    ("firewall thwarts intrusion", "new_guard thwarts new_threat", "PREVENT"),
    ("filter averts contamination", "alpha averts beta", "PREVENT"),
    ("water transforms into vapor", "alpha transforms into beta", "BECOME"),
    ("material morphs into brittle state", "alpha morphs into beta", "BECOME"),
]


NEGATION = [
    ("practice does not sharpen ability", "NOT:INCREASE"),
    ("filter does not avert contamination", "NOT:PREVENT"),
]

SAFETY = [
    "purple banana glorp quantum sandwich",
    "mysterious object flarns unrelated entity",
    "Could practice sharpen ability?",
    "if practice sharpens ability then performance improves",
    "maybe cooling trims temperature",
]


def relation(asm, text):
    result = asm.parse_open(text)
    return result["signature"][0] if result["signature"] else None, result


def run(seed):
    rng = random.Random(seed)
    with tempfile.TemporaryDirectory() as td:
        asm = ASMEngine(Path(td) / "bench.db")
        training = CANON * 3
        rng.shuffle(training)
        for text in training:
            asm.process(text, training=True)

        adaptive_rows = []
        induction_pass = 0
        transfer_pass = 0
        first_sighting_abstain = 0

        items = ADAPTIVE[:]
        rng.shuffle(items)
        for teaching, transfer, expected in items:
            before, before_info = relation(asm, teaching)
            first_sighting_abstain += int(before is None and not before_info["supported"])

            event = asm.process(teaching, training=True)
            learned = bool(event["perception"]["learned_after_observation"])
            induction_pass += int(learned)

            got, info = relation(asm, transfer)
            ok = got == expected
            transfer_pass += int(ok)
            adaptive_rows.append({
                "teaching": teaching,
                "transfer": transfer,
                "first_sighting": before,
                "learned_after_observation": learned,
                "expected": expected,
                "got": got,
                "confidence": info["confidence"],
                "pass": ok,
            })

        neg_rows = []
        neg_pass = 0
        for text, expected in NEGATION:
            # Connector may already be learned from adaptive cases; if not, the
            # observation itself supplies the exposure.
            asm.process(text, training=True)
            got, info = relation(asm, text)
            ok = got == expected
            neg_pass += int(ok)
            neg_rows.append({"text": text, "expected": expected, "got": got, "pass": ok})

        safety_rows = []
        safety_pass = 0
        for text in SAFETY:
            got, info = relation(asm, text)
            ok = got is None and not info["supported"]
            safety_pass += int(ok)
            safety_rows.append({
                "text": text,
                "got": got,
                "warnings": info["warnings"],
                "pass": ok,
            })

        # Interference should not erase learned wording.
        for i in range(300):
            asm.process(f"unrelated item{i} becomes state{i}", training=True)

        retention_rows = []
        retention_pass = 0
        for _, transfer, expected in ADAPTIVE:
            got, _ = relation(asm, transfer)
            ok = got == expected
            retention_pass += int(ok)
            retention_rows.append({"text": transfer, "expected": expected, "got": got, "pass": ok})

        result = {
            "seed": seed,
            "first_sighting_abstention": first_sighting_abstain / len(ADAPTIVE),
            "one_observation_induction": induction_pass / len(ADAPTIVE),
            "new_context_transfer": transfer_pass / len(ADAPTIVE),
            "simple_negation": neg_pass / len(NEGATION),
            "safety_abstention": safety_pass / len(SAFETY),
            "post_interference_retention": retention_pass / len(ADAPTIVE),
            "adaptive_cases": adaptive_rows,
            "negation_cases": neg_rows,
            "safety_cases": safety_rows,
            "retention_cases": retention_rows,
            "stats": asm.stats(),
        }
        asm.close()
        return result

runs = [run(seed) for seed in range(10)]
summary = {
    "version": __version__,
    "runs": len(runs),
    "first_sighting_abstention_pct": round(100 * sum(r["first_sighting_abstention"] for r in runs) / len(runs), 2),
    "one_observation_relation_induction_pct": round(100 * sum(r["one_observation_induction"] for r in runs) / len(runs), 2),
    "learned_connector_new_context_transfer_pct": round(100 * sum(r["new_context_transfer"] for r in runs) / len(runs), 2),
    "simple_negation_pct": round(100 * sum(r["simple_negation"] for r in runs) / len(runs), 2),
    "safety_abstention_pct": round(100 * sum(r["safety_abstention"] for r in runs) / len(runs), 2),
    "post_interference_retention_pct": round(100 * sum(r["post_interference_retention"] for r in runs) / len(runs), 2),
    "runs_detail": runs,
}
out = Path("/mnt/data/ASM_v0.1.1.8_benchmark_summary.json")
out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps({k: v for k, v in summary.items() if k != "runs_detail"}, indent=2))
print(f"saved: {out}")
