from __future__ import annotations

import json
import math
import random
import statistics
from dataclasses import dataclass, asdict
from typing import Callable

from asm.adaptive_evidence import AdaptiveEvidenceModel
from asm.planning import DiscreteBeliefState

SEED = 4060
EPISODES = 6000
CLUES = 9
TAIL = 1500
EPS = 1e-15


def obs_from_state(rng: random.Random, state: str, reliability: float) -> str:
    return state if rng.random() < reliability else ("B" if state == "A" else "A")


def infer(seq: list[str], reliability: float) -> tuple[str, float]:
    b = DiscreteBeliefState.from_mapping({"A": 0.5, "B": 0.5})
    for obs in seq:
        if obs == "A":
            likes = {"A": reliability, "B": 1.0 - reliability}
        else:
            likes = {"A": 1.0 - reliability, "B": reliability}
        b = b.update(likes)
    probs = b.as_dict()
    pred = max(probs, key=probs.get)
    return pred, float(probs[pred])


@dataclass
class Metrics:
    accuracy: float
    mean_confidence: float
    calibration_gap: float
    brier: float
    wrong_confidence: float


def metrics(rows: list[tuple[bool, float]]) -> Metrics:
    acc = statistics.fmean(1.0 if ok else 0.0 for ok, _ in rows)
    conf = statistics.fmean(c for _, c in rows)
    brier = statistics.fmean((c - (1.0 if ok else 0.0)) ** 2 for ok, c in rows)
    wrong = [c for ok, c in rows if not ok]
    return Metrics(acc, conf, abs(conf - acc), brier, statistics.fmean(wrong) if wrong else 0.0)


def stationary(true_r: float):
    def gen(rng: random.Random, ep: int, state: str) -> list[str]:
        return [obs_from_state(rng, state, true_r) for _ in range(CLUES)]
    return gen


def drift_90_to_60(rng: random.Random, ep: int, state: str) -> list[str]:
    r = 0.9 if ep < EPISODES // 2 else 0.6
    return [obs_from_state(rng, state, r) for _ in range(CLUES)]


def flip_90_to_10(rng: random.Random, ep: int, state: str) -> list[str]:
    r = 0.9 if ep < EPISODES // 2 else 0.1
    return [obs_from_state(rng, state, r) for _ in range(CLUES)]


def correlated_70(rng: random.Random, ep: int, state: str) -> list[str]:
    base = obs_from_state(rng, state, 0.7)
    return [base] * CLUES


SCENARIOS: list[tuple[str, float, Callable[[random.Random, int, str], list[str]]]] = [
    ("matched70", 0.7, stationary(0.7)),
    ("true70_model90", 0.9, stationary(0.7)),
    ("true90_model70", 0.7, stationary(0.9)),
    ("antiinformative20_model90", 0.9, stationary(0.2)),
    ("drift90_to60_model90", 0.9, drift_90_to_60),
    ("flip90_to10_model90", 0.9, flip_90_to_10),
    ("correlated70_model70", 0.7, correlated_70),
]


def run_one(name: str, supplied_r: float, gen) -> dict:
    rng = random.Random(SEED + sum(ord(c) for c in name))
    adaptive = AdaptiveEvidenceModel(prior_strength=4.0)
    fixed_rows: list[tuple[bool, float]] = []
    adaptive_rows: list[tuple[bool, float]] = []
    reliability_trace = []
    for ep in range(EPISODES):
        truth = "A" if rng.random() < 0.5 else "B"
        seq = gen(rng, ep, truth)
        fixed_pred, fixed_conf = infer(seq, supplied_r)
        learned_r = adaptive.reliability("sensor", supplied_reliability=supplied_r)
        adaptive_pred, adaptive_conf = infer(seq, learned_r)
        fixed_rows.append((fixed_pred == truth, fixed_conf))
        adaptive_rows.append((adaptive_pred == truth, adaptive_conf))
        # Ground truth becomes available only after the episode is resolved.
        for obs in seq:
            adaptive.observe_resolved(
                "sensor", observation=obs, resolved_hypothesis=truth,
                supplied_reliability=supplied_r,
            )
        if ep in (0, 99, 999, EPISODES//2-1, EPISODES//2+99, EPISODES-1):
            reliability_trace.append({"episode": ep+1, "reliability": adaptive.reliability("sensor", supplied_reliability=supplied_r)})
    f_all, a_all = metrics(fixed_rows), metrics(adaptive_rows)
    f_tail, a_tail = metrics(fixed_rows[-TAIL:]), metrics(adaptive_rows[-TAIL:])
    return {
        "name": name,
        "supplied_reliability": supplied_r,
        "learned_final_reliability": adaptive.reliability("sensor", supplied_reliability=supplied_r),
        "source_status": adaptive.status("sensor", supplied_reliability=supplied_r),
        "fixed_all": asdict(f_all),
        "adaptive_all": asdict(a_all),
        "fixed_tail": asdict(f_tail),
        "adaptive_tail": asdict(a_tail),
        "reliability_trace": reliability_trace,
    }


results = [run_one(*spec) for spec in SCENARIOS]
out = {
    "benchmark": "alpha.6 online evidence-source reliability learning",
    "seed": SEED,
    "episodes": EPISODES,
    "clues_per_episode": CLUES,
    "tail_window": TAIL,
    "update_rule": "source reliability is updated only after externally resolved episode truth",
    "results": results,
}
with open("results/planning_v040a6_adaptive_evidence.json", "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2)

print(f"episodes={EPISODES} clues={CLUES} tail={TAIL}")
print(f"{'scenario':28} {'learned':>8} | {'fixed acc':>9} {'fixed conf':>10} {'gap':>8} | {'adapt acc':>9} {'adapt conf':>10} {'gap':>8}")
for r in results:
    f = r['fixed_tail']; a = r['adaptive_tail']
    print(f"{r['name']:28} {r['learned_final_reliability']*100:8.2f} | {f['accuracy']*100:9.2f} {f['mean_confidence']*100:10.2f} {f['calibration_gap']*100:8.2f} | {a['accuracy']*100:9.2f} {a['mean_confidence']*100:10.2f} {a['calibration_gap']*100:8.2f}")
