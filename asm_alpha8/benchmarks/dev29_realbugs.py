"""DEV29: on DEV15's real historical bugs (BugsInPy), does ASM's learned knowledge (DEV20's sealed procedures, shapes and
steps, phase 3 of the repair workflow) repair bugs that the workflow without it does not, once fault localization tells it
where to look? Pre-registered in benchmarks/preregistration/dev29_study.md.

prepare / envs / validate: dev14_realbugs.py, unchanged. evaluate (DEV29): for every valid bug, the shipped workflow
(DEV15's repair families, 150 s budget) runs twice, paired and one after the other in one process: 'control' (no learned
knowledge, DEV15's configuration) and 'learned' (+ the sealed DEV20 libraries in phase 3, reached only when phases 1 and 2
accept nothing). An accepted patch is judged against the developer's fixed program with DEV15's oracle; both diffs are
stored so that every accepted patch can be read by a person.
Usage: python benchmarks/dev29_realbugs.py evaluate <work_dir> [--shard=i/N] [--budget=150]
       python benchmarks/dev29_realbugs.py summary <work_dir>
"""
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
import dev14_realbugs as R14  # noqa: E402
import dev15_oracle as O  # noqa: E402
from asm.coding import SafeTestRunner  # noqa: E402
from asm.coding.integrity import ChainedWriter, code_hash, environment_provenance, file_sha256, read_records  # noqa: E402

PREREG = ROOT / "benchmarks" / "preregistration" / "dev29_study.md"
LIBRARIES = ROOT / "benchmarks" / "results" / "dev20"
MODES = ("control", "learned")


def libraries():
    from asm.coding.knowledge import KnowledgeBase
    from asm.coding.shapes import ShapeLibrary
    from asm.coding.steps import StepLibrary
    return {"knowledge": KnowledgeBase.load(LIBRARIES / "knowledge_dev20.json"), "shapes": ShapeLibrary.load(LIBRARIES / "shapes_dev20.json"),
            "steps": StepLibrary.load(LIBRARIES / "steps_dev20.json")}


def repair(work, r, mode, budget, libs):
    """DEV15's per-bug evaluation (dev15_realbugs.stage_evaluate) for one mode."""
    from asm.coding.faultloc import FaultLocalizer, RepairWorkflow, ast_normal, collect_spectrum, reconcile_spectrum
    from asm.coding.patches import apply_proposal
    from asm.coding.sandbox import interpreter
    from asm.coding.understanding import CodeUnderstanding
    p, n = r["project"], r["bug"]
    bug = R14.corpus_dir(work) / p / "bugs" / str(n)
    meta = R14.info(bug / "bug.info")
    base, err = R14.checkout(work, p, bug, meta)
    rec = {"project": p, "bug": n, "targets": r["targets"], "mode": mode}
    if err:
        return dict(rec, status="checkout_failed")
    runner = SafeTestRunner(timeout_seconds=180, python=str(work / "venvs" / r["venv"] / "bin" / "python"))
    suite = [t for t in R14.test_files(meta) if (base / "buggy" / t).exists()] or r["targets"]
    dev_patch = (bug / "bug_patch.txt").read_text(errors="replace")
    changed = R14.changed_buggy_lines(dev_patch)
    truth = R14.truth_functions(base / "buggy", changed)
    rec.update(suite=suite, changed_files=sorted(changed), truth=truth, developer_patch=dev_patch[:6000])
    t0 = time.monotonic()
    spectrum = collect_spectrum(base / "buggy", suite, runner)
    plain = runner.run_pytest(base / "buggy", suite)
    reconcile_spectrum(spectrum, set(plain.failed_ids))
    if not spectrum.complete or not spectrum.failing:
        return dict(rec, status="no_spectrum", reason=spectrum.incomplete_reason or "no failing tests in the suite")
    loc = FaultLocalizer(runner).localize(base / "buggy", suite, spectrum=spectrum)
    scores = {s.qname: s.score for s in loc.suspects}
    ranks = [sum(1 for v in scores.values() if v > scores[q]) + 1 for q in truth if scores.get(q, 0) > 0]
    rec.update(suspects=len(loc.suspects), best_rank=min(ranks) if ranks else None, localize_seconds=round(time.monotonic() - t0, 1))
    t1 = time.monotonic()
    learned = libs if mode == "learned" else {}
    d = RepairWorkflow(runner, time_budget_seconds=budget, extended_ops=True, **learned).run(base / "buggy", suite)
    rec.update(status=d.status, repair_seconds=round(time.monotonic() - t1, 1), notes=[str(x)[:300] for x in d.notes[:6]],
               rejected_by_reason=d.reasons)
    if d.steps:
        st = d.steps[0]
        rec.update(suspect=st["suspect"], desc=st["description"], label=st["confidence"], n_steps=len(d.steps),
                   families=[s.get("edit_family") for s in d.steps], asm_diff=d.diff[:6000])
    if d.status == "resolved" and d.steps:
        pdir = base / "patched"
        if pdir.exists():
            shutil.rmtree(pdir)
        shutil.copytree(base / "buggy", pdir)
        for prop in d._proposals:
            apply_proposal(pdir, prop, backup=False)
        files = sorted({prop.path for prop in d._proposals})
        restored = all((base / "fixed" / f).exists() and ast_normal((pdir / f).read_text()) == ast_normal((base / "fixed" / f).read_text())
                       for f in files)
        with interpreter(runner.python):
            fixed_spec = collect_spectrum(base / "fixed", suite, runner)
            finfos = {f.qname: f for f in CodeUnderstanding().analyze(base / "fixed").functions}
            cls = O.classify_patch(base / "fixed", pdir, restored, sorted(set(truth) | {s["suspect"] for s in d.steps}),
                                   finfos, fixed_spec, extra_repos=[base / "buggy"])
        rec.update(patched_files=files, oracle_class=cls["class"],
                   oracle={k: {kk: v.get(kk) for kk in ("status", "mode", "n_diff", "example", "why")} for k, v in cls["details"].items()},
                   fixed_tests_on_patched=R14.run_side(runner, pdir, suite)["classification"])
    return rec


def stage_evaluate(work: Path, shard: tuple, budget: float):
    i, n = shard
    _, vrecs = read_records(work / "validate.jsonl")
    valid = [r for r in vrecs if r.get("status") == "valid"]
    libs = libraries()
    w = ChainedWriter(work / f"dev29_evaluate_{i}of{n}.jsonl", {
        "run": "dev29_realbugs_evaluate", "shard": [i, n], "modes": MODES, "budget": budget, "provenance": environment_provenance(),
        "asm_coding_sha256": code_hash(), "harness_sha256": file_sha256(Path(__file__)),
        "preregistration_sha256": file_sha256(PREREG) if PREREG.exists() else None,
        "validate_sha256": file_sha256(work / "validate.jsonl"), "valid_bugs": len(valid),
        "libraries_sha256": {f: file_sha256(LIBRARIES / f) for f in ("knowledge_dev20.json", "shapes_dev20.json", "steps_dev20.json")},
        "oracle": {"module": "dev15_oracle", "gen_budget": O.GEN_BUDGET, "gen_seed": O.GEN_SEED}})
    for k, r in enumerate(valid):
        if k % n != i:
            continue
        for mode in MODES:
            rec = repair(work, r, mode, budget, libs)
            w.append(rec)
            print(json.dumps({x: rec.get(x) for x in ("project", "bug", "mode", "best_rank", "status", "families", "oracle_class")}), flush=True)


def summary(work: Path):
    recs = [r for f in sorted(work.glob("dev29_evaluate_*of*.jsonl")) for r in read_records(f)[1] if "mode" in r]
    by = {}
    for r in recs:
        by.setdefault((r["project"], r["bug"]), {})[r["mode"]] = r
    resolved = {m: sorted(k for k, v in by.items() if v.get(m, {}).get("status") == "resolved") for m in MODES}
    out = {"bugs": len(by), **{f"{m}_resolved": len(resolved[m]) for m in MODES},
           "learned_only_resolved": sorted(set(resolved["learned"]) - set(resolved["control"])),
           "control_only_resolved": sorted(set(resolved["control"]) - set(resolved["learned"])),
           "oracle_class": {m: {str(k): by[k][m].get("oracle_class") for k in resolved[m]} for m in MODES}}
    print(json.dumps(out, indent=1, default=str))


def main():
    stage, work = sys.argv[1], Path(sys.argv[2])
    arg = lambda k, d: next((a.split("=", 1)[1] for a in sys.argv if a.startswith(f"--{k}=")), d)  # noqa: E731
    if stage == "evaluate":
        i, n = (int(x) for x in arg("shard", "0/1").split("/"))
        stage_evaluate(work, (i, n), float(arg("budget", "150")))
    elif stage == "summary":
        summary(work)
    else:
        raise SystemExit("DEV29 adds the evaluate and summary stages; run prepare/envs/validate with dev14_realbugs.py")


if __name__ == "__main__":
    main()
