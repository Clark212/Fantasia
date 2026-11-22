"""DEV21 Part B: mine fix commits for the FRESH evaluation from projects never inspected before the DEV21 pre-registration
(none of the 44 projects used in DEV17-DEV20, none of BugsInPy's).
Selection criteria and problem context are DEV18's (`dev18_mine_fresh.mine`), unchanged.
Usage: python benchmarks/dev21_mine.py <work_dir> <out.jsonl> [repo ...]
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

FRESH = {"six": "https://github.com/benjaminp/six", "colorama": "https://github.com/tartley/colorama",
         "prettytable": "https://github.com/jazzband/prettytable", "simplejson": "https://github.com/simplejson/simplejson",
         "sortedcontainers": "https://github.com/grantjenks/python-sortedcontainers",
         "pyrsistent": "https://github.com/tobgu/pyrsistent", "funcy": "https://github.com/Suor/funcy",
         "jsonpatch": "https://github.com/stefankoegel/python-json-patch", "box": "https://github.com/cdgriffith/Box",
         "cattrs": "https://github.com/python-attrs/cattrs", "parso": "https://github.com/davidhalter/parso",
         "asttokens": "https://github.com/gristlabs/asttokens"}
PREREG = ROOT / "benchmarks" / "preregistration" / "dev21_study.md"


def main():
    work, out = Path(sys.argv[1]), Path(sys.argv[2])
    names = sys.argv[3:] or list(FRESH)
    work.mkdir(parents=True, exist_ok=True)
    w = ChainedWriter(out, {"run": "dev21_mine fresh", "provenance": environment_provenance(),
                            "repos": {n: FRESH[n] for n in names},
                            "criteria": {"fix_re": M.FIX_RE.pattern, "max_changed_lines": M.MAX_CHANGED_LINES},
                            "preregistration_sha256": file_sha256(PREREG)})
    for n in names:
        try:
            c = F.mine(n, FRESH[n], work, w)
        except Exception as e:  # an unreachable repository is reported, not silently skipped
            print(json.dumps({"repo": n, "error": repr(e)[:200]}), flush=True)
            continue
        print(json.dumps({"repo": n, "head": M.git(work / n, "rev-parse", "HEAD").strip()[:12], **c}), flush=True)
    print(json.dumps({"head": w.head}))


if __name__ == "__main__":
    main()
