"""DEV31 analysis of the fresh evaluation: the pre-registration's reported-not-gated items. With phase3_seconds the learned
arm reaches phase 3 whenever phases 1-2 accept nothing after trying candidates (also when they ran out of time); its
extra candidates over the paired control are phase 3's (the records do not mark phases).
Usage: python benchmarks/dev31_analysis.py <work_dir>
"""
import collections
import json
import statistics
import sys
from pathlib import Path

import dev31_realbugs as D


def main():
    work = Path(sys.argv[1])
    extra = D.records(work, "dev31_time_control.jsonl")
    by = {k: {**v, **extra.get(k, {})} for k, v in D.records(work, "dev31_control_learned_*of*.jsonl").items()}
    pairs = {k: v for k, v in by.items() if {"control", "learned"} <= set(v)}
    tried = lambda r: sum((r.get("rejected_by_reason") or {}).values()) + (r["status"] == "resolved")  # noqa: E731
    reached = {k: tried(v["learned"]) - tried(v["control"]) for k, v in pairs.items()
               if v["control"]["status"] in ("unresolved", "time_budget") and tried(v["control"]) > 0}
    secs = sorted(v["learned"]["repair_seconds"] for v in pairs.values() if "repair_seconds" in v["learned"])
    res = {m: {k for k, v in by.items() if v.get(m, {}).get("status") == "resolved"} for m in D.ARMS}
    out = {"bugs": len(pairs),
           "status": {m: dict(collections.Counter(v[m]["status"] for v in pairs.values())) for m in ("control", "learned")},
           "status_pairs": dict(collections.Counter(f"{v['control']['status']} -> {v['learned']['status']}" for v in pairs.values())),
           "no_spectrum_reasons": dict(collections.Counter(v["control"].get("reason") for v in pairs.values() if v["control"]["status"] == "no_spectrum")),
           "best_rank": dict(collections.Counter(str(v["control"].get("best_rank")) for v in pairs.values())),
           "phase3": {"reached": len(reached), "by_project": dict(collections.Counter(k[0] for k in reached)),
                      "candidates_tested_median": statistics.median(reached.values()) if reached else None,
                      "none_tested": sum(n <= 0 for n in reached.values()),
                      "learned_outcome": dict(collections.Counter(pairs[k]["learned"]["status"] for k in reached))},
           "learned_seconds": {"median": statistics.median(secs), "max": secs[-1], "over_300": sum(s > 300 for s in secs),
                               "over_360": sum(s > 360 for s in secs)} if secs else None,
           "resolved": {m: sorted(f"{k[0]}-{k[1]}" for k in res[m]) for m in D.ARMS},
           "learned_only": sorted(f"{k[0]}-{k[1]}" for k in res["learned"] - res["control"]),
           "control_only": sorted(f"{k[0]}-{k[1]}" for k in res["control"] - res["learned"]),
           "projects": {p: {m: dict(collections.Counter(v[m]["status"] for k, v in pairs.items() if k[0] == p)) for m in ("control", "learned")}
                        for p in sorted({k[0] for k in pairs})}}
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
