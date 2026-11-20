from __future__ import annotations

import importlib.util
import json
import math
import random
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASELINE_FILE = ROOT.parent / "ASM_v0.4.0-alpha.6" / "asm" / "adaptive_evidence.py"


def load_baseline():
    spec = importlib.util.spec_from_file_location("asm_alpha6_adaptive_evidence_baseline", BASELINE_FILE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.AdaptiveEvidenceModel


def sample_case(rng: random.Random, reliability: float):
    truth = "A" if rng.random() < 0.5 else "B"
    correct = rng.random() < reliability
    obs = truth if correct else ("B" if truth == "A" else "A")
    return truth, obs


def run_seed(seed: int, schedule: list[float]):
    from asm.adaptive_evidence import AdaptiveEvidenceModel
    Baseline = load_baseline()
    old = Baseline(prior_strength=4.0)
    new = AdaptiveEvidenceModel(prior_strength=4.0, drift_window=32,
                                drift_min_abs_change=.25, drift_min_zscore=3.0)
    rng = random.Random(seed)
    rows = []
    first_cross = None
    for i, true_r in enumerate(schedule):
        truth, obs = sample_case(rng, true_r)
        # Prediction uses the estimate available before external resolution.
        old_r = old.reliability("s", supplied_reliability=.9)
        new_r = new.reliability("s", supplied_reliability=.9)
        old_pred = obs if old_r >= .5 else ("B" if obs == "A" else "A")
        new_pred = obs if new_r >= .5 else ("B" if obs == "A" else "A")
        rows.append({
            "i": i, "true_r": true_r,
            "old_r": old_r, "new_r": new_r,
            "old_correct": int(old_pred == truth), "new_correct": int(new_pred == truth),
        })
        old.observe_resolved("s", observation=obs, resolved_hypothesis=truth, supplied_reliability=.9)
        new.observe_resolved("s", observation=obs, resolved_hypothesis=truth, supplied_reliability=.9,
                             temporal_index=i)
        if first_cross is None and i >= 500 and new.reliability("s", supplied_reliability=.9) < .5:
            first_cross = i - 500 + 1
    status = new.status("s", supplied_reliability=.9)
    tail = rows[-200:]
    return {
        "seed": seed,
        "old_tail_accuracy": sum(r["old_correct"] for r in tail)/len(tail),
        "new_tail_accuracy": sum(r["new_correct"] for r in tail)/len(tail),
        "old_tail_calibration_gap": sum(abs(r["old_r"] - r["true_r"]) for r in tail)/len(tail),
        "new_tail_calibration_gap": sum(abs(r["new_r"] - r["true_r"]) for r in tail)/len(tail),
        "old_final_r": rows[-1]["old_r"],
        "new_final_r": rows[-1]["new_r"],
        "new_regimes": status["regime_count"],
        "new_recovery_to_below_half": first_cross,
    }


def aggregate(runs):
    keys = [k for k in runs[0] if k not in {"seed", "new_recovery_to_below_half"}]
    out = {k: statistics.mean(r[k] for r in runs) for k in keys}
    rec = [r["new_recovery_to_below_half"] for r in runs if r["new_recovery_to_below_half"] is not None]
    out["new_recovery_to_below_half_mean"] = statistics.mean(rec) if rec else None
    out["recovered_seeds"] = len(rec)
    return out


def stationary_seed(seed: int):
    from asm.adaptive_evidence import AdaptiveEvidenceModel
    rng = random.Random(seed)
    m = AdaptiveEvidenceModel(prior_strength=4.0, drift_window=32,
                              drift_min_abs_change=.25, drift_min_zscore=3.0)
    for i in range(2000):
        truth, obs = sample_case(rng, .7)
        m.observe_resolved("s", observation=obs, resolved_hypothesis=truth,
                           supplied_reliability=.9, temporal_index=i)
    status = m.status("s", supplied_reliability=.9)
    return {"regimes": status["regime_count"], "effective_r": status["effective_reliability"]}


def main():
    abrupt = [.9] * 500 + [.1] * 500
    gradual = [.9] * 300 + [max(.55, .9 - .35 * (i / 699.0)) for i in range(700)]
    flip_runs = [run_seed(seed, abrupt) for seed in range(30)]
    gradual_runs = [run_seed(seed + 100, gradual) for seed in range(30)]
    stationary = [stationary_seed(seed + 1000) for seed in range(50)]
    result = {
        "abrupt_90_to_10": aggregate(flip_runs),
        "gradual_90_to_55": aggregate(gradual_runs),
        "stationary_70": {
            "seeds": len(stationary),
            "false_split_seeds": sum(1 for r in stationary if r["regimes"] > 1),
            "mean_regimes": statistics.mean(r["regimes"] for r in stationary),
            "mean_effective_r": statistics.mean(r["effective_r"] for r in stationary),
        },
        "raw_abrupt": flip_runs,
        "raw_gradual": gradual_runs,
        "claim": "Measured against the actual alpha.6 AdaptiveEvidenceModel on identical generated streams.",
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
