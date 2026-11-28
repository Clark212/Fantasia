"""DEV14 evaluation on REAL historical bugs from BugsInPy (https://github.com/soarsmu/BugsInPy).

Stages (each writes a hash-chained JSONL with a run manifest):
  prepare   clone each project (partial clone), install its dependency NAMES unpinned into a per-project directory
  validate  for every bug: materialize buggy and fixed versions (git archive), run the bug's failing test(s);
            VALID = fails on buggy AND passes on fixed under the current interpreter (BugsInPy's own criterion)
  evaluate  for valid bugs: localization rank of the developer-changed functions; repair workflow; the accepted patch
            (if any) judged against the DEVELOPER'S FIXED VERSION with the DEV14 oracle
Attrition (clone/dependency/collection failures, tests that do not reproduce on this interpreter) is recorded per bug.

Honest scope: BugsInPy targets Python 3.6-3.8 with pinned 2020-era dependencies; this run uses the current interpreter
and unpinned dependencies, so many bugs will not reproduce. Those are reported, not hidden.
Usage: python benchmarks/dev14_realbugs.py <stage> <work_dir> [--projects=a,b] [--limit=N]
"""
import json
import re
import shutil
import subprocess
import sys
import tarfile
import io
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from asm.coding import SafeTestRunner  # noqa: E402
from asm.coding.integrity import ChainedWriter, environment_provenance, file_sha256, read_records  # noqa: E402

PROJECTS = ["PySnooper", "thefuck", "tqdm", "cookiecutter", "httpie", "youtube-dl"]
SKIP_DEPS = re.compile(r"^(pytest.*|flake8|pycodestyle|pyflakes|mccabe|twine|tox|coverage|codecov|wheel|setuptools|pip|"
                       r"readme.renderer|pypandoc|pywin32.ctypes|win.unicode.console|keyring|bleach|docutils|pkginfo|"
                       r"requests.toolbelt|sphinx.*|black|mypy|isort|pylint|pre.commit|nose|py.cpuinfo|atomicwrites)$", re.I)


def info(path: Path) -> dict:
    out = {}
    for line in path.read_text().splitlines():
        m = re.match(r'^(\w+)\s*=\s*"(.*)"\s*$', line.strip())  # the corpus has "key =" and CRLF lines
        if m:
            out[m.group(1)] = m.group(2)
    return out


def requirement_lines(path: Path) -> list:
    """A bug's requirements.txt; in black, fastapi, luigi, sanic and scrapy they are UTF-16 with a byte-order mark."""
    data = path.read_bytes()
    return data.decode("utf-16" if data[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf-8").splitlines()


def git(args, cwd, timeout=600):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=timeout)


def corpus_dir(work: Path) -> Path:
    return work / "corpus" / "projects"


def materialize(repo: Path, commit: str, dest: Path) -> str | None:
    """Clean copy of a commit (no .git). Returns an error string or None."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    p = subprocess.run(["git", "archive", "--format=tar", commit], cwd=repo, capture_output=True, timeout=600)
    if p.returncode != 0:
        return p.stderr.decode(errors="replace")[-300:]
    with tarfile.open(fileobj=io.BytesIO(p.stdout)) as tf:
        tf.extractall(dest, filter="data")
    return None


def test_targets(bug_dir: Path) -> list:
    """Test node ids from run_test.sh ('pytest a::b c::d' or 'python -m pytest ...'; unittest forms are converted)."""
    ids = []
    for line in (bug_dir / "run_test.sh").read_text().splitlines():
        line = line.strip()
        m = re.search(r"(?:pytest|^tox)\s+(.*)$", line)  # cookiecutter's run_test.sh uses `tox <node ids>`
        if m:
            ids += [t for t in m.group(1).split() if not t.startswith("-")]
            continue
        m = re.search(r"unittest\s+(?:-q\s+)?([\w./]+)\.(\w+)\.(\w+)$", line)  # python -m unittest test.mod.Class.test
        if m:
            ids.append(m.group(1).replace(".", "/") + ".py::" + m.group(2) + "::" + m.group(3))
    return ids


def stage_prepare(work: Path, projects: list):
    w = ChainedWriter(work / "prepare.jsonl", {"run": "dev14_realbugs_prepare", "provenance": environment_provenance(),
                                              "projects": projects})
    for p in projects:
        pdir = corpus_dir(work) / p
        url = info(pdir / "project.info")["github_url"]
        repo = work / "repos" / p
        rec = {"project": p, "url": url}
        if not repo.exists():
            r = git(["clone", "-q", "--filter=blob:none", url, str(repo)], cwd=work, timeout=900)
            rec["clone"] = "ok" if r.returncode == 0 else f"failed: {r.stderr[-200:]}"
        else:
            rec["clone"] = "cached"
        names = set()
        for req in sorted(pdir.glob("bugs/*/requirements.txt")):
            for line in requirement_lines(req):
                line = line.strip()
                if not line or line.startswith(("-e", "#", "git+")):
                    continue
                name = re.split(r"[=<>!~;\[ ]", line, maxsplit=1)[0]
                if name and not SKIP_DEPS.match(name) and name.lower() != p.lower():
                    names.add(name)
        deps = work / "deps" / p
        deps.mkdir(parents=True, exist_ok=True)
        ok, failed = [], []
        for name in sorted(names):  # one at a time: one unbuildable package must not block the rest
            r = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check", "--no-deps",
                                "--target", str(deps), name], capture_output=True, text=True, timeout=600)
            (ok if r.returncode == 0 else failed).append(name)
        rec.update({"deps_requested": sorted(names), "deps_installed": ok, "deps_failed": failed})
        w.append(rec)
        print(json.dumps({k: rec[k] for k in ("project", "clone")} | {"deps_ok": len(ok), "deps_failed": failed}), flush=True)


def bug_dirs(work: Path, p: str, limit: int = 0) -> list:
    return sorted((corpus_dir(work) / p / "bugs").iterdir(), key=lambda d: int(d.name))[:limit or None]


def setup_pip_names(bug: Path) -> list:
    """`pip install X` lines from the bug's setup.sh (BugsInPy runs these before testing)."""
    f = bug / "setup.sh"
    if not f.exists():
        return []
    text = f.read_text().replace("python setup.py", "\npython setup.py")
    return [n for m in re.finditer(r"pip3?\s+install\s+([^\n]+)", text) for n in m.group(1).split()
            if not n.startswith("-") and not re.match(r"^(coverage|flake8|nose)$", n)]


def stage_envs(work: Path, projects: list, limit: int, python: str):
    """One virtualenv per distinct requirement set, on the oldest interpreter available here (BugsInPy wants 3.6-3.8;
    only 3.8 can be obtained), with the bug's PINNED requirements. Pins that do not install on 3.8 fall back to the
    unpinned name, and that is recorded."""
    w = ChainedWriter(work / "envs.jsonl", {"run": "dev14_realbugs_envs", "provenance": environment_provenance(),
                                           "python": python, "projects": projects, "limit": limit})
    import hashlib
    for p in projects:
        for bug in bug_dirs(work, p, limit):
            reqf = bug / "requirements.txt"
            reqs = [l.strip() for l in (requirement_lines(reqf) if reqf.exists() else [])
                    if l.strip() and not l.startswith(("#", "-e", "git+"))]
            reqs += setup_pip_names(bug)
            reqs = [r for r in reqs if re.split(r"[=<>!~;\[ ]", r, maxsplit=1)[0].lower() != p.lower()]
            # setuptools >= 70 vendors a typeguard that registers a pytest plugin needing a newer importlib-metadata
            # than 2020 pins provide; old pytest then fails at startup. 2020-era setuptools matches the corpus' era.
            added = [] if any(r.lower().startswith("setuptools") for r in reqs) else ["setuptools<60"]
            reqs += added
            key = hashlib.sha256("\n".join(sorted(set(reqs)) + [python]).encode()).hexdigest()[:16]
            venv = work / "venvs" / key
            rec = {"project": p, "bug": int(bug.name), "venv": key, "requirements": reqs, "added_constraints": added}
            if (venv / "ok.json").exists():
                w.append(dict(rec, **json.loads((venv / "ok.json").read_text()), cached=True))
                continue
            r = subprocess.run(["uv", "venv", "-q", "--python", python, str(venv)], capture_output=True, text=True, timeout=300)
            if r.returncode:
                w.append(dict(rec, status="venv_failed", detail=r.stderr[-300:]))
                continue
            vpy = str(venv / "bin" / "python")
            pip = lambda args: subprocess.run(["uv", "pip", "install", "-q", "--python", vpy, *args],  # noqa: E731
                                              capture_output=True, text=True, timeout=900)
            res = {"pinned_all": pip(reqs + (["pytest<7"] if not any(x.lower().startswith("pytest") for x in reqs) else [])).returncode == 0}
            unpinned, failed = [], []
            if not res["pinned_all"]:
                for x in reqs:
                    if pip([x]).returncode == 0:
                        continue
                    name = re.split(r"[=<>!~;\[ ]", x, maxsplit=1)[0]
                    (unpinned if pip([name]).returncode == 0 else failed).append(x)
                if pip(["pytest<7"]).returncode and pip(["pytest"]).returncode:
                    failed.append("pytest")
            res.update(unpinned=unpinned, failed=failed, status="ok")
            (venv / "ok.json").write_text(json.dumps(res))
            w.append(dict(rec, **res))
            print(json.dumps({"project": p, "bug": rec["bug"], "pinned_all": res["pinned_all"], "unpinned": unpinned,
                              "failed": failed}), flush=True)


NOT_RUNNABLE = ("collection_error", "startup_error", "usage_error", "internal_error", "target_missing", "timeout", "crashed")


def env_for(work: Path) -> dict:
    _, recs = read_records(work / "envs.jsonl")
    return {(r["project"], r["bug"]): r for r in recs}


def test_files(meta: dict) -> list:
    return [t for t in re.split(r"[;,\s]+", meta.get("test_file", "")) if t]


def checkout(work: Path, p: str, bug: Path, meta: dict) -> tuple:
    """BugsInPy semantics: buggy source + the FIXED version's test files (which contain the bug-revealing test)."""
    repo, base = work / "repos" / p, work / "bugs" / p / bug.name
    err = materialize(repo, meta["buggy_commit_id"], base / "buggy") or materialize(repo, meta["fixed_commit_id"], base / "fixed")
    if err:
        return base, err
    for t in test_files(meta):
        src, dst = base / "fixed" / t, base / "buggy" / t
        if src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
    return base, None


def run_side(runner, root: Path, targets: list) -> dict:
    try:
        run = runner.run_pytest(root, targets)
        text = run.stdout + run.stderr
        return {"classification": run.classification, "failed": run.failed_ids,
                "passed": sorted(t for t, o in run.outcome.items() if o == "passed"), "tail": text[-600:],
                "missing": sorted(set(re.findall(r"No module named '([\w.]+)'", text)))}
    except (FileNotFoundError, ValueError) as exc:
        return {"classification": "target_missing", "failed": [], "passed": [], "tail": str(exc)[:300]}


def stage_validate(work: Path, projects: list, limit: int):
    envs = env_for(work)
    w = ChainedWriter(work / "validate.jsonl", {"run": "dev14_realbugs_validate", "provenance": environment_provenance(),
                                               "projects": projects, "limit": limit, "envs_sha256": file_sha256(work / "envs.jsonl"),
                                               "criterion": "bug's failing test fails on buggy (+fixed tests) and passes on fixed"})
    for p in projects:
        for bug in bug_dirs(work, p, limit):
            meta = info(bug / "bug.info")
            rec = {"project": p, "bug": int(bug.name), "python_version": meta.get("python_version"),
                   "buggy": meta.get("buggy_commit_id"), "fixed": meta.get("fixed_commit_id"), "targets": test_targets(bug)}
            env = envs.get((p, rec["bug"]))
            if not env or env.get("status") != "ok" or "pytest" in env.get("failed", []):
                w.append(dict(rec, status="environment_failed", env=env))
                continue
            rec["venv"], rec["env_unpinned"], rec["env_failed"] = env["venv"], env.get("unpinned", []), env.get("failed", [])
            if not rec["targets"]:
                w.append(dict(rec, status="no_parsable_test_command"))
                continue
            base, err = checkout(work, p, bug, meta)
            if err:
                w.append(dict(rec, status="checkout_failed", detail=err))
                continue
            vpy = str(work / "venvs" / env["venv"] / "bin" / "python")
            runner = SafeTestRunner(timeout_seconds=180, python=vpy)
            b, f = run_side(runner, base / "buggy", rec["targets"]), run_side(runner, base / "fixed", rec["targets"])
            # one repair round for test-only imports the corpus does not declare (e.g. PySnooper's python_toolbox):
            # install the missing module's name unpinned and retry; recorded as env_augmented
            rec["env_augmented"] = []
            for _ in range(3):
                missing = sorted(set(b.get("missing", []) + f.get("missing", [])) - set(rec["env_augmented"]))
                if not missing:
                    break
                added = [m.split(".")[0] for m in missing
                         if subprocess.run(["uv", "pip", "install", "-q", "--python", vpy, m.split(".")[0]],
                                           capture_output=True, timeout=600).returncode == 0]
                if not added:
                    break
                rec["env_augmented"] += added
                b, f = run_side(runner, base / "buggy", rec["targets"]), run_side(runner, base / "fixed", rec["targets"])
            rec["missing_modules"] = sorted(set(b.get("missing", []) + f.get("missing", [])))
            if b["classification"] in ("collection_error", "usage_error") and f["classification"] == "passed" \
                    and not rec["missing_modules"]:
                status = "valid_buggy_does_not_import"  # the bug-revealing test cannot even load against the buggy API
            elif b["classification"] in NOT_RUNNABLE or f["classification"] in NOT_RUNNABLE:
                status = f"not_runnable({b['classification']}/{f['classification']})"
            elif b["classification"] == "tests_failed" and f["classification"] == "passed":
                status = "valid"
            elif b["classification"] == "passed":
                status = "does_not_fail_on_buggy"
            else:
                status = f"fixed_version_fails({f['classification']})"
            w.append(dict(rec, status=status, buggy_result=b, fixed_result=f))
            print(json.dumps({"project": p, "bug": rec["bug"], "status": status}), flush=True)


def changed_buggy_lines(patch: str) -> dict:
    """path -> buggy-side line numbers the developer's fix touched (removed lines, or the line before a pure insertion)."""
    out, path, line = {}, None, 0
    for l in patch.splitlines():
        if l.startswith("--- "):
            path = l[4:].split("\t")[0]
            path = path[2:] if path.startswith("a/") else None
        elif l.startswith("+++ "):
            continue
        elif l.startswith("@@"):
            line = int(re.match(r"@@ -(\d+)", l).group(1))
        elif path is None:
            continue
        elif l.startswith("-"):
            out.setdefault(path, set()).add(line)
            line += 1
        elif l.startswith("+"):
            out.setdefault(path, set()).add(max(1, line - 1))
        else:
            line += 1
    return {k: sorted(v) for k, v in out.items()}


def truth_functions(root: Path, changed: dict) -> list:
    """Innermost function enclosing each changed line (module-level changes have no function)."""
    from asm.coding.understanding import CodeUnderstanding
    funcs = CodeUnderstanding().analyze(root).functions
    out = set()
    for path, lines in changed.items():
        for ln in lines:
            enclosing = [f for f in funcs if f.path == path and f.line <= ln <= f.end_line]
            if enclosing:
                out.add(min(enclosing, key=lambda f: f.end_line - f.line).qname)
    return sorted(out)


def stage_evaluate(work: Path, projects: list, limit: int, budget: float, out: str = "evaluate.jsonl", skip: int = 0):
    sys.path.insert(0, str(ROOT / "benchmarks"))
    import dev14_oracle as O
    from asm.coding.faultloc import FaultLocalizer, RepairWorkflow, ast_normal, collect_spectrum, reconcile_spectrum
    from asm.coding.patches import apply_proposal
    from asm.coding.understanding import CodeUnderstanding
    _, vrecs = read_records(work / "validate.jsonl")
    valid = [r for r in vrecs if r.get("status") == "valid" and r["project"] in projects]
    w = ChainedWriter(work / out, {"run": "dev14_realbugs_evaluate", "projects": projects, "provenance": environment_provenance(),
                                               "validate_sha256": file_sha256(work / "validate.jsonl"), "budget": budget, "skip": skip, "limit": limit,
                                               "repair_suite": "the bug's test file(s) from the fixed version",
                                               "oracle": {"gen_budget": O.GEN_BUDGET, "gen_seed": O.GEN_SEED}})
    for r in valid[skip:skip + limit if limit else None]:
        p, n = r["project"], r["bug"]
        bug = corpus_dir(work) / p / "bugs" / str(n)
        meta = info(bug / "bug.info")
        base, err = checkout(work, p, bug, meta)
        rec = {"project": p, "bug": n, "targets": r["targets"]}
        if err:
            w.append(dict(rec, status="checkout_failed"))
            continue
        runner = SafeTestRunner(timeout_seconds=180, python=str(work / "venvs" / r["venv"] / "bin" / "python"))
        suite = [t for t in test_files(meta) if (base / "buggy" / t).exists()] or r["targets"]
        changed = changed_buggy_lines((bug / "bug_patch.txt").read_text(errors="replace"))
        truth = truth_functions(base / "buggy", changed)
        rec.update(suite=suite, changed_files=sorted(changed), truth=truth,
                   developer_fix_lines=sum(len(v) for v in changed.values()))
        t0 = time.monotonic()
        spectrum = collect_spectrum(base / "buggy", suite, runner)
        plain = runner.run_pytest(base / "buggy", suite)
        reconcile_spectrum(spectrum, set(plain.failed_ids))
        if not spectrum.complete or not spectrum.failing:
            w.append(dict(rec, status="no_spectrum", reason=spectrum.incomplete_reason or "no failing tests in the suite",
                          plain=plain.classification))
            print(json.dumps({"project": p, "bug": n, "status": "no_spectrum"}), flush=True)
            continue
        loc = FaultLocalizer(runner).localize(base / "buggy", suite, spectrum=spectrum)
        scores = {s.qname: s.score for s in loc.suspects}
        ranks = []
        for q in truth:
            if scores.get(q, 0) > 0:
                better = sum(1 for v in scores.values() if v > scores[q])
                ranks.append([better + 1, better + 1 + sum(1 for k, v in scores.items() if v == scores[q] and k != q)])
        rec.update(failing=len(spectrum.failing), passing=len(spectrum.passing), suspects=len(loc.suspects),
                   best_rank=min(ranks) if ranks else None, top5=[s.qname for s in loc.suspects[:5]],
                   localize_seconds=round(time.monotonic() - t0, 1))
        t1 = time.monotonic()
        d = RepairWorkflow(runner, time_budget_seconds=budget).run(base / "buggy", suite)
        rec.update(status=d.status, repair_seconds=round(time.monotonic() - t1, 1), notes=[str(x)[:300] for x in d.notes[:6]])
        if d.steps:
            st = d.steps[0]
            rec.update(suspect=st["suspect"], desc=st["description"], label=st["confidence"], flags=st["confidence_basis"],
                       n_steps=len(d.steps))
        if d.status == "resolved" and d.steps:
            pdir = base / "patched"
            if pdir.exists():
                shutil.rmtree(pdir)
            shutil.copytree(base / "buggy", pdir)
            for prop in d._proposals:
                apply_proposal(pdir, prop, backup=False)
            files = sorted({prop.path for prop in d._proposals})
            restored = all((base / "fixed" / f).exists() and ast_normal((pdir / f).read_text()) == ast_normal((base / "fixed" / f).read_text())
                           for f in files)
            # oracle reference: the developer's fixed program, compared on the developer-changed functions and ASM's suspects
            with __import__("asm.coding.sandbox", fromlist=["interpreter"]).interpreter(runner.python):
                fixed_spec = collect_spectrum(base / "fixed", suite, runner)
                finfos = {f.qname: f for f in CodeUnderstanding().analyze(base / "fixed").functions}
                cls = O.classify_patch(base / "fixed", pdir, restored, sorted(set(truth) | {s["suspect"] for s in d.steps}),
                                       finfos, fixed_spec)
            # held-out evidence: the developer's other tests in the repository (not used for repair), buggy vs patched
            rec.update(patched_files=files, oracle_class=cls["class"], original_ok=cls.get("original_ok"),
                       oracle={k: v.get("status") for k, v in cls["details"].items()},
                       patch_sha256={f: file_sha256(pdir / f) for f in files},
                       fixed_tests_on_patched=run_side(runner, pdir, suite)["classification"])
        w.append(rec)
        print(json.dumps({k: rec.get(k) for k in ("project", "bug", "best_rank", "status", "label", "oracle_class")}), flush=True)


def main():
    stage, work = sys.argv[1], Path(sys.argv[2])
    projects = next((a.split("=", 1)[1].split(",") for a in sys.argv if a.startswith("--projects=")), PROJECTS)
    limit = int(next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--limit=")), "0"))
    work.mkdir(parents=True, exist_ok=True)
    if stage == "prepare":
        stage_prepare(work, projects)
    elif stage == "envs":
        stage_envs(work, projects, limit, next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--python=")), "3.8"))
    elif stage == "validate":
        stage_validate(work, projects, limit)
    elif stage == "evaluate":
        stage_evaluate(work, projects, limit, float(next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--budget=")), "150")),
                       next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--out=")), "evaluate.jsonl"),
                       int(next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--skip=")), "0")))
    else:
        raise SystemExit(f"unknown stage {stage}")


if __name__ == "__main__":
    main()
