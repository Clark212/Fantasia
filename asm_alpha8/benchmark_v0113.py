import json
import random
import tempfile
import time
from pathlib import Path

from asm import ASMEngine, __version__


CORE = [
    # INCREASE -> THRESHOLD
    "repeated requests increase queue pressure; queue pressure crosses threshold, server fails",
    "repeated charging increases battery heat; battery heat crosses threshold, battery shuts down",
    "repeated traffic increases road pressure; road pressure crosses threshold, traffic flow fails",

    # INCREASE -> ENABLE
    "daily practice increases skill; skill enables accurate performance",
    "study increases knowledge; knowledge enables problem solving",
    "training increases strength; strength enables lifting",

    # INCREASE -> TRIGGER
    "signal increases voltage; high voltage triggers alarm",
    "current increases circuit voltage; high circuit voltage triggers protection",
    "electrical load increases current; high current triggers breaker",

    # CAUSE -> TRIGGER
    "high wind causes branch motion; branch motion triggers sensor alarm",
    "strong sound causes membrane motion; membrane motion triggers detector response",
    "rapid vibration causes machine motion; machine motion triggers safety alarm",
]

DISTRACTORS = [
    "camera detects object",
    "database stores record",
    "user enters password",
    "network sends packet",
    "program reads file",
    "robot moves forward",
    "sensor records light",
    "memory stores event",
    "client opens connection",
    "screen displays image",
]

TESTS = [
    ("repeated computation increases processor temperature", "THRESHOLD"),
    ("repeated pumping increases pipe pressure", "THRESHOLD"),
    ("practice increases ability", "ENABLE"),
    ("training increases endurance", "ENABLE"),
    ("electrical input increases voltage", "TRIGGER"),
    ("current increases circuit voltage", "TRIGGER"),
    ("ground movement causes building motion", "TRIGGER"),
    ("air pressure causes membrane motion", "TRIGGER"),
]


def top_relation(expansion):
    rels = [
        item
        for item in expansion["hypotheses"]
        if item["hypothesis"].startswith("RELATION:")
    ]
    return (
        rels[0]["hypothesis"].split(":", 1)[1]
        if rels else None
    )


def run(seed):
    rng = random.Random(seed)

    with tempfile.TemporaryDirectory() as td:
        asm = ASMEngine(Path(td) / "bench.db")
        training = CORE * 3 + DISTRACTORS * 5
        rng.shuffle(training)

        t0 = time.perf_counter()
        for obs in training:
            asm.process(obs, training=True)
        train_s = time.perf_counter() - t0

        correct = 0
        test_details = []

        for query, expected in TESTS:
            expansion = asm.expand_problem(query)
            got = top_relation(expansion)
            hit = got == expected
            correct += int(hit)
            test_details.append({
                "query": query,
                "expected_next_relation": expected,
                "predicted_next_relation": got,
                "pass": hit,
                "top_hypotheses": expansion["hypotheses"][:5],
                "top_analogy": (
                    expansion["analogies"][0]
                    if expansion["analogies"]
                    else None
                ),
            })

        # Heavy unrelated structural interference.
        for i in range(300):
            asm.process(
                f"unrelated item{i} becomes passive state{i}",
                training=True,
            )

        retained = 0
        for query, expected in TESTS:
            got = top_relation(asm.expand_problem(query))
            retained += int(got == expected)

        result = {
            "seed": seed,
            "top1_accuracy": correct / len(TESTS),
            "post_interference_top1_accuracy": retained / len(TESTS),
            "training_seconds": train_s,
            "details": test_details,
            "stats": asm.stats(),
        }
        asm.close()
        return result


runs = [run(seed) for seed in range(10)]

summary = {
    "version": __version__,
    "runs": len(runs),
    "cross_domain_top1_structural_accuracy_pct": round(
        100 * sum(r["top1_accuracy"] for r in runs) / len(runs),
        2,
    ),
    "post_interference_top1_accuracy_pct": round(
        100 * sum(
            r["post_interference_top1_accuracy"]
            for r in runs
        ) / len(runs),
        2,
    ),
    "mean_training_seconds": round(
        sum(r["training_seconds"] for r in runs) / len(runs),
        4,
    ),
    "runs_detail": runs,
}

out = Path(__file__).resolve().parent / "results" / "benchmark_v0113_summary.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(
    json.dumps(summary, indent=2),
    encoding="utf-8",
)

print(json.dumps(
    {k: v for k, v in summary.items() if k != "runs_detail"},
    indent=2,
))
print(f"saved: {out}")
