from __future__ import annotations

import copy
import random
import tempfile
import unittest
from pathlib import Path

from asm import ASMConfig, ASMEngine, EvidenceDependencyModel, __version__


def flip(x: str) -> str:
    return "B" if x == "A" else "A"


def sense(rng: random.Random, truth: str, reliability: float = 0.7) -> str:
    return truth if rng.random() < reliability else flip(truth)


def repeated_sequence(rng: random.Random, truth: str, correlated: bool) -> list[str]:
    if correlated:
        x = sense(rng, truth)
        return [x] * 9
    return [sense(rng, truth) for _ in range(9)]


class Alpha71DependencyRegimeTests(unittest.TestCase):
    def test_01_version(self):
        self.assertEqual(__version__, "0.4.0-alpha.7.9")

    def test_02_non_temporal_preserves_alpha7_cumulative_semantics(self):
        rng = random.Random(101)
        model = EvidenceDependencyModel()
        for t in range(600):
            truth = "A" if rng.random() < 0.5 else "B"
            obs = sense(rng, truth)
            model.observe_trial(str(t), resolved_hypothesis=truth, observations={"s": [obs] * 9})
        status = model.self_dependency("s")
        self.assertEqual(status["view"], "cumulative")
        self.assertEqual(status["regime_count"], 0)
        self.assertGreater(status["active_correlation"], 0.99)

    def test_03_temporal_index_must_increase_and_failure_is_atomic(self):
        model = EvidenceDependencyModel()
        model.observe_trial("a", resolved_hypothesis="A", observations={"s": ["A", "A"]}, temporal_index=10)
        before = copy.deepcopy(model.export_state())
        with self.assertRaises(ValueError):
            model.observe_trial("b", resolved_hypothesis="A", observations={"s": ["A", "A"]}, temporal_index=10)
        self.assertEqual(before, model.export_state())
        with self.assertRaises(ValueError):
            model.observe_trial("c", resolved_hypothesis="A", observations={"s": ["A", "A"]}, temporal_index=float("nan"))
        self.assertEqual(before, model.export_state())

    def test_04_correlated_to_independent_uses_recent_view(self):
        rng = random.Random(102)
        model = EvidenceDependencyModel()
        idx = 0
        for corr in (True, False):
            for t in range(500):
                truth = "A" if rng.random() < 0.5 else "B"; idx += 1
                model.observe_trial(f"{corr}-{t}", resolved_hypothesis=truth,
                                    observations={"s": repeated_sequence(rng, truth, corr)}, temporal_index=idx)
        status = model.self_dependency("s")
        self.assertEqual(status["view"], "recent")
        self.assertEqual(status["active_correlation"], 0.0)
        self.assertGreater(status["cumulative_active_correlation"], 0.25)
        self.assertGreaterEqual(len(model.dependency_regimes("s")), 2)

    def test_05_independent_to_correlated_uses_recent_view(self):
        rng = random.Random(103)
        model = EvidenceDependencyModel()
        idx = 0
        for corr in (False, True):
            for t in range(500):
                truth = "A" if rng.random() < 0.5 else "B"; idx += 1
                model.observe_trial(f"{corr}-{t}", resolved_hypothesis=truth,
                                    observations={"s": repeated_sequence(rng, truth, corr)}, temporal_index=idx)
        status = model.self_dependency("s")
        self.assertEqual(status["view"], "recent")
        self.assertGreater(status["active_correlation"], 0.99)
        self.assertGreaterEqual(len(model.dependency_regimes("s")), 2)

    def test_06_full_reversal_preserves_three_regimes(self):
        rng = random.Random(104)
        model = EvidenceDependencyModel(); idx = 0
        for phase, corr in enumerate((True, False, True)):
            for t in range(400):
                truth = "A" if rng.random() < 0.5 else "B"; idx += 1
                model.observe_trial(f"{phase}-{t}", resolved_hypothesis=truth,
                                    observations={"s": repeated_sequence(rng, truth, corr)}, temporal_index=idx)
        regimes = model.dependency_regimes("s")
        self.assertEqual(len(regimes), 3)
        self.assertEqual([r["label"] for r in regimes], ["dependent", "independent_or_unproven", "dependent"])

    def test_07_schema1_migration_preserves_cumulative_without_fake_temporal_history(self):
        rng = random.Random(105)
        old = EvidenceDependencyModel()
        for t in range(300):
            truth = "A" if rng.random() < 0.5 else "B"
            x = sense(rng, truth)
            old.observe_trial(str(t), resolved_hypothesis=truth, observations={"s": [x] * 9})
        payload = old.export_state()
        payload["schema"] = 1
        payload.pop("temporal", None)
        before = old.self_dependency("s")["cumulative_raw_correlation"]
        new = EvidenceDependencyModel(); new.import_state(payload)
        self.assertEqual(new.stats()["trials"], 300)
        self.assertEqual(new.dependency_regimes("s"), [])
        self.assertEqual(new.stats()["temporal_self_views"], 0)
        self.assertEqual(before, new.self_dependency("s")["cumulative_raw_correlation"])

    def test_08_schema2_roundtrip_preserves_temporal_regimes(self):
        rng = random.Random(106)
        a = EvidenceDependencyModel(); idx = 0
        for corr in (True, False):
            for t in range(300):
                truth = "A" if rng.random() < 0.5 else "B"; idx += 1
                a.observe_trial(f"{corr}-{t}", resolved_hypothesis=truth,
                                observations={"s": repeated_sequence(rng, truth, corr)}, temporal_index=idx)
        b = EvidenceDependencyModel(); b.import_state(a.export_state())
        self.assertEqual(a.stats(), b.stats())
        self.assertEqual(a.dependency_regimes("s"), b.dependency_regimes("s"))
        self.assertEqual(a.self_dependency("s"), b.self_dependency("s"))

    def test_09_inference_never_trains_dependency_model(self):
        with tempfile.TemporaryDirectory() as td:
            e = ASMEngine(Path(td) / "x.db", config=ASMConfig(snapshot_every_events=999999, prune_every_events=999999))
            before = e.evidence_dependency.version
            evidence = [{"source_id": "s", "observation": "A", "supplied_reliability": 0.7} for _ in range(9)]
            for _ in range(20):
                e.update_belief_from_evidence_batch({"A": 0.5, "B": 0.5}, evidence=evidence)
            self.assertEqual(before, e.evidence_dependency.version)
            e.close(save_snapshot=False)

    def test_10_capacity_failure_has_no_partial_mutation(self):
        model = EvidenceDependencyModel(max_sources=1)
        before = copy.deepcopy(model.export_state())
        with self.assertRaises(RuntimeError):
            model.observe_trial("x", resolved_hypothesis="A", observations={"a": ["A"], "b": ["A"]}, temporal_index=1)
        self.assertEqual(before, model.export_state())

    def test_11_engine_temporal_snapshot_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "x.db"
            cfg = ASMConfig(snapshot_every_events=999999, prune_every_events=999999)
            e = ASMEngine(path, config=cfg); rng = random.Random(107)
            for t in range(160):
                truth = "A" if rng.random() < 0.5 else "B"; x = sense(rng, truth)
                e.observe_evidence_dependency_trial(str(t), resolved_hypothesis=truth,
                                                    observations={"s": [x] * 9}, temporal_index=t + 1)
            before_status = e.evidence_dependency_status("s")
            before_regimes = e.evidence_dependency_regimes("s")
            e.save(); e.close(save_snapshot=False)
            r = ASMEngine(path, config=cfg)
            self.assertEqual(before_status, r.evidence_dependency_status("s"))
            self.assertEqual(before_regimes, r.evidence_dependency_regimes("s"))
            r.close(save_snapshot=False)


if __name__ == "__main__":
    unittest.main()
