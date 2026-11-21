from __future__ import annotations

import random
import tempfile
import unittest
from pathlib import Path

from asm import ASMEngine


def train_exact_reliability(engine, source: str, correct: int, total: int = 200):
    for i in range(total):
        engine.observe_evidence_source(
            source,
            observation="A" if i < correct else "B",
            resolved_hypothesis="A",
        )


def trust(engine, source: str = "oracle"):
    train_exact_reliability(engine, source, 80, 80)


def activate_context(engine, mechanism: str, context: str, delta: int):
    fn = lambda x: x + delta
    for i, x in enumerate((0, 1, 2)):
        engine.observe_procedural_experience(
            mechanism,
            {"x": x},
            fn(x),
            evidence_id=f"{mechanism}-{context}-fit-{i}",
            source_id="oracle",
            context=context,
        )
    for i, x in enumerate(range(10, 18)):
        engine.observe_procedural_experience(
            mechanism,
            {"x": x},
            fn(x),
            evidence_id=f"{mechanism}-{context}-val-{i}",
            source_id="oracle",
            context=context,
        )
    assert engine.procedure_versions(mechanism, context=context)[-1]["state"] == "active"


def train_pair_dependency(engine, a: str, b: str, *, shared: float, start: int = 0,
                          trials: int = 100, seed: int = 1, temporal: bool = False):
    rng = random.Random(seed)
    for i in range(trials):
        truth = "A" if rng.random() < 0.5 else "B"

        def noisy():
            return truth if rng.random() < 0.7 else ("B" if truth == "A" else "A")

        if rng.random() < shared:
            oa = noisy(); ob = oa
        else:
            oa = noisy(); ob = noisy()
        options = {"temporal_index": start + i} if temporal else {}
        engine.observe_evidence_dependency_trial(
            f"dep-{a}-{b}-{start+i}",
            resolved_hypothesis=truth,
            observations={a: [oa], b: [ob]},
            **options,
        )


def train_clique_dependency(engine, sources: list[str], *, trials: int = 100, seed: int = 1):
    rng = random.Random(seed)
    for i in range(trials):
        truth = "A" if rng.random() < 0.5 else "B"
        obs = truth if rng.random() < 0.7 else ("B" if truth == "A" else "A")
        engine.observe_evidence_dependency_trial(
            f"clique-{i}",
            resolved_hypothesis=truth,
            observations={source: [obs] for source in sources},
        )


class Alpha76R3Tests(unittest.TestCase):
    def make(self):
        td = tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup)
        engine = ASMEngine(Path(td.name) / "state.db"); self.addCleanup(engine.close)
        trust(engine)
        return engine

    def prepare_two_contexts(self, engine, mechanism="m"):
        activate_context(engine, mechanism, "left", 1)
        activate_context(engine, mechanism, "right", -1)

    def test_reliability_is_a_real_ablation_not_frequency_alias(self):
        e = self.make(); self.prepare_two_contexts(e)
        # Six barely-admitted sources vote left, one near-perfect source votes right.
        # Frequency crosses the 0.8 confidence gate; reliability weighting does not.
        lows = []
        for i in range(6):
            source = f"low{i}"; lows.append(source)
            train_exact_reliability(e, source, 162, 200)  # 0.8039 posterior reliability
            self.assertGreaterEqual(e.evidence_source_status(source)["effective_reliability"], 0.8)
        train_exact_reliability(e, "high", 200, 200)
        for i, source in enumerate(lows):
            e.observe_procedure_route("m", {"signal": True}, "left",
                                      evidence_id=f"low-route-{i}", source_id=source)
        e.observe_procedure_route("m", {"signal": True}, "right",
                                  evidence_id="high-route", source_id="high")
        freq = e.route_procedure_context("m", {"signal": True}, epistemic_mode="frequency")
        rel = e.route_procedure_context("m", {"signal": True}, epistemic_mode="reliability")
        self.assertEqual((freq["status"], freq["context"]), ("routed", "left"))
        self.assertNotEqual(rel["status"], "routed")
        self.assertLess(rel["support"]["left"], freq["support"]["left"])

    def test_perfect_duplicate_pair_becomes_one_stream_without_taxing_independents(self):
        e = self.make(); self.prepare_two_contexts(e)
        for source in ("s1", "s2", "s3", "s4"):
            trust(e, source)
        train_pair_dependency(e, "s1", "s2", shared=1.0)
        for i, source in enumerate(("s1", "s2", "s3", "s4")):
            e.observe_procedure_route("m", {"mode": False}, "left",
                                      evidence_id=f"r{i}", source_id=source)
        rows = e.procedures._effective_route_rows("m")
        weights = e.procedures._route_support_weights(rows, "dependency")
        by_source = {row["source"]: weight for row, weight in zip(rows, weights)}
        self.assertAlmostEqual(by_source["s1"] + by_source["s2"], 1.0, places=6)
        self.assertAlmostEqual(by_source["s3"], 1.0, places=6)
        self.assertAlmostEqual(by_source["s4"], 1.0, places=6)

    def test_large_duplicate_clique_does_not_suppress_unrelated_sources(self):
        e = self.make(); self.prepare_two_contexts(e)
        clique = [f"dup{i}" for i in range(16)]
        independent = [f"ind{i}" for i in range(3)]
        for source in clique + independent:
            trust(e, source)
        train_clique_dependency(e, clique)
        for i, source in enumerate(clique + independent):
            e.observe_procedure_route("m", {"mode": False}, "left",
                                      evidence_id=f"route-{i}", source_id=source)
        rows = e.procedures._effective_route_rows("m")
        weights = e.procedures._route_support_weights(rows, "dependency")
        clique_total = sum(w for row, w in zip(rows, weights) if row["source"] in clique)
        independent_weights = [w for row, w in zip(rows, weights) if row["source"] in independent]
        self.assertAlmostEqual(clique_total, 1.0, places=5)
        self.assertTrue(all(abs(w - 1.0) < 1e-9 for w in independent_weights))
        self.assertAlmostEqual(sum(weights), 4.0, places=5)

    def test_repeated_history_accumulates_instead_of_global_batch_collapse(self):
        e = self.make(); self.prepare_two_contexts(e)
        sources = ("s1", "s2", "s3", "s4")
        for source in sources:
            trust(e, source)
        train_pair_dependency(e, "s1", "s2", shared=1.0)
        for t in range(20):
            for j, source in enumerate(sources):
                e.observe_procedure_route("m", {"mode": False}, "left",
                                          evidence_id=f"r-{t}-{j}", root_id=f"root-{t}-{j}", source_id=source)
        rows = e.procedures._effective_route_rows("m")
        weights = e.procedures._route_support_weights(rows, "dependency")
        # 20 rounds * (0.5 + 0.5 + 1 + 1) = 60 effective dependency units.
        self.assertAlmostEqual(sum(weights), 60.0, places=4)
        giant_batch = e.evidence_dependency.effective_batch([row["source"] for row in rows])
        self.assertLess(giant_batch["effective_count"], 10.0)  # demonstrates why global-batch use was wrong here
        routed = e.route_procedure_context("m", {"mode": False}, epistemic_mode="full")
        self.assertEqual((routed["status"], routed["context"]), ("routed", "left"))

    def test_dependency_drift_recovers_support_without_rewriting_route_history(self):
        e = self.make(); self.prepare_two_contexts(e)
        sources = ("s1", "s2", "s3", "s4")
        for source in sources:
            trust(e, source)
        train_pair_dependency(e, "s1", "s2", shared=1.0, start=0, trials=100, seed=1, temporal=True)
        for i, source in enumerate(sources):
            e.observe_procedure_route("m", {"mode": False}, "left",
                                      evidence_id=f"r{i}", source_id=source)
        before_count = e.procedure_route_evidence_status("m")["total_records"]
        before = e.route_procedure_context("m", {"mode": False}, epistemic_mode="full")
        self.assertNotEqual(before["status"], "routed")
        # Correlation disappears; the evidence-dependency model's recent view adapts.
        train_pair_dependency(e, "s1", "s2", shared=0.0, start=100, trials=140, seed=2, temporal=True)
        after = e.route_procedure_context("m", {"mode": False}, epistemic_mode="full")
        self.assertEqual((after["status"], after["context"]), ("routed", "left"))
        self.assertEqual(e.procedure_route_evidence_status("m")["total_records"], before_count)
        self.assertGreater(after["support"]["left"], before["support"]["left"])

    def test_correlated_majority_cannot_force_false_route_against_independent_minority(self):
        e = self.make(); self.prepare_two_contexts(e)
        duplicated = [f"dup{i}" for i in range(16)]
        independent = [f"ind{i}" for i in range(3)]
        for source in duplicated + independent:
            trust(e, source)
        train_clique_dependency(e, duplicated)
        # Same observed signature; duplicated cluster says left, three independent sources say right.
        for i, source in enumerate(duplicated):
            e.observe_procedure_route("m", {"signal": True}, "left",
                                      evidence_id=f"bad-{i}", source_id=source)
        for i, source in enumerate(independent):
            e.observe_procedure_route("m", {"signal": True}, "right",
                                      evidence_id=f"good-{i}", source_id=source)
        freq = e.route_procedure_context("m", {"signal": True}, epistemic_mode="frequency", min_support=1)
        full = e.route_procedure_context("m", {"signal": True}, epistemic_mode="full", min_support=1)
        self.assertEqual((freq["status"], freq["context"]), ("routed", "left"))
        self.assertNotEqual(full["status"], "routed")
        self.assertLess(full["support"]["left"], full["support"]["right"])

    def test_information_query_uses_epistemic_weights_not_raw_row_count(self):
        e = self.make(); self.prepare_two_contexts(e)
        low_a=[f"la{i}" for i in range(6)]; low_b=[f"lb{i}" for i in range(6)]
        high_a=[f"ha{i}" for i in range(4)]; high_b=[f"hb{i}" for i in range(4)]
        for source in low_a+low_b+high_a+high_b:
            trust(e,source)

        def clique(sources,prefix):
            rng=random.Random(11)
            for i in range(100):
                truth="A" if rng.random()<0.5 else "B"
                obs=truth if rng.random()<0.7 else ("B" if truth=="A" else "A")
                e.observe_evidence_dependency_trial(
                    f"{prefix}-{i}", resolved_hypothesis=truth,
                    observations={source:[obs] for source in sources})
        clique(low_a,"qa"); clique(low_b,"qb")
        for i,source in enumerate(low_a):
            e.observe_procedure_route("m",{"a_bad":False},"left",evidence_id=f"la-{i}",source_id=source)
        for i,source in enumerate(low_b):
            e.observe_procedure_route("m",{"a_bad":True},"right",evidence_id=f"lb-{i}",source_id=source)
        for i,source in enumerate(high_a):
            e.observe_procedure_route("m",{"z_good":False},"left",evidence_id=f"ha-{i}",source_id=source)
        for i,source in enumerate(high_b):
            e.observe_procedure_route("m",{"z_good":True},"right",evidence_id=f"hb-{i}",source_id=source)
        before=e.procedure_route_evidence_status("m")["total_records"]
        frequency=e.route_procedure_context("m",{},epistemic_mode="frequency")
        full=e.route_procedure_context("m",{},epistemic_mode="full")
        after=e.procedure_route_evidence_status("m")["total_records"]
        self.assertEqual(frequency["information_query"]["feature"],"a_bad")
        self.assertEqual(full["information_query"]["feature"],"z_good")
        self.assertEqual(before,after)



if __name__ == "__main__":
    unittest.main()
