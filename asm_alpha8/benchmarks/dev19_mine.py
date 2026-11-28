"""DEV19: mine fix commits for TRAINING (new training projects) or for the FRESH evaluation (projects never inspected before
the DEV19 pre-registration). Selection criteria and problem context are DEV18's (`dev18_mine_fresh.mine`), unchanged.
Usage: python benchmarks/dev19_mine.py train|fresh <work_dir> <out.jsonl> [repo ...]
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
import dev17_mine_history as M  # noqa: E402
import dev18_mine_fresh as F  # noqa: E402
from asm.coding.integrity import ChainedWriter, environment_provenance, file_sha256  # noqa: E402

TRAIN = {"dateutil": "https://github.com/dateutil/dateutil", "pyparsing": "https://github.com/pyparsing/pyparsing",
         "itsdangerous": "https://github.com/pallets/itsdangerous", "markupsafe": "https://github.com/pallets/markupsafe",
         "jsonschema": "https://github.com/python-jsonschema/jsonschema", "pathspec": "https://github.com/cpburnz/python-pathspec",
         "tomlkit": "https://github.com/python-poetry/tomlkit", "sqlparse": "https://github.com/andialbrecht/sqlparse",
         "pyflakes": "https://github.com/PyCQA/pyflakes", "isort": "https://github.com/PyCQA/isort"}
FRESH = {"pluggy": "https://github.com/pytest-dev/pluggy", "wcwidth": "https://github.com/jquast/wcwidth",
         "xmltodict": "https://github.com/martinblech/xmltodict", "slugify": "https://github.com/un33k/python-slugify",
         "cerberus": "https://github.com/pyeve/cerberus", "schema": "https://github.com/keleshev/schema",
         "jmespath": "https://github.com/jmespath/jmespath.py", "parsimonious": "https://github.com/erikrose/parsimonious"}
PREREG = ROOT / "benchmarks" / "preregistration" / "dev19_study.md"


def main():
    kind, work, out = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    repos = {"train": TRAIN, "fresh": FRESH}[kind]
    names = sys.argv[4:] or list(repos)
    work.mkdir(parents=True, exist_ok=True)
    w = ChainedWriter(out, {"run": f"dev19_mine {kind}", "provenance": environment_provenance(),
                            "repos": {n: repos[n] for n in names},
                            "criteria": {"fix_re": M.FIX_RE.pattern, "max_changed_lines": M.MAX_CHANGED_LINES},
                            "preregistration_sha256": file_sha256(PREREG)})
    for n in names:
        try:
            c = F.mine(n, repos[n], work, w)
        except Exception as e:  # an unreachable repository is reported, not silently skipped
            print(json.dumps({"repo": n, "error": repr(e)[:200]}), flush=True)
            continue
        print(json.dumps({"repo": n, "head": M.git(work / n, "rev-parse", "HEAD").strip()[:12], **c}), flush=True)
    print(json.dumps({"head": w.head}))


if __name__ == "__main__":
    main()
