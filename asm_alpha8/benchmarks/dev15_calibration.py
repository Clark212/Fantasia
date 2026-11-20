"""DEV15 paired calibration on injected faults in the FRESH subjects (semver, parse, more-itertools).

Question (pre-registered, benchmarks/preregistration/dev15_study.md, gate G1): do the DEV15 repair families make the
shipped workflow accept more WRONG patches than the DEV14 repair space, on the same faults and the same test suites?
For every single-site fault detected by the subject's full suite (DEV14 fault model, seed fixed in advance), and for
each suite strength (half = failing + random half of passing; weak = failing only), the shipped RepairWorkflow is run
twice: extended_ops=True (DEV15) and extended_ops=False (DEV14 repair space). Each accepted patch is classed by the
DEV15 oracle against the known-correct original program. Flags are stored, so every label rule can be recomputed.
Usage: python benchmarks/dev15_calibration.py <subject> <n_keep> <out.jsonl> --seed=N [--skip=K]
"""
import json
import random
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
import dev15_oracle as O  # noqa: E402
import dev15_subjects as S  # noqa: E402
from dev15_bench import manifest, text_sha  # noqa: E402
from asm.coding import SafeTestRunner  # noqa: E402
from asm.coding.faultloc import RepairWorkflow, apply_site, ast_normal, collect_spectrum, enumerate_sites  # noqa: E402
from asm.coding.integrity import ChainedWriter  # noqa: E402
from asm.coding.patches import apply_proposal  # noqa: E402
from asm.coding.understanding import CodeUnderstanding  # noqa: E402

BUDGET = 150.0


def judged_workflow(work, suite, runner, template, rel, original, truth, infos, orig_spectrum, td, extended):
    t0 = time.monotonic()
    d = RepairWorkflow(runner, time_budget_seconds=BUDGET, max_suspects=3, extended_ops=extended).run(work, suite)
    out = {"status": d.status, "seconds": round(time.monotonic() - t0, 1)}
    if d.steps:
        st = d.steps[0]
        out.update({"suspect": st["suspect"], "desc": st["description"], "label": st["confidence"],
                    "flags": st["confidence_basis"], "n_steps": len(d.steps),
                    "families": [s.get("edit_family") for s in d.steps],
                    "verification_mode": (st.get("verification") or {}).get("mode", "replay")
                    if (st.get("verification") or {}).get("available") else None})
    if d.status == "resolved" and d.steps:
        cdir = td / "cls"
        if cdir.exists():
            shutil.rmtree(cdir)
        shutil.copytree(work, cdir)
        for p in d._proposals:
            apply_proposal(cdir, p, backup=False)
        final = (cdir / rel).read_text()
        funcs = sorted({truth} | {s["suspect"] for s in d.steps})
        cls = O.classify_patch(template, cdir, ast_normal(final) == ast_normal(original), funcs, infos, orig_spectrum,
                               extra_repos=[work])
        shutil.rmtree(cdir)
        out.update({"class": cls["class"], "original_ok": cls.get("original_ok"), "patch_sha256": text_sha(final),
                    "diff": d.diff[:3000]})
    return out


def main():
    subject, n_keep, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    seed = int(next(a.split("=")[1] for a in sys.argv if a.startswith("--seed=")))
    skip = int(next((a.split("=")[1] for a in sys.argv if a.startswith("--skip=")), "0"))
    spec = S.SUBJECTS[subject]
    runner = SafeTestRunner(timeout_seconds=60)
    with tempfile.TemporaryDirectory(prefix="dev15_cal_") as td:
        td = Path(td)
        template = S.make_template(subject, td)
        base_run = runner.run_pytest(template, spec["tests"])
        assert base_run.classification == "passed", base_run.classification
        all_tests = sorted(base_run.outcome)
        und = CodeUnderstanding().analyze(template)
        infos = {f.qname: f for f in und.functions}
        ranges = {}
        for f in und.functions:
            ranges.setdefault(f.path, []).append((f.qname, f.line, f.end_line))
        orig_spectrum = collect_spectrum(template, spec["tests"], runner)
        pool = []
        for rel in spec["files"]:
            src = (template / rel).read_text()
            for site in enumerate_sites(src, rel, ranges.get(rel, [])):
                for opt in site.options:
                    pool.append((rel, site, opt))
        random.Random(seed).shuffle(pool)
        kept, idx = 0, skip
        writer = ChainedWriter(out, manifest("dev15_calibration", subject, spec, template,
                                             {"seed": seed, "skip": skip, "n_keep": n_keep, "budget": BUDGET}))
        for rel, site, opt in pool[skip:]:
            if kept >= n_keep:
                break
            idx += 1
            original = (template / rel).read_text()
            mutated = apply_site(original, site, opt)
            try:
                compile(mutated, rel, "exec")
            except SyntaxError:
                continue
            work = td / "work"
            if work.exists():
                shutil.rmtree(work)
            shutil.copytree(template, work)
            (work / rel).write_text(mutated)
            run = runner.run_pytest(work, spec["tests"])
            if run.classification != "tests_failed" or not run.failed_ids:
                continue
            others = [t for t in all_tests if t not in run.failed_ids]
            random.Random(seed + idx).shuffle(others)
            suites = {"half": sorted(run.failed_ids + others[: len(others) // 2]), "weak": sorted(run.failed_ids)}
            rec = {"subject": subject, "file": rel, "line": site.line, "kind": site.kind, "original": site.original,
                   "option": opt, "truth": site.function, "abs_index": idx, "failing": len(run.failed_ids)}
            for strength, suite in suites.items():
                rec[strength] = {mode: judged_workflow(work, suite, runner, template, rel, original, site.function, infos,
                                                       orig_spectrum, td, mode == "dev15") for mode in ("dev15", "dev14")}
            writer.append(rec)
            kept += 1
            print(json.dumps({"subject": subject, "kept": kept, "idx": idx,
                              **{f"{s}_{m}": rec[s][m].get("class", rec[s][m]["status"]) for s in suites for m in ("dev15", "dev14")}}),
                  flush=True)
        print(json.dumps({"subject": subject, "kept": kept, "next_skip": idx, "head": writer.head}))


if __name__ == "__main__":
    main()
