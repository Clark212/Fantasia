"""DEV30 exploratory ablation, NOT pre-registered and run after the held-out test: the stack without one mechanism at a time
(that option back at its default), on the same held-out attempts as benchmarks/results/dev30/battery.jsonl. It shows what
each mechanism contributes to the whole stack; it is no gate and changes no conclusion of G30-A.
Usage: python benchmarks/dev30_ablation.py <out.jsonl> <committed battery.jsonl>
"""
import json
import sys
import tempfile
import time
from pathlib import Path

import dev30_battery as D
from asm.coding.integrity import ChainedWriter, environment_provenance, file_sha256, read_records

DEFAULT = {"family_parameters": "enumerate", "family_ambiguity": "first", "family_memory": "window", "contradiction_policy": "strict"}
ABLATIONS = {f"stack_without_{k}": {**D.CONFIGS["stack"], k: v} for k, v in DEFAULT.items()}


def main():
    out, battery = Path(sys.argv[1]), Path(sys.argv[2])
    out.unlink(missing_ok=True)
    D.CONFIGS.update(ABLATIONS)
    w = ChainedWriter(out, {"run": "dev30_ablation (exploratory)", "provenance": environment_provenance(), "configs": ABLATIONS,
                            "harness_sha256": file_sha256(Path(__file__)), "battery_harness_sha256": file_sha256(Path(D.__file__)),
                            "battery_sha256": file_sha256(battery), "seed": D.SEED, "memory_seed": D.MEMORY_SEED})
    t0, recs = time.time(), []
    with tempfile.TemporaryDirectory() as workdir:
        memory_file = D.memory_template(workdir, D.MEMORY_SEED)
        for structure in D.HELD_OUT:
            for arm in D.ARMS:
                for c in D.constants(arm):
                    for s in range(D.D21.FIT_SEEDS):
                        for config in ABLATIONS:
                            recs.append(D.attempt(D.HELD_OUT, structure, arm, c, s, D.SEED, config, memory_file, workdir, D.UNRELATED))
                            w.append({"part": "attempt", **recs[-1]})
    stack = {(r["structure"], r["arm"], r["c"], r["fit_seed"]): r["success"] for r in read_records(battery)
             if r.get("part") == "attempt" and r["config"] == "stack"}
    summary = {}
    for config in ABLATIONS:
        for arm in D.ARMS + ("transfer",):
            rs = [r for r in recs if r["config"] == config and (r["arm"] == arm or arm == "transfer" and r["arm"] in D.TRANSFER)]
            cell = D.cell(rs, config, D.ARMS)
            cell["lost_vs_stack"] = sum(stack[(r["structure"], r["arm"], r["c"], r["fit_seed"])] and not r["success"] for r in rs)
            cell["won_vs_stack"] = sum(r["success"] and not stack[(r["structure"], r["arm"], r["c"], r["fit_seed"])] for r in rs)
            summary[f"{config}|{arm}"] = cell
    w.append({"part": "result", "summary": summary, "seconds": round(time.time() - t0, 1)})
    for k, v in summary.items():
        print(f"{k:50s} {v['success_rate']:.3f} calls {v['mean_evaluator_calls']:7.1f} asked {v['mean_asked']:.3f} wrong {v['wrong']}"
              f" lost {v['lost_vs_stack']} won {v['won_vs_stack']} n {v['n']}")


if __name__ == "__main__":
    main()
