"""DEV32: mine FRESH real bugs, BugsInPy-style, from light pure-Python projects ASM has never run on, into the BugsInPy
corpus format, so that DEV14's envs and validate stages and DEV29's per-bug evaluation run on them unchanged.

A commit is a candidate bug when it is in the window, is not a merge, has a fix-like subject (DEV17's FIX_RE), and
  - modifies 1-2 Python files outside the tests (none added or deleted), at most MAX_LINES changed lines in all: the
    developer's fix (bug_patch.txt);
  - adds or modifies test modules (test_*.py, *_test.py), and changes nothing else that ASM counts as test code
    (faultloc.is_test_path: no conftest.py, helpers or data files);
  - changes nothing else but documentation (docs/, *.md, *.rst, changelog and news files); setup.py and other
    packaging or task files count as something else;
  - adds or changes test functions in those modules: the bug's tests (run_test.sh);
  - does not repeat an earlier candidate's fix line for line (a backport or cherry-pick: the first is kept).
The buggy version is the parent with the fixed test modules (BugsInPy semantics, dev14_realbugs.checkout). Dependencies:
the project's declared names (projects.json) with pytest and setuptools, resolved by uv for Python 3.11 as they were the
day after the fix (--exclude-newer), so each bug gets the versions of its time (requirements.txt); a name with no release
by then is dropped and recorded. A project gives at most PER_PROJECT bugs: a seeded random sample of its candidates.
VALID (the bug's tests fail on buggy and pass on fixed) is decided by dev14_realbugs.py validate, as for BugsInPy.
Usage: python benchmarks/dev32_mine_bugs.py <work_dir> <projects.json> [project ...]
       (projects.json: {"name": {"url": ..., "deps": [...]}}; the fresh list is the pre-registration's)
"""
import datetime
import json
import random
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
import dev17_mine_history as M  # noqa: E402
from asm.coding.faultloc import is_test_path  # noqa: E402
from asm.coding.integrity import ChainedWriter, environment_provenance, file_sha256  # noqa: E402

WINDOW = ("2023-01-01", "2026-10-31")
PER_PROJECT, MAX_LINES, SEED, PYTHON = 20, 20, 32, "3.11"
TEST_MODULE = re.compile(r"(^|/)(test_[^/]*|[^/]*_test)\.py$")
DOC = re.compile(r"(^|/)(docs?|changelog\.d|newsfragments|changes)/|\.(md|rst)$|^(CHANGES|CHANGELOG|HISTORY|NEWS|AUTHORS)[^/]*$", re.I)
PACKAGING = {"setup.py", "noxfile.py", "fabfile.py", "tasks.py", "conftest.py"}


def split_change(changes: list):
    """[(status, path)] -> (fix files, test modules), or None when the commit is not a candidate."""
    src, tests = [], []
    for status, path in changes:
        if is_test_path(path):
            if status == "D" or not TEST_MODULE.search(path) or path.endswith("conftest.py"):
                return None
            tests.append(path)
        elif DOC.search(path):
            continue
        elif status == "M" and path.endswith(".py") and path.rsplit("/", 1)[-1] not in PACKAGING:
            src.append(path)
        else:
            return None
    return (src, tests) if 1 <= len(src) <= 2 and tests else None


def changed_tests(before: str, after: str, path: str) -> list:
    """Node ids of the test functions `after` adds or changes (not nested in another function)."""
    fb, fa = M.functions(before), M.functions(after)
    return [f"{path}::{q.replace('.', '::')}" for q in sorted(fa) if q.rsplit(".", 1)[-1].startswith("test")
            and not any(q.startswith(p + ".") for p in fa) and (q not in fb or fb[q][1] != fa[q][1])]


def candidates(repo: Path) -> list:
    lo, hi = (int(datetime.datetime.fromisoformat(d).replace(tzinfo=datetime.timezone.utc).timestamp()) for d in WINDOW)
    out = []
    for line in M.git(repo, "log", "--no-merges", "--format=%H%x00%P%x00%ct%x00%s").splitlines():
        sha, parents, ts, subject = line.split("\x00", 3)
        if not (lo <= int(ts) <= hi and len(parents.split()) == 1 and M.FIX_RE.search(subject)):
            continue
        changes = [tuple(x.split("\t")[:2]) for x in M.git(repo, "diff-tree", "--no-commit-id", "--name-status", "-r", sha).splitlines()]
        split = split_change(changes)
        if split is None:
            continue
        src, tests = split
        stat = [x.split("\t") for x in M.git(repo, "diff", "--numstat", parents, sha, "--", *src).splitlines()]
        n = sum(int(a) + int(d) if a.isdigit() and d.isdigit() else MAX_LINES + 1 for a, d, _ in stat)
        if n > MAX_LINES:
            continue
        targets = [t for p in tests for t in changed_tests(M.git(repo, "show", f"{parents}:{p}"), M.git(repo, "show", f"{sha}:{p}"), p)]
        if targets:
            fix = tuple(x for x in M.git(repo, "diff", parents, sha, "--", *src).splitlines() if x[:1] in "+-" and x[:3] not in ("+++", "---"))
            out.append({"commit": sha, "parent": parents, "date": int(ts), "subject": subject[:160], "src": src, "tests": tests,
                        "targets": targets, "changed_lines": n, "fix": fix})
    seen, unique = set(), []
    for c in sorted(reversed(out), key=lambda c: c["date"]):  # the same fix twice (a backport, a cherry-pick): the first
        if c["fix"] not in seen:
            seen.add(c["fix"])
            unique.append(c)
        del c["fix"]
    return unique


def requirements(deps: list, date: int) -> tuple:
    """(pinned requirements as uv resolves them for the day after `date`, or None; the names dropped because they had no
    release yet then)."""
    day = (datetime.datetime.fromtimestamp(date, datetime.timezone.utc) + datetime.timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z")
    norm = lambda n: re.sub(r"[-_.]+", "-", re.split(r"[=<>!~;\[ ]", n, maxsplit=1)[0]).lower()  # noqa: E731
    deps, dropped = list(deps), []
    while True:
        p = subprocess.run(["uv", "pip", "compile", "-", "-q", "--no-header", "--no-annotate", "--python-version", PYTHON,
                            "--exclude-newer", day], input="\n".join(deps + ["pytest", "setuptools"]) + "\n",
                           capture_output=True, text=True, timeout=600)
        if p.returncode == 0:
            return p.stdout, dropped
        m = re.search(r"no versions of ([\w.-]+)", p.stderr)
        gone = [d for d in deps if m and norm(d) == norm(m.group(1))]
        if not gone:
            return None, dropped
        deps.remove(gone[0])
        dropped.append(gone[0])


def mine(work: Path, name: str, spec: dict, w: ChainedWriter) -> dict:
    repo = work / "repos" / name
    if not repo.exists():
        subprocess.run(["git", "clone", "-q", "--filter=blob:none", spec["url"], str(repo)], check=True, timeout=1800)
    found = candidates(repo)
    chosen = sorted(random.Random(f"{SEED}:{name}").sample(found, min(PER_PROJECT, len(found))), key=lambda c: c["date"])
    pdir = work / "corpus" / "projects" / name
    if pdir.exists():
        shutil.rmtree(pdir)
    (pdir / "bugs").mkdir(parents=True)
    (pdir / "project.info").write_text(f'github_url="{spec["url"]}"\n')
    kept = 0
    for c in chosen:
        reqs, dropped = requirements(spec["deps"], c["date"])
        rec = {"project": name, **c, "requirements_resolved": reqs is not None, "deps_dropped": dropped}
        if reqs is not None:
            kept += 1
            bug = pdir / "bugs" / str(kept)
            bug.mkdir()
            (bug / "bug.info").write_text(f'python_version="{PYTHON}"\nbuggy_commit_id="{c["parent"]}"\n'
                                          f'fixed_commit_id="{c["commit"]}"\ntest_file="{";".join(c["tests"])}"\n')
            (bug / "bug_patch.txt").write_text(M.git(repo, "diff", c["parent"], c["commit"], "--", *c["src"]))
            (bug / "run_test.sh").write_text("pytest " + " ".join(c["targets"]) + "\n")
            (bug / "requirements.txt").write_text(reqs)
            rec["bug"] = kept
        w.append(rec)
    return {"project": name, "url": spec["url"], "head": M.git(repo, "rev-parse", "HEAD").strip(), "candidates": len(found),
            "chosen": len(chosen), "bugs": kept}


def main():
    work, spec_file = Path(sys.argv[1]), Path(sys.argv[2])
    specs = json.loads(spec_file.read_text())
    names = sys.argv[3:] or list(specs)
    w = ChainedWriter(work / "mine.jsonl", {"run": "dev32_mine_bugs", "provenance": environment_provenance(), "window": WINDOW,
                                            "per_project": PER_PROJECT, "max_lines": MAX_LINES, "seed": SEED, "python": PYTHON,
                                            "projects": {n: specs[n] for n in names}, "projects_sha256": file_sha256(spec_file),
                                            "harness_sha256": file_sha256(Path(__file__)),
                                            "uv": subprocess.run(["uv", "--version"], capture_output=True, text=True).stdout.strip()})
    for n in names:
        summary = mine(work, n, specs[n], w)
        w.append({"summary": summary})
        print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
