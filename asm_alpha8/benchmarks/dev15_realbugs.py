"""DEV15 evaluation on the same REAL historical bugs as DEV14 (BugsInPy; PySnooper, thefuck, tqdm, cookiecutter, httpie,
youtube-dl). The prepare / envs / validate stages are DEV14's (benchmarks/dev14_realbugs.py) and are reused unchanged;
DEV15 re-ran them from scratch and obtained the same 83 valid bugs.

evaluate (DEV15):
  - localization rank of the developer-changed functions (unchanged method, reported for comparability)
  - the shipped workflow with DEV15 repair families (`--mode=dev15`, default) or the DEV14 repair space
    (`--mode=dev14`: extended_ops=False) on the same machine, 150 s budget
  - an accepted patch is judged against the developer's fixed program with the DEV15 oracle (constants mined from
    buggy, fixed and patched versions; import-time functions compared by module state)
  - the full patch diff and the developer's diff are stored, so every accepted patch can be read by a person
Usage: python benchmarks/dev15_realbugs.py evaluate <work_dir> [--mode=dev15|dev14] [--out=F] [--skip=K] [--limit=N]
                                                              [--budget=150] [--projects=a,b]
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

PREREG = ROOT / "benchmarks" / "preregistration" / "dev15_study.md"


def stage_evaluate(work: Path, projects: list, limit: int, budget: float, out: str, skip: int, mode: str):
    from asm.coding.faultloc import FaultLocalizer, RepairWorkflow, ast_normal, collect_spectrum, reconcile_spectrum
    from asm.coding.patches import apply_proposal
    from asm.coding.sandbox import interpreter
    from asm.coding.understanding import CodeUnderstanding
    _, vrecs = read_records(work / "validate.jsonl")
    valid = [r for r in vrecs if r.get("status") == "valid" and r["project"] in projects]
    w = ChainedWriter(work / out, {"run": "dev15_realbugs_evaluate", "mode": mode, "projects": projects,
                                   "provenance": environment_provenance(), "asm_coding_sha256": code_hash(),
                                   "preregistration_sha256": file_sha256(PREREG) if PREREG.exists() else None,
                                   "validate_sha256": file_sha256(work / "validate.jsonl"), "budget": budget, "skip": skip,
                                   "limit": limit, "repair_suite": "the bug's test file(s) from the fixed version",
                                   "oracle": {"module": "dev15_oracle", "gen_budget": O.GEN_BUDGET, "gen_seed": O.GEN_SEED}})
    for r in valid[skip:skip + limit if limit else None]:
        p, n = r["project"], r["bug"]
        bug = R14.corpus_dir(work) / p / "bugs" / str(n)
        meta = R14.info(bug / "bug.info")
        base, err = R14.checkout(work, p, bug, meta)
        rec = {"project": p, "bug": n, "targets": r["targets"], "mode": mode}
        if err:
            w.append(dict(rec, status="checkout_failed"))
            continue
        runner = SafeTestRunner(timeout_seconds=180, python=str(work / "venvs" / r["venv"] / "bin" / "python"))
        suite = [t for t in R14.test_files(meta) if (base / "buggy" / t).exists()] or r["targets"]
        dev_patch = (bug / "bug_patch.txt").read_text(errors="replace")
        changed = R14.changed_buggy_lines(dev_patch)
        truth = R14.truth_functions(base / "buggy", changed)
        rec.update(suite=suite, changed_files=sorted(changed), truth=truth,
                   developer_fix_lines=sum(len(v) for v in changed.values()), developer_patch=dev_patch[:6000])
        t0 = time.monotonic()
        spectrum = collect_spectrum(base / "buggy", suite, runner)
        plain = runner.run_pytest(base / "buggy", suite)
        reconcile_spectrum(spectrum, set(plain.failed_ids))
        if not spectrum.complete or not spectrum.failing:
            w.append(dict(rec, status="no_spectrum", reason=spectrum.incomplete_reason or "no failing tests in the suite",
                          plain=plain.classification))
            print(json.dumps({"project": p, "bug": n, "status": "no_spectrum"}), flush=True)
            continue
        loc = FaultLocalizer(runner).localize(base / "buggy", suite, spectrum=spectrum)
        scores = {s.qname: s.score for s in loc.suspects}
        ranks = []
        for q in truth:
            if scores.get(q, 0) > 0:
                better = sum(1 for v in scores.values() if v > scores[q])
                ranks.append([better + 1, better + 1 + sum(1 for k, v in scores.items() if v == scores[q] and k != q)])
        rec.update(failing=len(spectrum.failing), passing=len(spectrum.passing), suspects=len(loc.suspects),
                   best_rank=min(ranks) if ranks else None, top5=[s.qname for s in loc.suspects[:5]],
                   localize_seconds=round(time.monotonic() - t0, 1))
        t1 = time.monotonic()
        d = RepairWorkflow(runner, time_budget_seconds=budget, extended_ops=(mode == "dev15")).run(base / "buggy", suite)
        rec.update(status=d.status, repair_seconds=round(time.monotonic() - t1, 1), notes=[str(x)[:300] for x in d.notes[:6]],
                   rejected_by_reason=d.reasons)
        if d.steps:
            st = d.steps[0]
            rec.update(suspect=st["suspect"], desc=st["description"], label=st["confidence"], flags=st["confidence_basis"],
                       counted=st.get("confidence_counted"), n_steps=len(d.steps),
                       families=[s.get("edit_family") for s in d.steps], asm_diff=d.diff[:6000],
                       verification_mode=(st.get("verification") or {}).get("mode", "replay")
                       if (st.get("verification") or {}).get("available") else None)
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
            rec.update(patched_files=files, oracle_class=cls["class"], original_ok=cls.get("original_ok"),
                       oracle={k: {kk: v.get(kk) for kk in ("status", "mode", "n_diff", "n_diff_in_dist", "example", "why")}
                               for k, v in cls["details"].items()},
                       patch_sha256={f: file_sha256(pdir / f) for f in files},
                       fixed_tests_on_patched=R14.run_side(runner, pdir, suite)["classification"])
        w.append(rec)
        print(json.dumps({k: rec.get(k) for k in ("project", "bug", "best_rank", "status", "families", "label", "oracle_class")}),
              flush=True)


def main():
    stage, work = sys.argv[1], Path(sys.argv[2])
    arg = lambda k, d: next((a.split("=", 1)[1] for a in sys.argv if a.startswith(f"--{k}=")), d)  # noqa: E731
    projects = arg("projects", ",".join(R14.PROJECTS)).split(",")
    if stage != "evaluate":
        raise SystemExit("DEV15 adds only the evaluate stage; run prepare/envs/validate with dev14_realbugs.py")
    mode = arg("mode", "dev15")
    assert mode in {"dev15", "dev14"}
    stage_evaluate(work, projects, int(arg("limit", "0")), float(arg("budget", "150")), arg("out", f"evaluate_{mode}.jsonl"),
                   int(arg("skip", "0")), mode)


if __name__ == "__main__":
    main()
