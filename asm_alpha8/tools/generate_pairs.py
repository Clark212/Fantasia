"""DEV16 bug generator: runs on YOUR computer, talks to a local Ollama model, writes candidate bug pairs to a file.

What it does
  1. Reads tools/dev16_subjects.json (made by ASM: which open-source projects, which functions their tests execute).
  2. Downloads each project's source archive from PyPI and checks its SHA-256 against the manifest.
  3. For each listed function, asks the model to introduce ONE realistic bug of a given kind into the correct function.
     The ORIGINAL function is the fix, so every pair has a known-correct fix by construction.
  4. Checks the reply locally (valid Python, same function name and signature, really changed, small) and appends one
     JSON line per pair to the output file, with full provenance (model, model digest, prompt hash, seed, time).

What it does NOT do: it never runs any downloaded code or tests. Nothing it produces is trusted: ASM re-checks every pair
in its sandbox (the buggy version must make the project's tests fail) before learning from it.
Standard library only. Python 3.9+. Works on Windows, macOS and Linux.

Usage (see tools/README_DEV16_DATA.md):
  ollama pull qwen2.5-coder:7b
  python tools/generate_pairs.py --model qwen2.5-coder:7b --out pairs.jsonl
  python tools/generate_pairs.py --model qwen2.5-coder:7b --out pairs.jsonl --limit 20     # quick test first
The run can be stopped at any time (Ctrl+C) and resumed with the same command: finished pairs are skipped.
"""
from __future__ import annotations

import argparse
import ast
import difflib
import hashlib
import io
import json
import random
import re
import sys
import tarfile
import textwrap
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

PROMPT_VERSION = "dev16-bug-v1"
# Kinds of bug, written to resemble what developers actually fix (from reading the BugsInPy fixes in DEV15).
BUG_KINDS = [
    "the wrong variable is used where another variable that is in scope was intended",
    "an off-by-one error in a comparison, an index, a slice or a range",
    "a missing check for None or for an empty value before it is used",
    "a condition has a missing clause, an extra clause, or the wrong boolean operator (and/or)",
    "a comparison uses the wrong operator",
    "an edge case that should be handled (by a guard or an exception handler) is no longer handled",
    "a wrong value is returned on one of the paths through the function",
    "a string literal, format string or regular expression has a small mistake",
    "a variable was only partly renamed, so one use refers to a different, similar name",
    "a call receives the wrong argument, or its arguments are in the wrong order",
    "the wrong attribute, method or dictionary key is used",
    "an arithmetic mistake: a wrong operator or a wrong constant",
]
PROMPT = """You are helping to build a dataset of realistic software bugs for research on automatic program repair.
Below is a correct Python function from the open-source project "{project}".

Introduce exactly ONE realistic bug of this kind: {kind}.

Rules:
- Keep the function name, its parameters, its docstring and its formatting.
- Change as few lines as possible (one to three lines).
- The result must still be valid Python.
- Do not add comments and do not mention the bug anywhere.
- Reply with only the complete modified function, in one ```python code block.

```python
{source}
```"""


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def http_json(url: str, payload: dict | None = None, timeout: float = 600.0) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_sdist(subject: dict, cache: Path) -> Path:
    """Download (once) and unpack the project's sdist; refuse it if its SHA-256 differs from the manifest."""
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / subject["sdist_filename"]
    if not archive.exists():
        meta = http_json(f"https://pypi.org/pypi/{subject['pypi_name']}/{subject['version']}/json", timeout=60)
        url = next(u["url"] for u in meta["urls"] if u["filename"] == subject["sdist_filename"])
        with urllib.request.urlopen(url, timeout=300) as r:
            archive.write_bytes(r.read())
    data = archive.read_bytes()
    if sha256_bytes(data) != subject["sdist_sha256"]:
        archive.unlink()
        raise SystemExit(f"{archive.name}: SHA-256 does not match the manifest; deleted it. Re-run to download again.")
    out = cache / (subject["name"] + "-src")
    if not out.exists():
        out.mkdir()
        if archive.name.endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                for m in z.namelist():
                    if m.startswith("/") or ".." in Path(m).parts:
                        raise SystemExit(f"unsafe path in archive: {m}")
                z.extractall(out)
        else:
            with tarfile.open(fileobj=io.BytesIO(data)) as t:
                for m in t.getmembers():
                    if m.name.startswith("/") or ".." in Path(m.name).parts or m.issym() or m.islnk():
                        raise SystemExit(f"unsafe path in archive: {m.name}")
                t.extractall(out)
    roots = [p for p in out.iterdir() if p.is_dir()]
    return roots[0] if len(roots) == 1 else out


def function_source(root: Path, fn: dict) -> tuple:
    """(dedented source, indentation) of the function at the manifest's lines; checks the file hash."""
    p = root / fn["sdist_path"]
    raw = p.read_bytes()
    if sha256_bytes(raw) != fn["file_sha256"]:
        raise SystemExit(f"{fn['sdist_path']}: file hash differs from the manifest")
    lines = raw.decode("utf-8").splitlines(keepends=True)[fn["line"] - 1: fn["end_line"]]
    text = "".join(lines)
    indent = re.match(r"[ \t]*", lines[0]).group(0) if lines else ""
    return textwrap.dedent(text), indent


def extract_code(reply: str) -> str | None:
    m = re.search(r"```(?:python|py)?\s*\n(.*?)```", reply, re.S)
    return m.group(1) if m else None


def _strip_docstring(fn: ast.AST) -> list:
    body = list(fn.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]
    return body


def check_reply(original: str, buggy: str, max_changed_lines: int = 6) -> str | None:
    """None if the reply is a usable buggy version of `original`; otherwise the reason it is rejected."""
    try:
        a, b = ast.parse(original), ast.parse(buggy)
    except SyntaxError:
        return "reply is not valid Python"
    fa = next((n for n in a.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))), None)
    fb = [n for n in b.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    if fa is None or len(fb) != 1 or len(b.body) != 1:
        return "reply must contain exactly one function and nothing else"
    fb = fb[0]
    if fb.name != fa.name or ast.dump(fb.args) != ast.dump(fa.args):
        return "function name or parameters changed"
    if ast.dump(ast.Module(_strip_docstring(fa), [])) == ast.dump(ast.Module(_strip_docstring(fb), [])):
        return "no change to the code"
    changed = [l for l in difflib.unified_diff(original.splitlines(), buggy.splitlines(), lineterm="", n=0)
               if l[:1] in "+-" and not l.startswith(("+++", "---"))]
    if len(changed) > 2 * max_changed_lines:
        return f"too many changed lines ({len(changed)} diff lines)"
    if any(re.search(r"#.*\b(bug|fix|wrong|error|mistake|introduc)", l, re.I) for l in changed if l.startswith("+")):
        return "the reply comments on the bug"
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True, help="Ollama model name, e.g. qwen2.5-coder:7b")
    ap.add_argument("--out", required=True, help="output JSONL file (appended to; resumable)")
    ap.add_argument("--manifest", default=str(Path(__file__).with_name("dev16_subjects.json")))
    ap.add_argument("--host", default="http://localhost:11434")
    ap.add_argument("--per-function", type=int, default=3, help="bugs requested per function (different kinds)")
    ap.add_argument("--limit", type=int, default=0, help="stop after this many accepted pairs (0 = no limit)")
    ap.add_argument("--seed", type=int, default=16)
    ap.add_argument("--temperature", type=float, default=0.7)
    ap.add_argument("--cache", default=str(Path.home() / ".asm_dev16_cache"))
    args = ap.parse_args()

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    try:
        tags = http_json(args.host + "/api/tags", timeout=10)
    except (urllib.error.URLError, OSError) as exc:
        raise SystemExit(f"cannot reach Ollama at {args.host} ({exc}). Is Ollama running?")
    model_info = next((m for m in tags.get("models", []) if m.get("name") == args.model or m.get("model") == args.model), None)
    if model_info is None:
        raise SystemExit(f"model {args.model!r} is not installed. Run: ollama pull {args.model}")
    out = Path(args.out)
    done = set()
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            try:
                done.add(json.loads(line)["id"])
            except (json.JSONDecodeError, KeyError):
                pass
    rng = random.Random(args.seed)
    jobs = []
    for subj in manifest["subjects"]:
        for fn in subj["functions"]:
            kinds = rng.sample(range(len(BUG_KINDS)), min(args.per_function, len(BUG_KINDS)))
            for k in kinds:
                jobs.append((subj, fn, k))
    rng.shuffle(jobs)  # interleave projects, so a short run still covers all of them
    roots = {}
    accepted = rejected = 0
    started = time.time()
    with out.open("a", encoding="utf-8") as f:
        for subj, fn, k in jobs:
            if args.limit and accepted >= args.limit:
                break
            jid = hashlib.sha256(f"{PROMPT_VERSION}|{args.model}|{args.seed}|{subj['name']}|{fn['qualname']}|{k}".encode()).hexdigest()[:24]
            if jid in done:
                continue
            if subj["name"] not in roots:
                roots[subj["name"]] = fetch_sdist(subj, Path(args.cache))
            src, indent = function_source(roots[subj["name"]], fn)
            prompt = PROMPT.format(project=subj["name"], kind=BUG_KINDS[k], source=src.rstrip())
            seed = int(jid[:8], 16) % 2**31
            t0 = time.time()
            try:
                resp = http_json(args.host + "/api/generate", {"model": args.model, "prompt": prompt, "stream": False,
                                                                "options": {"temperature": args.temperature, "seed": seed,
                                                                            "num_predict": 2048}})
            except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
                print(f"request failed ({exc}); stopping. Re-run the same command to resume.", file=sys.stderr)
                break
            code = extract_code(resp.get("response", ""))
            why = "no ```python code block in the reply" if code is None else check_reply(src, code)
            rec = {"id": jid, "prompt_version": PROMPT_VERSION, "subject": subj["name"], "version": subj["version"],
                   "sdist_sha256": subj["sdist_sha256"], "path": fn["path"], "qualname": fn["qualname"],
                   "line": fn["line"], "end_line": fn["end_line"], "file_sha256": fn["file_sha256"],
                   "original_sha256": sha256_bytes(src.encode()), "indent": indent, "bug_kind": BUG_KINDS[k],
                   "model": args.model, "model_digest": model_info.get("digest"), "temperature": args.temperature,
                   "seed": seed, "prompt_sha256": sha256_bytes(prompt.encode()),
                   "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   "seconds": round(time.time() - t0, 1), "accepted_locally": why is None, "reject_reason": why,
                   "buggy_function": code if why is None else None}
            f.write(json.dumps(rec, sort_keys=True) + "\n")
            f.flush()
            accepted += why is None
            rejected += why is not None
            if (accepted + rejected) % 10 == 0:
                rate = (accepted + rejected) / max(1e-9, time.time() - started) * 3600
                print(f"{accepted} accepted, {rejected} rejected ({rate:.0f} requests/hour)", flush=True)
    print(f"done: {accepted} accepted, {rejected} rejected this run; output: {out}")


if __name__ == "__main__":
    main()
