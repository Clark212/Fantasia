"""DEV14 benchmark subjects: DEV13's subjects plus inflection 0.5.1 (PyPI sdist), a third independent repository."""
from dev13_subjects import INDEP, SUBJECTS as _S13, make_template  # noqa: F401

SUBJECTS = dict(_S13)
SUBJECTS["inflection"] = {"kind": "dir", "dir": "inflection-0.5.1", "flatten_src": False,
                          "files": ["inflection/__init__.py"], "tests": ["test_inflection.py"]}

import dev13_subjects as _m  # noqa: E402
_m.SUBJECTS.update(SUBJECTS)  # make_template looks subjects up in dev13_subjects.SUBJECTS
