"""DEV29 analysis of the evaluation records: the pre-registration's reported-not-gated items.
The two arms are identical through phases 1 and 2. When the control ends 'unresolved' (both phases exhausted inside the
budget) the learned arm reaches phase 3. Its extra rejected candidates are phase 3's; the records do not mark phases.
Usage: python benchmarks/dev29_analysis.py <dir with dev29_evaluate_*of*.jsonl> [<DEV15 results dir>]
"""
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from asm.coding.integrity import read_records  # noqa: E402


def main():
    work = Path(sys.argv[1])
    dev15 = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "benchmarks" / "results" / "dev15"
    by = collections.defaultdict(dict)
    for f in sorted(work.glob("dev29_evaluate_*of*.jsonl")):
        for r in read_records(f)[1]:
            if "mode" in r:
                by[(r["project"], r["bug"])][r["mode"]] = r
    old = {(r["project"], r["bug"]): r for f in sorted(dev15.glob("realbugs_eval_*.jsonl")) for r in read_records(f)[1] if r.get("project")}
    pairs = {k: v for k, v in by.items() if len(v) == 2}
    out = {"bugs": len(pairs), "status": {m: dict(collections.Counter(v[m]["status"] for v in pairs.values())) for m in ("control", "learned")},
           "status_pairs": dict(collections.Counter(f"{v['control']['status']} -> {v['learned']['status']}" for v in pairs.values())),
           "best_rank": dict(collections.Counter(str(v["control"].get("best_rank")) for v in pairs.values())),
           "control_vs_dev15": dict(collections.Counter(f"{old[k]['status']} -> {v['control']['status']}" for k, v in pairs.items() if k in old))}
    tried = lambda r: sum((r.get("rejected_by_reason") or {}).values()) + (r["status"] == "resolved")  # noqa: E731
    reached = {k: tried(v["learned"]) - tried(v["control"]) for k, v in pairs.items() if v["control"]["status"] == "unresolved"}
    out["phase3"] = {"reached (control unresolved)": len(reached),
                     "learned outcome there": dict(collections.Counter(pairs[k]["learned"]["status"] for k in reached)),
                     "phase-3 candidates tried, median": sorted(reached.values())[len(reached) // 2] if reached else None,
                     "phase-3 candidates tried, range": [min(reached.values()), max(reached.values())] if reached else None,
                     "not reached: control status": dict(collections.Counter(v["control"]["status"] for k, v in pairs.items() if k not in reached))}
    out["accepted"] = [{"bug": f"{k[0]}-{k[1]}", "mode": m, "status": v[m]["status"], "family": (v[m].get("families") or [None])[0],
                        "desc": v[m].get("desc"), "oracle_class": v[m].get("oracle_class"),
                        "same_patch_as_dev15": v[m].get("asm_diff") == old.get(k, {}).get("asm_diff"),
                        "dev15_status": old.get(k, {}).get("status")}
                       for k, v in sorted(pairs.items()) for m in ("control", "learned") if v[m]["status"] in ("resolved", "partial")]
    out["seconds"] = {m: {"repair_mean": round(sum(v[m].get("repair_seconds", 0) for v in pairs.values()) / max(1, len(pairs)), 1),
                          "at_budget": sum(v[m]["status"] == "time_budget" for v in pairs.values())} for m in ("control", "learned")}
    out["projects"] = {p: {m: dict(collections.Counter(v[m]["status"] for k, v in pairs.items() if k[0] == p)) for m in ("control", "learned")}
                       for p in sorted({k[0] for k in pairs})}
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
