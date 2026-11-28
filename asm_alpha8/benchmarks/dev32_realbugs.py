"""DEV32: on fresh real bugs mined BugsInPy-style (benchmarks/dev32_mine_bugs.py), does the test-copy guard stop learned
knowledge from accepting patches that hard-code the failing tests' data, without losing its correct repairs? And DEV31's
question on new bugs: does learned knowledge repair bugs that the workflow without it does not?
Pre-registered in benchmarks/preregistration/dev32_study.md.

Arms (DEV29's per-bug evaluation, dev29_realbugs.repair; paired, one after the other in one process):
  control       the shipped workflow with DEV15's repair families, 150 s (DEV31's control)
  learned       DEV31's learned arm: phases 1-2 in 150 s, then DEV20's sealed libraries in phase 3 with 150 s of its own
  guarded       the learned arm with RepairWorkflow(test_copy_guard=True)
  control_long  the control with 300 s, run on every bug the learned or the guarded arm resolves and the control does not
Usage: python benchmarks/dev32_realbugs.py evaluate <work_dir> [--shard=i/N] [--arms=control,learned,guarded] [--resume]
       python benchmarks/dev32_realbugs.py time_control <work_dir>
       python benchmarks/dev32_realbugs.py summary <work_dir>
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
import dev29_realbugs as D29  # noqa: E402
from dev31_realbugs import records  # noqa: E402
from asm.coding.integrity import ChainedWriter, code_hash, environment_provenance, file_sha256, read_records  # noqa: E402

PREREG = ROOT / "benchmarks" / "preregistration" / "dev32_study.md"
LEARNED = ("learned", 150.0, {"phase3_seconds": 150.0})
ARMS = {"control": ("control", 150.0, {}), "learned": LEARNED,
        "guarded": ("learned", 150.0, {**LEARNED[2], "test_copy_guard": True}), "control_long": ("control", 300.0, {})}


def run(work: Path, out: Path, bugs: list, arms: tuple):
    libs = D29.libraries()
    w = ChainedWriter(out, {"run": "dev32_realbugs", "arms": {a: ARMS[a] for a in arms}, "bugs": [[r["project"], r["bug"]] for r in bugs],
                            "provenance": environment_provenance(), "asm_coding_sha256": code_hash(),
                            "harness_sha256": file_sha256(Path(__file__)), "dev29_harness_sha256": file_sha256(Path(D29.__file__)),
                            "preregistration_sha256": file_sha256(PREREG) if PREREG.exists() else None,
                            "validate_sha256": file_sha256(work / "validate.jsonl"),
                            "libraries_sha256": {f: file_sha256(D29.LIBRARIES / f) for f in ("knowledge_dev20.json", "shapes_dev20.json", "steps_dev20.json")}})
    for r in bugs:
        for arm in arms:
            mode, budget, options = ARMS[arm]
            rec = {**D29.repair(work, r, mode, budget, libs, **options), "mode": arm}
            w.append(rec)
            print(json.dumps({k: rec.get(k) for k in ("project", "bug", "mode", "best_rank", "status", "families", "repair_seconds")}
                             | {"test_copy": (rec.get("rejected_by_reason") or {}).get("test_copy")}), flush=True)


def resolved(by: dict) -> dict:
    return {m: sorted(k for k, v in by.items() if v.get(m, {}).get("status") == "resolved") for m in ARMS}


def main():
    stage, work = sys.argv[1], Path(sys.argv[2])
    arg = lambda k, d: next((a.split("=", 1)[1] for a in sys.argv if a.startswith(f"--{k}=")), d)  # noqa: E731
    valid = [r for r in read_records(work / "validate.jsonl")[1] if r.get("status") == "valid"]
    if stage == "evaluate":
        (i, n), arms = (int(x) for x in arg("shard", "0/1").split("/")), tuple(arg("arms", "control,learned,guarded").split(","))
        name, bugs = f"dev32_{'_'.join(arms)}_{i}of{n}.jsonl", [r for k, r in enumerate(valid) if k % n == i]
        if "--resume" in sys.argv:  # the bugs a stopped run did not finish in every arm, all arms again, in new files
            done = {k for k, v in records(work, f"dev32_{'_'.join(arms)}_*of*.jsonl").items() if set(arms) <= set(v)}
            name, bugs = f"dev32_{'_'.join(arms)}_resume_{i}of{n}.jsonl", [r for r in valid if (r["project"], r["bug"]) not in done][i::n]
        run(work, work / name, bugs, arms)
    elif stage == "time_control":
        res = resolved(records(work, "dev32_control_learned_guarded_*of*.jsonl"))
        wins = (set(res["learned"]) | set(res["guarded"])) - set(res["control"])
        run(work, work / "dev32_time_control.jsonl", [r for r in valid if (r["project"], r["bug"]) in wins], ("control_long",))
    elif stage == "summary":
        extra = records(work, "dev32_time_control.jsonl")
        by = {k: {**v, **extra.get(k, {})} for k, v in records(work, "dev32_control_learned_guarded_*of*.jsonl").items()}
        res = resolved(by)
        print(json.dumps({"bugs": len(by), **{f"{m}_resolved": res[m] for m in ARMS},
                          **{f"{m}_only": sorted(set(res[m]) - set(res["control"])) for m in ("learned", "guarded")},
                          "control_only": sorted(set(res["control"]) - set(res["learned"]) - set(res["guarded"])),
                          "learned_not_guarded": sorted(set(res["learned"]) - set(res["guarded"]))}, indent=1, default=str))
    else:
        raise SystemExit("stages: evaluate, time_control, summary (bugs: dev32_mine_bugs.py, then dev14_realbugs.py envs/validate)")


if __name__ == "__main__":
    main()
