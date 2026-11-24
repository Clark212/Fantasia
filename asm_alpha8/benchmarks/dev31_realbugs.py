"""DEV31: on fresh real bugs (BugsInPy projects ASM had never run on), does ASM's learned knowledge repair bugs that the
workflow without it does not, once phase 3 gets its own time and builds its candidates fast enough to test them?
Pre-registered in benchmarks/preregistration/dev31_study.md.

Arms (DEV29's per-bug evaluation, dev29_realbugs.repair; paired, one after the other in one process):
  control       the shipped workflow with DEV15's repair families, 150 s (DEV29's control)
  learned       the same 150 s for phases 1-2, then DEV20's sealed libraries in phase 3 with 150 s of its own
                (RepairWorkflow(phase3_seconds=150)); its candidate building stops when that clock runs out
  control_long  the control with the learned arm's total time, 300 s: run on every bug the learned arm resolves and the
                control does not, so that a learned-only repair cannot come from the extra time alone
Usage: python benchmarks/dev31_realbugs.py evaluate <work_dir> [--shard=i/N] [--arms=control,learned]
       python benchmarks/dev31_realbugs.py time_control <work_dir>
       python benchmarks/dev31_realbugs.py summary <work_dir>
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
import dev29_realbugs as D29  # noqa: E402
from asm.coding.integrity import ChainedWriter, code_hash, environment_provenance, file_sha256, read_records  # noqa: E402

PREREG = ROOT / "benchmarks" / "preregistration" / "dev31_study.md"
ARMS = {"control": ("control", 150.0, {}), "learned": ("learned", 150.0, {"phase3_seconds": 150.0}),
        "control_long": ("control", 300.0, {})}


def records(work: Path, pattern: str) -> dict:
    by = {}
    for f in sorted(work.glob(pattern)):
        for r in read_records(f)[1]:
            if "mode" in r:
                by.setdefault((r["project"], r["bug"]), {})[r["mode"]] = r
    return by


def run(work: Path, out: Path, bugs: list, arms: tuple):
    libs = D29.libraries()
    w = ChainedWriter(out, {"run": "dev31_realbugs", "arms": {a: ARMS[a] for a in arms}, "bugs": [[r["project"], r["bug"]] for r in bugs],
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
            print(json.dumps({k: rec.get(k) for k in ("project", "bug", "mode", "best_rank", "status", "families", "oracle_class",
                                                       "repair_seconds")}), flush=True)


def main():
    stage, work = sys.argv[1], Path(sys.argv[2])
    arg = lambda k, d: next((a.split("=", 1)[1] for a in sys.argv if a.startswith(f"--{k}=")), d)  # noqa: E731
    valid = [r for r in read_records(work / "validate.jsonl")[1] if r.get("status") == "valid"]
    if stage == "evaluate":
        (i, n), arms = (int(x) for x in arg("shard", "0/1").split("/")), tuple(arg("arms", "control,learned").split(","))
        run(work, work / f"dev31_{'_'.join(arms)}_{i}of{n}.jsonl", [r for k, r in enumerate(valid) if k % n == i], arms)
    elif stage == "time_control":
        by = records(work, "dev31_control_learned_*of*.jsonl")
        wins = [r for r in valid if by.get((r["project"], r["bug"]), {}).get("learned", {}).get("status") == "resolved"
                and by[(r["project"], r["bug"])]["control"]["status"] != "resolved"]
        run(work, work / "dev31_time_control.jsonl", wins, ("control_long",))
    elif stage == "summary":
        extra = records(work, "dev31_time_control.jsonl")
        by = {k: {**v, **extra.get(k, {})} for k, v in records(work, "dev31_control_learned_*of*.jsonl").items()}
        resolved = {m: sorted(k for k, v in by.items() if v.get(m, {}).get("status") == "resolved") for m in ARMS}
        print(json.dumps({"bugs": len(by), **{f"{m}_resolved": resolved[m] for m in ARMS},
                          "learned_only": sorted(set(resolved["learned"]) - set(resolved["control"])),
                          "control_only": sorted(set(resolved["control"]) - set(resolved["learned"])),
                          "oracle_class": {m: {f"{k[0]}-{k[1]}": by[k][m].get("oracle_class") for k in resolved[m]} for m in ARMS}},
                         indent=1, default=str))
    else:
        raise SystemExit("stages: evaluate, time_control, summary (prepare/envs/validate: dev14_realbugs.py)")


if __name__ == "__main__":
    main()
