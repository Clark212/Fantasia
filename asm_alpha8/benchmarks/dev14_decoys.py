"""DEV14 decoy benchmark (derived from dev13_decoys.py: DEV14 oracle, hash-chained output, patch content hashes,
inflection subject).

Original DEV13 description: decoy benchmark: DELIBERATELY INCORRECT repairs that still pass the repair tests.

Why: on toolz, even a weak suite (failing tests only) admitted no wrong single-site patch, so calibration had nothing
to detect. A decoy is constructed as: the TRUE fix (inverse of the injected fault) + ONE extra single-site edit elsewhere
in the faulty function ("fixes the bug and also changes something"). Only decoys that pass the repair suite are kept,
so every decoy is test-plausible; the differential oracle then says whether it is really wrong (the extra edit may be
benign). Correct controls: the true fix alone, and every single-site plausible patch from dev13_calibration.

Flags are computed with the same rules as dev13_calibration.plausible_patches. A decoy's "alternatives" are the
single-site plausible patches of the same function (what the workflow would also have found), so
alternatives_disagree fires when the decoy and a single-site fix behave differently somewhere.
Usage: python benchmarks/dev13_decoys.py <subject> <n_keep> <out.jsonl> --seed=N [--skip=K] [--per-fault=8]
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
import dev14_subjects as S  # noqa: E402
from dev14_calibration import classify  # noqa: E402
from dev14_bench import manifest  # noqa: E402
from asm.coding.integrity import ChainedWriter  # noqa: E402
from asm.coding import SafeTestRunner  # noqa: E402
from asm.coding.faultloc import (FaultLocalizer, RepairWorkflow, apply_site, collect_spectrum, reconcile_spectrum, enumerate_sites,  # noqa: E402
                                 generate_candidates)
from asm.coding.patches import PatchProposalBuilder  # noqa: E402
from asm.coding.research import Candidate  # noqa: E402
from asm.coding.understanding import CodeUnderstanding  # noqa: E402
from asm.coding.verification import verify_patch  # noqa: E402

FAULT_BUDGET = 200.0


def flags_for(work, q, name, prop, others, spectrum, finfos, tied):
    try:
        v = verify_patch(work, q, (name, prop), others, spectrum, finfos)
    except Exception as exc:
        v = {"available": False, "reason": f"{type(exc).__name__}: {exc}"}
    flags = []
    if not v.get("available"):
        flags.append("behaviour_unverified")
    elif v.get("changed_on_passing_recorded", {}).get(name):
        flags.append("behaviour_changed_where_tests_passed")
    if others:
        if v.get("available") and v.get("alternatives_agree_everywhere"):
            pass
        elif v.get("available") and v.get("distinguishing"):
            flags.append("alternatives_disagree")
        else:
            flags.append("underdetermined")
    if tied:
        flags.append("tied_localization")
    return flags, bool(v.get("available"))


def main():
    subject, n_keep, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    seed = int(next(a.split("=")[1] for a in sys.argv if a.startswith("--seed=")))
    skip = int(next((a.split("=")[1] for a in sys.argv if a.startswith("--skip=")), "0"))
    per_fault = int(next((a.split("=")[1] for a in sys.argv if a.startswith("--per-fault=")), "8"))
    spec = S.SUBJECTS[subject]
    runner = SafeTestRunner(timeout_seconds=60)
    wf = RepairWorkflow(runner)
    with tempfile.TemporaryDirectory(prefix="dev13_decoy_") as td:
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
        random.Random(seed).shuffle(pool)  # same seed and order as dev13_calibration: the same faults, in the same order
        kept, idx = 0, skip
        writer = ChainedWriter(out, manifest("dev14_decoys", subject, spec, template,
                                             {"seed": seed, "skip": skip, "n_keep": n_keep, "per_fault": per_fault}))
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
                t0 = time.monotonic()
                others = [t for t in all_tests if t not in run.failed_ids]
                random.Random(seed + idx).shuffle(others)
                suites = {"half": sorted(run.failed_ids + others[: len(others) // 2]), "weak": sorted(run.failed_ids)}
                rec = {"subject": subject, "file": rel, "line": site.line, "kind": site.kind, "truth": site.function,
                       "abs_index": idx}
                q = site.function
                # decoy material: every OTHER mutation site in the faulty function, applied on top of the true fix
                extra_sites = [s for s in enumerate_sites(original, rel, ranges[rel])
                               if s.function == q and not (s.start == site.start and s.end == site.end)]
                extra = [(s, o) for s in extra_sites for o in s.options]
                random.Random(seed * 7 + idx).shuffle(extra)
                for strength, suite in suites.items():
                    spectrum = collect_spectrum(work, suite, runner)
                    reconcile_spectrum(spectrum, set(runner.run_pytest(work, suite).failed_ids))  # same rule as the workflow
                    if not spectrum.complete or not spectrum.failing:
                        rec[strength] = {"skipped": spectrum.incomplete_reason or "no failing tests"}
                        continue
                    loc = FaultLocalizer(runner, use_semantic=False).localize(work, suite, spectrum=spectrum)
                    score_of = {s.qname: s.score for s in loc.suspects}
                    tied = [x.qname for x in loc.suspects if q in score_of and x.score == score_of[q] and x.qname != q]
                    finfos = {f.qname: f for f in CodeUnderstanding().analyze(work).functions}
                    wranges = {}
                    for f in finfos.values():
                        wranges.setdefault(f.path, []).append((f.qname, f.line, f.end_line))
                    sus = next((s for s in loc.suspects if s.qname == q), None)
                    singles = []
                    if sus is not None:
                        for c in generate_candidates(mutated, rel, sus, wranges[rel], loc.line_scores)[:20]:
                            p = wf._quick_pass(work, c, suite, spectrum.outcomes)
                            if p is not None:
                                singles.append((c.reason, p))
                    decoys, tried = [], 0
                    for s2, o2 in extra:
                        if len(decoys) >= per_fault or time.monotonic() - t0 > FAULT_BUDGET:
                            break
                        # the original program IS the true fix; a decoy is the original plus one extra single-site edit
                        text = apply_site(original, s2, o2)
                        try:
                            compile(text, rel, "exec")
                        except SyntaxError:
                            continue
                        tried += 1
                        cand = Candidate(rel, text, f"true fix + {s2.describe(o2)}")
                        p = wf._quick_pass(work, cand, suite, spectrum.outcomes)
                        if p is not None:
                            decoys.append((cand.reason, p))
                    true_fix = PatchProposalBuilder.from_replacement(work, rel, original, "true fix")
                    rows = []
                    for kind, items in (("true_fix", [("true fix", true_fix)]), ("single", singles), ("decoy", decoys)):
                        for name, prop in items:
                            alts = [(n, p) for n, p in singles if n != name]
                            fl, verified = flags_for(work, q, name, prop, alts, spectrum, finfos, tied)
                            cls = classify(template, work, [prop], rel, original, [q], infos, orig_spectrum, td, "d")
                            rows.append({"kind": kind, "desc": name, "class": cls["class"], "flags": fl,
                                         "patch_sha256": cls["patch_sha256"], "original_ok": cls.get("original_ok"),
                                         "label": "low" if len(fl) >= 2 else ("medium" if fl else "high"),
                                         "verified": verified})
                    rec[strength] = {"tried_decoys": tried, "rows": rows, "n_singles": len(singles), "tied": len(tied)}
                rec["seconds"] = round(time.monotonic() - t0, 1)
                writer.append(rec)
                kept += 1
        print(json.dumps({"subject": subject, "kept": kept, "next_skip": idx, "head": writer.head}))


if __name__ == "__main__":
    main()
