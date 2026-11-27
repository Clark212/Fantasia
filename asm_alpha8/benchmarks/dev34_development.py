"""DEV34 development (DEV32's and DEV33's seen bugs): can a project's OWN earlier fixes make learned knowledge produce the
developer's fix? For every valid bug, the project's fix examples (DEV17's criteria) among the commits before its buggy
commit are learned into DEV20's sealed libraries ("adapted"). Phase 3's candidates (RepairWorkflow._learned_candidates)
for each function the developer changed are generated with DEV20's libraries alone and with the adapted ones; a bug is
reproduced when a candidate equals the developer's fixed file (AST). No test runs except the bug's spectrum.
Usage: python benchmarks/dev34_development.py <out.jsonl> <work_dir> [<work_dir> ...] [--shard=i/N] [--ceiling]
       (--ceiling, a diagnosis only: the bug's OWN fix is learned too, deliberately leaked, to see whether the learned
        layers can reproduce a fix they were shown)
"""
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
import dev14_realbugs as R14  # noqa: E402
import dev29_realbugs as D29  # noqa: E402
from dev17_mine_history import examples, fn_source, functions  # noqa: E402
from asm.coding import SafeTestRunner  # noqa: E402
from asm.coding.faultloc import RepairWorkflow, ast_normal, collect_spectrum  # noqa: E402
from asm.coding.integrity import read_records  # noqa: E402
from asm.coding.understanding import CodeUnderstanding  # noqa: E402


def history(work: Path, project: str) -> list:
    """The project's fix examples at its mined head, cached in the work dir (DEV17's criteria)."""
    cache = work / f"dev34_history_{project}.jsonl"
    if not cache.exists():
        recs = list(examples(work / "repos" / project, project))
        cache.write_text("".join(json.dumps(r) + "\n" for r in recs))
    return [json.loads(line) for line in cache.read_text().splitlines()]


def own_past(work: Path, project: str, rev: str) -> list:
    """(before, after, id) of the project's fix examples among the ancestors of `rev`: only the bug's own past."""
    past = set(subprocess.run(["git", "rev-list", rev], cwd=work / "repos" / project, capture_output=True, text=True).stdout.split())
    return [(r["before"], r["after"], r["id"]) for r in history(work, project) if r["commit"] in past]


def adapted(own: list, project: str) -> dict:
    libs = D29.libraries()
    for name in ("knowledge", "shapes", "steps"):
        libs[name].learn(own, f"own:{project}")
    return libs


def own_fix(buggy: Path, fixed: Path, truth: list) -> list:
    """--ceiling: the developer's fix of each changed function as a (before, after, id) example."""
    out = []
    for q in truth:
        for path in sorted({p for p in (buggy.rglob("*.py")) if p.relative_to(buggy).as_posix().replace("/", ".")[:-3] in q}):
            rel = path.relative_to(buggy)
            if not (fixed / rel).exists():
                continue
            b, a = path.read_text(encoding="utf-8"), (fixed / rel).read_text(encoding="utf-8")
            inner = q[len(rel.as_posix().replace("/", ".")[:-3]) + 1:]
            fb, fa = functions(b), functions(a)
            if inner in fb and inner in fa:
                out.append((fn_source(b, fb[inner][0]), fn_source(a, fa[inner][0]), f"leak:{q}"))
    return out


def reproduced(libs: dict, buggy: Path, fixed: Path, spectrum, truth: list) -> dict:
    wf, funcs = RepairWorkflow(**libs), {f.qname: f for f in CodeUnderstanding().analyze(buggy).functions}
    out = {"candidates": 0, "hit": None}
    for q in truth:
        f = funcs.get(q)
        if f is None or not (fixed / f.path).exists():
            continue
        cands, _ = wf._learned_candidates(buggy, spectrum, (buggy / f.path).read_text(encoding="utf-8"), f.path, (f.line, f.end_line))
        target = ast_normal((fixed / f.path).read_text(encoding="utf-8"))
        out["candidates"] += len(cands)
        hit = next((i for i, c in enumerate(cands) if ast_normal(c.replacement) == target), None)
        if hit is not None and out["hit"] is None:
            out["hit"] = {"function": q, "index": hit, "reason": cands[hit].reason[:160]}
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out, works = Path(args[0]), [Path(a) for a in args[1:]]
    i, n = (int(x) for x in next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--shard=")), "0/1").split("/"))
    bugs = [(w, r) for w in works for r in read_records(w / "validate.jsonl")[1] if r.get("status") == "valid"][i::n]
    done = {json.loads(line)["bug"] for line in out.open()} if out.exists() else set()
    with out.open("a") as fh:
        for work, r in bugs:
            p, b = r["project"], r["bug"]
            if f"{p}-{b}" in done:
                continue
            base, bug = work / "bugs" / p / str(b), R14.corpus_dir(work) / p / "bugs" / str(b)
            meta = R14.info(bug / "bug.info")
            rec = {"bug": f"{p}-{b}", "work": work.name}
            runner = SafeTestRunner(timeout_seconds=180, python=str(work / "venvs" / r["venv"] / "bin" / "python"))
            suite = [t for t in R14.test_files(meta) if (base / "buggy" / t).exists()] or r["targets"]
            spectrum = collect_spectrum(base / "buggy", suite, runner)
            truth = R14.truth_functions(base / "buggy", R14.changed_buggy_lines((bug / "bug_patch.txt").read_text(errors="replace")))
            if not spectrum.failing or not truth:
                fh.write(json.dumps({**rec, "skipped": "no failing test traced" if truth else "no changed function"}) + "\n")
                continue
            t0 = time.monotonic()
            own = own_past(work, p, meta["buggy_commit_id"]) + (own_fix(base / "buggy", base / "fixed", truth) if "--ceiling" in sys.argv else [])
            libs = adapted(own, p)
            rec.update(own_examples=len(own), learn_seconds=round(time.monotonic() - t0, 1), truth=truth,
                       dev20=reproduced(D29.libraries(), base / "buggy", base / "fixed", spectrum, truth),
                       adapted=reproduced(libs, base / "buggy", base / "fixed", spectrum, truth))
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            print(json.dumps({k: rec[k] for k in ("bug", "own_examples", "learn_seconds")} | {
                "dev20": rec["dev20"]["hit"] is not None, "adapted": rec["adapted"]["hit"] is not None}), flush=True)


if __name__ == "__main__":
    main()
