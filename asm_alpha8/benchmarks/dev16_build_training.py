"""DEV16: turn VERIFIED bug pairs into training data for learned candidate ranking, plus fix-pattern records.

For each `status == "verified"` record of dev16_verify_pairs.py:
  1. rebuild the buggy project and collect ASM's spectrum on the project's tests (the same localization the workflow uses);
  2. for the top suspects, generate exactly the candidate lists the workflow would try (phase 1: DEV14 templates;
     phase 2: DEV15 families), in the workflow's order;
  3. label every candidate: 1 iff it reproduces the original (correct) file, AST-equal. No tests are run for labels:
     the original is the fix by construction, and AST equality is exact.
  4. record the pair's fix signature (patterns.edit_signature) and whether the fix is in ASM's repair space at all.
Output (hash-chained): one record per pair with its candidate rows. Rows carry the subject so training can hold whole
projects out. Usage: python benchmarks/dev16_build_training.py <verified.jsonl> <out.jsonl> [--suspects=3]
"""
import json
import shutil
import sys
import tempfile
import textwrap
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
import dev16_subjects as S  # noqa: E402
from dev16_verify_pairs import build_buggy  # noqa: E402
from asm.coding import SafeTestRunner  # noqa: E402
from asm.coding.faultloc import (FaultLocalizer, _ranking_context, ast_normal, collect_spectrum, generate_candidates,  # noqa: E402
                                 reconcile_spectrum)
from asm.coding.integrity import ChainedWriter, code_hash, environment_provenance, file_sha256, read_records  # noqa: E402
from asm.coding.learned import candidate_features  # noqa: E402
from asm.coding.patterns import edit_signature, in_repair_space, signature_key  # noqa: E402
from asm.coding.repair_ops import family_of  # noqa: E402
from asm.coding.understanding import CodeUnderstanding  # noqa: E402


def main():
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    n_sus = int(next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--suspects=")), "3"))
    _, recs = read_records(src)
    verified = [r for r in recs if r.get("status") == "verified"]
    w = ChainedWriter(out, {"run": "dev16_build_training", "provenance": environment_provenance(), "asm_coding_sha256": code_hash(),
                            "input_sha256": file_sha256(src), "verified_pairs": len(verified), "suspects": n_sus,
                            "label": "candidate AST-equal to the original file"})
    runner = SafeTestRunner(timeout_seconds=180)
    with tempfile.TemporaryDirectory(prefix="dev16_train_") as td:
        td = Path(td)
        templates = {}
        for k, r in enumerate(verified):
            name = r["subject"]
            if name not in templates:
                templates[name] = S.make_template(name, td / name)
            work = td / "work"
            if work.exists():
                shutil.rmtree(work)
            shutil.copytree(templates[name], work)
            original_file = (work / r["path"]).read_text(encoding="utf-8")
            buggy_file, orig_fn = build_buggy(original_file, r)
            (work / r["path"]).write_text(buggy_file, encoding="utf-8")
            target = ast_normal(original_file)
            t0 = time.monotonic()
            suite = S.SUBJECTS[name]["tests"]
            spectrum = collect_spectrum(work, suite, runner)
            plain = runner.run_pytest(work, suite)
            reconcile_spectrum(spectrum, set(plain.failed_ids))
            rec = {"id": r["id"], "subject": name, "qualname": r["qualname"], "bug_kind": r.get("bug_kind"),
                   "generator": r.get("generator"), "model": r.get("model")}
            sig = edit_signature(textwrap.dedent(r["buggy_function"]), textwrap.dedent(orig_fn))
            rec.update(signature=sig, signature_key=signature_key(sig))
            funcs = CodeUnderstanding().analyze(work).functions
            ranges_by_file: dict = {}
            for f in funcs:
                ranges_by_file.setdefault(f.path, []).append((f.qname, f.line, f.end_line))
            ok, fam, _ = in_repair_space(buggy_file, original_file, r["path"], r["qualname"], ranges_by_file.get(r["path"], []))
            rec.update(in_repair_space=ok, reachable_family=fam)
            if not spectrum.complete or not spectrum.failing:
                w.append(dict(rec, status="no_spectrum", reason=spectrum.incomplete_reason))
                continue
            loc = FaultLocalizer(runner, use_semantic=False).localize(work, suite, spectrum=spectrum)
            suspects = [s for s in loc.suspects if s.score > 0][:n_sus]
            truth_rank = next((i for i, s in enumerate(loc.suspects, 1) if s.qname == r["qualname"]), None)
            rows, true_pos = [], None
            for rank, sus in enumerate(suspects, 1):
                source = (work / sus.path).read_text(encoding="utf-8")
                for phase in (1, 2):
                    cands = generate_candidates(source, sus.path, sus, ranges_by_file.get(sus.path, []), loc.line_scores,
                                                extended=(phase == 2), failure_texts=list(spectrum.failures.values()))
                    if phase == 2:
                        cands = [c for c in cands if family_of(c.reason) != "single_site"]
                    ctx = _ranking_context(spectrum, sus, rank, phase)
                    for pos, c in enumerate(cands):
                        label = int(sus.path == r["path"] and ast_normal(c.replacement) == target)
                        if label and true_pos is None:
                            true_pos = {"suspect_rank": rank, "phase": phase, "position": pos, "phase_size": len(cands)}
                        feats = candidate_features(c.meta, dict(ctx, position=pos, n_candidates=len(cands)))
                        feats["traceback_lines"] = None
                        rows.append({"suspect": sus.qname, "suspect_rank": rank, "phase": phase, "position": pos,
                                     "label": label, "features": {k: v for k, v in feats.items() if v is not None}})
            w.append(dict(rec, status="ok", truth_rank=truth_rank, true_candidate=true_pos, n_rows=len(rows), rows=rows,
                          seconds=round(time.monotonic() - t0, 1)))
            if (k + 1) % 10 == 0:
                print(json.dumps({"pairs": k + 1}), flush=True)
    print(json.dumps({"done": len(verified), "head": w.head}))


if __name__ == "__main__":
    main()
