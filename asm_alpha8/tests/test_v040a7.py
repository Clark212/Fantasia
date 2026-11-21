from __future__ import annotations

import random
import tempfile
import unittest
from pathlib import Path

from asm import ASMConfig, ASMEngine, EvidenceDependencyModel, __version__


class Alpha7EvidenceDependencyTests(unittest.TestCase):
    def test_version(self):
        self.assertEqual(__version__, "0.4.0-alpha.7.9")

    def _full_corr_model(self):
        m=EvidenceDependencyModel(min_trials=32,min_abs_correlation=.2,min_fisher_z=3.0)
        rng=random.Random(1)
        for t in range(128):
            truth="A" if rng.random()<.5 else "B"
            obs=truth if rng.random()<.7 else ("B" if truth=="A" else "A")
            m.observe_trial(str(t),resolved_hypothesis=truth,observations={"s":[obs]*9})
        return m

    def test_fully_correlated_repeated_source_is_learned(self):
        m=self._full_corr_model(); status=m.self_dependency("s")
        self.assertGreater(status["active_correlation"],.99)
        eff=m.effective_batch(["s"]*9)
        self.assertAlmostEqual(eff["effective_count"],1.0,places=8)
        self.assertAlmostEqual(eff["scale"],1/9,places=8)

    def test_independent_repeated_source_not_discounted(self):
        m=EvidenceDependencyModel(min_trials=64,min_abs_correlation=.25,min_fisher_z=4.0); rng=random.Random(2)
        for t in range(1000):
            truth="A" if rng.random()<.5 else "B"
            obs=[truth if rng.random()<.7 else ("B" if truth=="A" else "A") for _ in range(9)]
            m.observe_trial(str(t),resolved_hypothesis=truth,observations={"s":obs})
        self.assertEqual(m.self_dependency("s")["active_correlation"],0.0)
        self.assertEqual(m.effective_batch(["s"]*9)["scale"],1.0)

    def test_hidden_cross_source_common_noise_is_learned(self):
        m=EvidenceDependencyModel(min_trials=32,min_abs_correlation=.2,min_fisher_z=3.0); rng=random.Random(3)
        names=["a","b","c"]
        for t in range(200):
            truth="A" if rng.random()<.5 else "B"
            common=truth if rng.random()<.7 else ("B" if truth=="A" else "A")
            m.observe_trial(str(t),resolved_hypothesis=truth,observations={s:[common] for s in names})
        self.assertGreater(m.pair_dependency("a","b")["active_correlation"],.99)
        self.assertAlmostEqual(m.effective_batch(names)["effective_count"],1.0,places=8)

    def test_independent_sources_remain_independent(self):
        m=EvidenceDependencyModel(min_trials=64,min_abs_correlation=.25,min_fisher_z=4.0); rng=random.Random(4)
        names=["a","b","c"]
        for t in range(2000):
            truth="A" if rng.random()<.5 else "B"
            rows={s:[truth if rng.random()<.7 else ("B" if truth=="A" else "A")] for s in names}
            m.observe_trial(str(t),resolved_hypothesis=truth,observations=rows)
        for a,b in (("a","b"),("a","c"),("b","c")):
            self.assertEqual(m.pair_dependency(a,b)["active_correlation"],0.0)
        self.assertEqual(m.effective_batch(names)["scale"],1.0)

    def test_engine_batch_uses_learned_dependency(self):
        with tempfile.TemporaryDirectory() as td:
            cfg=ASMConfig(snapshot_every_events=999999,prune_every_events=999999,
                          evidence_dependency_min_trials=32,evidence_dependency_min_abs_correlation=.2,
                          evidence_dependency_min_fisher_z=3.0)
            e=ASMEngine(Path(td)/"x.db",config=cfg); rng=random.Random(5)
            for t in range(160):
                truth="A" if rng.random()<.5 else "B"
                obs=truth if rng.random()<.7 else ("B" if truth=="A" else "A")
                e.observe_evidence_dependency_trial(str(t),resolved_hypothesis=truth,observations={"s":[obs]*9})
            evidence=[{"source_id":"s","observation":"A","supplied_reliability":.7} for _ in range(9)]
            b=e.update_belief_from_evidence_batch({"A":.5,"B":.5},evidence=evidence)
            self.assertAlmostEqual(b.as_dict()["A"],.7,places=8)
            diag=e.last_evidence_dependency_batch()
            self.assertAlmostEqual(diag["effective_evidence_count"],1.0,places=8)
            e.close()

    def test_batch_is_order_invariant(self):
        with tempfile.TemporaryDirectory() as td:
            e=ASMEngine(Path(td)/"x.db",config=ASMConfig(snapshot_every_events=999999,prune_every_events=999999,
                                                           evidence_dependency_min_trials=16,evidence_dependency_min_abs_correlation=.1,
                                                           evidence_dependency_min_fisher_z=2.0))
            rng=random.Random(6)
            for t in range(100):
                truth="A" if rng.random()<.5 else "B"
                common=truth if rng.random()<.7 else ("B" if truth=="A" else "A")
                e.observe_evidence_dependency_trial(str(t),resolved_hypothesis=truth,observations={"a":[common],"b":[common]})
            rows=[{"source_id":"a","observation":"A","supplied_reliability":.7},
                  {"source_id":"b","observation":"B","supplied_reliability":.7},
                  {"source_id":"a","observation":"A","supplied_reliability":.7}]
            p1=e.update_belief_from_evidence_batch({"A":.5,"B":.5},evidence=rows).as_dict()
            p2=e.update_belief_from_evidence_batch({"A":.5,"B":.5},evidence=list(reversed(rows))).as_dict()
            self.assertAlmostEqual(p1["A"],p2["A"],places=15)
            e.close()

    def test_sequential_api_preserves_alpha62_behavior(self):
        # Hidden dependency correction is batch-only; the old sequential API is
        # intentionally unchanged rather than applying an order-dependent hack.
        with tempfile.TemporaryDirectory() as td:
            e=ASMEngine(Path(td)/"x.db",config=ASMConfig(snapshot_every_events=999999,prune_every_events=999999))
            b={"A":.5,"B":.5}
            for _ in range(9):
                b=e.update_belief_from_source(b,source_id="s",observation="A",supplied_reliability=.7)
            expected=(.7**9)/(.7**9+.3**9)
            self.assertAlmostEqual(b.as_dict()["A"],expected,places=14)
            e.close()

    def test_negative_correlation_is_reported_but_not_exploited(self):
        m=EvidenceDependencyModel(min_trials=16,min_abs_correlation=.1,min_fisher_z=2.0)
        for t in range(100):
            truth="A"; a="A" if t%2==0 else "B"; b="B" if t%2==0 else "A"
            m.observe_trial(str(t),resolved_hypothesis=truth,observations={"a":[a],"b":[b]})
        row=m.pair_dependency("a","b")
        self.assertLess(row["raw_correlation"],-.99); self.assertEqual(row["active_correlation"],0.0)
        self.assertEqual(m.effective_batch(["a","b"])["scale"],1.0)

    def test_model_snapshot_roundtrip(self):
        m=self._full_corr_model(); payload=m.export_state()
        n=EvidenceDependencyModel(min_trials=32,min_abs_correlation=.2,min_fisher_z=3.0); n.import_state(payload)
        self.assertEqual(m.stats(),n.stats())
        self.assertAlmostEqual(m.correlation("s","s"),n.correlation("s","s"),places=15)

    def test_engine_snapshot_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"x.db"; cfg=ASMConfig(snapshot_every_events=999999,prune_every_events=999999,
                                                evidence_dependency_min_trials=16,evidence_dependency_min_abs_correlation=.1,
                                                evidence_dependency_min_fisher_z=2.0)
            e=ASMEngine(path,config=cfg)
            for t in range(50):
                truth="A" if t%2 else "B"; obs=truth if t%4 else ("B" if truth=="A" else "A")
                e.observe_evidence_dependency_trial(str(t),resolved_hypothesis=truth,observations={"a":[obs]*3,"b":[obs]})
            before=e.evidence_dependency.stats(); e.save(); e.close()
            r=ASMEngine(path,config=cfg); self.assertEqual(before,r.evidence_dependency.stats()); r.close()

    def test_duplicate_trial_fails_closed(self):
        m=EvidenceDependencyModel(min_trials=8)
        m.observe_trial("x",resolved_hypothesis="A",observations={"s":["A"]})
        with self.assertRaises(ValueError): m.observe_trial("x",resolved_hypothesis="A",observations={"s":["A"]})

    def test_malformed_batch_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            e=ASMEngine(Path(td)/"x.db",config=ASMConfig(snapshot_every_events=999999,prune_every_events=999999))
            with self.assertRaises(ValueError): e.update_belief_from_evidence_batch({"A":.5,"B":.5},evidence=[])
            with self.assertRaises(ValueError): e.update_belief_from_evidence_batch({"A":.5,"B":.5},evidence=[{"source_id":"s"}])
            with self.assertRaises(ValueError): e.update_belief_from_evidence_batch({"A":.5,"B":.5},evidence=[{"source_id":"s","observation":"A","evidence_id":"x"}])
            e.close()

if __name__=='__main__': unittest.main()
