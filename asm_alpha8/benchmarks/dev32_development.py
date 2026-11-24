"""DEV32 development evidence for the test-copy guard (content.copied_test_strings), on data ASM has already seen.
  patches <dev15_work> <dev31_work>  every patch ASM accepted in DEV15, DEV29 and DEV31 (development and fresh runs), with
                                     the strings it wrote into the code and whether the guard flags them. The failing
                                     tests' literals come from their source (the workflow also adds quoted failure text)
  fixes                              the real developer fixes mined in DEV18-DEV21 (with their changed tests' literals):
                                     how many the guard would flag, overall and among those ASM's learned knowledge
                                     reproduced (DEV18-DEV21 evaluations). The mined records hold the changed function, so
                                     the module's own strings come from the record's context
Usage: python benchmarks/dev32_development.py patches|fixes [work dirs]
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from asm.coding.content import ProblemContext, copied_test_strings, literals  # noqa: E402
from asm.coding.integrity import read_records  # noqa: E402

R = ROOT / "benchmarks" / "results"
RUNS = {"dev15": ("dev15", "realbugs_eval_*.jsonl", 0), "dev29": ("dev29", "dev29_evaluate_*.jsonl", 0),
        "dev31_development": ("dev31/development", "dev31_learned_*.jsonl", 0), "dev31": ("dev31", "dev31_control_learned_*.jsonl", 1)}
MINED = ["dev18/fresh.jsonl", "dev19/train.jsonl", "dev19/fresh.jsonl", "dev20/fresh.jsonl", "dev21/fresh.jsonl"]
EVALS = {"dev18/dev18_eval.jsonl": ["s18"], "dev19/dev19_eval.jsonl": ["s18", "d18"], "dev20/dev20_eval.jsonl": ["s18", "s20"],
         "dev21/dev21_eval.jsonl": ["control", "guard", "round_robin", "both"]}


def patched_files(buggy: Path, diff: str, files: list) -> dict | None:
    with tempfile.TemporaryDirectory() as td:
        for f in files:
            (Path(td) / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(buggy / f, Path(td) / f)
        if subprocess.run(["patch", "-p1", "-s", "-d", td], input=diff, text=True, capture_output=True).returncode:
            return None
        return {f: (Path(td) / f).read_text(encoding="utf-8") for f in files}


def patches(works: list):
    seen, flagged = set(), []
    for run, (d, pattern, w) in RUNS.items():
        for f in sorted((R / d).glob(pattern)):
            for r in read_records(f)[1]:
                key = (run, r.get("project"), r.get("bug"), r.get("mode"), r.get("asm_diff"))
                if not r.get("asm_diff") or key in seen:
                    continue
                seen.add(key)
                buggy = works[w] / "bugs" / r["project"] / str(r["bug"]) / "buggy"
                names = {t.split("::")[-1].split("[", 1)[0] for t in r["targets"]}
                ts = [s for p in sorted({t.split("::", 1)[0] for t in r["targets"]}) if (buggy / p).exists()
                      for s in literals((buggy / p).read_text(encoding="utf-8", errors="replace"), names)[0]]
                new = patched_files(buggy, r["asm_diff"], re.findall(r"^\+\+\+ b/(.+)$", r["asm_diff"], re.M))
                copied = None if new is None else sorted({s for fn, src in new.items() for s in copied_test_strings(
                    (buggy / fn).read_text(encoding="utf-8"), src, ProblemContext(test_strings=ts))})
                out = {"run": run, "bug": f"{r['project']}-{r['bug']}", "mode": r["mode"], "status": r["status"],
                       "desc": r.get("desc"), "copied": copied}
                print(json.dumps(out, ensure_ascii=False))
                flagged += [out] if copied else []
    print(json.dumps({"accepted_patches": len(seen), "flagged": [
        f"{o['run']} {o['bug']} {o['mode']}" for o in flagged]}))


def fixes():
    pairs = {}
    for f in MINED:
        for r in read_records(R / f)[1]:
            if "context" in r:
                pairs.setdefault(r["id"], r)

    def flag(r):
        ctx = r["context"]
        module = set(ctx.get("module_strings", []))
        return copied_test_strings(r["before"], r["after"], ProblemContext(test_strings=[t for t in ctx.get("test_strings", []) if t not in module]))
    flagged = {i: flag(r) for i, r in pairs.items()}
    flagged = {i: v for i, v in flagged.items() if v}
    hits = {}
    for f, keys in EVALS.items():
        recs = [r for r in read_records(R / f)[1] if "id" in r]
        for k in keys:
            ids = sorted({r["id"] for r in recs if r.get(k) is True and r["id"] in pairs})
            hits[f"{f.split('/')[0]}:{k}"] = {"hits": len(ids), "flagged": [i for i in ids if i in flagged]}
    print(json.dumps({"developer_fixes": len(pairs), "flagged": len(flagged), "flagged_fixes": flagged,
                      "learned_hits": hits}, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    if sys.argv[1] == "patches":
        patches([Path(a) for a in sys.argv[2:4]])
    else:
        fixes()
