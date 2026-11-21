"""DEV17: mine REAL developer fixes from the git history of the training projects (observed evidence, no model).

A commit becomes a (before, after) example when ALL hold (criteria fixed in benchmarks/preregistration/dev17_study.md):
  - not a merge; its message matches FIX_RE (fix, bug, issue, error, correct, wrong, typo, handle, crash, regression,
    broken);
  - it changes at most 2 non-test Python files, and across them exactly ONE function's code changes (docstring-only
    changes do not count), with no function added or removed;
  - that function's change is at most MAX_CHANGED_LINES lines (diff of the function's source).
Output: a hash-chained JSONL with a run manifest; one record per example (repo, commit, date, message, path, qualname,
before/after function source with the def line's indentation removed).
Usage: python benchmarks/dev17_mine_history.py <work_dir> <out.jsonl> [repo ...]
"""
import ast
import difflib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from asm.coding.integrity import ChainedWriter, environment_provenance, file_sha256  # noqa: E402
from generate_pairs import strip_indent  # noqa: E402

REPOS = {"toolz": "https://github.com/pytoolz/toolz", "cachetools": "https://github.com/tkem/cachetools",
         "inflection": "https://github.com/jpvanhal/inflection", "semver": "https://github.com/python-semver/python-semver",
         "parse": "https://github.com/r1chardj0n3s/parse", "more_itertools": "https://github.com/more-itertools/more-itertools"}
FIX_RE = re.compile(r"\b(fix|fixes|fixed|fixing|bug|bugs|issue|error|correct|corrects|wrong|typo|handle|handles|crash|"
                    r"regression|broken)\b", re.I)
MAX_CHANGED_LINES = 6
PREREG = ROOT / "benchmarks" / "preregistration" / "dev17_study.md"


def git(repo: Path, *args) -> str:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=600).stdout


def is_test_path(p: str) -> bool:
    parts = p.split("/")
    return any(x in ("tests", "test", "testing", "docs", "doc") for x in parts[:-1]) or parts[-1].startswith("test") \
        or parts[-1] in ("setup.py", "conftest.py") or parts[-1].endswith("_test.py")


def functions(source: str) -> dict:
    """qualname -> (node, code-dump without docstring) for every function and method."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}
    out = {}

    def walk(body, prefix):
        for n in body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                q = prefix + n.name
                inner = list(n.body)
                if inner and isinstance(inner[0], ast.Expr) and isinstance(getattr(inner[0], "value", None), ast.Constant) \
                        and isinstance(inner[0].value.value, str):
                    inner = inner[1:]
                code = ast.dump(ast.Module(inner, [])) + ast.dump(n.args) + "".join(ast.dump(d) for d in n.decorator_list)
                out[q] = (n, code)
                walk(n.body, q + ".")
            elif isinstance(n, ast.ClassDef):
                walk(n.body, prefix + n.name + ".")
    walk(tree.body, "")
    return out


def fn_source(source: str, node) -> str:
    lines = source.splitlines(keepends=True)
    first = min([node.lineno] + [d.lineno for d in node.decorator_list])
    text = "".join(lines[first - 1: node.end_lineno])
    return strip_indent(text)


def mine(name: str, url: str, work: Path, w: ChainedWriter) -> dict:
    repo = work / name
    if not repo.exists():
        subprocess.run(["git", "clone", "-q", "--filter=blob:none", url, str(repo)], check=True, timeout=900)
    counts = {"commits": 0, "fix_message": 0, "examples": 0}
    log = git(repo, "log", "--no-merges", "--format=%H%x00%ct%x00%s")
    for line in log.splitlines():
        sha, ts, msg = line.split("\x00", 2)
        counts["commits"] += 1
        if not FIX_RE.search(msg):
            continue
        counts["fix_message"] += 1
        files = [f for f in git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", sha).split() if f.endswith(".py")]
        src_files = [f for f in files if not is_test_path(f)]
        if not src_files or len(src_files) > 2:
            continue
        changed = []
        bad = False
        for f in src_files:
            before = git(repo, "show", f"{sha}^:{f}")
            after = git(repo, "show", f"{sha}:{f}")
            if not before or not after:
                bad = True
                break
            fb, fa = functions(before), functions(after)
            if set(fb) != set(fa):
                bad = True
                break
            for q in fb:
                if fb[q][1] != fa[q][1]:
                    changed.append((f, q, before, after, fb[q][0], fa[q][0]))
        if bad or len(changed) != 1:
            continue
        f, q, before, after, nb, na = changed[0]
        if any(q2.startswith(q + ".") for q2 in functions(before)):  # a function with nested functions: skip
            continue
        b_src, a_src = fn_source(before, nb), fn_source(after, na)
        diff = [l for l in difflib.unified_diff(b_src.splitlines(), a_src.splitlines(), lineterm="", n=0)
                if l[:1] in "+-" and not l.startswith(("+++", "---"))]
        n_changed = max(sum(1 for l in diff if l.startswith("-")), sum(1 for l in diff if l.startswith("+")))
        if n_changed > MAX_CHANGED_LINES:
            continue
        w.append({"id": f"{name}@{sha[:12]}:{q}", "repo": name, "commit": sha, "date": int(ts), "message": msg[:160],
                  "path": f, "qualname": q, "before": b_src, "after": a_src, "changed_lines": n_changed})
        counts["examples"] += 1
    return counts


def main():
    work, out = Path(sys.argv[1]), Path(sys.argv[2])
    names = sys.argv[3:] or list(REPOS)
    work.mkdir(parents=True, exist_ok=True)
    w = ChainedWriter(out, {"run": "dev17_mine_history", "provenance": environment_provenance(), "repos": {n: REPOS[n] for n in names},
                            "criteria": {"fix_re": FIX_RE.pattern, "max_changed_lines": MAX_CHANGED_LINES,
                                         "max_source_files": 2, "changed_functions": 1},
                            "preregistration_sha256": file_sha256(PREREG) if PREREG.exists() else None})
    for n in names:
        c = mine(n, REPOS[n], work, w)
        heads = git(work / n, "rev-parse", "HEAD").strip()
        print(json.dumps({"repo": n, "head": heads[:12], **c}), flush=True)
    print(json.dumps({"head": w.head}))


if __name__ == "__main__":
    main()
