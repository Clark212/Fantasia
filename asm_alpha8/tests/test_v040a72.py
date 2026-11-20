from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from asm.config import ASMConfig
from asm.engine import ASMEngine
from asm.procedure_cortex import ProcedureCortex


# These lifecycle tests probe validated rules far outside the evidence range (x=99, 100, 40, 60). Since DEV3.3 the default guard abstains
# there, so the affected tests use the explicit legacy mode; assertions are unchanged. See test_alpha8_dev3_3_default_abstain.py.
LEGACY_EXTRAPOLATION = ASMConfig(procedure_extrapolation_guard="off")


def trust_oracle(engine: ASMEngine, source: str = "oracle", start: int = 0, n: int = 80) -> None:
    for i in range(start, start + n):
        engine.observe_evidence_source(
            source, observation="A", resolved_hypothesis="A", temporal_index=i
        )


def feed(engine: ASMEngine, mechanism: str, tag: str, xs, fn, *, root=None):
    rows = []
    for x in xs:
        kwargs = {}
        if root is not None:
            kwargs["root_id"] = root
        rows.append(
            engine.observe_procedural_experience(
                mechanism,
                {"x": x},
                fn(x),
                evidence_id=f"{tag}-{x}",
                source_id="oracle",
                **kwargs,
            )
        )
    return rows


class AutonomousProcedureIntegrationTests(unittest.TestCase):
    def test_three_trusted_roots_propose_then_heldout_activates(self):
        with tempfile.TemporaryDirectory() as d:
            e = ASMEngine(Path(d) / "state.db", config=LEGACY_EXTRAPOLATION)
            try:
                trust_oracle(e)
                rows = feed(e, "f", "fit", range(3), lambda x: 2*x + 3)
                self.assertEqual(rows[-1]["auto_induction"]["status"], "proposed")
                self.assertEqual(e.predict_procedure("f", {"x": 99})["status"], "abstained")
                feed(e, "f", "val", range(10, 18), lambda x: 2*x + 3)
                pred = e.predict_procedure("f", {"x": 99})
                self.assertEqual(pred["status"], "predicted")
                self.assertEqual(pred["value"], 201)
                self.assertEqual(pred["support"], 8)
            finally:
                e.close()

    def test_rule_drift_creates_new_version_after_fresh_roots(self):
        with tempfile.TemporaryDirectory() as d:
            e = ASMEngine(Path(d) / "state.db", config=LEGACY_EXTRAPOLATION)
            try:
                trust_oracle(e)
                feed(e, "f", "a", range(3), lambda x: 2*x + 3)
                feed(e, "f", "av", range(10, 18), lambda x: 2*x + 3)
                first = e.observe_procedural_experience("f", {"x": 20}, -53, evidence_id="b-20", source_id="oracle")
                self.assertEqual(first["auto_induction"]["status"], "collecting")
                self.assertEqual(e.predict_procedure("f", {"x": 7})["status"], "abstained")
                e.observe_procedural_experience("f", {"x": 21}, -56, evidence_id="b-21", source_id="oracle")
                third = e.observe_procedural_experience("f", {"x": 22}, -59, evidence_id="b-22", source_id="oracle")
                self.assertEqual(third["auto_induction"]["status"], "proposed")
                self.assertEqual(third["auto_induction"]["mode"], "induction")
                self.assertEqual(third["auto_induction"]["version"], 2)
                feed(e, "f", "bv", range(30, 38), lambda x: -3*x + 7)
                self.assertEqual(e.predict_procedure("f", {"x": 40})["value"], -113)
            finally:
                e.close()

    def test_full_reversal_revalidates_old_structure_as_new_version(self):
        with tempfile.TemporaryDirectory() as d:
            e = ASMEngine(Path(d) / "state.db", config=LEGACY_EXTRAPOLATION)
            try:
                trust_oracle(e)
                feed(e, "f", "a", range(3), lambda x: 2*x + 3)
                feed(e, "f", "av", range(10, 18), lambda x: 2*x + 3)
                feed(e, "f", "b", range(20, 23), lambda x: -3*x + 7)
                feed(e, "f", "bv", range(30, 38), lambda x: -3*x + 7)
                rows = feed(e, "f", "c", range(40, 43), lambda x: 2*x + 3)
                auto = rows[-1]["auto_induction"]
                self.assertEqual(auto["status"], "proposed")
                self.assertEqual(auto["mode"], "revalidation")
                self.assertEqual(auto["version"], 3)
                feed(e, "f", "cv", range(50, 58), lambda x: 2*x + 3)
                versions = e.procedure_versions("f")
                self.assertEqual(versions[-1]["state"], "active")
                self.assertTrue(versions[-1]["provenance"].startswith("asm_auto_revalidation:"))
                self.assertEqual(e.predict_procedure("f", {"x": 60})["value"], 123)
            finally:
                e.close()

    def test_descendants_of_one_root_do_not_trigger_induction(self):
        with tempfile.TemporaryDirectory() as d:
            e = ASMEngine(Path(d) / "state.db")
            try:
                trust_oracle(e)
                rows = feed(e, "f", "copy", range(8), lambda x: x + 1, root="same-root")
                self.assertEqual(rows[-1]["auto_induction"]["status"], "collecting")
                self.assertEqual(rows[-1]["auto_induction"]["trusted_independent_roots"], 1)
                self.assertEqual(e.procedure_versions("f"), [])
            finally:
                e.close()

    def test_low_trust_source_cannot_trigger_autonomous_hypothesis(self):
        with tempfile.TemporaryDirectory() as d:
            e = ASMEngine(Path(d) / "state.db")
            try:
                rows = []
                for x in range(8):
                    rows.append(e.observe_procedural_experience(
                        "f", {"x": x}, x + 1,
                        evidence_id=f"low-{x}", source_id="unknown-source"
                    ))
                self.assertEqual(rows[-1]["auto_induction"]["status"], "collecting")
                self.assertEqual(rows[-1]["auto_induction"]["trusted_independent_roots"], 0)
                self.assertEqual(e.procedure_versions("f"), [])
            finally:
                e.close()

    def test_unsupported_experience_fails_closed_without_version(self):
        with tempfile.TemporaryDirectory() as d:
            e = ASMEngine(Path(d) / "state.db")
            try:
                trust_oracle(e)
                # Boolean procedures became supported in alpha.7.4, so keep
                # this inherited fail-closed contract focused on a genuinely
                # unsupported mixed input schema rather than disabling the new
                # capability.
                rows = []
                cases = [({"x": False}, True), ({"x": 1}, False), ({"x": True}, False)]
                for i, (values, expected) in enumerate(cases):
                    rows.append(e.observe_procedural_experience(
                        "bool_task", values, expected,
                        evidence_id=f"bool-{i}", source_id="oracle"
                    ))
                self.assertEqual(rows[-1]["auto_induction"]["status"], "unsupported")
                self.assertEqual(e.procedure_versions("bool_task"), [])
            finally:
                e.close()

    def test_auto_state_persists_across_reopen(self):
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / "state.db"
            e = ASMEngine(db)
            trust_oracle(e)
            feed(e, "f", "fit", range(3), lambda x: x + 1)
            before = e.procedure_autonomy_status("f")
            e.close()
            e = ASMEngine(db)
            try:
                after = e.procedure_autonomy_status("f")
                self.assertEqual(after, before)
                self.assertEqual(len(e.procedure_versions("f")), 1)
            finally:
                e.close()

    def test_prediction_is_read_only_for_autonomy_state(self):
        with tempfile.TemporaryDirectory() as d:
            e = ASMEngine(Path(d) / "state.db", config=LEGACY_EXTRAPOLATION)
            try:
                trust_oracle(e)
                feed(e, "f", "fit", range(3), lambda x: x + 1)
                feed(e, "f", "val", range(10, 18), lambda x: x + 1)
                before = e.procedure_autonomy_status("f")
                dep_before = e.evidence_dependency.export_state()
                for _ in range(50):
                    self.assertEqual(e.predict_procedure("f", {"x": 100})["value"], 101)
                self.assertEqual(e.procedure_autonomy_status("f"), before)
                self.assertEqual(e.evidence_dependency.export_state(), dep_before)
            finally:
                e.close()

    def test_capacity_block_preserves_history_and_observation(self):
        with tempfile.TemporaryDirectory() as d:
            e = ASMEngine(Path(d) / "state.db")
            try:
                trust_oracle(e)
                e.procedures.MAX_VERSIONS = 1
                feed(e, "f", "a", range(3), lambda x: x + 1)
                feed(e, "f", "av", range(10, 18), lambda x: x + 1)
                feed(e, "f", "b", range(20, 22), lambda x: 3*x + 4)
                third = e.observe_procedural_experience("f", {"x": 22}, 70, evidence_id="b-22", source_id="oracle")
                self.assertEqual(third["auto_induction"]["status"], "blocked")
                self.assertEqual(len(e.procedure_versions("f")), 1)
                ids = [row["id"] for row in e.procedures.training("f", limit=64)]
                self.assertIn("b-22", ids)
            finally:
                e.close()

    def test_manual_explicit_path_remains_backward_compatible(self):
        with tempfile.TemporaryDirectory() as d:
            e = ASMEngine(Path(d) / "state.db")
            try:
                trust_oracle(e)
                for x in range(3):
                    row = e.observe_procedure("manual", {"x": x}, 4*x - 2, evidence_id=f"m-{x}", source_id="oracle")
                    self.assertNotIn("auto_induction", row)
                result = e.induce_procedure("manual")
                self.assertEqual(result["status"], "proposed")
            finally:
                e.close()


if __name__ == "__main__":
    unittest.main()
