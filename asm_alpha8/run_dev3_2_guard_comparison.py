"""Compare ProcedureCortex extrapolation-guard modes. Usage: python run_dev3_2_guard_comparison.py [outdir]

Part A re-evaluates the DEV3.1 pre-registered criteria U1-U3 (fixed before the guard existed) for each mode.
The discount-cap sweep is EXPLORATORY. Part B checks that enabling the guard does not change ASM's DEV3 results.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from asm.learning import simlab as S                                       # noqa: E402
from asm.learning import simlab_underdetermined as U                       # noqa: E402
from asm.learning.simlab_ud_prereg import UD_PREREG as P                   # noqa: E402
from asm.learning.simlab_prereg import PREREG as P3                        # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else "results")
out.mkdir(parents=True, exist_ok=True)
t0 = time.time()
modes = {
    "off (pre-DEV3.2 behaviour)": lambda: U.ASMHiddenModLearner(extrapolation_guard="off"),
    "default (no setting; abstain since DEV3.3)": lambda: U.ASMHiddenModLearner(),
    "abstain (explicit)": lambda: U.ASMHiddenModLearner(extrapolation_guard="abstain"),
    **{f"discount cap {c}": (lambda c=c: U.ASMHiddenModLearner(extrapolation_guard="discount", extrapolation_confidence_cap=c)) for c in (0.3, 0.5, 0.7, 0.9)},
}
ks = [8, 16, 24]
a = U.run_underdetermined(modes, seed=P["seed"], tasks=P["tasks"], ks=ks)

lines = ["# DEV3.2 extrapolation-guard comparison", "",
         "## A. DEV3.1 underdetermination population (100 tasks; 600 extrapolation / 200 interpolation queries per k)", "",
         "U1/U2/U3 are the criteria pre-registered in DEV3.1 (version 2), evaluated at k=24. The discount cap sweep is exploratory.", "",
         "| mode | extrap answered | extrap correct | confident-wrong rate | ECE (extrap) | interp correct | U1 | U2 | U3 |", "|---|---|---|---|---|---|---|---|---|"]
for name in modes:
    e, i = a["cells"][name]["24"]["extrap"], a["cells"][name]["24"]["interp"]
    u1 = e["confident_wrong_rate"] <= P["asm_claims"]["U1_not_confidently_wrong_when_underdetermined"]["max_confident_wrong_rate_extrap"]
    u2 = e["answered"] == 0 or e["ece"] <= P["asm_claims"]["U2_calibrated_when_underdetermined"]["max_ece_extrap"]
    u3 = i["correct_rate"] >= P["asm_claims"]["U3_learns_the_easy_regime"]["min_correct_rate_interp"]
    lines.append(f"| {name} | {e['answered']}/{e['n']} | {e['correct']} | {e['confident_wrong_rate']:.3f} | {e['ece']:.3f} | {i['correct']}/{i['n']} | "
                 f"{'PASS' if u1 else 'FAIL'} | {'PASS' if u2 else 'FAIL'} | {'PASS' if u3 else 'FAIL'} |")
lines += ["", "Answered/correct at k=8 and k=16 (all modes abstain at k=8; the guard never changes interpolation):", "",
          "| mode | k=16 extrap answered/correct | k=16 interp answered/correct |", "|---|---|---|"]
for name in modes:
    e, i = a["cells"][name]["16"]["extrap"], a["cells"][name]["16"]["interp"]
    lines.append(f"| {name} | {e['answered']}/{e['correct']} | {i['answered']}/{i['correct']} |")

# Part B: ASM results on the DEV3 families with the guard off vs abstain (k in 12, 16, 24)
ks3 = [12, 16, 24]
b = S.run_benchmark({"asm_off": lambda: S.ASMProcedureLearner(extrapolation_guard="off"), "asm_abstain": lambda: S.ASMProcedureLearner()},
                    seed=P3["seed"], tasks_per_family=P3["tasks_per_family"], ks=ks3, families=P3["families"])
identical = {fam: all(b["cells"]["asm_off"][fam][str(k)][f] == b["cells"]["asm_abstain"][fam][str(k)][f]
                      for k in ks3 for f in ("answered", "correct", "n")) for fam in P3["families"]}
lines += ["", "## B. DEV3 families: does the DEV3.3 default (abstain) change ASM's results versus guard off?", "",
          "| family | identical answered/correct/n at k=12,16,24 |", "|---|---|"]
lines += [f"| {fam} | {'yes' if same else 'NO'} |" for fam, same in identical.items()]
lines += ["", "Bit families have no integer inputs (not guarded) and ASM abstains on affine_mod regardless, so identity is expected.",
          f"Runtime {time.time() - t0:.0f} s."]
(out / "ALPHA8_DEV3_2_GUARD_COMPARISON.md").write_text("\n".join(lines) + "\n")
(out / "ALPHA8_DEV3_2_GUARD_COMPARISON.json").write_text(json.dumps({"dev31_population": a, "dev3_identity": identical}, indent=1, sort_keys=True) + "\n")
print("\n".join(lines))
