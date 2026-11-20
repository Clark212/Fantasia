"""DEV3.3: 'abstain' is the default extrapolation guard. These tests pin the default and show the behaviour change on the
same scenarios the alpha 7.1 / 7.2 lifecycle tests use (which now run in explicit legacy mode)."""
import tempfile
import unittest
from pathlib import Path

from asm.config import ASMConfig
from asm.engine import ASMEngine
from asm.procedure_cortex import ProcedureCortex

TRUST = lambda source: {"reliability": 0.99, "version": 1}


def train_affine(cortex, mech="f", a=2, b=3):
    """Same protocol as the alpha 7.1 audit test: fit on x=0..2, propose, validate on x=10..17."""
    for x in range(3):
        cortex.observe(mech, {"x": x}, a * x + b, evidence_id=f"{mech}-fit-{x}", source_id="oracle")
    assert cortex.induce(mech)["status"] == "proposed"
    for x in range(10, 18):
        cortex.observe(mech, {"x": x}, a * x + b, evidence_id=f"{mech}-val-{x}", source_id="oracle")


def trust_oracle(engine, n=80):
    for i in range(n):
        engine.observe_evidence_source("oracle", observation="A", resolved_hypothesis="A", temporal_index=i)


def feed(engine, tag, xs, fn):
    for x in xs:
        engine.observe_procedural_experience("f", {"x": x}, fn(x), evidence_id=f"{tag}-{x}", source_id="oracle")


class DefaultsTests(unittest.TestCase):
    def test_cortex_config_and_engine_default_to_abstain(self):
        self.assertEqual(ProcedureCortex(":memory:", trust_provider=TRUST).extrapolation_guard, "abstain")
        self.assertEqual(ASMConfig().procedure_extrapolation_guard, "abstain")
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(ASMEngine(Path(d) / "a.db").procedures.extrapolation_guard, "abstain")

    def test_rollback_to_legacy_behaviour_is_one_setting(self):
        with tempfile.TemporaryDirectory() as d:
            engine = ASMEngine(Path(d) / "a.db", config=ASMConfig(procedure_extrapolation_guard="off"))
            self.assertEqual(engine.procedures.extrapolation_guard, "off")


class CortexScenarioTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "p.db"
        self.c = ProcedureCortex(self.db, trust_provider=TRUST)            # DEFAULT configuration
        train_affine(self.c)

    def tearDown(self):
        self.c.close(); self.tmp.cleanup()

    def test_validated_rule_answers_inside_the_evidence_range_and_refuses_outside(self):
        for x in (0, 1, 15, 17):                                            # fit points, validation points and both boundaries
            self.assertEqual(self.c.predict("f", {"x": x})["value"], 2 * x + 3)
        for x in (-1, 18, 99, 100):
            r = self.c.predict("f", {"x": x})
            self.assertEqual((r["status"], r["reason"], r["outside"]), ("abstained", "outside_evidence_support", ["x"]))

    def test_interior_gap_is_answered_because_the_check_is_a_bounding_box(self):
        # Evidence covers 0..2 and 10..17; x=5 lies in the gap but inside the box. Documented limit of the guard.
        r = self.c.predict("f", {"x": 5})
        self.assertEqual((r["status"], r["value"], r["extrapolating"]), ("predicted", 13, False))

    def test_legacy_off_still_extrapolates_the_same_validated_rule(self):
        legacy = ProcedureCortex(Path(self.tmp.name) / "legacy.db", trust_provider=TRUST, extrapolation_guard="off")
        try:
            train_affine(legacy)
            self.assertEqual(legacy.predict("f", {"x": 100})["value"], 203)
        finally:
            legacy.close()

    def test_guard_survives_close_and_reopen_of_the_persisted_database(self):
        self.c.close()
        self.c = ProcedureCortex(self.db, trust_provider=TRUST)
        self.assertEqual(self.c.predict("f", {"x": 15})["value"], 33)
        self.assertEqual(self.c.predict("f", {"x": 100})["reason"], "outside_evidence_support")

    def test_untrusted_evidence_suspends_the_procedure_instead_of_widening_its_range(self):
        self.trust = {"reliability": 0.1, "version": 1}
        bad = ProcedureCortex(Path(self.tmp.name) / "bad.db", trust_provider=lambda s: {"reliability": 0.99, "version": 1} if s == "oracle" else self.trust)
        try:
            train_affine(bad)
            for x in range(100, 105):
                bad.observe("f", {"x": x}, 2 * x + 3, evidence_id=f"bad-{x}", source_id="stranger")
            r = bad.predict("f", {"x": 100})
            self.assertEqual((r["status"], r["reason"]), ("abstained", "dependency_invalidated"))   # trust handling still comes first
        finally:
            bad.close()


class EngineScenarioTests(unittest.TestCase):
    def build(self, d, **cfg):
        e = ASMEngine(Path(d) / "state.db", config=ASMConfig(**cfg) if cfg else None)
        trust_oracle(e)
        feed(e, "fit", range(3), lambda x: 2 * x + 3)
        feed(e, "val", range(10, 18), lambda x: 2 * x + 3)
        return e

    def test_engine_default_refuses_far_extrapolation_but_answers_inside(self):
        with tempfile.TemporaryDirectory() as d:
            e = self.build(d)
            try:
                self.assertEqual(e.predict_procedure("f", {"x": 15})["value"], 33)
                r = e.predict_procedure("f", {"x": 99})
                self.assertEqual((r["status"], r["reason"]), ("abstained", "outside_evidence_support"))
            finally:
                e.close()

    def test_engine_legacy_mode_extrapolates(self):
        with tempfile.TemporaryDirectory() as d:
            e = self.build(d, procedure_extrapolation_guard="off")
            try:
                self.assertEqual(e.predict_procedure("f", {"x": 99})["value"], 201)
            finally:
                e.close()

    def test_guarded_predictions_are_still_read_only_for_autonomy_state(self):
        with tempfile.TemporaryDirectory() as d:
            e = self.build(d)
            try:
                before, dep_before = e.procedure_autonomy_status("f"), e.evidence_dependency.export_state()
                for _ in range(50):
                    self.assertEqual(e.predict_procedure("f", {"x": 100})["status"], "abstained")
                    self.assertEqual(e.predict_procedure("f", {"x": 16})["value"], 35)
                self.assertEqual(e.procedure_autonomy_status("f"), before)
                self.assertEqual(e.evidence_dependency.export_state(), dep_before)
            finally:
                e.close()


if __name__ == "__main__":
    unittest.main()
