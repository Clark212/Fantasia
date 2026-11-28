"""DEV21 DEVELOPMENT (exploratory; development data only, all of it already inspected): S20 within K = 80 under three
variants, in three settings. Variants: "key" (DEV20 as run), "round_robin" (DEV21's round-robin across steps inside each
candidate kind), "raise_guard" (DEV20's ordering; an exception hole applies only at the exception of a `raise`), and
"round_robin_guard" (both).
Settings:
  dev18: knowledge DEV17 history (91)                                   -> DEV18 fresh (472)
  dev19: + DEV18 fresh + DEV19 training (1,151)                         -> DEV19 fresh (103)
  dev20: + DEV19 fresh (1,254)                                          -> DEV20 fresh (483)
"New" uses the B, P17 and S18 results recorded for the same fix in that DEV's own evaluation.
Usage: python benchmarks/dev21_dev_steps.py <out.jsonl> <dev18|dev19|dev20> [variant,variant,...]
"""
import collections
import json
import multiprocessing
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
import asm.coding.steps as ST  # noqa: E402
import dev18_evaluate as E  # noqa: E402
from asm.coding.content import ProblemContext  # noqa: E402
from asm.coding.integrity import read_records  # noqa: E402

R = ROOT / "benchmarks" / "results"
K = E.K
VARIANTS = {"key": {"sharing": "key"}, "round_robin": {"sharing": "round_robin"},
            "raise_guard": {"sharing": "key", "exception_sites": "raise"},
            "round_robin_guard": {"sharing": "round_robin", "exception_sites": "raise"}}
SETTINGS = {
    "dev18": (["dev17/history.jsonl"], "dev18/fresh.jsonl", ("dev18/dev18_eval.jsonl", "part", "fresh")),
    "dev19": (["dev17/history.jsonl", "dev18/fresh.jsonl", "dev19/train.jsonl"], "dev19/fresh.jsonl",
              ("dev19/dev19_eval.jsonl", "level", "LALL")),
    "dev20": (["dev17/history.jsonl", "dev18/fresh.jsonl", "dev19/train.jsonl", "dev19/fresh.jsonl"], "dev20/fresh.jsonl",
              ("dev20/dev20_eval.jsonl", "part", "fresh")),
}
_G: dict = {}


def score(p):
    before, target = p["before"], E.norm(p["after"])
    span, ctx = (1, before.count("\n") + 1), ProblemContext.from_dict(p["context"])
    row = {"id": p["id"]}
    for name in _G["variants"]:
        got = _G["lib"].candidates_for(before, "m.py", span, ctx, limit=K, as_candidates=False, **VARIANTS[name])
        hit = E.first_hit([x for x, _ in got], target)
        row[name] = hit
        row[name + "_kind"] = got[hit][1]["kind"] if hit is not None else None
    b = _G["base"][p["id"]]
    row["known"] = bool(b["builtin_any"] or b["p17_any"] or b["s18"])
    return row


def main():
    out, setting = Path(sys.argv[1]), sys.argv[2]
    _G["variants"] = sys.argv[3].split(",") if len(sys.argv) > 3 else list(VARIANTS)
    trains, test, (base, fk, fv) = SETTINGS[setting]
    _G["base"] = {r["id"]: r for r in read_records(R / base)[1] if r.get(fk) == fv and "id" in r}
    lib = ST.StepLibrary()
    for f in trains:  # in order, per-project batches (as the DEV20 evaluation)
        by = collections.defaultdict(list)
        for r in read_records(R / f)[1]:
            by[r["repo"]].append((r["before"], r["after"], r["id"]))
        for repo, ex in by.items():
            lib.learn(ex, f"{Path(f).parent.name}/{Path(f).stem}:{repo}")
    _G["lib"] = lib
    t0 = time.time()
    with multiprocessing.get_context("fork").Pool(4) as pool:
        rows = list(pool.imap(score, read_records(R / test)[1], chunksize=1))
    summary = {"setting": setting, "problems": len(rows), "library": lib.summary(), "seconds": round(time.time() - t0)}
    for name in _G["variants"]:
        summary[name] = sum(r[name] is not None for r in rows)
        summary[name + "_new"] = sum(r[name] is not None and not r["known"] for r in rows)
        if name != "key" and "key" in _G["variants"]:
            summary[f"{name}_gains_vs_key"] = [r["id"] for r in rows if r[name] is not None and r["key"] is None]
            summary[f"{name}_losses_vs_key"] = [r["id"] for r in rows if r["key"] is not None and r[name] is None]
    with open(out, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
        fh.write(json.dumps({"summary": summary}) + "\n")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
