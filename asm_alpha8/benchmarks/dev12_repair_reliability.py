"""DEV12 repair-reliability benchmark (fresh seed, stronger oracle).

For each seeded fault the repair workflow runs with held-out tests as before, and every accepted patch is judged by a
DIFFERENTIAL oracle against the known-correct original program: the functions involved (the truly faulty one plus every
patched one) are executed in the sandbox on perturbed real test inputs, original vs patched. Classes:
  restored    the patched file is AST-equal to the original
  equivalent  not restored, but identical to the original on every compared input (>=3) for every checked function
  wrong       differs from the original on at least one input (a confirmed behavioural difference)
  unknown     differential execution was unavailable (non-literal arguments, methods, nondeterminism)
Also recorded: confidence label and flags, caveats, rank with/without DEV10 evidence, and for faults with several
passing candidates the oracle class of EVERY candidate, so selection policies can be compared offline.
Usage: python benchmarks/dev12_repair_reliability.py <subject> <n_try> <n_keep> <out.jsonl> --seed=N --skip=K
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
import dev11_seeded_faults as B  # noqa: E402
from asm.coding import SafeTestRunner  # noqa: E402
from asm.coding.counterexamples import _canon, perturb_inputs, run_versions  # noqa: E402
from asm.coding.faultloc import (FaultLocalizer, RepairWorkflow, apply_site, ast_normal, collect_spectrum,  # noqa: E402
                                 enumerate_sites)
from asm.coding.patches import apply_proposal  # noqa: E402
from asm.coding.semantics import SemanticAnalyzer  # noqa: E402
from asm.coding.understanding import CodeUnderstanding  # noqa: E402


def behaviour_diff(original_repo: Path, patched_repo: Path, finfo, calls: dict) -> dict:
    """Original vs patched behaviour of one function on perturbed real inputs."""
    local = finfo.qname[len(finfo.module) + 1:]
    if finfo.kind != "function" or "." in local:
        return {"status": "unavailable", "why": "method or nested function"}
    recorded = calls.get(f"{finfo.path}:{local}", [])
    inputs = perturb_inputs(recorded)
    if not inputs:
        return {"status": "unavailable", "why": "no literal-argument calls recorded"}
    an = SemanticAnalyzer(per_call_timeout=1.0, per_module_timeout=30)
    diags: list = []
    a = run_versions(an, original_repo, finfo.module, local, {"v": None}, inputs, diags)["v"]
    b = run_versions(an, patched_repo, finfo.module, local, {"v": None}, inputs, diags)["v"]
    if a is None or b is None:
        return {"status": "unavailable", "why": "could not execute"}
    idx = [i for i in sorted(set(a) & set(b)) if a[i]["det"] and b[i]["det"]]
    if len(idx) < 3:
        return {"status": "unavailable", "why": "too few deterministic inputs"}
    diff = [i for i in idx if _canon(a[i]) != _canon(b[i])]
    return {"status": "differs" if diff else "equal", "inputs": len(idx), "n_diff": len(diff),
            "example": repr(inputs[diff[0]]) if diff else None}


def classify_patch(original_repo: Path, patched_repo: Path, rel: str, restored: bool, funcs: list, infos: dict, calls: dict) -> dict:
    if restored:
        return {"class": "restored", "details": {}}
    details = {q: behaviour_diff(original_repo, patched_repo, infos[q], calls) for q in funcs if q in infos}
    if any(d["status"] == "differs" for d in details.values()):
        return {"class": "wrong", "details": details}
    if details and all(d["status"] == "equal" for d in details.values()):
        return {"class": "equivalent", "details": details}
    return {"class": "unknown", "details": details}


def main():
    subject, n_try, n_keep, out = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
    seed = int(next(a.split("=")[1] for a in sys.argv if a.startswith("--seed=")))
    skip = int(next((a.split("=")[1] for a in sys.argv if a.startswith("--skip=")), "0"))
    spec = B.SUBJECTS[subject]
    runner = SafeTestRunner(timeout_seconds=60)
    with tempfile.TemporaryDirectory(prefix="dev12_bench_") as td:
        td = Path(td)
        template = B.make_template(subject, td)
        base_run = runner.run_pytest(template, spec["tests"])
        assert base_run.classification == "passed"
        all_tests = sorted(base_run.outcome)
        und = CodeUnderstanding().analyze(template)
        infos = {f.qname: f for f in und.functions}
        ranges = {}
        for f in und.functions:
            ranges.setdefault(f.path, []).append((f.qname, f.line, f.end_line))
        truth_calls = collect_spectrum(template, spec["tests"], runner).calls  # inputs the ORIGINAL program's tests use
        pool = []
        for rel in spec["files"]:
            src = (template / rel).read_text()
            for site in enumerate_sites(src, rel, ranges.get(rel, [])):
                for opt in site.options:
                    pool.append((rel, site, opt))
        random.Random(seed).shuffle(pool)
        pool = pool[skip:]
        kept, tried = 0, 0
        with open(out, "a") as fh:
            for rel, site, opt in pool[:n_try]:
                if kept >= n_keep:
                    break
                tried += 1
                original = (template / rel).read_text()
                mutated = apply_site(original, site, opt)
                try:
                    compile(mutated, rel, "exec")
                except SyntaxError:
                    continue
                work = td / f"w{tried}"
                shutil.copytree(template, work)
                (work / rel).write_text(mutated)
                run = runner.run_pytest(work, spec["tests"])
                if run.classification != "tests_failed" or not run.failed_ids:
                    shutil.rmtree(work)
                    continue
                rec = {"subject": subject, "file": rel, "line": site.line, "kind": site.kind, "original": site.original,
                       "option": opt, "truth": site.function, "failing": run.failed_ids, "abs_index": skip + tried}
                # --- localization with and without DEV10 evidence
                with_sem = FaultLocalizer(runner).localize(work, spec["tests"])
                no_sem = FaultLocalizer(runner, use_semantic=False).localize(work, spec["tests"])
                rec["rank_with_dev10"] = B.rank_info(with_sem.suspects, site.function, lambda s: s.score)
                rec["rank_without_dev10"] = B.rank_info(no_sem.suspects, site.function, lambda s: s.score)
                rec["dev10_nonzero_suspects"] = sum(1 for s in with_sem.suspects if s.sources["semantic"] > 0)
                # --- repair
                rng = random.Random(seed + tried)
                others = [t for t in all_tests if t not in run.failed_ids]
                rng.shuffle(others)
                repair_set = sorted(run.failed_ids + others[: len(others) // 2])
                held_out = sorted(others[len(others) // 2:])
                t0 = time.monotonic()
                d = RepairWorkflow(runner, time_budget_seconds=90, max_suspects=3).run(work, repair_set)
                rec["repair_seconds"] = round(time.monotonic() - t0, 1)
                rec["status"] = d.status
                rec["n_steps"] = len(d.steps)
                if d.steps:
                    st = d.steps[0]
                    rec.update({"confidence": st["confidence"], "flags": st["confidence_basis"], "caveats": len(d.caveats),
                                "kind_of_step": st["kind"], "n_alternatives": len(st.get("alternatives_passing", [])),
                                "cx_available": bool(st["counterexamples"].get("available")),
                                "cx_agree": bool(st["counterexamples"].get("alternatives_agree_everywhere")),
                                "footprint": st["counterexamples"].get("footprint")})
                if d.status == "resolved" and d.steps:
                    fixed = td / f"fixed{tried}"
                    shutil.copytree(work, fixed)
                    for p in d._proposals:
                        apply_proposal(fixed, p, backup=False)
                    restored = ast_normal((fixed / rel).read_text()) == ast_normal(original)
                    funcs = sorted({site.function} | {s["suspect"] for s in d.steps})
                    cls = classify_patch(template, fixed, rel, restored, funcs, infos, truth_calls)
                    rec["oracle"] = cls["class"]
                    rec["oracle_details"] = {q: v["status"] for q, v in cls["details"].items()}
                    held = runner.run_pytest(fixed, held_out) if held_out else None
                    rec["held_out_passed"] = (held.classification == "passed") if held else None
                    # --- selection-policy data: oracle class of every candidate that passed in the first step
                    if d._step_candidates and len(d._step_candidates[0]) > 1:
                        cands = []
                        for name, prop in d._step_candidates[0]:
                            cdir = td / f"cand{tried}"
                            if cdir.exists():
                                shutil.rmtree(cdir)
                            shutil.copytree(work, cdir)
                            apply_proposal(cdir, prop, backup=False)
                            r2 = ast_normal((cdir / rel).read_text()) == ast_normal(original)
                            c2 = classify_patch(template, cdir, rel, r2, [site.function], infos, truth_calls)
                            cands.append({"name": name, "class": c2["class"],
                                          "footprint": (st["counterexamples"].get("footprint") or {}).get(name)})
                            shutil.rmtree(cdir)
                        rec["candidates"] = cands
                    shutil.rmtree(fixed, ignore_errors=True)
                fh.write(json.dumps(rec) + "\n")
                fh.flush()
                kept += 1
                shutil.rmtree(work, ignore_errors=True)
        print(json.dumps({"subject": subject, "tried": tried, "kept": kept}))


if __name__ == "__main__":
    main()
