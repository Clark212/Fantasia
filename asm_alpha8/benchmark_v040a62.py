from __future__ import annotations

import json
import random
import statistics
from pathlib import Path

from asm.evidence_lineage import EvidenceLineageGraph
from asm.planning import DiscreteBeliefState

R = 0.70
TRIALS = 20000
SEED = 12345


def likelihoods(observation: str, r: float = R) -> dict[str, float]:
    return {
        "A": r if observation == "A" else 1.0 - r,
        "B": r if observation == "B" else 1.0 - r,
    }


def choose_observation(rng: random.Random, truth: str, r: float = R) -> str:
    if rng.random() < r:
        return truth
    return "B" if truth == "A" else "A"


def summarize(rows: list[tuple[bool, float]]) -> dict[str, float]:
    accuracy = sum(1 for ok, _ in rows if ok) / len(rows)
    confidence = sum(conf for _, conf in rows) / len(rows)
    return {
        "trials": len(rows),
        "accuracy": accuracy,
        "mean_confidence": confidence,
        "calibration_gap_abs": abs(confidence - accuracy),
        "confidence_stddev": statistics.pstdev(conf for _, conf in rows),
    }


def baseline_shared(n: int = 9) -> dict[str, float]:
    rng = random.Random(SEED)
    rows = []
    for _ in range(TRIALS):
        truth = "A" if rng.random() < .5 else "B"
        obs = choose_observation(rng, truth)
        belief = DiscreteBeliefState.from_mapping({"A": .5, "B": .5})
        for _ in range(n):
            belief = belief.update(likelihoods(obs))
        pred, conf = belief.most_likely()
        rows.append((pred == truth, conf))
    return summarize(rows)


def lineage_shared(n: int = 9) -> dict[str, float]:
    rng = random.Random(SEED)
    rows = []
    for t in range(TRIALS):
        truth = "A" if rng.random() < .5 else "B"
        obs = choose_observation(rng, truth)
        belief = DiscreteBeliefState.from_mapping({"A": .5, "B": .5})
        graph = EvidenceLineageGraph(max_nodes=n + 1)
        root = f"t{t}:root"
        first = graph.register(root, source_id="camera")
        belief = belief.update_weighted(likelihoods(obs), evidence_weight=1.0, evidence_roots=first.roots)
        for i in range(1, n):
            record = graph.register(f"t{t}:copy{i}", source_id=f"relay{i}", parent_ids=[root])
            novelty = graph.novelty(belief.evidence_roots(), record.roots)
            belief = belief.update_weighted(likelihoods(obs), evidence_weight=novelty, evidence_roots=record.roots)
        pred, conf = belief.most_likely()
        rows.append((pred == truth, conf))
    return summarize(rows)


def independent(lineage: bool, n: int = 9) -> dict[str, float]:
    rng = random.Random(SEED)
    rows = []
    for t in range(TRIALS):
        truth = "A" if rng.random() < .5 else "B"
        belief = DiscreteBeliefState.from_mapping({"A": .5, "B": .5})
        graph = EvidenceLineageGraph(max_nodes=n + 1)
        for i in range(n):
            obs = choose_observation(rng, truth)
            if lineage:
                record = graph.register(f"t{t}:e{i}", source_id=f"s{i}")
                novelty = graph.novelty(belief.evidence_roots(), record.roots)
                belief = belief.update_weighted(likelihoods(obs), evidence_weight=novelty, evidence_roots=record.roots)
            else:
                belief = belief.update(likelihoods(obs))
        pred, conf = belief.most_likely()
        rows.append((pred == truth, conf))
    return summarize(rows)


def three_roots_repeated(lineage: bool) -> dict[str, float]:
    rng = random.Random(SEED)
    rows = []
    for t in range(TRIALS):
        truth = "A" if rng.random() < .5 else "B"
        belief = DiscreteBeliefState.from_mapping({"A": .5, "B": .5})
        graph = EvidenceLineageGraph(max_nodes=16)
        for group in range(3):
            obs = choose_observation(rng, truth)
            root = f"t{t}:r{group}"
            if lineage:
                rec = graph.register(root, source_id=f"sensor{group}")
                belief = belief.update_weighted(likelihoods(obs), evidence_weight=1.0, evidence_roots=rec.roots)
                for copy in range(2):
                    rec = graph.register(f"t{t}:g{group}:c{copy}", source_id="relay", parent_ids=[root])
                    novelty = graph.novelty(belief.evidence_roots(), rec.roots)
                    belief = belief.update_weighted(likelihoods(obs), evidence_weight=novelty, evidence_roots=rec.roots)
            else:
                for _ in range(3):
                    belief = belief.update(likelihoods(obs))
        pred, conf = belief.most_likely()
        rows.append((pred == truth, conf))
    return summarize(rows)


def copy_depth_torture() -> list[dict[str, float]]:
    out = []
    for depth in (1, 2, 3, 5, 9, 16, 32, 64):
        graph = EvidenceLineageGraph(max_nodes=depth + 2)
        belief = DiscreteBeliefState.from_mapping({"A": .5, "B": .5})
        root = graph.register("root", source_id="camera")
        belief = belief.update_weighted(likelihoods("A"), evidence_weight=1.0, evidence_roots=root.roots)
        previous = "root"
        for i in range(1, depth):
            eid = f"copy{i}"
            rec = graph.register(eid, source_id=f"relay{i}", parent_ids=[previous])
            novelty = graph.novelty(belief.evidence_roots(), rec.roots)
            belief = belief.update_weighted(likelihoods("A"), evidence_weight=novelty, evidence_roots=rec.roots)
            previous = eid
        out.append({"depth": depth, "posterior_A": belief.as_dict()["A"], "root_count": len(belief.evidence_roots())})
    return out


def random_independence_equivalence(sequences: int = 1000, length: int = 20) -> dict[str, float]:
    rng = random.Random(98765)
    max_error = 0.0
    exact_rank_matches = 0
    for s in range(sequences):
        ordinary = DiscreteBeliefState.from_mapping({"A": .5, "B": .5})
        lineaged = DiscreteBeliefState.from_mapping({"A": .5, "B": .5})
        graph = EvidenceLineageGraph(max_nodes=length + 1)
        for i in range(length):
            obs = "A" if rng.random() < .5 else "B"
            r = rng.uniform(.500001, .999999)
            likes = likelihoods(obs, r)
            ordinary = ordinary.update(likes)
            rec = graph.register(f"s{s}:e{i}", source_id=f"sensor{i}")
            novelty = graph.novelty(lineaged.evidence_roots(), rec.roots)
            lineaged = lineaged.update_weighted(likes, evidence_weight=novelty, evidence_roots=rec.roots)
        err = max(abs(ordinary.as_dict()[h] - lineaged.as_dict()[h]) for h in ("A", "B"))
        max_error = max(max_error, err)
        if ordinary.most_likely()[0] == lineaged.most_likely()[0]:
            exact_rank_matches += 1
    return {
        "sequences": sequences,
        "length": length,
        "max_probability_error": max_error,
        "decision_rank_matches": exact_rank_matches,
    }


def main() -> None:
    results = {
        "shared_9_before": baseline_shared(9),
        "shared_9_after": lineage_shared(9),
        "independent_9_before": independent(False, 9),
        "independent_9_after": independent(True, 9),
        "three_roots_x3_before": three_roots_repeated(False),
        "three_roots_x3_after": three_roots_repeated(True),
        "copy_depth_torture": copy_depth_torture(),
        "independent_equivalence": random_independence_equivalence(),
    }
    print(json.dumps(results, indent=2, sort_keys=True))
    Path("ALPHA62_BEFORE_AFTER.json").write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
