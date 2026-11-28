"""DEV16 training subjects for generated bug data, and the evaluation-set exclusion rule.

Training subjects: pure-Python PyPI sdists whose own test suites run cleanly in ASM's sandbox. They are where generated
bugs come from, so they must never be used to EVALUATE a DEV16 learner. `assert_disjoint` is called by every DEV16
training and evaluation script: no training subject may be a project of any evaluation corpus."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmarks"))
import dev15_subjects as S15  # noqa: E402
from dev13_subjects import INDEP  # noqa: E402,F401

SUBJECTS = dict(S15.SUBJECTS)
META = {"toolz": ("toolz", "1.2.0"), "cachetools": ("cachetools", "8.0.0"), "inflection": ("inflection", "0.5.1"),
        "semver": ("semver", "3.0.4"), "parse": ("parse", "1.20.2"), "more_itertools": ("more-itertools", "10.5.0")}
SUBJECTS["more_itertools_more"] = {"kind": "dir", "dir": "more-itertools-10.5.0", "flatten_src": False,
                                   "files": ["more_itertools/more.py"], "tests": ["tests/test_more.py"]}
META["more_itertools_more"] = ("more-itertools", "10.5.0")
import dev13_subjects as _m13  # noqa: E402  (make_template looks subjects up in these tables)
_m13.SUBJECTS["more_itertools_more"] = SUBJECTS["more_itertools_more"]
S15.SUBJECTS["more_itertools_more"] = SUBJECTS["more_itertools_more"]
for k, (pypi, ver) in META.items():
    SUBJECTS[k] = dict(SUBJECTS[k], pypi_name=pypi, version=ver)
TRAINING = tuple(META)
# projects of evaluation corpora (BugsInPy, as used by DEV14/DEV15); lower-case PyPI-style names
EVALUATION_PROJECTS = {"pysnooper", "thefuck", "tqdm", "cookiecutter", "httpie", "youtube-dl", "youtube_dl", "ansible",
                       "black", "fastapi", "keras", "luigi", "matplotlib", "pandas", "sanic", "scrapy", "spacy", "tornado"}
make_template = S15.make_template


def assert_disjoint(training=TRAINING, evaluation=EVALUATION_PROJECTS):
    bad = {t.lower().replace("_", "-") for t in training} & {e.lower().replace("_", "-") for e in evaluation}
    if bad:
        raise SystemExit(f"training subjects overlap evaluation projects: {sorted(bad)}")


def sdist_path(name: str, rel: str) -> str:
    return ("src/" + rel) if SUBJECTS[name].get("flatten_src") else rel


def sdist_file(name: str) -> Path:
    spec = SUBJECTS[name]
    cands = sorted((INDEP / "dl").glob(f"{spec['pypi_name']}-{spec['version']}.tar.gz")) or \
        sorted((INDEP / "dl").glob(f"{spec['pypi_name'].replace('-', '_')}-{spec['version']}.tar.gz"))
    if not cands:
        raise SystemExit(f"sdist for {name} not found under {INDEP / 'dl'}")
    return cands[0]


assert_disjoint()
