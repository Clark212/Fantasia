"""Benchmark subjects: ASM's own coding package, and two INDEPENDENT open-source repositories (toolz 1.2.0,
cachetools 8.0.0; PyPI sdists, sha256 recorded in the DEV13 report). Faults seeded in them are injected, not historical."""
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmarks"))
import dev11_seeded_faults as B  # noqa: E402

INDEP = Path(os.environ.get("ASM_INDEP_DIR", "/tmp/asm_indep"))
SUBJECTS = dict(B.SUBJECTS)
SUBJECTS["toolz"] = {"kind": "dir", "dir": "toolz-1.2.0", "flatten_src": False,
                     "files": ["toolz/itertoolz.py", "toolz/dicttoolz.py", "toolz/recipes.py"],
                     "tests": ["toolz/tests/test_itertoolz.py", "toolz/tests/test_dicttoolz.py", "toolz/tests/test_recipes.py"]}
SUBJECTS["cachetools"] = {"kind": "dir", "dir": "cachetools-8.0.0", "flatten_src": True,
                          "files": ["cachetools/__init__.py", "cachetools/keys.py"], "tests": ["tests"]}


def make_template(subject: str, td: Path) -> Path:
    spec = SUBJECTS[subject]
    if spec.get("kind") != "dir":
        return B.make_template(subject, td)
    repo = td / "repo"
    shutil.copytree(INDEP / spec["dir"], repo, ignore=shutil.ignore_patterns("__pycache__", ".git", "*.egg-info", "docs"))
    if spec["flatten_src"] and (repo / "src").exists():
        for p in (repo / "src").iterdir():
            if p.is_dir() and not p.name.endswith("egg-info"):
                shutil.copytree(p, repo / p.name)
        shutil.rmtree(repo / "src")  # both copies would otherwise map to the same module name
    return repo
