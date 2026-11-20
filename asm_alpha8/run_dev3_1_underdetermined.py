"""Run the pre-registered DEV3.1 underdetermination benchmark. Usage: python run_dev3_1_underdetermined.py [outdir]"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from asm.learning import simlab as S                                       # noqa: E402
from asm.learning import simlab_underdetermined as U                       # noqa: E402
from asm.learning.simlab_ud_prereg import UD_PREREG as P                   # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else "results")
out.mkdir(parents=True, exist_ok=True)
factories = {
    "memorizer": S.MemorizerLearner,
    "naive_affine_extrapolator": U.NaiveAffineExtrapolator,
    "hidden_mod_bayes_vote": lambda: U.HiddenModBayesLearner("vote"),
    "hidden_mod_bayes_abstain": lambda: U.HiddenModBayesLearner("abstain"),
    # Pinned to the pre-DEV3.2 behaviour (guard off): this is the configuration the pre-registered DEV3.1 verdicts were obtained with.
    # The DEV3.3 default (abstain) is evaluated in run_dev3_2_guard_comparison.py.
    "asm_procedure_cortex": lambda: U.ASMHiddenModLearner(extrapolation_guard="off"),
    "support_guarded_asm": lambda: U.SupportGuarded(U.ASMHiddenModLearner(extrapolation_guard="off")),
}
t0 = time.time()
res = U.run_underdetermined(factories, seed=P["seed"], tasks=P["tasks"], ks=P["ks"])
verdicts = U.evaluate_ud_preregistration(res, P)
res["preregistration"] = {"sha256": S.prereg_hash(P), "version": P["version"], "verdicts": verdicts}
res["runtime_seconds"] = round(time.time() - t0, 1)
(out / "ALPHA8_DEV3_1_RESULTS.json").write_text(json.dumps(res, indent=1, sort_keys=True) + "\n")

ks = res["ks"]
lines = ["# Alpha 8 DEV3.1 underdetermination results", "",
         f"Pre-registration `{P['version']}` sha256 `{res['preregistration']['sha256']}`; seed {P['seed']}; {P['tasks']} tasks "
         f"({res['kinds']['plain']} plain affine, {res['kinds']['mod']} hidden modulus); runtime {res['runtime_seconds']} s.", "",
         "Extrapolation = x in 12..17 (wraps under the hidden modulus). Interpolation = x in {3, 7}. "
         "Cells: `answered / n`, correct, confident-wrong rate (wrong with confidence >= 0.8, over all queries), ECE on answered.", ""]
for qtype in ("extrap", "interp"):
    lines += [f"## {qtype}", "", "| learner | " + " | ".join(f"k={k}" for k in ks) + " |", "|---|" + "---|" * len(ks)]
    for name in factories:
        cells = [res["cells"][name][str(k)][qtype] for k in ks]
        lines.append(f"| {name} | " + " | ".join(
            f"{c['answered']}/{c['n']}, ok {c['correct']}, cw {c['confident_wrong_rate']:.3f}, ece {c['ece']:.2f}" for c in cells) + " |")
    lines.append("")
lines += ["## Pre-registered verdicts", "", "| id | group | passed | rule |", "|---|---|---|---|"]
lines += [f"| {v['id']} | {v['group']} | {'PASS' if v['passed'] else 'FAIL'} | {v['rule']} |" for v in verdicts]
lines += ["", f"ASM adapter errors: {res['errors'] or 'none'}", "Observed values per criterion: `ALPHA8_DEV3_1_RESULTS.json` (`preregistration.verdicts`)."]
(out / "ALPHA8_DEV3_1_RESULTS.md").write_text("\n".join(lines) + "\n")
print("done", res["runtime_seconds"], "s")
for v in verdicts:
    print(v["id"], "PASS" if v["passed"] else "FAIL", json.dumps(v["observed"])[:200])
