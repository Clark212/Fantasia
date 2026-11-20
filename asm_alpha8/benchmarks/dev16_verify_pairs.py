"""DEV16: verify generated bug pairs by EXECUTION in ASM's sandbox, before anything learns from them.

Input: the JSONL written by tools/generate_pairs.py on the user's computer (or by the non-LLM stand-in generator used
for the pipeline dry run). For each record that the generator accepted locally:
  1. the project template is rebuilt from the same sdist (SHA-256 checked) and the target file must have the recorded
     SHA-256; the original function text must hash to `original_sha256` (so the "fix" really is the shipped code);
  2. the buggy function replaces the original at the recorded lines;
  3. rejected without running anything if it is not valid Python, equals the original, or introduces a new risky
     construct (process, network, file deletion, dynamic code; `sandbox.new_risks`);
  4. the project's tests run (plain, sandboxed). VERIFIED iff at least one test that passes on the original fails on the
     buggy version, and nothing fails to collect.
Output: a hash-chained JSONL (`ChainedWriter`) with a run manifest, one record per input: status, newly failing tests,
and the full buggy file hash. Only `status == "verified"` records may train anything.
Usage: python benchmarks/dev16_verify_pairs.py <pairs.jsonl> <out.jsonl> [--limit=N]
"""
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
import dev16_subjects as S  # noqa: E402
from asm.coding import SafeTestRunner  # noqa: E402
from asm.coding.integrity import ChainedWriter, code_hash, environment_provenance, file_sha256  # noqa: E402
from asm.coding.sandbox import new_risks  # noqa: E402

PREREG = ROOT / "benchmarks" / "preregistration" / "dev16_study.md"


def build_buggy(original_file: str, rec: dict) -> tuple:
    """(buggy file text, original function text) with the buggy function placed at the recorded lines/indent."""
    lines = original_file.splitlines(keepends=True)
    orig_fn = "".join(lines[rec["line"] - 1: rec["end_line"]])
    import textwrap
    body = textwrap.dedent(rec["buggy_function"]).rstrip("\n") + "\n"
    placed = "".join((rec["indent"] + ln if ln.strip() else ln) for ln in body.splitlines(keepends=True))
    return "".join(lines[: rec["line"] - 1]) + placed + "".join(lines[rec["end_line"]:]), orig_fn


def main():
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    limit = int(next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--limit=")), "0"))
    records = [json.loads(l) for l in src.read_text(encoding="utf-8").splitlines() if l.strip()]
    w = ChainedWriter(out, {"run": "dev16_verify_pairs", "provenance": environment_provenance(),
                            "asm_coding_sha256": code_hash(), "input_sha256": file_sha256(src), "input_records": len(records),
                            "preregistration_sha256": file_sha256(PREREG) if PREREG.exists() else None,
                            "criterion": "a test passing on the original fails on the buggy version; no collection errors"})
    runner = SafeTestRunner(timeout_seconds=180)
    with tempfile.TemporaryDirectory(prefix="dev16_verify_") as td:
        td = Path(td)
        templates, baselines = {}, {}
        done = 0
        for rec in records:
            if limit and done >= limit:
                break
            base = {"id": rec.get("id"), "subject": rec.get("subject"), "qualname": rec.get("qualname"),
                    "bug_kind": rec.get("bug_kind"), "model": rec.get("model"), "model_digest": rec.get("model_digest"),
                    "prompt_sha256": rec.get("prompt_sha256"), "generator": rec.get("generator", "ollama")}
            if not rec.get("accepted_locally"):
                w.append(dict(base, status="rejected_by_generator", why=rec.get("reject_reason")))
                continue
            name = rec["subject"]
            if name not in S.SUBJECTS or name not in S.TRAINING:
                w.append(dict(base, status="unknown_subject"))
                continue
            if file_sha256(S.sdist_file(name)) != rec["sdist_sha256"]:
                w.append(dict(base, status="sdist_mismatch"))
                continue
            if name not in templates:
                templates[name] = S.make_template(name, td / name)
                t0 = time.monotonic()
                run = runner.run_pytest(templates[name], S.SUBJECTS[name]["tests"])
                baselines[name] = {"failed": set(run.failed_ids), "passed": {t for t, o in run.outcome.items() if o == "passed"},
                                   "seconds": round(time.monotonic() - t0, 1)}
            tpl = templates[name]
            target = tpl / rec["path"]
            if file_sha256(target) != rec["file_sha256"]:
                w.append(dict(base, status="file_mismatch"))
                continue
            original_file = target.read_text(encoding="utf-8")
            buggy_file, orig_fn = build_buggy(original_file, rec)
            import hashlib
            import textwrap
            if hashlib.sha256(textwrap.dedent(orig_fn).encode()).hexdigest() != rec["original_sha256"]:
                w.append(dict(base, status="original_mismatch"))
                continue
            try:
                compile(buggy_file, rec["path"], "exec")
            except SyntaxError as exc:
                w.append(dict(base, status="invalid_python", why=str(exc)[:120]))
                continue
            import ast
            if ast.dump(ast.parse(buggy_file)) == ast.dump(ast.parse(original_file)):
                w.append(dict(base, status="identical_to_original"))
                continue
            risks = new_risks(original_file, buggy_file)
            if risks:
                w.append(dict(base, status="rejected_new_risk", risks=risks))
                continue
            work = td / "work"
            if work.exists():
                shutil.rmtree(work)
            shutil.copytree(tpl, work)
            (work / rec["path"]).write_text(buggy_file, encoding="utf-8")
            t0 = time.monotonic()
            run = runner.run_pytest(work, S.SUBJECTS[name]["tests"])
            newly = sorted(set(run.failed_ids) - baselines[name]["failed"])
            caught = sorted(t for t in newly if t in baselines[name]["passed"])
            if run.classification in ("collection_error", "usage_error", "internal_error", "startup_error"):
                status = f"not_runnable({run.classification})"
            elif caught:
                status = "verified"
            elif run.timed_out:
                status = "timeout"
            else:
                status = "not_caught_by_tests"
            w.append(dict(base, status=status, failing_tests=caught[:50], n_failing=len(caught), path=rec["path"],
                          line=rec["line"], end_line=rec["end_line"], buggy_file_sha256=hashlib.sha256(buggy_file.encode()).hexdigest(),
                          buggy_function=rec["buggy_function"], indent=rec["indent"], file_sha256=rec["file_sha256"],
                          seconds=round(time.monotonic() - t0, 1)))
            done += 1
            if done % 25 == 0:
                print(json.dumps({"checked": done, "head": w.head[:12]}), flush=True)
    print(json.dumps({"done": done, "head": w.head}))


if __name__ == "__main__":
    main()
