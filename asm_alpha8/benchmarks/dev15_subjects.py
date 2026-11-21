"""DEV15 fresh subjects for the pre-registered study: three independent PyPI sdists never used by DEV11-DEV14
(semver 3.0.4, parse 1.20.2, more-itertools 10.5.0; sha256 in benchmarks/preregistration/dev15_study.md and in every
run manifest). Faults are injected (single-site), not historical. DEV14's subjects stay available for comparison.

semver's own .pytest.ini asks for pytest-cov options and doctests over docs/; it is replaced by a minimal ini that
keeps only the import path and warning filter its tests rely on (recorded in the run manifest as `ini_override`)."""
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmarks"))
import dev13_subjects as _m  # noqa: E402
import dev14_subjects  # noqa: E402,F401  (registers inflection in dev13_subjects.SUBJECTS)
from dev13_subjects import INDEP  # noqa: E402,F401

SEMVER_INI = "[pytest]\npythonpath = . tests\nfilterwarnings =\n    ignore:Function 'semver.*:DeprecationWarning\n"

FRESH = {
    "semver": {"kind": "dir", "dir": "semver-3.0.4", "flatten_src": True, "files": ["semver/version.py"],
               "tests": ["tests"], "ini_override": {".pytest.ini": SEMVER_INI}},
    "parse": {"kind": "dir", "dir": "parse-1.20.2", "flatten_src": False, "files": ["parse.py"], "tests": ["tests"]},
    "more_itertools": {"kind": "dir", "dir": "more-itertools-10.5.0", "flatten_src": False,
                       "files": ["more_itertools/recipes.py"], "tests": ["tests/test_recipes.py"]},
}
SUBJECTS = dict(_m.SUBJECTS)
SUBJECTS.update(FRESH)
_m.SUBJECTS.update(FRESH)  # make_template looks subjects up in dev13_subjects.SUBJECTS


def make_template(subject: str, td: Path) -> Path:
    repo = _m.make_template(subject, td)
    for rel, text in SUBJECTS[subject].get("ini_override", {}).items():
        (repo / rel).write_text(text)
    for junk in repo.glob("*.egg-info"):
        shutil.rmtree(junk)
    return repo
