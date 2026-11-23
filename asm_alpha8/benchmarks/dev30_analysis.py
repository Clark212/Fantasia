"""DEV30 exploratory analysis, NOT pre-registered and run after the held-out test.
  losses <out.jsonl>       re-run every attempt the stack lost (7 held out, 1 in development) with the stack, the stack under
                           the strict policy, and the stack enumerating parameters; record the target's fit and validation support
  noise <battery.jsonl>    replay the harness's noise generator (its draws do not depend on label values) and tabulate success
                           by the wrong labels each attempt had
"""
import collections
import json
import random
import sqlite3
import sys
import tempfile
from pathlib import Path

import dev30_battery as D

LOST = [("held_out", s, c, f) for s, c, f in (("x_times_sum_shift", -3, 0), ("x_times_sum_shift", 7, 0), ("x_times_sum_shift", 8, 1),
        ("yy_minus_x_shift", -4, 2), ("yy_minus_x_shift", -2, 2), ("yy_minus_x_shift", 4, 0), ("yy_minus_x_shift", 8, 1))] + [
        ("development", "dev3_mul_add", 6, 0)]
VARIANTS = {"stack_strict": {"contradiction_policy": "strict"}, "stack_enumerate": {"family_parameters": "enumerate"}}


def losses(out):
    D.CONFIGS.update({k: {**D.CONFIGS["stack"], **v} for k, v in VARIANTS.items()})
    with tempfile.TemporaryDirectory() as tmp, open(out, "w") as f:
        for data in ("held_out", "development"):
            dev, wd = data == "development", Path(tmp) / data
            wd.mkdir()
            structures, seed, unrelated = (D.DEV, D.DEV_SEED, D.DEV_UNRELATED) if dev else (D.HELD_OUT, D.SEED, D.UNRELATED)
            memory = D.memory_template(wd, D.DEV_MEMORY_SEED if dev else D.MEMORY_SEED)
            for _, s, c, fs in (x for x in LOST if x[0] == data):
                for config in ("defaults", "stack", *VARIANTS):
                    r = D.attempt(structures, s, "ambiguous", c, fs, seed, config, memory, wd, unrelated)
                    with sqlite3.connect(wd / "attempt.db") as db:
                        rows = db.execute("SELECT phase, matched, count(*) FROM procedure_support WHERE mechanism='target' GROUP BY 1, 2")
                        support = {f"{phase}:{'matched' if m else 'contradicted'}": n for phase, m, n in rows}
                    f.write(json.dumps({"data": data, **{k: r[k] for k in ("structure", "c", "fit_seed", "config", "fit", "status", "origin",
                                                                           "asked", "success")}, "target_support": support}) + "\n")


def noise(battery):
    def wrong(rng, k):
        return sum(rng.random() < D.NOISE and rng.choice(D.OFFSETS) is not None for _ in range(k))
    table = collections.defaultdict(lambda: [0, 0])
    for r in (json.loads(line) for line in open(battery)):
        if r.get("part") == "attempt" and r["arm"] in ("noisy", "combined"):
            rng = random.Random(f"{D.SEED}:noise:{r['structure']}:{r['arm']}:{r['c']}:{r['fit_seed']}")
            donors, target = [wrong(rng, 5) + wrong(rng, 10) for _ in range(2)], wrong(rng, 5) + wrong(rng, 10)
            kind = ("none" if target == max(donors) == 0 else "at most 1 per hypothesis" if max(target, *donors) <= 1
                    else "2 or more in the target" if target >= 2 else "2 or more in a donor")
            table[(r["arm"], r["config"], kind)][0] += r["success"]
            table[(r["arm"], r["config"], kind)][1] += 1
    for k in sorted(table):
        print(*k, "%d of %d" % tuple(table[k]), sep=" | ")


if __name__ == "__main__":
    {"losses": losses, "noise": noise}[sys.argv[1]](sys.argv[2])
