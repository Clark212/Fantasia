"""DEV33 development (DEV32's 143 bugs, already seen): would a wider acceptance check, the project's whole test suite,
tell DEV32's accepted patches apart? For every bug resolved in DEV32 and every valid bug's developer fix, the suite runs
on the buggy, the patched and the fixed tree; a test that passes on buggy and fails on patched is a regression. A test
module that cannot be imported (an optional dependency) does not stop the run.
Usage: python benchmarks/dev33_development.py <dev32_work_dir> <out.jsonl> [--fixes] [--shard=i/N]
       (--fixes: every valid bug's buggy and fixed tree only, the check's cost to real fixes)
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
from dev31_realbugs import records  # noqa: E402
from asm.coding import SafeTestRunner  # noqa: E402
from asm.coding.faultloc import is_test_path  # noqa: E402
from asm.coding.integrity import read_records  # noqa: E402


def project_suite(tree: Path) -> list:
    """The project's own tests: its tests/ or test/ directory, else its top-level test modules."""
    dirs = [d for d in ("tests", "test") if (tree / d).is_dir()]
    return dirs or sorted(p.name for p in tree.glob("*.py") if is_test_path(p.name))


def outcomes(runner, tree: Path, suite: list) -> dict:
    r = runner.run_pytest(tree, suite, extra_args=("--continue-on-collection-errors",))  # a module that cannot import is one error, not the end
    return {"classification": r.classification, "seconds": round(r.duration_seconds, 1), "outcome": r.outcome}


def main():
    work, out = Path(sys.argv[1]), Path(sys.argv[2])
    venv = {(r["project"], r["bug"]): r["venv"] for r in read_records(work / "validate.jsonl")[1] if r.get("status") == "valid"}
    by = records(work, "dev32_control_learned_guarded_*of*.jsonl")
    resolved = sorted(k for k, v in by.items() if any(v[m]["status"] == "resolved" for m in v))
    trees = ("buggy", "fixed") if "--fixes" in sys.argv else ("buggy", "patched", "fixed")
    done = {json.loads(line)["bug"] for line in out.open()} if out.exists() else set()  # a stopped run goes on
    with out.open("a") as fh:
        i, n = (int(x) for x in next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--shard=")), "0/1").split("/"))
        for k in (sorted(venv) if "--fixes" in sys.argv else resolved)[i::n]:
            base = work / "bugs" / k[0] / str(k[1])
            runner = SafeTestRunner(timeout_seconds=600, python=str(work / "venvs" / venv[k] / "bin" / "python"))
            suite = project_suite(base / "buggy")
            if f"{k[0]}-{k[1]}" in done or not suite:  # no suite found: the check is off for this bug
                if not suite and f"{k[0]}-{k[1]}" not in done:
                    fh.write(json.dumps({"bug": f"{k[0]}-{k[1]}", "suite": [], "no_suite": True}) + "\n")
                continue
            runs = {t: outcomes(runner, base / t, suite) for t in trees}
            passed = {i for i, s in runs["buggy"]["outcome"].items() if s == "passed"}
            rec = {"bug": f"{k[0]}-{k[1]}", "suite": suite, **{f"{t}_run": {x: runs[t][x] for x in ("classification", "seconds")} for t in runs},
                   **{f"{t}_regressions": sorted(i for i in passed if runs[t]["outcome"].get(i, "missing") not in ("passed", "skipped", "xfailed"))
                      for t in trees[1:]}}
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            print(json.dumps({x: (v if not isinstance(v, list) else len(v)) for x, v in rec.items()}), flush=True)


if __name__ == "__main__":
    main()
