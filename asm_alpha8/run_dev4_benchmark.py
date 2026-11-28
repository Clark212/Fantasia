"""Run the pre-registered DEV4 benchmark (Part A structural discovery map, Part B structural transfer). Usage: python run_dev4_benchmark.py [outdir]"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from asm.learning import simlab as S                                       # noqa: E402
from asm.learning import structlab as L                                    # noqa: E402
from asm.learning import structtransfer as T                               # noqa: E402
from asm.learning.structlab_prereg import PREREG as P                      # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else "results")
out.mkdir(parents=True, exist_ok=True)
t0 = time.time()
pa, pb = P["part_a"], P["part_b"]
factories = {
    "memorizer": S.MemorizerLearner, "majority": S.MajorityLearner, "grid_reference": L.GridReferenceLearner,
    "shuffled_grid_reference": lambda: S.ShuffledControl(L.GridReferenceLearner()),
    "asm_struct": L.ASMStructLearner,                                                  # DEFAULT ASM configuration (guard = abstain)
    "shuffled_asm_struct": lambda: S.ShuffledControl(L.ASMStructLearner()),
}
a = L.run_struct_benchmark(factories, seed=P["seed"], tasks_per_family=pa["tasks_per_family"], ks=pa["ks"], families=pa["families"])
a_verdicts = L.evaluate_part_a(a, P)
b = T.run_transfer(seed=P["seed"], fit_seeds=pb["fit_seeds"], arms=pb["arms"], in_range=pb["in_range_constants"], out_of_range=pb["out_of_range_constants"])
b_verdicts = T.evaluate_part_b(b, P)
res = {"part_a": a, "part_b": b, "preregistration": {"sha256": S.prereg_hash(P), "version": P["version"], "verdicts": a_verdicts + b_verdicts},
       "runtime_seconds": round(time.time() - t0, 1)}
(out / "ALPHA8_DEV4_RESULTS.json").write_text(json.dumps(res, indent=1, sort_keys=True) + "\n")

ks = a["ks"]
L_ = [f"# Alpha 8 DEV4 results", "", f"Pre-registration `{P['version']}` sha256 `{res['preregistration']['sha256']}`; seed {P['seed']}; runtime {res['runtime_seconds']} s.", "",
      "## Part A: structural discovery map (ASM default configuration)", "",
      "Cells: `correct_rate / wrong_rate` on held-out interior determined queries (abstention counts as not correct). ASM coverage = answered fraction.", ""]
for fam in pa["families"]:
    L_ += [f"### {fam}  ({a['queries_per_family'][fam]} queries)", "", "| learner | " + " | ".join(f"k={k}" for k in ks) + " |", "|---|" + "---|" * len(ks)]
    for name in factories:
        L_.append(f"| {name} | " + " | ".join(f"{a['cells'][name][fam][str(k)]['correct_rate']:.2f} / {a['cells'][name][fam][str(k)]['wrong_rate']:.2f}" for k in ks) + " |")
    L_ += ["", "ASM coverage: " + ", ".join(f"k={k}: {a['cells']['asm_struct'][fam][str(k)]['coverage']:.2f}" for k in ks), ""]
L_ += ["## Part B: structural transfer (target y = x*x + c; donors validated through the public lifecycle)", "",
       "| group | arm | success | mean evaluator calls | family-origin rate | wrong per query |", "|---|---|---|---|---|---|"]
for grp in ("in_range", "out_of_range"):
    for arm in pb["arms"]:
        s = b["summary"][grp][arm]
        L_.append(f"| {grp} | {arm} | {s['success_rate']:.2f} | {s['mean_evaluator_calls']:.0f} | {s['family_origin_rate']:.2f} | {s['wrong_per_query']:.3f} |")
L_ += ["", "## Pre-registered verdicts", "", "| id | group | passed | rule |", "|---|---|---|---|"]
L_ += [f"| {v['id']} | {v['group']} | {'PASS' if v['passed'] else 'FAIL'} | {v['rule']} |" for v in res["preregistration"]["verdicts"]]
L_ += ["", f"ASM adapter errors (Part A): {a['errors'] or 'none'}", "Observed values per criterion: `ALPHA8_DEV4_RESULTS.json` (`preregistration.verdicts`)."]
(out / "ALPHA8_DEV4_RESULTS.md").write_text("\n".join(L_) + "\n")
print("done", res["runtime_seconds"], "s")
for v in res["preregistration"]["verdicts"]:
    print(v["id"], "PASS" if v["passed"] else "FAIL", json.dumps(v["observed"])[:160])
