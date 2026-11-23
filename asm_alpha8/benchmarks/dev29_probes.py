"""DEV29 review probes: run a distinguishing input on the developer's fixed tree and on ASM's patched tree of a real bug, in
the bug's own Python 3.8 virtualenv and inside ASM's sandbox (run_python_worker, the SafeTestRunner protections). The
probes are DEV15's (benchmarks/results/dev15/REALBUGS_REVIEW.md) plus the oracle's own example for thefuck-15.
Usage: python benchmarks/dev29_probes.py <work_dir>
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from asm.coding.integrity import read_records  # noqa: E402
from asm.coding.sandbox import run_python_worker  # noqa: E402

PROBES = {
    ("tqdm", 8): "from tqdm import tqdm\nprint(repr(tqdm.format_meter(3, 10, 1.0, ncols=40, bar_format='L{n}|{bar}|R{total}')))",
    ("youtube-dl", 11): "from youtube_dl.utils import str_to_int\nprint([str_to_int(5.5), str_to_int(7), str_to_int('1,000')])",
    ("youtube-dl", 29): "from youtube_dl.utils import unified_strdate\nprint([unified_strdate(x) for x in ['', 'nonsense', 'Dec 14, 2012', '1968-12-10']])",
    ("thefuck", 21): "from thefuck.rules.git_fix_stash import match\nfrom thefuck.types import Command\nprint(repr(match(Command('git', '', ''))))",
    ("thefuck", 15): ("from thefuck.rules.git_add import match\nfrom thefuck.types import Command\n"
                      "print(repr(match(Command('git submodule update unknown', '', \"Did you forget to 'git add'? did not match any file(s) known to git.\"))))"),
    ("tqdm", 6): ("from tqdm import tqdm\ndef n(**k):\n    try:\n        return len(tqdm([1, 2, 3], total=10, **k))\n"
                  "    except Exception as e:\n        return type(e).__name__\nprint([n(disable=True), n()])"),
    ("thefuck", 22): ("from thefuck.types import CorrectedCommand, Settings, SortedCorrectedCommandsSequence as Seq\n"
                      "def seen(pairs, first):\n    s = Seq((CorrectedCommand(c, None, p) for c, p in pairs), Settings(debug=False))\n"
                      "    head = [s[0].script] if first and s else []\n    return [bool(s), len(s), head + [s[i].script for i in range(len(s))]]\n"
                      "cases = [[], [('a', 1)], [('a', 1), ('a', 2)], [('a', 1), ('b', 2)], [('b', 3), ('a', 1), ('c', 2), ('a', 5)]]\n"
                      "print([seen(c, f) for c in cases for f in (False, True)])"),
}


def main():
    work = Path(sys.argv[1])
    venv = {(r["project"], r["bug"]): r["venv"] for r in read_records(work / "validate.jsonl")[1] if r.get("status") == "valid"}
    for (project, bug), code in PROBES.items():
        out = {"bug": f"{project}-{bug}", "probe": code}
        for tree in ("fixed", "patched"):
            script = "import sys, warnings\nwarnings.simplefilter('ignore')\nsys.path.insert(0, sys.argv[1])\n" + code + "\n"
            path = work / "bugs" / project / str(bug) / tree
            r = run_python_worker(script, [str(path)], path, timeout=120, python=str(work / "venvs" / venv[(project, bug)] / "bin" / "python"))
            out[tree] = r["stdout"].strip() if r["returncode"] == 0 else f"exit {r['returncode']}: {r['stderr'].strip()[-300:]}"
        out["differ"] = out["fixed"] != out["patched"]
        print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
