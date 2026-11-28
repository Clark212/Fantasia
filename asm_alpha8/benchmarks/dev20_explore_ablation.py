"""DEV20 EXPLORATORY (after the pre-registered run; not pre-registered): S20 without both DEV20 additions beyond single
steps, i.e. single steps only AND no exception holes, on the fresh set with the same knowledge and K = 80. The
pre-registered ablations removed one addition each (single steps only: 7; without exception holes: 7; S20: 4).
"New" uses the pre-registered run's B, P17 and S18 results for the same fix.
Usage: python benchmarks/dev20_explore_ablation.py <out.jsonl> <dev20_eval.jsonl> <dev20_fresh.jsonl> <knowledge.jsonl> ...
"""
import collections
import json
import multiprocessing
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
import asm.coding.steps as ST  # noqa: E402
import dev18_evaluate as E  # noqa: E402
from asm.coding.content import ProblemContext  # noqa: E402
from asm.coding.integrity import read_records  # noqa: E402

K = E.K
SINGLE = {"single": 1, "multi": 0, "pair": 0}
_G: dict = {}


def score(p):
    before, target = p["before"], E.norm(p["after"])
    span, ctx = (1, before.count("\n") + 1), ProblemContext.from_dict(p["context"])
    got = _G["noexc"].candidates_for(before, "m.py", span, ctx, limit=K, as_candidates=False, quota=SINGLE)
    singles = [x for x, info in got if info["kind"] == "single"]
    hit = E.first_hit(singles, target)
    b = _G["base"][p["id"]]
    return {"id": p["id"], "repo": p["repo"], "single_noexc": hit is not None, "position": hit,
            "new": hit is not None and not (b["builtin_any"] or b["p17_any"] or b["s18"]),
            "s20": b["s20"], "s20_single_only": b["s20_single_only"], "s20_without_exception_holes": b["s20_without_exception_holes"]}


def main():
    out, base, fresh, know = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), [Path(a) for a in sys.argv[4:]]
    _G["base"] = {r["id"]: r for r in read_records(base)[1] if r.get("part") == "fresh"}
    ST.EXCEPTION_HOLES = False
    noexc = ST.StepLibrary()
    for f in know:  # as dev20_evaluate.learn_all: in order, per-project batches
        by = collections.defaultdict(list)
        for r in read_records(f)[1]:
            by[r["repo"]].append((r["before"], r["after"], r["id"]))
        for repo, ex in by.items():
            noexc.learn(ex, f"{f.parent.name}/{f.stem}:{repo}")
    ST.EXCEPTION_HOLES = True
    _G["noexc"] = noexc
    with multiprocessing.get_context("fork").Pool(4) as pool:
        rows = list(pool.imap(score, read_records(fresh)[1], chunksize=1))
    summary = {"problems": len(rows), "single_steps_without_exception_holes": sum(r["single_noexc"] for r in rows),
               "new": [r["id"] for r in rows if r["new"]], "s20": sum(r["s20"] for r in rows),
               "s20_single_only": sum(r["s20_single_only"] for r in rows),
               "s20_without_exception_holes": sum(r["s20_without_exception_holes"] for r in rows),
               "reproduced": [r["id"] for r in rows if r["single_noexc"]]}
    with open(out, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
        fh.write(json.dumps({"summary": summary}) + "\n")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
