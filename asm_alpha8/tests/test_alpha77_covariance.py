from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path

from asm import ASMEngine
from asm.procedure_cortex import ProcedureCortex
from tests.test_alpha76_r3 import activate_context, trust, train_clique_dependency, train_pair_dependency
from tests.test_alpha76_r4 import train_independent_dependency_set


def pairmap(sources, fn):
    out = {}
    for i, a in enumerate(sources):
        for b in sources[i + 1:]:
            rho = float(fn(a, b))
            if rho:
                out[f"{a}\t{b}"] = rho
    return out


class Alpha77CovarianceTests(unittest.TestCase):
    def test_equicorrelation_matches_closed_form(self):
        with tempfile.TemporaryDirectory() as td:
            sources = [f"s{i}" for i in range(6)]
            rho = 0.3
            pairs = pairmap(sources, lambda _a, _b: rho)
            cortex = ProcedureCortex(
                Path(td) / "p.db",
                trust_provider=lambda _s: {"reliability": 1.0, "version": 1},
                dependency_provider=lambda _s: {"pairwise": pairs, "version": 1},
            )
            rows = [{"source": s, "reliability": 1.0, "context": "left", "features": {}} for s in sources]
            got = sum(cortex._route_support_weights(rows, "covariance"))
            expected = len(sources) / (1.0 + (len(sources) - 1.0) * rho)
            self.assertAlmostEqual(got, expected, places=10)
            cortex.close()

    def test_heterogeneous_star_recovers_support_local_graph_loses(self):
        with tempfile.TemporaryDirectory() as td:
            sources = ["c", "a", "b", "d"]
            pairs = {"a\tc": 0.25, "b\tc": 0.25, "c\td": 0.25}
            cortex = ProcedureCortex(
                Path(td) / "p.db",
                trust_provider=lambda _s: {"reliability": 1.0, "version": 1},
                dependency_provider=lambda _s: {"pairwise": pairs, "version": 1},
            )
            rows = [{"source": s, "reliability": 1.0, "context": "left", "features": {}} for s in sources]
            local = sum(cortex._route_support_weights(rows, "dependency"))
            cov = sum(cortex._route_support_weights(rows, "covariance"))
            self.assertAlmostEqual(local, 2.9714285714285715, places=10)
            self.assertAlmostEqual(cov, 3.0769230769230766, places=10)
            self.assertLess(local, 3.0)
            self.assertGreater(cov, 3.0)
            cortex.close()

    def test_negative_or_amplifying_inverse_weights_fall_back_exactly(self):
        with tempfile.TemporaryDirectory() as td:
            sources = ["c", "a", "b", "d"]
            pairs = {"a\tc": 0.35, "b\tc": 0.35, "c\td": 0.35}
            cortex = ProcedureCortex(
                Path(td) / "p.db",
                trust_provider=lambda _s: {"reliability": 1.0, "version": 1},
                dependency_provider=lambda _s: {"pairwise": pairs, "version": 1},
            )
            rows = [{"source": s, "reliability": 1.0, "context": "left", "features": {}} for s in sources]
            local = cortex._route_support_weights(rows, "dependency")
            cov = cortex._route_support_weights(rows, "covariance")
            self.assertEqual(cov, local)
            cortex.close()

    def test_singular_perfect_duplicate_component_falls_back_to_alpha76(self):
        with tempfile.TemporaryDirectory() as td:
            sources = ["s1", "s2", "s3"]
            pairs = {"s1\ts2": 1.0}
            cortex = ProcedureCortex(
                Path(td) / "p.db",
                trust_provider=lambda _s: {"reliability": 1.0, "version": 1},
                dependency_provider=lambda _s: {"pairwise": pairs, "version": 1},
            )
            rows = [{"source": s, "reliability": 1.0, "context": "left", "features": {}} for s in sources]
            self.assertEqual(
                cortex._route_support_weights(rows, "covariance"),
                cortex._route_support_weights(rows, "dependency"),
            )
            cortex.close()

    def test_cache_invalidates_when_dependency_version_changes(self):
        with tempfile.TemporaryDirectory() as td:
            state = {"version": 1, "pairs": {"a\tc": 0.25, "b\tc": 0.25, "c\td": 0.25}}
            def provider(_sources):
                return {"pairwise": dict(state["pairs"]), "version": state["version"]}
            cortex = ProcedureCortex(
                Path(td) / "p.db",
                trust_provider=lambda _s: {"reliability": 1.0, "version": 1},
                dependency_provider=provider,
            )
            rows = [{"source": s, "reliability": 1.0, "context": "left", "features": {}} for s in ["c", "a", "b", "d"]]
            before = sum(cortex._route_support_weights(rows, "covariance"))
            state["version"] = 2
            state["pairs"] = {}
            after = sum(cortex._route_support_weights(rows, "covariance"))
            self.assertLess(before, 4.0)
            self.assertAlmostEqual(after, 4.0, places=12)
            cortex.close()

    def test_real_fdr_false_positive_is_not_reintroduced_by_covariance(self):
        with tempfile.TemporaryDirectory() as td:
            e = ASMEngine(Path(td) / "state.db")
            names = train_independent_dependency_set(e, sources=32, seed=23)
            status = e._procedure_dependency_status(names)
            self.assertEqual(status["pairwise_fdr"]["base_active_pairs"], 1)
            self.assertEqual(status["pairwise_fdr"]["accepted_pairs"], 0)
            rows = [{"source": s, "reliability": 1.0, "context": "left", "features": {}} for s in names]
            weights = e.procedures._route_support_weights(rows, "covariance")
            self.assertTrue(all(abs(w - 1.0) < 1e-12 for w in weights))
            e.close()

    def test_real_duplicate_majority_attack_remains_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            e = ASMEngine(Path(td) / "state.db")
            trust(e)
            activate_context(e, "m", "left", 1)
            activate_context(e, "m", "right", -1)
            duplicated = [f"dup{i}" for i in range(16)]
            independent = [f"ind{i}" for i in range(3)]
            for source in duplicated + independent:
                trust(e, source)
            train_clique_dependency(e, duplicated)
            for i, source in enumerate(duplicated):
                e.observe_procedure_route("m", {"signal": True}, "left", evidence_id=f"bad-{i}", source_id=source)
            for i, source in enumerate(independent):
                e.observe_procedure_route("m", {"signal": True}, "right", evidence_id=f"good-{i}", source_id=source)
            freq = e.route_procedure_context("m", {"signal": True}, epistemic_mode="frequency", min_support=1)
            cov = e.route_procedure_context("m", {"signal": True}, epistemic_mode="full_covariance", min_support=1)
            self.assertEqual((freq["status"], freq["context"]), ("routed", "left"))
            self.assertNotEqual(cov["status"], "routed")
            self.assertLess(cov["support"]["left"], cov["support"]["right"])
            e.close()

    def test_planner_and_routed_prediction_propagate_covariance_mode(self):
        with tempfile.TemporaryDirectory() as td:
            e = ASMEngine(Path(td) / "state.db")
            trust(e)
            activate_context(e, "m", "left", 1)
            activate_context(e, "m", "right", -1)
            left = ["c", "a", "b", "d"]
            right = ["r0", "r1", "r2", "r3"]
            for source in left + right:
                trust(e, source)
            pairs = {"a\tc": 0.25, "b\tc": 0.25, "c\td": 0.25}
            e.procedures.dependency_provider = lambda _sources: {"pairwise": pairs, "version": 999}
            for i, source in enumerate(left):
                e.observe_procedure_route("m", {"signal": True}, "left", evidence_id=f"l-{i}", source_id=source)
            for i, source in enumerate(right):
                e.observe_procedure_route("m", {"signal": False}, "right", evidence_id=f"r-{i}", source_id=source)
            old = e.route_procedure_context("m", {"signal": True}, epistemic_mode="dependency")
            new = e.route_procedure_context("m", {"signal": True}, epistemic_mode="covariance")
            self.assertNotEqual(old["status"], "routed")
            self.assertEqual((new["status"], new["context"]), ("routed", "left"))
            plan = e.plan_procedure_route_queries("m", {"signal": True}, epistemic_mode="covariance")
            self.assertEqual(plan["epistemic_mode"], "covariance")
            self.assertEqual(plan["tree"]["status"], "routed")
            pred = e.predict_routed_procedure("m", {"x": 4}, {"signal": True}, epistemic_mode="covariance")
            self.assertEqual(pred["routing"]["context"], "left")
            self.assertEqual(pred["value"], 5)
            e.close()


if __name__ == "__main__":
    unittest.main()
