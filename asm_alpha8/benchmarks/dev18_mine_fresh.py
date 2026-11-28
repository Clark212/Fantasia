"""DEV18: mine fix commits from FRESH projects (never inspected before the DEV18 pre-registration), each with the
PROBLEM CONTEXT a repair would have: the literals of the test functions the commit added or changed (the analogue of
"the tests that fail"), and the module's own constants, names, attributes and exceptions (from the BEFORE version).

Selection criteria are DEV17's (`dev17_mine_history`: fix-like message, <= 2 non-test files, exactly one function changed,
<= 6 changed lines), applied unchanged. Output: hash-chained JSONL with a run manifest (repository URLs and HEADs).
Usage: python benchmarks/dev18_mine_fresh.py <work_dir> <out.jsonl> [repo ...]
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
import dev17_mine_history as M  # noqa: E402
from asm.coding.content import ProblemContext  # noqa: E402
from asm.coding.integrity import ChainedWriter, environment_provenance, file_sha256  # noqa: E402

FRESH = {"click": "https://github.com/pallets/click", "attrs": "https://github.com/python-attrs/attrs",
         "packaging": "https://github.com/pypa/packaging", "arrow": "https://github.com/arrow-py/arrow",
         "humanize": "https://github.com/python-humanize/humanize", "tabulate": "https://github.com/astanin/python-tabulate",
         "boltons": "https://github.com/mahmoud/boltons", "marshmallow": "https://github.com/marshmallow-code/marshmallow"}
PREREG = ROOT / "benchmarks" / "preregistration" / "dev18_study.md"


def changed_test_functions(before: str, after: str) -> list:
    fb, fa = M.functions(before), M.functions(after)
    return sorted(q.rsplit(".", 1)[-1] for q in fa if q not in fb or fb[q][1] != fa[q][1])


def mine(name: str, url: str, work: Path, w: ChainedWriter) -> dict:
    repo = work / name
    if not repo.exists():
        subprocess.run(["git", "clone", "-q", "--filter=blob:none", url, str(repo)], check=True, timeout=1800)
    counts = {"commits": 0, "fix_message": 0, "examples": 0, "with_test_context": 0}
    for line in M.git(repo, "log", "--no-merges", "--format=%H%x00%ct%x00%s").splitlines():
        sha, ts, msg = line.split("\x00", 2)
        counts["commits"] += 1
        if not M.FIX_RE.search(msg):
            continue
        counts["fix_message"] += 1
        files = [f for f in M.git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", sha).split() if f.endswith(".py")]
        src_files = [f for f in files if not M.is_test_path(f)]
        test_files = [f for f in files if M.is_test_path(f)]
        if not src_files or len(src_files) > 2:
            continue
        changed, bad = [], False
        for f in src_files:
            before, after = M.git(repo, "show", f"{sha}^:{f}"), M.git(repo, "show", f"{sha}:{f}")
            if not before or not after:
                bad = True
                break
            fb, fa = M.functions(before), M.functions(after)
            if set(fb) != set(fa):
                bad = True
                break
            for q in fb:
                if fb[q][1] != fa[q][1]:
                    changed.append((f, q, before, after, fb[q][0], fa[q][0]))
        if bad or len(changed) != 1:
            continue
        f, q, before, after, nb, na = changed[0]
        if any(q2.startswith(q + ".") for q2 in M.functions(before)):
            continue
        b_src, a_src = M.fn_source(before, nb), M.fn_source(after, na)
        import difflib
        diff = [l for l in difflib.unified_diff(b_src.splitlines(), a_src.splitlines(), lineterm="", n=0)
                if l[:1] in "+-" and not l.startswith(("+++", "---"))]
        if max(sum(1 for l in diff if l.startswith("-")), sum(1 for l in diff if l.startswith("+"))) > M.MAX_CHANGED_LINES:
            continue
        tests, names = [], []
        for tf in test_files:
            t_after = M.git(repo, "show", f"{sha}:{tf}")
            if not t_after:
                continue
            t_before = M.git(repo, "show", f"{sha}^:{tf}")
            tests.append(t_after)
            names += changed_test_functions(t_before, t_after)
        ctx = ProblemContext.build(before, tests, names or None, [])
        w.append({"id": f"{name}@{sha[:12]}:{q}", "repo": name, "commit": sha, "date": int(ts), "message": msg[:160],
                  "path": f, "qualname": q, "before": b_src, "after": a_src, "test_files": test_files,
                  "test_functions": names[:50], "context": ctx.to_dict()})
        counts["examples"] += 1
        counts["with_test_context"] += bool(tests)
    return counts


def main():
    work, out = Path(sys.argv[1]), Path(sys.argv[2])
    names = sys.argv[3:] or list(FRESH)
    work.mkdir(parents=True, exist_ok=True)
    w = ChainedWriter(out, {"run": "dev18_mine_fresh", "provenance": environment_provenance(),
                            "repos": {n: FRESH[n] for n in names},
                            "criteria": {"fix_re": M.FIX_RE.pattern, "max_changed_lines": M.MAX_CHANGED_LINES},
                            "preregistration_sha256": file_sha256(PREREG) if PREREG.exists() else None})
    for n in names:
        c = mine(n, FRESH[n], work, w)
        print(json.dumps({"repo": n, "head": M.git(work / n, "rev-parse", "HEAD").strip()[:12], **c}), flush=True)
    print(json.dumps({"head": w.head}))


if __name__ == "__main__":
    main()
