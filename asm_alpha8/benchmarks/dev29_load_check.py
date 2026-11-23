"""DEV29 load check, NOT pre-registered. During part of the pre-registered run (15:46:36-16:07:09 UTC), other experiments
shared the 4-CPU machine: DEV30's runs and analyses, one process at a time. The workflow runs under a wall-clock budget,
so that load could change an arm's outcome. This re-runs both arms of the bugs that ran in that window, with the same
harness function, on the same machine once nothing else runs, and compares them with the pre-registered records.
Usage: python benchmarks/dev29_load_check.py run <work_dir> --shard=i/N
       python benchmarks/dev29_load_check.py compare <work_dir>
"""
import json
import sys
from pathlib import Path

import dev29_realbugs as D
from asm.coding.integrity import ChainedWriter, environment_provenance, file_sha256, read_records

WINDOW = ("15:46:36Z", "16:07:09Z")
BUGS = [("thefuck", n) for n in (*range(3, 21), 21, 24, 27, 30, 33)]  # every bug with an arm that ran in WINDOW


def run(work, shard):
    i, n = shard
    valid = {(r["project"], r["bug"]): r for r in read_records(work / "validate.jsonl")[1] if r.get("status") == "valid"}
    w = ChainedWriter(work / f"dev29_loadcheck_{i}of{n}.jsonl", {"run": "dev29_load_check (exploratory)", "window": WINDOW,
                      "bugs": BUGS, "shard": [i, n], "provenance": environment_provenance(),
                      "harness_sha256": file_sha256(Path(D.__file__)), "check_sha256": file_sha256(Path(__file__))})
    libs = D.libraries()
    for k, bug in enumerate(BUGS):
        if k % n == i:
            for mode in D.MODES:
                w.append(D.repair(work, valid[bug], mode, 150.0, libs))


def compare(work):
    first = {(r["project"], r["bug"], r["mode"]): r for f in work.glob("dev29_evaluate_*of*.jsonl") for r in read_records(f)[1] if "mode" in r}
    again = {(r["project"], r["bug"], r["mode"]): r for f in work.glob("dev29_loadcheck_*of*.jsonl") for r in read_records(f)[1] if "mode" in r}
    for key in sorted(again):
        a, b = first[key], again[key]
        same = (a["status"], a.get("asm_diff"), a.get("oracle_class")) == (b["status"], b.get("asm_diff"), b.get("oracle_class"))
        print(json.dumps({"bug": f"{key[0]}-{key[1]}", "mode": key[2], "run": a["status"], "load_check": b["status"],
                          "same_status_patch_and_class": same, "run_seconds": a.get("repair_seconds"), "load_check_seconds": b.get("repair_seconds")}))


if __name__ == "__main__":
    stage, work = sys.argv[1], Path(sys.argv[2])
    if stage == "run":
        run(work, tuple(int(x) for x in next(a for a in sys.argv if a.startswith("--shard=")).split("=")[1].split("/")))
    else:
        compare(work)
