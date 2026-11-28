"""DEV35 development (DEV32-DEV34's seen bugs): what does causal repair by intervention (asm.coding.causal) find on real
bugs? For every valid bug with a spectrum, the top 3 suspects of DEV15's localization and the functions the developer
changed are investigated while the bug's tests run. Each proposed edit is then checked as the workflow would: the bug's
tests on the patched copy (the failing ones pass, the passing ones still pass), then the project's own suite (DEV33's
check). An edit that passes both is PLAUSIBLE; it is RESTORED when it equals the developer's fixed file (AST).
Usage: python benchmarks/dev35_development.py <out.jsonl> <work_dir> [<work_dir> ...] [--shard=i/N] [--bugs=a-1,b-2]
"""
import difflib
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
import dev14_realbugs as R14  # noqa: E402
from dev33_development import project_suite  # noqa: E402
from asm.coding import SafeTestRunner  # noqa: E402
from asm.coding.causal import investigate  # noqa: E402
from asm.coding.faultloc import FaultLocalizer, _stable_id, ast_normal, collect_spectrum, reconcile_spectrum  # noqa: E402
from asm.coding.integrity import read_records  # noqa: E402
from asm.coding.understanding import CodeUnderstanding  # noqa: E402


def passing_set(runner, tree: Path, suite: list) -> tuple:
    r = runner.run_pytest(tree, suite, extra_args=("--continue-on-collection-errors",))
    return {_stable_id(t) for t, s in r.outcome.items() if s == "passed"}, r


def check(runner, buggy: Path, path: str, source: str, suite: list, failing: list, passing: set, wide):
    """(passes the bug's tests, passes the project's suite) for one edit."""
    with tempfile.TemporaryDirectory(prefix="asm_dev35_check_") as td:
        tree = Path(td) / "repo"
        shutil.copytree(buggy, tree, symlinks=True)
        (tree / path).write_text(source, encoding="utf-8")
        r = runner.run_pytest(tree, suite)
        now = {t for t, s in r.outcome.items() if s == "passed"}
        if not (set(failing) <= now and passing <= now):
            return False, None
        if wide() is None:
            return True, None
        after, _ = passing_set(runner, tree, wide()[1])
        return True, not (wide()[0] - after)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out, works = Path(args[0]), [Path(a) for a in args[1:]]
    i, n = (int(x) for x in next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--shard=")), "0/1").split("/"))
    only = next((a.split("=", 1)[1].split(",") for a in sys.argv if a.startswith("--bugs=")), None)
    bugs = [(w, r) for w in works for r in read_records(w / "validate.jsonl")[1] if r.get("status") == "valid"
            and (only is None or f"{r['project']}-{r['bug']}" in only)][i::n]
    done = {json.loads(line)["bug"] for line in out.open()} if out.exists() else set()
    with out.open("a") as fh:
        for work, r in bugs:
            p, b = r["project"], r["bug"]
            if f"{p}-{b}" in done:
                continue
            t0 = time.monotonic()
            base, bug = work / "bugs" / p / str(b), R14.corpus_dir(work) / p / "bugs" / str(b)
            meta, buggy = R14.info(bug / "bug.info"), work / "bugs" / p / str(b) / "buggy"
            runner = SafeTestRunner(timeout_seconds=180, python=str(work / "venvs" / r["venv"] / "bin" / "python"))
            suite = [t for t in R14.test_files(meta) if (buggy / t).exists()] or r["targets"]
            rec = {"bug": f"{p}-{b}", "work": work.name}
            spectrum = collect_spectrum(buggy, suite, runner)
            plain = runner.run_pytest(buggy, suite)
            reconcile_spectrum(spectrum, set(plain.failed_ids))
            if not spectrum.complete or not spectrum.failing:
                fh.write(json.dumps({**rec, "skipped": spectrum.incomplete_reason or "no failing test"}) + "\n")
                continue
            failing = sorted(spectrum.failing)
            passing = {t for t, s in plain.outcome.items() if s == "passed"}
            truth = R14.truth_functions(buggy, R14.changed_buggy_lines((bug / "bug_patch.txt").read_text(errors="replace")))
            loc = FaultLocalizer(runner).localize(buggy, suite, spectrum=spectrum)
            top = [s.qname for s in loc.suspects if s.score > 0][:3]
            funcs = {f.qname: f for f in CodeUnderstanding().analyze(buggy).functions}
            cache = {}

            def wide():  # the project's suite and what passes on buggy, computed once and only if needed
                if "w" not in cache:
                    ps = project_suite(buggy)
                    cache["w"] = (passing_set(runner, buggy, ps)[0], ps) if ps else None
                return cache["w"]

            rec.update(failing=failing, truth=truth, top=top, functions=[])
            for q in dict.fromkeys(top + truth):
                f = funcs.get(q)
                if f is None:
                    continue
                res = investigate(runner, buggy, f.path, (f.line, f.end_line), failing, sorted(passing)[:200])
                fixed_src = (base / "fixed" / f.path).read_text(encoding="utf-8") if (base / "fixed" / f.path).exists() else None
                fr = {"qname": q, "in_top3": q in top, "is_truth": q in truth, "sites": res["sites"], "tried": res["tried"],
                      "causes": len(res["causes"]), "note": res["note"][:300], "edits": []}
                original = (buggy / f.path).read_text(encoding="utf-8")
                for src, why in res["edits"][:20]:
                    ok, wide_ok = check(runner, buggy, f.path, src, suite, failing, passing, wide)
                    e = {"why": why, "bug_tests": ok, "suite": wide_ok}
                    if ok:
                        e["restored"] = fixed_src is not None and ast_normal(src) == ast_normal(fixed_src)
                        e["diff"] = "".join(difflib.unified_diff(original.splitlines(True), src.splitlines(True), f"a/{f.path}", f"b/{f.path}", n=1))[:3000]
                    fr["edits"].append(e)
                rec["functions"].append(fr)
            rec["seconds"] = round(time.monotonic() - t0, 1)
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            pl = [e for fr in rec["functions"] for e in fr["edits"] if e["bug_tests"] and e["suite"] is not False]
            print(json.dumps({"bug": rec["bug"], "causes": sum(fr["causes"] for fr in rec["functions"]), "plausible": len(pl),
                              "restored": sum(bool(e.get("restored")) for e in pl), "seconds": rec["seconds"]}), flush=True)


if __name__ == "__main__":
    main()
