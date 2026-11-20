"""DEV11 seeded-fault benchmark on real code (the ASM coding package and its own tests).

Single-site faults (operator / comparison / constant / boolean / negated condition) are injected one at a time;
only faults that the selected tests DETECT ("killed") are kept. For each killed fault we measure:
  * localization: tie-aware rank of the truly faulty function for each evidence source and the combination
  * repair: whether the workflow resolves it, whether the patch RESTORES the original program (AST-equal),
    and whether it is actually CORRECT, judged by held-out tests that the repair never saw.
Weights are fixed in faultloc.DEFAULT_WEIGHTS before any run; nothing here tunes them.

Usage: python benchmarks/dev11_seeded_faults.py <subject> <n_try> <n_keep> <out.jsonl> [--repair]
"""
import ast
import json
import random
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from asm.coding import SafeTestRunner, tree_fingerprint  # noqa: E402
from asm.coding.faultloc import (FaultLocalizer, RepairWorkflow, apply_site, ast_normal, enumerate_sites)  # noqa: E402
from asm.coding.patches import apply_proposal  # noqa: E402
from asm.coding.understanding import CodeUnderstanding  # noqa: E402

SUBJECTS = {
    "understanding": {"files": ["asm/coding/understanding.py"], "tests": ["tests/test_alpha8_coding_dev9.py"]},
    "semantics_static": {"files": ["asm/coding/semantics.py"],
                         "tests": ["tests/test_alpha8_coding_dev10.py::StaticSemanticsTests",
                                   "tests/test_alpha8_coding_dev10.py::MatchingUnitTests"]},
    "coding_core": {"files": [f"asm/coding/{m}.py" for m in ("diagnostics", "patches", "procedures", "analyzer", "testing",
                                                            "repair", "planner")],
                    "tests": ["tests/test_alpha8_coding_dev6.py", "tests/test_alpha8_coding_dev7.py",
                              "tests/test_alpha8_coding_intelligence.py"]},
}


def make_template(subject: str, td: Path) -> Path:
    repo = td / "repo"
    repo.mkdir()
    (repo / "asm").mkdir()
    (repo / "asm" / "__init__.py").write_text('"""stub: the coding package does not need the rest of ASM"""\n')
    shutil.copytree(ROOT / "asm" / "coding", repo / "asm" / "coding", ignore=shutil.ignore_patterns("__pycache__"))
    (repo / "tests").mkdir()
    for t in SUBJECTS[subject]["tests"]:
        f = t.split("::")[0]
        if not (repo / f).exists():
            shutil.copy(ROOT / f, repo / f)
    return repo


def rank_info(suspects, qname, key):
    """Tie-aware rank of qname under a scoring key: (optimistic, pessimistic, average) or None if score is zero."""
    scores = {s.qname: key(s) for s in suspects}
    if qname not in scores or scores[qname] <= 0:
        return None
    better = sum(1 for v in scores.values() if v > scores[qname])
    tied = sum(1 for q, v in scores.items() if v == scores[qname] and q != qname)
    return [better + 1, better + 1 + tied, round(better + 1 + tied / 2, 2)]


def main():
    subject, n_try, n_keep, out = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
    do_repair = "--repair" in sys.argv
    seed = int(next((a.split("=")[1] for a in sys.argv if a.startswith("--seed=")), "11"))
    skip = int(next((a.split("=")[1] for a in sys.argv if a.startswith("--skip=")), "0"))
    spec = SUBJECTS[subject]
    runner = SafeTestRunner(timeout_seconds=60)
    with tempfile.TemporaryDirectory(prefix="dev11_bench_") as td:
        td = Path(td)
        template = make_template(subject, td)
        base_run = runner.run_pytest(template, spec["tests"])
        assert base_run.classification == "passed", f"subject baseline must pass: {base_run.classification}"
        all_tests = sorted(base_run.outcome)
        und = CodeUnderstanding().analyze(template)
        ranges = {}
        for f in und.functions:
            ranges.setdefault(f.path, []).append((f.qname, f.line, f.end_line))
        pool = []
        for rel in spec["files"]:
            src = (template / rel).read_text()
            for site in enumerate_sites(src, rel, ranges.get(rel, [])):
                for opt in site.options:
                    pool.append((rel, site, opt))
        random.Random(seed).shuffle(pool)
        pool = pool[skip:]
        kept = 0
        stats = {"tried": 0, "killed": 0, "survived": 0, "invalid": 0, "collection_error": 0}
        with open(out, "a") as fh:
            for rel, site, opt in pool[:n_try]:
                if kept >= n_keep:
                    break
                stats["tried"] += 1
                original = (template / rel).read_text()
                mutated = apply_site(original, site, opt)
                try:
                    ast.parse(mutated)
                except SyntaxError:
                    stats["invalid"] += 1
                    continue
                work = td / f"w{stats['tried']}"
                shutil.copytree(template, work)
                (work / rel).write_text(mutated)
                run = runner.run_pytest(work, spec["tests"])
                if run.classification == "collection_error":
                    stats["collection_error"] += 1
                    shutil.rmtree(work)
                    continue
                if run.classification != "tests_failed" or not run.failed_ids:
                    stats["survived"] += 1
                    shutil.rmtree(work)
                    continue
                stats["killed"] += 1
                rec = {"subject": subject, "file": rel, "line": site.line, "kind": site.kind, "original": site.original,
                       "option": opt, "truth": site.function, "failing": run.failed_ids,
                       "n_tests": len(all_tests), "tried_index": stats["tried"], "abs_index": skip + stats["tried"]}
                t0 = time.monotonic()
                loc = FaultLocalizer(runner).localize(work, spec["tests"])
                rec["loc_seconds"] = round(time.monotonic() - t0, 1)
                rec["n_suspects_scored"] = sum(1 for s in loc.suspects if s.score > 0)
                rec["rank"] = {
                    "combined": rank_info(loc.suspects, site.function, lambda s: s.score),
                    "spectrum": rank_info(loc.suspects, site.function, lambda s: s.sources["spectrum"]),
                    "traceback": rank_info(loc.suspects, site.function, lambda s: s.sources["traceback"]),
                    "semantic": rank_info(loc.suspects, site.function, lambda s: s.sources["semantic"])}
                rec["has_traceback_evidence"] = any(s.sources["traceback"] > 0 for s in loc.suspects)
                if do_repair:
                    rng = random.Random(seed + stats["tried"])
                    others = [t for t in all_tests if t not in run.failed_ids]
                    rng.shuffle(others)
                    repair_set = sorted(run.failed_ids + others[: len(others) // 2])
                    held_out = sorted(others[len(others) // 2:])
                    # run ids grouped per file so the runner receives file::test selectors
                    t0 = time.monotonic()
                    d = RepairWorkflow(runner, time_budget_seconds=90, max_suspects=3).run(work, repair_set)
                    rec["repair_seconds"] = round(time.monotonic() - t0, 1)
                    rec["repair_status"] = d.status
                    rec["repair_suspects"] = [s["suspect"] for s in d.steps]
                    rec["caveats"] = len(d.caveats)
                    rec["rejected"] = dict(d.reasons)
                    if d.status == "resolved" and d.steps:
                        fixed = td / f"fixed{stats['tried']}"
                        shutil.copytree(work, fixed)
                        for p in d._proposals:
                            apply_proposal(fixed, p, backup=False)
                        rec["restored"] = ast_normal((fixed / rel).read_text()) == ast_normal(original)
                        rec["truth_function_patched"] = any(s == site.function for s in rec["repair_suspects"])
                        held = runner.run_pytest(fixed, held_out) if held_out else None
                        rec["held_out_n"] = len(held_out)
                        rec["held_out_passed"] = (held.classification == "passed") if held else None
                        full = runner.run_pytest(fixed, spec["tests"])
                        rec["full_suite_passed"] = full.classification == "passed"
                        shutil.rmtree(fixed)
                fh.write(json.dumps(rec) + "\n")
                fh.flush()
                kept += 1
                shutil.rmtree(work, ignore_errors=True)
        print(json.dumps({"subject": subject, **stats, "kept": kept}))


if __name__ == "__main__":
    main()
