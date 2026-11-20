from __future__ import annotations

import random
import tempfile
import unittest
from pathlib import Path

from asm import ASMEngine
from asm.procedure_cortex import ProcedureCortex
from tests.test_alpha76_r3 import activate_context, trust


def train_independent_dependency_set(engine: ASMEngine, *, sources: int, seed: int, trials: int = 100):
    rng = random.Random(seed)
    names = [f"s{i}" for i in range(sources)]
    for t in range(trials):
        truth = "A" if rng.random() < 0.5 else "B"
        observations = {}
        for source in names:
            observations[source] = [truth if rng.random() < 0.7 else ("B" if truth == "A" else "A")]
        engine.observe_evidence_dependency_trial(
            f"ind-{seed}-{t}", resolved_hypothesis=truth, observations=observations
        )
    return names


class Alpha76R4Tests(unittest.TestCase):
    def test_routing_fdr_suppresses_known_scale_false_positive(self):
        with tempfile.TemporaryDirectory() as td:
            e = ASMEngine(Path(td) / "state.db")
            names = train_independent_dependency_set(e, sources=32, seed=23)
            raw_active = []
            for i, a in enumerate(names):
                for b in names[i + 1:]:
                    d = e.evidence_dependency.pair_dependency(a, b)
                    if d["active_correlation"] > 0:
                        raw_active.append((a, b, d["active_correlation"]))
            self.assertEqual(len(raw_active), 1)  # deterministic adversarial seed
            status = e._procedure_dependency_status(names)
            self.assertEqual(status["pairwise_fdr"]["base_active_pairs"], 1)
            self.assertEqual(status["pairwise_fdr"]["accepted_pairs"], 0)
            self.assertEqual(status["pairwise_fdr"]["suppressed_pairs"], 1)
            self.assertTrue(all(v == 0.0 for v in status["pairwise"].values()))
            e.close()

    def test_covariance_linear_weight_matches_equicorrelated_design_effect(self):
        with tempfile.TemporaryDirectory() as td:
            rho = 0.5
            sources = [f"s{i}" for i in range(4)]
            pairs = {}
            for i, a in enumerate(sources):
                for b in sources[i + 1:]:
                    pairs[f"{a}\t{b}"] = rho
            cortex = ProcedureCortex(
                Path(td) / "p.db",
                trust_provider=lambda _s: {"reliability": 1.0, "version": 1},
                dependency_provider=lambda _sources: {"pairwise": pairs, "effective_count": 4.0},
            )
            rows = [
                {"source": s, "reliability": 1.0, "context": "left", "features": {"x": 1}}
                for s in sources
            ]
            support = sum(cortex._route_support_weights(rows, "dependency"))
            expected = 4.0 / (1.0 + 3.0 * rho)
            self.assertAlmostEqual(support, expected, places=12)
            cortex.close()

    def test_true_perfect_dependency_survives_routing_fdr_at_scale(self):
        with tempfile.TemporaryDirectory() as td:
            e = ASMEngine(Path(td) / "state.db")
            rng = random.Random(7)
            clique = [f"d{i}" for i in range(16)]
            independent = [f"i{i}" for i in range(16)]
            names = clique + independent
            for t in range(100):
                truth = "A" if rng.random() < 0.5 else "B"
                shared = truth if rng.random() < 0.7 else ("B" if truth == "A" else "A")
                observations = {s: [shared] for s in clique}
                for s in independent:
                    observations[s] = [truth if rng.random() < 0.7 else ("B" if truth == "A" else "A")]
                e.observe_evidence_dependency_trial(
                    f"mixed-{t}", resolved_hypothesis=truth, observations=observations
                )
            status = e._procedure_dependency_status(names)
            # All 120 within-clique pairs are real and extremely strong.
            accepted = status["pairwise_fdr"]["accepted_pairs"]
            self.assertGreaterEqual(accepted, 120)
            rows = [{"source": s, "reliability": 1.0, "context": "left", "features": {}} for s in names]
            weights = e.procedures._route_support_weights(rows, "dependency")
            by_source = {row["source"]: w for row, w in zip(rows, weights)}
            self.assertAlmostEqual(sum(by_source[s] for s in clique), 1.0, places=6)
            self.assertTrue(all(abs(by_source[s] - 1.0) < 1e-12 for s in independent))
            e.close()

    def test_wrong_dependency_can_temporally_recover_without_route_history_rewrite(self):
        # Seed 73 creates a rare but FDR-surviving false pair among 32 truly
        # independent sources.  R4 must fail closed initially, then recover once
        # fresh externally resolved independent evidence corrects the dependency view.
        with tempfile.TemporaryDirectory() as td:
            e = ASMEngine(Path(td) / "state.db")
            trust(e)
            activate_context(e, "m", "left", 1)
            activate_context(e, "m", "right", -1)
            names = train_independent_dependency_set(e, sources=32, seed=73)
            status = e._procedure_dependency_status(names)
            accepted = [k for k, v in status["pairwise"].items() if v > 0]
            self.assertEqual(accepted, ["s15\ts23"])
            for s in names:
                trust(e, s)
            left_sources = {"s15", "s23", "s0"}
            for i, s in enumerate(names):
                if s in left_sources:
                    e.observe_procedure_route("m", {"mode": False}, "left", evidence_id=f"l-{s}", source_id=s)
                else:
                    e.observe_procedure_route("m", {"mode": True}, "right", evidence_id=f"r-{s}", source_id=s)
            before_count = e.procedure_route_evidence_status("m")["total_records"]
            frequency = e.route_procedure_context("m", {"mode": False}, epistemic_mode="frequency")
            dependency = e.route_procedure_context("m", {"mode": False}, epistemic_mode="dependency")
            self.assertEqual((frequency["status"], frequency["context"]), ("routed", "left"))
            self.assertNotEqual(dependency["status"], "routed")

            rng = random.Random(9001)
            recovered_at = None
            for t in range(1, 97):
                truth = "A" if rng.random() < 0.5 else "B"
                def noisy():
                    return truth if rng.random() < 0.7 else ("B" if truth == "A" else "A")
                e.observe_evidence_dependency_trial(
                    f"recovery-{t}", resolved_hypothesis=truth,
                    observations={"s15": [noisy()], "s23": [noisy()]}, temporal_index=t,
                )
                now = e.route_procedure_context("m", {"mode": False}, epistemic_mode="dependency")
                if now.get("status") == "routed" and now.get("context") == "left":
                    recovered_at = t
                    break
            self.assertIsNotNone(recovered_at)
            self.assertLessEqual(recovered_at, 96)
            self.assertEqual(e.procedure_route_evidence_status("m")["total_records"], before_count)
            e.close()


if __name__ == "__main__":
    unittest.main()
