"""DEV33 review probes: a distinguishing input on the developer's fixed tree and on an arm's patched tree of a fresh real
bug, in the bug's own Python 3.11 virtualenv and inside ASM's sandbox (run_python_worker). The patched tree is rebuilt
from the arm's stored diff (patched_<arm>/), since the arms of one bug accepted different patches.
Usage: python benchmarks/dev33_probes.py <work_dir>
"""
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
from dev31_realbugs import records  # noqa: E402
from dev32_development import patched_files  # noqa: E402
from asm.coding.integrity import read_records  # noqa: E402
from asm.coding.sandbox import run_python_worker  # noqa: E402

TRY = "def t(f, *a):\n    try:\n        return f(*a)\n    except Exception as e:\n        return type(e).__name__\n"
DC = "from dataclasses import dataclass, field\nfrom typing import List, Tuple, Optional\nfrom dataclasses_json import dataclass_json\n" + TRY
PROBES = {  # (bug, arms whose patch is probed): code
    (("dataclasses-json", 4), ("control", "checked")): DC + (
        "@dataclass_json\n@dataclass\nclass P:\n    x: int\n"
        "@dataclass_json\n@dataclass\nclass A:\n    v: Tuple[int, ...]\n    f: Tuple[int, str]\n    p: List[P]\n"
        "@dataclass_json\n@dataclass\nclass B:\n    p: P\n    o: Optional[P] = None\n"
        "s = t(A.schema)\nprint(s if isinstance(s, str) else sorted((k, type(f).__name__) for k, f in s.fields.items()),"
        " t(lambda: A.schema().load({'v': ['x'], 'f': [1, 'a'], 'p': []})), t(lambda: A.schema().load({'v': [1, 2, 3], 'f': [1, 'a'], 'p': [{'x': 1}]})),"
        " t(lambda: sorted((k, type(f).__name__) for k, f in B.schema().fields.items())), t(lambda: B.schema().load({'p': {'x': 1}, 'o': {'x': 2}})),"
        " t(lambda: B.schema().dump(B(P(1)))))"),
    (("dataclasses-json", 5), ("control",)): DC + (
        "import enum\nclass F(enum.IntFlag):\n    A = 1\n    B = 2\n"
        "@dataclass_json\n@dataclass\nclass P:\n    x: int\n"
        "@dataclass_json\n@dataclass\nclass A:\n    ps: List[P]\n    b: bytes = b''\n    fl: F = F.A\n"
        "print(t(lambda: A([P(1), P(2)]).to_dict()), t(lambda: A([P(3)], b'xy', F.A | F.B).to_dict()))"),
    (("dataclasses-json", 8), ("control",)): DC + (
        "@dataclass_json\n@dataclass\nclass P:\n    x: int\n"
        "@dataclass_json\n@dataclass\nclass A:\n    p: P\n    q: Optional[P] = None\n"
        "print(t(lambda: A(P(1), P(2)).to_dict()), t(lambda: A.from_dict({'p': {'x': 1}, 'q': None})), t(lambda: A.from_dict({'p': {'x': 1}, 'q': 'nope'})))"),
    (("markdown-it-py", 1), ("control",)): (
        "import io, os, tempfile, contextlib\nfrom markdown_it.cli import parse\n"
        "d = tempfile.mkdtemp()\np = os.path.join(d, 'x.md')\nopen(p, 'wb').write('# caf\\u00e9 \\u2713\\n'.encode('utf8') + b'\\xff ok\\n')\n"
        "out = io.StringIO()\nwith contextlib.redirect_stdout(out):\n    try:\n        parse.convert_file(p)\n    except BaseException as e:\n        print(type(e).__name__)\n"
        "out2 = io.StringIO()\nwith contextlib.redirect_stdout(out2):\n    try:\n        parse.convert([p])\n    except BaseException as e:\n        print(type(e).__name__)\n"
        "print(repr(out.getvalue()), repr(out2.getvalue()))"),
}


def tree(work: Path, project: str, bug: int, arm: str, diff: str) -> Path:
    base = work / "bugs" / project / str(bug)
    dst = base / f"patched_{arm}"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(base / "buggy", dst)
    for f, src in patched_files(base / "buggy", diff, re.findall(r"^\+\+\+ b/(.+)$", diff, re.M)).items():
        (dst / f).write_text(src, encoding="utf-8")
    return dst


def main():
    work = Path(sys.argv[1])
    venv = {(r["project"], r["bug"]): r["venv"] for r in read_records(work / "validate.jsonl")[1] if r.get("status") == "valid"}
    by = records(work, "dev33_control_learned_checked_checked_learned_*of*.jsonl")
    for ((project, bug), arms), code in PROBES.items():
        out = {"bug": f"{project}-{bug}", "probe": code}
        script = "import sys, warnings\nwarnings.simplefilter('ignore')\nsys.path.insert(0, sys.argv[1])\n" + code + "\n"
        trees = {"fixed": work / "bugs" / project / str(bug) / "fixed"}
        trees.update({a: tree(work, project, bug, a, by[(project, bug)][a]["asm_diff"]) for a in arms})
        for name, path in trees.items():
            r = run_python_worker(script, [str(path)], path, timeout=120, python=str(work / "venvs" / venv[(project, bug)] / "bin" / "python"))
            out[name] = r["stdout"].strip() if r["returncode"] == 0 else f"exit {r['returncode']}: {r['stderr'].strip()[-300:]}"
        out["differ"] = {a: out[a] != out["fixed"] for a in arms}
        print(json.dumps(out, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
