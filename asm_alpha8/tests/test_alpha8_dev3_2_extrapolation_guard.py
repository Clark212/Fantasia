import math
import tempfile
import unittest
from pathlib import Path

from asm.config import ASMConfig
from asm.engine import ASMEngine
from asm.learning import simlab_underdetermined as U
from asm.learning.simlab_ud_prereg import UD_PREREG
from asm.procedure_cortex import ProcedureCortex

TRUST = lambda source: {"reliability": 1.0, "version": 1}
KEYS_OFF = {"status", "value", "version", "confidence", "support", "contradictions"}


def trained(mech="m", fn=lambda x: 2 * x + 3, xs=tuple(range(12)), rounds=3, **kw):
    cortex = ProcedureCortex(":memory:", trust_provider=TRUST, **kw)
    i = 0
    for _ in range(rounds):
        for x in xs:
            cortex.observe(mech, {"x": x}, fn(x), evidence_id=f"e{i}", source_id="s", root_id=f"r{i}", auto_induce=True)
            i += 1
    assert cortex.predict(mech, {"x": 5})["status"] == "predicted", "fixture failed to activate a procedure"
    return cortex


class ExplicitOffTests(unittest.TestCase):
    def test_off_adds_no_keys_and_ignores_range(self):
        off = trained(extrapolation_guard="off")
        for x in (-5, 0, 5, 11, 12, 50, 10**6):
            a = off.predict("m", {"x": x})
            self.assertEqual(set(a), KEYS_OFF)
            self.assertEqual((a["status"], a["value"]), ("predicted", 2 * x + 3))      # legacy behaviour: answers far outside the range
        self.assertGreater(off.predict("m", {"x": 50})["confidence"], 0.9)


class AbstainModeTests(unittest.TestCase):
    def setUp(self):
        self.off, self.guard = trained(extrapolation_guard="off"), trained(extrapolation_guard="abstain")

    def test_inside_range_is_unchanged_including_boundaries_and_unseen_points(self):
        for x in (0, 3, 7, 11):                                             # 3 and 7 never appeared exactly? they did here; 0 and 11 are the boundaries
            a, b = self.off.predict("m", {"x": x}), self.guard.predict("m", {"x": x})
            self.assertEqual({k: v for k, v in b.items() if k != "extrapolating"}, a)
            self.assertFalse(b["extrapolating"])

    def test_unseen_interior_point_is_inside(self):
        # 10 distinct training inputs (ASM needs >= 8 distinct inputs before a procedure activates) with interior gaps at 4 and 7
        sparse = trained(xs=(0, 1, 2, 3, 5, 6, 8, 9, 10, 11), extrapolation_guard="abstain")
        for gap in (4, 7):
            r = sparse.predict("m", {"x": gap})
            self.assertEqual((r["status"], r["value"], r["extrapolating"]), ("predicted", 2 * gap + 3, False))   # bounding box allows gaps (documented limit)
        self.assertEqual(sparse.predict("m", {"x": 12})["status"], "abstained")

    def test_too_few_distinct_inputs_never_activates_so_nothing_is_answered(self):
        # Documents an observed property of the cortex itself: repeating 7 distinct inputs does not substitute for distinct evidence.
        cortex = ProcedureCortex(":memory:", trust_provider=TRUST, extrapolation_guard="abstain")
        for i in range(56):
            x = (0, 2, 4, 6, 8, 10, 11)[i % 7]
            cortex.observe("m", {"x": x}, 2 * x + 3, evidence_id=f"e{i}", source_id="s", root_id=f"r{i}", auto_induce=True)
        self.assertEqual(cortex.predict("m", {"x": 5})["reason"], "no_validated_active_procedure")

    def test_outside_range_abstains_with_reason(self):
        for x in (-1, 12, 50):
            r = self.guard.predict("m", {"x": x})
            self.assertEqual((r["status"], r["reason"], r["outside"]), ("abstained", "outside_evidence_support", ["x"]))
            self.assertNotIn("value", r)

    def test_multi_variable_any_variable_outside_triggers(self):
        cortex = ProcedureCortex(":memory:", trust_provider=TRUST, extrapolation_guard="abstain")
        i = 0
        for _ in range(3):
            for x in range(5):
                for y in range(5):
                    cortex.observe("add", {"x": x, "y": y}, x + y, evidence_id=f"e{i}", source_id="s", root_id=f"r{i}", auto_induce=True)
                    i += 1
        self.assertEqual(cortex.predict("add", {"x": 2, "y": 3})["value"], 5)
        self.assertEqual(cortex.predict("add", {"x": 9, "y": 3})["outside"], ["x"])
        self.assertEqual(cortex.predict("add", {"x": 2, "y": -4})["outside"], ["y"])
        self.assertEqual(sorted(cortex.predict("add", {"x": 9, "y": 9})["outside"]), ["x", "y"])

    def test_bool_only_procedures_are_not_guarded(self):
        outs = {}
        for mode in ("off", "abstain", "discount"):
            cortex = ProcedureCortex(":memory:", trust_provider=TRUST, extrapolation_guard=mode)
            i = 0
            for _ in range(6):
                for a in (False, True):
                    for b in (False, True):
                        cortex.observe("g", {"a": a, "b": b}, a and not b, evidence_id=f"e{i}", source_id="s", root_id=f"r{i}", auto_induce=True)
                        i += 1
            outs[mode] = [{k: v for k, v in cortex.predict("g", {"a": a, "b": b}).items() if k != "extrapolating"} for a in (False, True) for b in (False, True)]
        self.assertEqual(outs["off"], outs["abstain"]); self.assertEqual(outs["off"], outs["discount"])
        self.assertTrue(all(r["status"] == "predicted" for r in outs["off"]))

    def test_support_comes_only_from_the_procedures_dependency_sources(self):
        # White-box: plant a stored evidence row from a source the active procedure does NOT depend on, far outside the range.
        # (Through the public API, untrusted evidence suspends the procedure instead; this pins the filter itself.)
        self.guard.db.execute("INSERT INTO procedure_evidence VALUES('stray','m','','stray-root','other',1,'{\"x\":100}','203',999999)")
        r = self.guard.predict("m", {"x": 100})
        self.assertEqual((r["status"], r["reason"], r["outside"]), ("abstained", "outside_evidence_support", ["x"]))

    def test_unknown_support_abstains_conservatively(self):
        self.guard.db.execute("DELETE FROM procedure_evidence WHERE mechanism='m'")
        r = self.guard.predict("m", {"x": 5})
        self.assertEqual((r["status"], r["reason"]), ("abstained", "evidence_support_unknown"))


class DiscountModeTests(unittest.TestCase):
    def test_outside_is_capped_inside_is_unchanged_and_value_is_never_altered(self):
        off, disc = trained(extrapolation_guard="off"), trained(extrapolation_guard="discount", extrapolation_confidence_cap=0.5)
        inside_off, inside = off.predict("m", {"x": 5}), disc.predict("m", {"x": 5})
        self.assertEqual(inside["confidence"], inside_off["confidence"]); self.assertFalse(inside["extrapolating"])
        out_off, out = off.predict("m", {"x": 40}), disc.predict("m", {"x": 40})
        self.assertEqual(out["value"], out_off["value"])
        self.assertTrue(out["extrapolating"])
        self.assertEqual(out["confidence"], 0.5)
        self.assertLess(out["confidence"], out_off["confidence"])

    def test_cap_never_raises_confidence(self):
        low_evidence = trained(rounds=2, extrapolation_guard="discount", extrapolation_confidence_cap=1.0)
        r = low_evidence.predict("m", {"x": 40})
        self.assertLessEqual(r["confidence"], (r["support"] + 1) / (r["support"] + r["contradictions"] + 2))


class ValidationTests(unittest.TestCase):
    def test_invalid_settings_are_rejected_before_opening_anything(self):
        for bad in ("on", "", None, True, "ABSTAIN"):
            with self.assertRaises(ValueError):
                ProcedureCortex(":memory:", trust_provider=TRUST, extrapolation_guard=bad)
        for bad in (0, -0.1, 1.5, math.nan, math.inf, True, "0.5", None):
            with self.assertRaises(ValueError):
                ProcedureCortex(":memory:", trust_provider=TRUST, extrapolation_guard="discount", extrapolation_confidence_cap=bad)

    def test_engine_passes_config_through_and_rejects_bad_values(self):
        with tempfile.TemporaryDirectory() as d:
            engine = ASMEngine(Path(d) / "a.db", config=ASMConfig(procedure_extrapolation_guard="abstain", procedure_extrapolation_confidence_cap=0.3))
            self.assertEqual((engine.procedures.extrapolation_guard, engine.procedures.extrapolation_confidence_cap), ("abstain", 0.3))
            bad = ASMEngine(Path(d) / "b.db", config=ASMConfig(procedure_extrapolation_guard="nope"))
            with self.assertRaises(ValueError):
                bad.procedures


class UnderdeterminationWithGuardTests(unittest.TestCase):
    """The DEV3.1 pre-registered criteria U1-U3, re-evaluated with the guard on."""

    @classmethod
    def setUpClass(cls):
        factories = {
            "off": lambda: U.ASMHiddenModLearner(extrapolation_guard="off"),
            "default": lambda: U.ASMHiddenModLearner(),
            "abstain": lambda: U.ASMHiddenModLearner(extrapolation_guard="abstain"),
            "discount_0.5": lambda: U.ASMHiddenModLearner(extrapolation_guard="discount", extrapolation_confidence_cap=0.5),
            "discount_0.9": lambda: U.ASMHiddenModLearner(extrapolation_guard="discount", extrapolation_confidence_cap=0.9),
        }
        cls.res = U.run_underdetermined(factories, seed=UD_PREREG["seed"], tasks=UD_PREREG["tasks"], ks=[24])

    def verdict(self, name):
        results = {"cells": {"asm_procedure_cortex": self.res["cells"][name]}, "ks": [24]}
        out = U.evaluate_ud_preregistration({**results, "cells": {**results["cells"], **self._validity_stubs()}}, UD_PREREG)
        return {v["id"]: v["passed"] for v in out if v["group"] == "asm"}

    def _validity_stubs(self):
        # the evaluator also reads validity learners; they are not under test here, so reuse any cell shape
        stub = self.res["cells"]["off"]
        return {n: stub for n in ("hidden_mod_bayes_vote", "naive_affine_extrapolator", "hidden_mod_bayes_abstain", "memorizer")}

    def cell(self, name, q):
        return self.res["cells"][name]["24"][q]

    def test_off_still_shows_the_hazard(self):
        self.assertFalse(self.verdict("off")["U1"]); self.assertFalse(self.verdict("off")["U2"])
        self.assertAlmostEqual(self.cell("off", "extrap")["confident_wrong_rate"], 0.3933, places=3)

    def test_abstain_meets_U1_U2_U3_and_keeps_the_easy_regime(self):
        self.assertEqual(self.verdict("abstain"), {"U1": True, "U2": True, "U3": True})
        self.assertEqual(self.cell("abstain", "extrap")["answered"], 0)
        self.assertEqual(self.cell("abstain", "interp"), self.cell("off", "interp"))     # interpolation behaviour is untouched

    def test_discount_answers_stay_identical_and_only_confidence_changes(self):
        for q in ("interp", "extrap"):
            self.assertEqual(self.cell("discount_0.5", q)["answered"], self.cell("off", q)["answered"])
            self.assertEqual(self.cell("discount_0.5", q)["correct"], self.cell("off", q)["correct"])
        self.assertEqual(self.cell("discount_0.5", "extrap")["confident_wrong_rate"], 0.0)

    def test_discount_is_only_as_honest_as_its_cap(self):
        # A cap at or above the 0.8 "confident" line leaves confident errors: the knob is not self-calibrating.
        self.assertGreater(self.cell("discount_0.9", "extrap")["confident_wrong_rate"], 0.3)
        self.assertFalse(self.verdict("discount_0.9")["U1"])

    def test_default_configuration_equals_abstain(self):
        self.assertEqual(self.verdict("default"), {"U1": True, "U2": True, "U3": True})
        for q in ("interp", "extrap"):
            self.assertEqual(self.cell("default", q), self.cell("abstain", q))


if __name__ == "__main__":
    unittest.main()
