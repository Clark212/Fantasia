import json
import random
import tempfile
from pathlib import Path

from asm import ASMEngine, __version__


TRAIN_SEQUENCES = [
    [
        "Alice wants that project succeeds",
        "Alice believes that project succeeds",
        "Alice felt proud because the project succeeded",
    ],
    [
        "Ben wants that project succeeds",
        "Ben believes that project does not succeed",
        "Ben felt disappointed because the project failed",
    ],
    [
        "Cara fears that danger continues",
        "Cara believes that danger continues",
        "Cara felt anxious because the danger continued",
    ],
    [
        "Dan fears that danger continues",
        "Dan believes that danger does not continue",
        "Dan felt relieved because the danger ended",
    ],
]

TEST_CASES = [
    ("Eli", "goal", "mission succeeds", True, "proud"),
    ("Faye", "goal", "mission succeeds", False, "disappointed"),
    ("Gus", "goal", "exam succeeds", True, "proud"),
    ("Hope", "goal", "exam succeeds", False, "disappointed"),
    ("Ivy", "fear", "storm continues", True, "anxious"),
    ("Jay", "fear", "storm continues", False, "relieved"),
    ("Kira", "fear", "alarm continues", True, "anxious"),
    ("Liam", "fear", "alarm continues", False, "relieved"),
]


def train(asm, rng):
    seqs = TRAIN_SEQUENCES[:]
    rng.shuffle(seqs)
    for seq in seqs:
        # Preserve within-agent causal order, randomize only across examples.
        for text in seq:
            asm.process(text, training=True)


def install_case(asm, holder, kind, prop, truth):
    if kind == "goal":
        asm.process(f"{holder} wants that {prop}", training=True)
    else:
        asm.process(f"{holder} fears that {prop}", training=True)

    if truth:
        asm.process(f"{holder} believes that {prop}", training=True)
    else:
        # assumes a simple "... succeeds/continues" proposition
        words = prop.split()
        if words[-1] == "succeeds":
            neg = " ".join(words[:-1] + ["does not succeed"])
        elif words[-1] == "continues":
            neg = " ".join(words[:-1] + ["does not continue"])
        else:
            neg = "not " + prop
        asm.process(f"{holder} believes that {neg}", training=True)


def run(seed):
    rng = random.Random(seed)
    with tempfile.TemporaryDirectory() as td:
        asm = ASMEngine(Path(td) / "bench.db")
        train(asm, rng)

        rows = []
        passed = 0
        for holder, kind, prop, truth, expected in TEST_CASES:
            install_case(asm, holder, kind, prop, truth)
            got_rows = asm.infer_agent_emotion(holder)
            got = got_rows[0]["emotion"] if got_rows else None
            ok = got == expected
            passed += int(ok)
            rows.append({
                "holder": holder,
                "kind": kind,
                "proposition": prop,
                "belief_truth": truth,
                "expected": expected,
                "got": got,
                "appraisal": asm.appraisal_state(holder),
                "pass": ok,
            })

        # Adaptation: flip four agents' beliefs and require emotion to flip.
        flips = [
            ("Eli", "mission succeeds", False, "disappointed"),
            ("Faye", "mission succeeds", True, "proud"),
            ("Ivy", "storm continues", False, "relieved"),
            ("Jay", "storm continues", True, "anxious"),
        ]
        adapted = 0
        adapt_rows = []
        for holder, prop, truth, expected in flips:
            if truth:
                stmt = f"{holder} believes that {prop}"
            elif prop.endswith("succeeds"):
                stmt = f"{holder} believes that {prop[:-8]}does not succeed"
            elif prop.endswith("continues"):
                stmt = f"{holder} believes that {prop[:-9]}does not continue"
            else:
                stmt = f"{holder} believes that not {prop}"

            # Stronger contradictory evidence.
            asm.process(stmt, training=True)
            asm.process(stmt, training=True)
            got_rows = asm.infer_agent_emotion(holder)
            got = got_rows[0]["emotion"] if got_rows else None
            ok = got == expected
            adapted += int(ok)
            adapt_rows.append({
                "holder": holder,
                "expected": expected,
                "got": got,
                "pass": ok,
            })

        result = {
            "seed": seed,
            "appraisal_transfer_accuracy": passed / len(TEST_CASES),
            "belief_adaptation_accuracy": adapted / len(flips),
            "cases": rows,
            "adaptation_cases": adapt_rows,
            "stats": asm.stats(),
        }
        asm.close()
        return result


runs = [run(seed) for seed in range(10)]
summary = {
    "version": __version__,
    "runs": len(runs),
    "appraisal_transfer_pct": round(
        100 * sum(x["appraisal_transfer_accuracy"] for x in runs) / len(runs),
        2,
    ),
    "belief_adaptation_pct": round(
        100 * sum(x["belief_adaptation_accuracy"] for x in runs) / len(runs),
        2,
    ),
    "runs_detail": runs,
}

out = Path("/mnt/data/ASM_v0.1.1.6_appraisal_benchmark.json")
out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps({k: v for k, v in summary.items() if k != "runs_detail"}, indent=2))
print(f"saved: {out}")
