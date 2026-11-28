"""DEV34: the M4 real-data gate again (DEV33's G33-B), with DEV33's acceptance check fixed (suite runs bounded by the
remaining time, stable test ids): does learned knowledge repair fresh real bugs that the checked workflow without it
does not, without extra wrong patches? Pre-registered in benchmarks/preregistration/dev34_study.md.
Arms: DEV33's checked, checked_learned and checked_long (dev33_realbugs.ARMS), on the same per-bug evaluation.
Usage: python benchmarks/dev34_realbugs.py evaluate <work_dir> [--shard=i/N] [--resume]
       python benchmarks/dev34_realbugs.py time_control <work_dir>
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
import dev29_realbugs as D29  # noqa: E402
import dev33_realbugs as D33  # noqa: E402
from dev31_realbugs import records  # noqa: E402
from asm.coding.integrity import ChainedWriter, code_hash, environment_provenance, file_sha256, read_records  # noqa: E402

PREREG = ROOT / "benchmarks" / "preregistration" / "dev34_study.md"
MAIN = ("checked", "checked_learned")


def run(work: Path, out: Path, bugs: list, arms: tuple):
    libs = D29.libraries()
    w = ChainedWriter(out, {"run": "dev34_realbugs", "arms": {a: [D33.ARMS[a][0], D33.ARMS[a][1], sorted(D33.ARMS[a][2])] for a in arms},
                            "bugs": [[r["project"], r["bug"]] for r in bugs], "provenance": environment_provenance(),
                            "asm_coding_sha256": code_hash(), "harness_sha256": file_sha256(Path(__file__)),
                            "dev33_harness_sha256": file_sha256(Path(D33.__file__)), "dev29_harness_sha256": file_sha256(Path(D29.__file__)),
                            "preregistration_sha256": file_sha256(PREREG) if PREREG.exists() else None,
                            "validate_sha256": file_sha256(work / "validate.jsonl"),
                            "libraries_sha256": {f: file_sha256(D29.LIBRARIES / f) for f in ("knowledge_dev20.json", "shapes_dev20.json", "steps_dev20.json")}})
    for r in bugs:
        for arm in arms:
            mode, budget, options = D33.ARMS[arm]
            rec = {**D29.repair(work, r, mode, budget, libs, **options), "mode": arm}
            w.append(rec)
            print(json.dumps({k: rec.get(k) for k in ("project", "bug", "mode", "status", "families", "repair_seconds")}
                             | {"wide": (rec.get("rejected_by_reason") or {}).get("rejected_regression_suite")}), flush=True)


def main():
    stage, work = sys.argv[1], Path(sys.argv[2])
    valid = [r for r in read_records(work / "validate.jsonl")[1] if r.get("status") == "valid"]
    if stage == "evaluate":
        i, n = (int(x) for x in next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--shard=")), "0/1").split("/"))
        name, bugs = f"dev34_{i}of{n}.jsonl", [r for k, r in enumerate(valid) if k % n == i]
        if "--resume" in sys.argv:  # the bugs a stopped run did not finish in both arms, both again, in new files
            done = {k for k, v in records(work, "dev34_*of*.jsonl").items() if set(MAIN) <= set(v)}
            name, bugs = f"dev34_resume_{i}of{n}.jsonl", [r for r in valid if (r["project"], r["bug"]) not in done][i::n]
        run(work, work / name, bugs, MAIN)
    elif stage == "time_control":
        by = records(work, "dev34_*of*.jsonl")
        wins = {k for k, v in by.items() if v["checked_learned"]["status"] == "resolved" and v["checked"]["status"] != "resolved"}
        run(work, work / "dev34_time_control.jsonl", [r for r in valid if (r["project"], r["bug"]) in wins], ("checked_long",))
    else:
        raise SystemExit("stages: evaluate, time_control (bugs: dev32_mine_bugs.py, then dev14_realbugs.py envs/validate)")


if __name__ == "__main__":
    main()
