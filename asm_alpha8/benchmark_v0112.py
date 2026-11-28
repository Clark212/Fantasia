import json
import random
import tempfile
import time
from pathlib import Path

from asm import ASMEngine, __version__


def outcome_name(preds):
    if not preds:
        return None
    return preds[0][0].removeprefix("O:")


def run_seed(seed: int):
    random.seed(seed)

    with tempfile.TemporaryDirectory() as td:
        asm = ASMEngine(Path(td) / "bench.db")

        train = [
            ("red cube => left", "left"),
            ("blue cube => right", "right"),
            ("red sphere => left", "left"),
            ("blue sphere => right", "right"),
            ("ice sample => cold", "cold"),
            ("ice block => cold", "cold"),
            ("fire sample => hot", "hot"),
            ("fire source => hot", "hot"),
            ("battery empty => charge", "charge"),
            ("phone empty => charge", "charge"),
            ("battery full => use", "use"),
            ("phone full => use", "use"),
        ]

        random.shuffle(train)

        # Few-shot: three passes only.
        for _ in range(3):
            for text, _ in train:
                asm.process(text, training=True)

        tests = [
            ("red pyramid", "left"),
            ("blue pyramid", "right"),
            ("ice object", "cold"),
            ("fire object", "hot"),
            ("tablet empty", "charge"),
            ("tablet full", "use"),
        ]

        correct = 0
        predictions = []
        for query, expected in tests:
            preds = asm.infer_rule(query)
            got = outcome_name(preds)
            confidence = preds[0][1] if preds else 0.0
            predictions.append({
                "query": query,
                "expected": expected,
                "got": got,
                "confidence": round(confidence, 4),
            })
            correct += int(got == expected)

        # Interference: add unrelated mappings, then re-test.
        distractor_outputs = ["north", "south", "open", "close", "high", "low"]
        for i in range(120):
            asm.process(
                f"noise{i} token{i} => {distractor_outputs[i % len(distractor_outputs)]}",
                training=True,
            )

        retained = 0
        for query, expected in tests:
            retained += int(outcome_name(asm.infer_rule(query)) == expected)

        result = {
            "seed": seed,
            "few_shot_accuracy": correct / len(tests),
            "post_interference_accuracy": retained / len(tests),
            "predictions": predictions,
            "stats": asm.stats(),
        }

        asm.close()
        return result


results = [run_seed(seed) for seed in range(10)]

summary = {
    "version": __version__,
    "runs": len(results),
    "few_shot_generalization_accuracy_pct": round(
        100 * sum(r["few_shot_accuracy"] for r in results) / len(results),
        2,
    ),
    "post_interference_accuracy_pct": round(
        100 * sum(r["post_interference_accuracy"] for r in results) / len(results),
        2,
    ),
    "runs_detail": results,
}

out = Path(__file__).resolve().parent / "results" / "benchmark_v0112_summary.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(summary, indent=2), encoding="utf-8")

print(json.dumps({
    k: v
    for k, v in summary.items()
    if k != "runs_detail"
}, indent=2))
print(f"saved: {out}")
