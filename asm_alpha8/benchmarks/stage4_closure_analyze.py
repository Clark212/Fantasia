"""Summarise stage4_closure.py runs: per arm, the goal, hazard and decline rates, probes, and the score of every episode
(goal +1, hazard -RISK, declined or timed out 0, minus the probe costs paid; RISK = the belief planner's default
risk_aversion). Paired differences (score: full - arm; hazard rate: arm - full) are averaged over worlds, with a 95% bootstrap interval (seeded).
Usage: python benchmarks/stage4_closure_analyze.py <run.jsonl> [<run.jsonl> ...] [--json=<out.json>]
"""
import json
import random
import sys
from pathlib import Path

RISK = 2.0
ARMS = ("full", "no_reliability", "no_dependency", "no_probe", "no_planning", "oracle")


def score(rec: dict, arm: str) -> float:
    eps, cost = rec["arms"][arm]["episodes"], rec["world"]["probe_cost"]
    pairs = [(eps[i], int(eps[i + 1])) for i in range(0, len(eps), 2)]
    return sum({"G": 1.0, "H": -RISK}.get(o, 0.0) - cost * p for o, p in pairs) / len(pairs)


def interval(xs: list, n: int = 10000) -> tuple:
    rnd, m = random.Random(0), len(xs)
    means = sorted(sum(rnd.choice(xs) for _ in range(m)) / m for _ in range(n))
    return round(means[int(0.025 * n)], 4), round(means[int(0.975 * n)], 4)


def summarise(recs: list) -> dict:
    out = {"worlds": len(recs), "arms": {}, "full_minus": {}, "hazard_minus_full": {}}
    for arm in ARMS:
        a = [r["arms"][arm] for r in recs]
        out["arms"][arm] = {k: round(sum(x[k] for x in a) / len(a), 4) for k in ("goal", "hazard", "other", "probes")}
        out["arms"][arm]["score"] = round(sum(score(r, arm) for r in recs) / len(recs), 4)
        out["arms"][arm]["worst_world_hazard"] = max(x["hazard"] for x in a)
    for arm in ARMS[1:]:
        d = [score(r, "full") - score(r, arm) for r in recs]
        out["full_minus"][arm] = {"mean": round(sum(d) / len(d), 4), "ci95": interval(d),
                                  "worlds_full_better": sum(x > 0 for x in d), "worlds_full_worse": sum(x < 0 for x in d)}
        h = [r["arms"][arm]["hazard"] - r["arms"]["full"]["hazard"] for r in recs]
        out["hazard_minus_full"][arm] = {"mean": round(sum(h) / len(h), 4), "ci95": interval(h),
                                         "worlds_full_safer": sum(x > 0 for x in h), "worlds_full_less_safe": sum(x < 0 for x in h)}
    return out


def main():
    recs = [json.loads(line) for f in sys.argv[1:] if not f.startswith("--") for line in Path(f).open() if line.strip()]
    recs.sort(key=lambda r: r["world"]["seed"])
    res = summarise(recs)
    res["with_copies"] = summarise([r for r in recs if r["world"]["copies"]])
    print(json.dumps(res, indent=1))
    target = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--json=")), None)
    if target:
        Path(target).write_text(json.dumps(res, indent=1) + "\n")


if __name__ == "__main__":
    main()
