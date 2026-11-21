"""Run the pre-registered DEV3 benchmark. Usage: python run_dev3_benchmark.py [outdir]"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from asm.learning import ExperienceLog                                    # noqa: E402
from asm.learning import simlab as S                                      # noqa: E402
from asm.learning.simlab_prereg import PREREG                             # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else "results")
out.mkdir(parents=True, exist_ok=True)
log_path = out / "ALPHA8_DEV3_SUITE_LOG.jsonl"
log_path.unlink(missing_ok=True)
factories = {
    "memorizer": S.MemorizerLearner, "majority": S.MajorityLearner,
    "rulesearch_abstain": lambda: S.RuleSearchLearner("abstain"),
    "rulesearch_vote": lambda: S.RuleSearchLearner("vote"),
    "rulesearch_guess": lambda: S.RuleSearchLearner("guess"),
    "shuffled_rulesearch_abstain": lambda: S.ShuffledControl(S.RuleSearchLearner("abstain")),
    # Pinned to the pre-DEV3.2 behaviour (guard off) used for the official DEV3 results; abstain gives identical results here (see comparison).
    "asm_procedure_cortex": lambda: S.ASMProcedureLearner(extrapolation_guard="off"),
}
t0 = time.time()
log = ExperienceLog(log_path, fsync=False)
res = S.run_benchmark(factories, seed=PREREG["seed"], tasks_per_family=PREREG["tasks_per_family"],
                      ks=PREREG["ks"], families=PREREG["families"], log=log)
verdicts = S.evaluate_preregistration(res, PREREG)
res["preregistration"] = {"sha256": S.prereg_hash(PREREG), "version": PREREG["version"], "verdicts": verdicts}
res["runtime_seconds"] = round(time.time() - t0, 1)
(out / "ALPHA8_DEV3_RESULTS.json").write_text(json.dumps(res, indent=1, sort_keys=True) + "\n")

lines = ["# Alpha 8 DEV3 benchmark results", "",
         f"Pre-registration `{PREREG['version']}` sha256 `{res['preregistration']['sha256']}`; seed {PREREG['seed']}; "
         f"{PREREG['tasks_per_family']} tasks per family; scored queries per family: {res['queries_per_family']}; runtime {res['runtime_seconds']} s.",
         "", "Cells show `correct_rate / wrong_rate` (abstentions count as not correct). Learning-curve columns are k = shots per task.", ""]
ks = res["ks"]
for fam in PREREG["families"]:
    lines += [f"## {fam}", "", "| learner | " + " | ".join(f"k={k}" for k in ks) + " |", "|---|" + "---|" * len(ks)]
    for name in factories:
        cells = [res["cells"][name][fam][str(k)] for k in ks]
        lines.append(f"| {name} | " + " | ".join(f"{c['correct_rate']:.2f} / {c['wrong_rate']:.2f}" for c in cells) + " |")
    lines += ["", "ASM coverage (answered fraction) by k: " + ", ".join(
        f"k={k}: {res['cells']['asm_procedure_cortex'][fam][str(k)]['coverage']:.2f}" for k in ks), ""]
lines += ["## Pre-registered verdicts", "", "| id | group | passed | rule |", "|---|---|---|---|"]
for v in verdicts:
    lines.append(f"| {v['id']} | {v['group']} | {'PASS' if v['passed'] else 'FAIL'} | {v['rule']} |")
lines += ["", "Observed values per criterion are in `ALPHA8_DEV3_RESULTS.json` (`preregistration.verdicts`).",
          f"ASM adapter errors: {res['errors'] or 'none'}",
          f"Suite log: {res['suite_log_entries']} entries, head hash `{res['suite_log_head_hash']}`."]
(out / "ALPHA8_DEV3_RESULTS.md").write_text("\n".join(lines) + "\n")
print("done", res["runtime_seconds"], "s")
for v in verdicts:
    print(v["id"], "PASS" if v["passed"] else "FAIL")
