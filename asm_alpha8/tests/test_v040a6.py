from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path

from asm import ASMConfig, ASMEngine, __version__
from asm.adaptive_evidence import AdaptiveEvidenceModel
from asm.planning import DiscreteBeliefState


class Alpha6AdaptiveEvidenceTests(unittest.TestCase):
    def test_version(self):
        self.assertEqual(__version__, "0.4.0-alpha.7.9")

    def test_stationary_wrong_prior_calibrates_toward_resolved_truth(self):
        m = AdaptiveEvidenceModel(prior_strength=4.0)
        for _ in range(700):
            m.observe_resolved("sensor", observation="A", resolved_hypothesis="A", supplied_reliability=0.9)
        for _ in range(300):
            m.observe_resolved("sensor", observation="B", resolved_hypothesis="A", supplied_reliability=0.9)
        status = m.status("sensor", supplied_reliability=0.9)
        self.assertAlmostEqual(status["reliability"], 0.7, delta=0.003)
        self.assertGreater(status["model_mismatch_abs"], 0.19)

    def test_inference_does_not_self_train_source(self):
        m = AdaptiveEvidenceModel(prior_strength=4.0)
        before = m.status("s", supplied_reliability=0.8)
        b = DiscreteBeliefState.from_mapping({"A": 0.5, "B": 0.5})
        for _ in range(100):
            b = b.update(m.likelihoods("s", observation="A", hypotheses=b.hypothesis_names(), supplied_reliability=0.8))
        after = m.status("s", supplied_reliability=0.8)
        self.assertEqual(before["resolved_observations"], after["resolved_observations"])
        self.assertEqual(before["reliability"], after["reliability"])

    def test_anti_informative_source_can_be_learned_below_half(self):
        m = AdaptiveEvidenceModel(prior_strength=2.0)
        for _ in range(20):
            m.observe_resolved("flip", observation="B", resolved_hypothesis="A", supplied_reliability=0.9)
        r = m.status("flip", supplied_reliability=0.9)["reliability"]
        self.assertLess(r, 0.2)
        likes = m.likelihoods("flip", observation="B", hypotheses=("A", "B"), supplied_reliability=0.9)
        self.assertGreater(likes["A"], likes["B"])

    def test_multiclass_likelihood_contract_normalizes_per_hypothesis(self):
        m = AdaptiveEvidenceModel(prior_strength=4.0)
        names = ("A", "B", "C", "D")
        matrix = {obs: m.likelihoods("s", observation=obs, hypotheses=names, supplied_reliability=0.7) for obs in names}
        for h in names:
            self.assertAlmostEqual(sum(matrix[obs][h] for obs in names), 1.0, places=12)

    def test_invalid_inputs_fail_closed(self):
        m = AdaptiveEvidenceModel()
        for bad in (float("nan"), float("inf"), -0.1, 1.1):
            with self.assertRaises(ValueError):
                m.status("s", supplied_reliability=bad)
        with self.assertRaises(ValueError):
            m.observe_resolved("s", observation="A", resolved_hypothesis="A", weight=0.0)
        with self.assertRaises(ValueError):
            m.likelihoods("s", observation="X", hypotheses=("A", "B"), supplied_reliability=0.7)

    def test_engine_update_uses_learned_source_and_does_not_mutate_reliability(self):
        with tempfile.TemporaryDirectory() as td:
            e = ASMEngine(Path(td)/"x.db", config=ASMConfig(snapshot_every_events=999999))
            for i in range(100):
                truth = "A"
                obs = "A" if i < 70 else "B"
                e.observe_evidence_source("sensor", observation=obs, resolved_hypothesis=truth, supplied_reliability=0.9)
            before = e.evidence_source_status("sensor", supplied_reliability=0.9)
            b = e.update_belief_from_source({"A": 0.5, "B": 0.5}, source_id="sensor", observation="A", supplied_reliability=0.9)
            after = e.evidence_source_status("sensor", supplied_reliability=0.9)
            self.assertAlmostEqual(b.as_dict()["A"], before["reliability"], places=12)
            self.assertEqual(before["resolved_observations"], after["resolved_observations"])
            e.close()

    def test_source_capacity_is_bounded(self):
        m = AdaptiveEvidenceModel(max_sources=2)
        m.status("a", supplied_reliability=0.7)
        m.status("b", supplied_reliability=0.7)
        with self.assertRaises(RuntimeError):
            m.status("c", supplied_reliability=0.7)

    def test_planner_can_override_valid_but_wrong_sensor_likelihood_with_learned_source(self):
        from tests.test_v040a5 import HiddenBinary, make_planner
        with tempfile.TemporaryDirectory() as td:
            e = ASMEngine(Path(td)/"x.db", config=ASMConfig(snapshot_every_events=999999))
            # Predictor still supplies a valid but wrong 90% sensor model.
            e.belief_planner = make_planner(HiddenBinary(.9))
            # Resolved history says the source is actually about 70% reliable.
            for i in range(1000):
                e.observe_evidence_source(
                    "sensor", observation="A" if i < 700 else "B",
                    resolved_hypothesis="A", supplied_reliability=.9,
                )
            learned = e.evidence_source_status("sensor", supplied_reliability=.9)["reliability"]
            before_support = e.evidence_source_status("sensor", supplied_reliability=.9)["resolved_observations"]
            r = e.plan_world_actions_belief(
                "h", entity_id="x", initial_state={"loc":"start"},
                actions=("sense","chooseA","chooseB"), goal={"loc":"goal"}, avoid={"loc":"hazard"},
                initial_belief={"A":.5,"B":.5}, horizon=4,
                evidence_source_id="sensor", supplied_reliability=.9,
            )
            expected = learned**3 + 3*learned*learned*(1-learned)
            self.assertAlmostEqual(r["best"]["goal_probability"], expected, places=11)
            self.assertEqual(r["evidence_source_id"], "sensor")
            self.assertEqual(e.evidence_source_status("sensor", supplied_reliability=.9)["resolved_observations"], before_support)
            e.close()

    def test_snapshot_roundtrip_preserves_source_model(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/"x.db"
            e = ASMEngine(path, config=ASMConfig(snapshot_every_events=999999))
            for i in range(25):
                e.observe_evidence_source("cam", observation="A" if i < 18 else "B", resolved_hypothesis="A", supplied_reliability=0.95)
            expected = e.evidence_source_status("cam", supplied_reliability=0.95)
            e.close()
            e2 = ASMEngine(path, config=ASMConfig(snapshot_every_events=999999))
            got = e2.evidence_source_status("cam", supplied_reliability=0.95)
            self.assertEqual(got["resolved_observations"], expected["resolved_observations"])
            self.assertAlmostEqual(got["reliability"], expected["reliability"], places=15)
            e2.close()


if __name__ == "__main__":
    unittest.main()
