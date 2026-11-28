"""DEV20 DEVELOPMENT evaluation (exploratory; development data only, all of it already inspected): S20 (learned steps)
within K = 80 on a development split, beside the baselines recorded for the same problems in DEV18/DEV19.
Usage: python benchmarks/dev20_dev_eval.py <out.jsonl> <baseline_eval.jsonl> <baseline_filter: part=fresh | level=LALL> <test.jsonl> <train.jsonl>...
"""
import ast
import collections
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from asm.coding.content import ProblemContext  # noqa: E402
from asm.coding.integrity import read_records  # noqa: E402
from asm.coding.steps import StepLibrary  # noqa: E402

K = 80


def norm(s):
    try:
        return ast.unparse(ast.parse(s))
    except (SyntaxError, ValueError):
        return None


def main():
    out, base, filt, test = sys.argv[1:5]
    trains = sys.argv[5:]
    fk, fv = filt.split("=")
    baseline = {r["id"]: r for r in read_records(Path(base))[1] if r.get(fk) == fv and "id" in r}
    lib = StepLibrary()
    t0 = time.time()
    for f in trains:
        by = collections.defaultdict(list)
        for r in read_records(Path(f))[1]:
            by[r["repo"]].append((r["before"], r["after"], r["id"]))
        for repo, ex in by.items():
            lib.learn(ex, repo)
    learn_s = round(time.time() - t0, 1)
    fh = open(out, "w")
    fh.write(json.dumps({"library": lib.summary(), "learn_s": learn_s}) + "\n")
    print(json.dumps({"library": lib.summary(), "learn_s": learn_s}), flush=True)
    rows = []
    for p in read_records(Path(test))[1]:
        t1 = time.time()
        before = p["before"]
        cands = lib.candidates_for(before, "m.py", (1, before.count("\n") + 1), ProblemContext.from_dict(p.get("context", {})),
                                   limit=K, as_candidates=False)
        target = norm(p["after"])
        hit = next((i for i, (c, _) in enumerate(cands) if norm(c) == target), None)
        b = baseline.get(p["id"], {})
        row = {"id": p["id"], "s20": hit is not None, "s20_position": hit, "s20_kind": cands[hit][1]["kind"] if hit is not None else None,
               "s20_ops": cands[hit][1]["ops"] if hit is not None else None, "n": len(cands),
               "builtin_any": b.get("builtin_any"), "p17_any": b.get("p17_any"), "s18": b.get("s18"),
               "s": round(time.time() - t1, 2)}
        row["new"] = bool(row["s20"] and not row["builtin_any"] and not row["p17_any"] and not row["s18"])
        rows.append(row)
        fh.write(json.dumps(row) + "\n")
        fh.flush()
    summ = {"problems": len(rows), "s20": sum(r["s20"] for r in rows), "new": sum(r["new"] for r in rows),
            "s18": sum(bool(r["s18"]) for r in rows), "by_kind": dict(collections.Counter(r["s20_kind"] for r in rows if r["s20"])),
            "new_by_kind": dict(collections.Counter(r["s20_kind"] for r in rows if r["new"])),
            "new_ids": [r["id"] for r in rows if r["new"]], "mean_s": round(sum(r["s"] for r in rows) / max(1, len(rows)), 2),
            "max_s": max((r["s"] for r in rows), default=0)}
    fh.write(json.dumps({"summary": summ}) + "\n")
    print(json.dumps(summ), flush=True)


if __name__ == "__main__":
    main()
