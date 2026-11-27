"""DEV33: does a wider acceptance check, each project's own test suite (RepairWorkflow(regression_suite=...)), stop the
wrong patches that pass a real bug's tests, without losing correct repairs? With it, does learned knowledge repair fresh
real bugs that the workflow without it does not, without extra wrong patches (DEV31's G31-A with DEV32's safety)?
Pre-registered in benchmarks/preregistration/dev33_study.md.

Arms (DEV29's per-bug evaluation, dev29_realbugs.repair; paired, one after the other in one process):
  control          the shipped workflow with DEV15's repair families, 150 s (DEV31's and DEV32's control)
  learned          DEV31's learned arm: phases 1-2 in 150 s, then DEV20's sealed libraries in phase 3 with 150 s of its own
  checked          the control with the project's test suite as regression suite
  checked_learned  the learned arm with the project's test suite as regression suite
  checked_long     the checked control with 300 s, run on every bug checked_learned resolves and checked does not
Usage: python benchmarks/dev33_realbugs.py evaluate <work_dir> [--shard=i/N] [--arms=...] [--resume]
       python benchmarks/dev33_realbugs.py time_control <work_dir>
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
import dev29_realbugs as D29  # noqa: E402
from dev31_realbugs import records  # noqa: E402
from dev33_development import project_suite  # noqa: E402
from asm.coding.integrity import ChainedWriter, code_hash, environment_provenance, file_sha256, read_records  # noqa: E402

PREREG = ROOT / "benchmarks" / "preregistration" / "dev33_study.md"
P3 = {"phase3_seconds": 150.0}
SUITE = {"regression_suite": project_suite}  # resolved on each bug's buggy tree by dev29_realbugs.repair
ARMS = {"control": ("control", 150.0, {}), "learned": ("learned", 150.0, P3), "checked": ("control", 150.0, SUITE),
        "checked_learned": ("learned", 150.0, {**P3, **SUITE}), "checked_long": ("control", 300.0, SUITE)}
MAIN = ("control", "learned", "checked", "checked_learned")


def run(work: Path, out: Path, bugs: list, arms: tuple):
    libs = D29.libraries()
    w = ChainedWriter(out, {"run": "dev33_realbugs", "arms": {a: [ARMS[a][0], ARMS[a][1], sorted(ARMS[a][2])] for a in arms},
                            "bugs": [[r["project"], r["bug"]] for r in bugs], "provenance": environment_provenance(),
                            "asm_coding_sha256": code_hash(), "harness_sha256": file_sha256(Path(__file__)),
                            "dev29_harness_sha256": file_sha256(Path(D29.__file__)),
                            "preregistration_sha256": file_sha256(PREREG) if PREREG.exists() else None,
                            "validate_sha256": file_sha256(work / "validate.jsonl"),
                            "libraries_sha256": {f: file_sha256(D29.LIBRARIES / f) for f in ("knowledge_dev20.json", "shapes_dev20.json", "steps_dev20.json")}})
    for r in bugs:
        for arm in arms:
            mode, budget, options = ARMS[arm]
            rec = {**D29.repair(work, r, mode, budget, libs, **options), "mode": arm}
            w.append(rec)
            print(json.dumps({k: rec.get(k) for k in ("project", "bug", "mode", "status", "families", "repair_seconds")}
                             | {"wide": (rec.get("rejected_by_reason") or {}).get("rejected_regression_suite")}), flush=True)


def main():
    stage, work = sys.argv[1], Path(sys.argv[2])
    arg = lambda k, d: next((a.split("=", 1)[1] for a in sys.argv if a.startswith(f"--{k}=")), d)  # noqa: E731
    valid = [r for r in read_records(work / "validate.jsonl")[1] if r.get("status") == "valid"]
    only = arg("bugs", None)  # development: a comma-separated subset, e.g. astroid-4,marko-4
    if only:
        valid = [r for r in valid if f"{r['project']}-{r['bug']}" in only.split(",")]
    if stage == "evaluate":
        (i, n), arms = (int(x) for x in arg("shard", "0/1").split("/")), tuple(arg("arms", ",".join(MAIN)).split(","))
        name, bugs = f"dev33_{'_'.join(arms)}_{i}of{n}.jsonl", [r for k, r in enumerate(valid) if k % n == i]
        if "--resume" in sys.argv:  # the bugs a stopped run did not finish in every arm, all arms again, in new files
            done = {k for k, v in records(work, f"dev33_{'_'.join(arms)}_*of*.jsonl").items() if set(arms) <= set(v)}
            name, bugs = f"dev33_{'_'.join(arms)}_resume_{i}of{n}.jsonl", [r for r in valid if (r["project"], r["bug"]) not in done][i::n]
        run(work, work / name, bugs, arms)
    elif stage == "time_control":
        by = records(work, f"dev33_{'_'.join(MAIN)}_*of*.jsonl")
        wins = {k for k, v in by.items() if v["checked_learned"]["status"] == "resolved" and v["checked"]["status"] != "resolved"}
        run(work, work / "dev33_time_control.jsonl", [r for r in valid if (r["project"], r["bug"]) in wins], ("checked_long",))
    else:
        raise SystemExit("stages: evaluate, time_control (bugs: dev32_mine_bugs.py, then dev14_realbugs.py envs/validate)")


if __name__ == "__main__":
    main()
