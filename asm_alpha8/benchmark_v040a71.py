from __future__ import annotations

import json
import random
import statistics
from asm.evidence_dependency import EvidenceDependencyModel
from asm.planning import DiscreteBeliefState

SEED = 4710
TRAIN_PHASE = 1000
EVAL = 10000
CLUES = 9


def flip(x: str) -> str:
    return "B" if x == "A" else "A"


def sense(rng: random.Random, truth: str, reliability: float = 0.7) -> str:
    return truth if rng.random() < reliability else flip(truth)


def make_seq(rng: random.Random, truth: str, correlated: bool) -> list[str]:
    if correlated:
        x = sense(rng, truth)
        return [x] * CLUES
    return [sense(rng, truth) for _ in range(CLUES)]


def infer(seq: list[str], dep: EvidenceDependencyModel) -> tuple[str, float]:
    belief = DiscreteBeliefState.from_mapping({"A": 0.5, "B": 0.5})
    scale = dep.effective_batch(["s"] * CLUES)["scale"]
    for obs in seq:
        likes = {"A": 0.7 if obs == "A" else 0.3, "B": 0.7 if obs == "B" else 0.3}
        belief = belief.update_weighted(likes, evidence_weight=scale)
    posterior = belief.as_dict(); pred = max(posterior, key=posterior.get)
    return pred, float(posterior[pred])


def train(first_corr: bool, second_corr: bool, seed: int, temporal: bool) -> EvidenceDependencyModel:
    rng = random.Random(seed); model = EvidenceDependencyModel(); idx = 0
    for phase, corr in enumerate((first_corr, second_corr)):
        for t in range(TRAIN_PHASE):
            truth = "A" if rng.random() < 0.5 else "B"; idx += 1
            kw = {"temporal_index": idx} if temporal else {}
            model.observe_trial(f"{phase}-{t}", resolved_hypothesis=truth,
                                observations={"s": make_seq(rng, truth, corr)}, **kw)
    return model


def evaluate(model: EvidenceDependencyModel, corr: bool, seed: int) -> dict:
    rng = random.Random(seed); rows = []
    for _ in range(EVAL):
        truth = "A" if rng.random() < 0.5 else "B"
        pred, conf = infer(make_seq(rng, truth, corr), model)
        rows.append((pred == truth, conf))
    acc = statistics.fmean(ok for ok, _ in rows)
    conf = statistics.fmean(c for _, c in rows)
    return {"accuracy": acc, "confidence": conf, "calibration_gap": abs(acc - conf)}


def case(first: bool, second: bool, seed: int) -> dict:
    before_model = train(first, second, seed, temporal=False)
    after_model = train(first, second, seed, temporal=True)
    eval_seed = seed + 9999
    return {
        "before_alpha7_cumulative": evaluate(before_model, second, eval_seed),
        "after_alpha71_temporal": evaluate(after_model, second, eval_seed),
        "before_status": before_model.self_dependency("s"),
        "after_status": after_model.self_dependency("s"),
        "regimes": after_model.dependency_regimes("s"),
    }


def detection_latency(first: bool, second: bool, seed: int) -> int | None:
    rng = random.Random(seed); model = EvidenceDependencyModel(); idx = 0
    for t in range(500):
        truth = "A" if rng.random() < 0.5 else "B"; idx += 1
        model.observe_trial(f"0-{t}", resolved_hypothesis=truth,
                            observations={"s": make_seq(rng, truth, first)}, temporal_index=idx)
    base = len(model.dependency_regimes("s"))
    for t in range(1, 201):
        truth = "A" if rng.random() < 0.5 else "B"; idx += 1
        model.observe_trial(f"1-{t}", resolved_hypothesis=truth,
                            observations={"s": make_seq(rng, truth, second)}, temporal_index=idx)
        if len(model.dependency_regimes("s")) > base:
            return t
    return None


def reversal(seed: int) -> bool:
    rng = random.Random(seed); model = EvidenceDependencyModel(); idx = 0
    for phase, corr in enumerate((True, False, True)):
        for t in range(500):
            truth = "A" if rng.random() < 0.5 else "B"; idx += 1
            model.observe_trial(f"{phase}-{t}", resolved_hypothesis=truth,
                                observations={"s": make_seq(rng, truth, corr)}, temporal_index=idx)
    regs = model.dependency_regimes("s")
    return len(regs) == 3 and [r["label"] for r in regs] == [
        "dependent", "independent_or_unproven", "dependent"
    ]


c2i = case(True, False, 7001)
i2c = case(False, True, 7002)
lat_c2i = [detection_latency(True, False, 10000 + i) for i in range(20)]
lat_i2c = [detection_latency(False, True, 11000 + i) for i in range(20)]
rev = [reversal(12000 + i) for i in range(20)]

checks = {
    "c2i_baseline_failure_reproduced": c2i["before_alpha7_cumulative"]["calibration_gap"] > 0.15,
    "c2i_after_gap_below_1pct": c2i["after_alpha71_temporal"]["calibration_gap"] < 0.01,
    "c2i_decision_accuracy_preserved": abs(c2i["before_alpha7_cumulative"]["accuracy"] - c2i["after_alpha71_temporal"]["accuracy"]) < 1e-15,
    "i2c_baseline_failure_reproduced": i2c["before_alpha7_cumulative"]["calibration_gap"] > 0.20,
    "i2c_after_gap_below_1pct": i2c["after_alpha71_temporal"]["calibration_gap"] < 0.01,
    "i2c_decision_accuracy_preserved": abs(i2c["before_alpha7_cumulative"]["accuracy"] - i2c["after_alpha71_temporal"]["accuracy"]) < 1e-15,
    "detection_20_of_20_both_directions": all(x is not None for x in lat_c2i + lat_i2c),
    "reversal_20_of_20_three_regimes": all(rev),
}

out = {
    "benchmark": "ASM v0.4.0-alpha.7.1 dependency regime learning",
    "cases": {"correlated_to_independent": c2i, "independent_to_correlated": i2c},
    "detection": {
        "correlated_to_independent": {"values": lat_c2i, "mean": statistics.fmean(x for x in lat_c2i if x is not None)},
        "independent_to_correlated": {"values": lat_i2c, "mean": statistics.fmean(x for x in lat_i2c if x is not None)},
    },
    "reversal": {"passed": sum(rev), "total": len(rev)},
    "checks": checks, "passed": sum(checks.values()), "total": len(checks),
}
print(json.dumps(out, indent=2, sort_keys=True))
open("ALPHA71_BEFORE_AFTER.json", "w").write(json.dumps(out, indent=2, sort_keys=True) + "\n")
if not all(checks.values()):
    raise SystemExit(1)
