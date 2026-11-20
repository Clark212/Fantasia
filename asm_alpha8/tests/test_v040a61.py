from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from asm import ASMConfig, ASMEngine, __version__
from asm.adaptive_evidence import AdaptiveEvidenceModel


class Alpha61RegimeAwareEvidenceTests(unittest.TestCase):
    def test_version(self):
        self.assertEqual(__version__, "0.4.0-alpha.7.9")

    def test_no_temporal_metadata_preserves_alpha6_exchangeable_semantics(self):
        m = AdaptiveEvidenceModel(prior_strength=4.0)
        for _ in range(700):
            m.observe_resolved("s", observation="A", resolved_hypothesis="A", supplied_reliability=.9)
        for _ in range(300):
            m.observe_resolved("s", observation="B", resolved_hypothesis="A", supplied_reliability=.9)
        status = m.status("s", supplied_reliability=.9)
        self.assertEqual(status["regime_count"], 1)
        self.assertAlmostEqual(status["reliability"], .7, delta=.003)
        self.assertAlmostEqual(status["effective_reliability"], status["reliability"], places=15)

    def test_abrupt_flip_creates_new_regime_and_recovers(self):
        m = AdaptiveEvidenceModel(prior_strength=4.0, drift_window=24, drift_min_abs_change=.30, drift_min_zscore=3.0)
        # Deterministic 90% blocks followed by deterministic 10% blocks.
        for i in range(300):
            correct = (i % 10) != 0
            m.observe_resolved("s", observation="A" if correct else "B", resolved_hypothesis="A",
                               supplied_reliability=.9, temporal_index=i)
        before = m.status("s", supplied_reliability=.9)
        self.assertGreater(before["effective_reliability"], .82)
        for j in range(300):
            i = 300 + j
            correct = (j % 10) == 0
            m.observe_resolved("s", observation="A" if correct else "B", resolved_hypothesis="A",
                               supplied_reliability=.9, temporal_index=i)
        after = m.status("s", supplied_reliability=.9)
        self.assertGreaterEqual(after["regime_count"], 2)
        self.assertLess(after["effective_reliability"], .20)
        # Full-history posterior remains available and intentionally averages regimes.
        self.assertAlmostEqual(after["reliability"], .5, delta=.02)

    def test_stationary_temporal_source_does_not_false_split(self):
        m = AdaptiveEvidenceModel(prior_strength=4.0, drift_window=32)
        # Repeating pattern is time ordered but stationary at 75%.
        for i in range(640):
            correct = (i % 4) != 0
            m.observe_resolved("s", observation="A" if correct else "B", resolved_hypothesis="A",
                               supplied_reliability=.75, temporal_index=i)
        status = m.status("s", supplied_reliability=.75)
        self.assertEqual(status["regime_count"], 1)
        self.assertAlmostEqual(status["effective_reliability"], .75, delta=.01)

    def test_temporal_indices_must_be_strictly_increasing(self):
        m = AdaptiveEvidenceModel()
        m.observe_resolved("s", observation="A", resolved_hypothesis="A", temporal_index=10)
        with self.assertRaises(ValueError):
            m.observe_resolved("s", observation="A", resolved_hypothesis="A", temporal_index=10)
        with self.assertRaises(ValueError):
            m.observe_resolved("s", observation="A", resolved_hypothesis="A", temporal_index=9)

    def test_alpha6_schema1_snapshot_migrates_without_changing_inference(self):
        old = {
            "schema": 1,
            "prior_strength": 4.0,
            "min_shape": 1e-6,
            "max_sources": 1024,
            "sources": {
                "cam": {"alpha": 72.6, "beta": 31.4, "prior_reliability": .9,
                        "prior_strength": 4.0, "resolved_observations": 100.0}
            },
        }
        m = AdaptiveEvidenceModel()
        m.import_state(old)
        status = m.status("cam", supplied_reliability=.9)
        self.assertEqual(status["regime_count"], 1)
        self.assertAlmostEqual(status["effective_reliability"], status["reliability"], places=15)
        self.assertEqual(status["regimes"][0]["trigger"], "alpha6_migration")

    def test_schema2_roundtrip_preserves_regimes(self):
        m = AdaptiveEvidenceModel(drift_window=16, drift_min_abs_change=.3)
        for i in range(160):
            correct = (i % 10) != 0
            m.observe_resolved("s", observation="A" if correct else "B", resolved_hypothesis="A", temporal_index=i)
        for j in range(160):
            i = 160 + j
            correct = (j % 10) == 0
            m.observe_resolved("s", observation="A" if correct else "B", resolved_hypothesis="A", temporal_index=i)
        payload = m.export_state()
        n = AdaptiveEvidenceModel(drift_window=16, drift_min_abs_change=.3)
        n.import_state(payload)
        a, b = m.status("s"), n.status("s")
        self.assertEqual(a["regime_count"], b["regime_count"])
        self.assertEqual(a["last_temporal_index"], b["last_temporal_index"])
        self.assertAlmostEqual(a["effective_reliability"], b["effective_reliability"], places=15)

    def test_engine_temporal_api_uses_effective_regime(self):
        with tempfile.TemporaryDirectory() as td:
            e = ASMEngine(Path(td) / "x.db", config=ASMConfig(snapshot_every_events=999999,
                                                               adaptive_evidence_drift_window=16,
                                                               adaptive_evidence_drift_min_abs_change=.3))
            for i in range(160):
                correct = (i % 10) != 0
                e.observe_evidence_source("cam", observation="A" if correct else "B", resolved_hypothesis="A",
                                          supplied_reliability=.9, temporal_index=i)
            for j in range(160):
                i = 160 + j
                correct = (j % 10) == 0
                e.observe_evidence_source("cam", observation="A" if correct else "B", resolved_hypothesis="A",
                                          supplied_reliability=.9, temporal_index=i)
            status = e.evidence_source_status("cam", supplied_reliability=.9)
            belief = e.update_belief_from_source({"A": .5, "B": .5}, source_id="cam", observation="A",
                                                 supplied_reliability=.9)
            self.assertGreaterEqual(status["regime_count"], 2)
            self.assertAlmostEqual(belief.as_dict()["A"], status["effective_reliability"], places=12)
            e.close()


if __name__ == "__main__":
    unittest.main()
