"""EXPLORATORY diagnostics for DEV3 (NOT pre-registered; 20 trials each; do not cite as verdicts)."""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from asm.learning import simlab as S  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else "results")
out.mkdir(parents=True, exist_ok=True)


def run(label, fn, pool, queries, k, trials=20, seed=5):
    ans = cor = tot = err = 0
    for t in range(trials):
        rng = random.Random(f"{seed}:{label}:{t}")
        a, b = rng.randint(1, 5), rng.randint(0, 9)
        order = list(pool)
        rng.shuffle(order)
        shots = [(order[i % len(order)], fn(a, b, order[i % len(order)])) for i in range(k)]
        learner = S.ASMProcedureLearner()
        learner.fit({"family": "affine_mod", "public": {"m": 0}, "task_id": f"diag_{label}_{t}".replace(" ", "_")}, shots)
        for q in queries:
            pred, _ = learner.predict(q)
            tot += 1
            if pred is not None:
                ans += 1
                cor += pred == fn(a, b, q)
        err += learner.errors
    return f"| {label} | {k} | {ans}/{tot} | {cor} | {ans - cor} | {err} |"


rows = [
    run("plain affine y=a*x+b (held-out x beyond training range)", lambda a, b, x: a * x + b, range(0, 16), range(16, 22), 24),
    run("plain affine y=a*x+b", lambda a, b, x: a * x + b, range(0, 16), range(16, 22), 8),
    run("affine mod 29, small a,b, wrap not always visible in shots", lambda a, b, x: (a * x + b) % 29, range(0, 16), range(16, 22), 24),
]
text = ["# DEV3 exploratory diagnostics (not pre-registered)", "",
        "Purpose: separate an adapter problem from a capability gap for ASM's ProcedureCortex on integer rules.", "",
        "| case | shots k | answered | correct | wrong | adapter errors |", "|---|---|---|---|---|---|", *rows, "",
        "Reading: plain integer affine is learned and extrapolated at k=24 but not at k=8; ASM's grammar has no modulus operation,",
        "so the benchmark's affine_mod family is outside what it can represent. In the third case the shots can fit a plain affine rule",
        "that is wrong for held-out inputs where the modulus wraps, and ASM answers some of those with confidence (see 'wrong').", ""]
(out / "ALPHA8_DEV3_DIAGNOSTIC.md").write_text("\n".join(text))
print("\n".join(rows))
