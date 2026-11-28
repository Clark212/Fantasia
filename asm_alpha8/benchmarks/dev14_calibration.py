"""DEV14 calibration benchmark (derived from dev13_calibration.py: DEV14 oracle with generated inputs, hash-chained
output with a run manifest, content hash of every judged patch, inflection subject).

Original DEV13 description: calibration benchmark with DELIBERATELY INCORRECT repairs.

Each seeded fault (detected by the subject's full test suite) is repaired under two test-suite strengths:
  half  the failing tests + a random half of the passing tests (realistic)
  weak  the failing tests ONLY (deliberately under-specified, so incorrect patches pass and must be caught by flags)
For each strength we record:
  A. every PLAUSIBLE patch: each single-site edit in the explored suspects that passes that suite, labelled by the
     differential oracle against the known-correct original program (restored | equivalent | wrong | unknown) and given
     the flags/label the workflow rules would assign (a re-derivation of the rules, documented below);
  B. the REAL shipped workflow (RepairWorkflow defaults) on that suite: its status, chosen patch, label, flags, and the
     oracle class of the patch it chose.
Flag re-derivation (mirrors faultloc.RepairWorkflow): tied_localization (another suspect with an exactly equal score);
competing_patches_in_other_functions (a different tied function also has a passing patch); behaviour_unverified
(verification unavailable); behaviour_changed_where_tests_passed; alternatives_disagree / underdetermined (other passing
edits in the same function that behave differently / cannot be compared). Label: low if >=2 flags, medium if 1, else high.
Usage: python benchmarks/dev13_calibration.py <subject> <n_keep> <out.jsonl> --seed=N [--skip=K] [--no-workflow]
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
import dev14_oracle as O  # noqa: E402
import dev14_subjects as S  # noqa: E402
from dev14_bench import manifest, text_sha  # noqa: E402
from asm.coding.integrity import ChainedWriter  # noqa: E402
from asm.coding import SafeTestRunner  # noqa: E402
from asm.coding.faultloc import (FaultLocalizer, RepairWorkflow, apply_site, reconcile_spectrum, ast_normal, collect_spectrum,  # noqa: E402
                                 enumerate_sites, generate_candidates)
from asm.coding.patches import apply_proposal  # noqa: E402
from asm.coding.understanding import CodeUnderstanding  # noqa: E402
from asm.coding.verification import verify_patch  # noqa: E402

PER_SUSPECT = 20
MAX_EXPLORED = 8
GROUP_CAP = 6
STRENGTH_BUDGET = 150.0


def rank_info(suspects, qname):
    scores = {s.qname: s.score for s in suspects}
    if qname not in scores or scores[qname] <= 0:
        return None
    better = sum(1 for v in scores.values() if v > scores[qname])
    tied = sum(1 for q, v in scores.items() if v == scores[qname] and q != qname)
    return [better + 1, better + 1 + tied]


def classify(template, work, prop_list, rel, original, funcs_to_check, infos, orig_spectrum, td, tag):
    cdir = td / f"cls_{tag}"
    if cdir.exists():
        shutil.rmtree(cdir)
    shutil.copytree(work, cdir)
    for p in prop_list:
        apply_proposal(cdir, p, backup=False)
    final = (cdir / rel).read_text()
    restored = ast_normal(final) == ast_normal(original)
    out = O.classify_patch(template, cdir, restored, funcs_to_check, infos, orig_spectrum)
    out["patch_sha256"] = text_sha(final)
    shutil.rmtree(cdir)
    return out


def plausible_patches(work, suite, runner, wf, template, rel, original, truth, infos, orig_spectrum, td):
    t0 = time.monotonic()
    spectrum = collect_spectrum(work, suite, runner)
    reconcile_spectrum(spectrum, set(runner.run_pytest(work, suite).failed_ids))  # same rule as the workflow
    if not spectrum.complete or not spectrum.failing:
        return {"skipped": spectrum.incomplete_reason or "no failing tests in this suite"}
    loc = FaultLocalizer(runner, use_semantic=False).localize(work, suite, spectrum=spectrum)
    scored = [s for s in loc.suspects if s.score > 0]
    explore = scored[:3]
    for s in scored[3:]:  # include functions tied with an explored suspect (the workflow explores tied functions too)
        if len(explore) >= MAX_EXPLORED:
            break
        if any(s.score == e.score for e in explore):
            explore.append(s)
    finfos = {f.qname: f for f in CodeUnderstanding().analyze(work).functions}
    ranges = {}
    for f in finfos.values():
        ranges.setdefault(f.path, []).append((f.qname, f.line, f.end_line))
    groups, evaluated = {}, 0
    for sus in explore:
        for c in generate_candidates((work / sus.path).read_text(), sus.path, sus, ranges[sus.path], loc.line_scores)[:PER_SUSPECT]:
            if time.monotonic() - t0 > STRENGTH_BUDGET:
                break
            evaluated += 1
            prop = wf._quick_pass(work, c, suite, spectrum.outcomes)
            if prop is not None:
                groups.setdefault(sus.qname, []).append((c, prop))
    score_of = {s.qname: s.score for s in loc.suspects}
    tied_of = {q: [x.qname for x in loc.suspects if x.score == score_of[q] and x.qname != q] for q in groups}
    patches = []
    for q, items in groups.items():
        items = items[:GROUP_CAP]
        for j, (c, prop) in enumerate(items):
            others = [(c2.reason, p2) for k, (c2, p2) in enumerate(items) if k != j]
            try:
                v = verify_patch(work, q, (c.reason, prop), others, spectrum, finfos)
            except Exception as exc:  # one bad function must not end the benchmark
                v = {"available": False, "reason": f"{type(exc).__name__}: {exc}"}
            flags = []
            if not v.get("available"):
                flags.append("behaviour_unverified")
            elif v.get("changed_on_passing_recorded", {}).get(c.reason):
                flags.append("behaviour_changed_where_tests_passed")
            if others:
                if v.get("available") and v.get("alternatives_agree_everywhere"):
                    pass
                elif v.get("available") and v.get("distinguishing"):
                    flags.append("alternatives_disagree")
                else:
                    flags.append("underdetermined")
            if any(t in groups for t in tied_of[q]):
                flags.append("competing_patches_in_other_functions")
            if tied_of[q]:
                flags.append("tied_localization")
            cls = classify(template, work, [prop], rel, original, sorted({truth, q}), infos, orig_spectrum, td, "p")
            patches.append({"suspect": q, "desc": c.reason, "class": cls["class"], "flags": flags,
                            "patch_sha256": cls["patch_sha256"], "original_ok": cls.get("original_ok"),
                            "label": "low" if len(flags) >= 2 else ("medium" if flags else "high"),
                            "verified": bool(v.get("available")), "group_size": len(items),
                            "oracle": {k: d["status"] for k, d in cls["details"].items()}})
    return {"rank": rank_info(loc.suspects, truth), "explored": [e.qname for e in explore], "evaluated": evaluated,
            "patches": patches, "seconds": round(time.monotonic() - t0, 1)}


def real_workflow(work, suite, runner, template, rel, original, truth, infos, orig_spectrum, td):
    t0 = time.monotonic()
    d = RepairWorkflow(runner, time_budget_seconds=150, max_suspects=3).run(work, suite)
    out = {"status": d.status, "seconds": round(time.monotonic() - t0, 1)}
    if d.steps:
        st = d.steps[0]
        out.update({"suspect": st["suspect"], "desc": st["description"], "label": st["confidence"],
                    "flags": st["confidence_basis"], "n_steps": len(d.steps)})
    if d.status == "resolved" and d.steps:
        funcs = sorted({truth} | {s["suspect"] for s in d.steps})
        cls = classify(template, work, d._proposals, rel, original, funcs, infos, orig_spectrum, td, "wf")
        out["class"] = cls["class"]
        out["patch_sha256"] = cls["patch_sha256"]
        out["original_ok"] = cls.get("original_ok")
    return out


def main():
    subject, n_keep, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    seed = int(next(a.split("=")[1] for a in sys.argv if a.startswith("--seed=")))
    skip = int(next((a.split("=")[1] for a in sys.argv if a.startswith("--skip=")), "0"))
    do_wf = "--no-workflow" not in sys.argv
    spec = S.SUBJECTS[subject]
    runner = SafeTestRunner(timeout_seconds=60)
    wf = RepairWorkflow(runner)
    with tempfile.TemporaryDirectory(prefix="dev13_cal_") as td:
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
        writer = ChainedWriter(out, manifest("dev14_calibration", subject, spec, template,
                                             {"seed": seed, "skip": skip, "n_keep": n_keep, "workflow": do_wf}))
        if True:
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
                    r = plausible_patches(work, suite, runner, wf, template, rel, original, site.function, infos,
                                          orig_spectrum, td)
                    if do_wf and "skipped" not in r:
                        r["workflow"] = real_workflow(work, suite, runner, template, rel, original, site.function, infos,
                                                      orig_spectrum, td)
                    rec[strength] = r
                writer.append(rec)
                kept += 1
        print(json.dumps({"subject": subject, "kept": kept, "next_skip": idx, "head": writer.head}))


if __name__ == "__main__":
    main()
