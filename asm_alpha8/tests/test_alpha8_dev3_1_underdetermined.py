import json
import re
import unittest
from pathlib import Path

from asm.learning import simlab as S
from asm.learning import simlab_underdetermined as U
from asm.learning.simlab_ud_prereg import UD_PREREG

ROOT = Path(__file__).resolve().parents[1]
SEED = 3


def factories(asm=False):
    f = {
        "memorizer": S.MemorizerLearner,
        "naive_affine_extrapolator": U.NaiveAffineExtrapolator,
        "hidden_mod_bayes_vote": lambda: U.HiddenModBayesLearner("vote"),
        "hidden_mod_bayes_abstain": lambda: U.HiddenModBayesLearner("abstain"),
    }
    if asm:
        f["asm_procedure_cortex"] = U.ASMHiddenModLearner
    return f


class TaskTests(unittest.TestCase):
    def setUp(self):
        self.tasks = [U.make_hidden_mod_task(i, SEED) for i in range(60)]

    def test_population_is_balanced_and_deterministic(self):
        self.assertEqual(sum(t.kind == "plain" for t in self.tasks), 30)
        self.assertEqual(sum(t.kind == "mod" for t in self.tasks), 30)
        self.assertEqual([t.truth for t in self.tasks], [U.make_hidden_mod_task(i, SEED).truth for i in range(60)])

    def test_shots_never_reveal_the_modulus_yet_extrapolation_does(self):
        for t in self.tasks:
            a, b = t.truth["a"], t.truth["b"]
            plain = lambda x: a * x + b
            self.assertTrue(all(plain(x) == t.label(x) for x in t.pool), t.task_id)        # underdetermination is real
            self.assertTrue(all(plain(x) == t.label(x) for x in U.INTERP_XS), t.task_id)    # interpolation is identical under both rules
            wraps = [x for x in U.EXTRAP_XS if plain(x) != t.label(x)]
            if t.kind == "mod":
                self.assertTrue(all(plain(x) < t.truth["m"] for x in t.pool))               # no shot value wraps
                self.assertGreaterEqual(len(wraps), 1)                                      # but at least one extrapolation query does
            else:
                self.assertEqual(wraps, [])

    def test_queries_are_unseen_and_typed(self):
        for t in self.tasks:
            self.assertFalse(set(t.queries) & set(t.pool))
            self.assertEqual({t.qtype(x) for x in U.INTERP_XS}, {"interp"})
            self.assertEqual({t.qtype(x) for x in U.EXTRAP_XS}, {"extrap"})
        rows = U.score_task_typed(U.NaiveAffineExtrapolator(), self.tasks[0], S.draw_shots(self.tasks[0], 24, SEED))
        self.assertEqual((len(rows["interp"]), len(rows["extrap"])), (2, 6))

    def test_summary_confident_wrong_rate_hand_values(self):
        rows = [(True, False, 0.95), (True, False, 0.5), (True, True, 0.9), (False, False, 0.0)]
        m = U.summarize_ud(rows)
        self.assertEqual(m["n_wrong"], 2)
        self.assertAlmostEqual(m["confident_wrong_rate"], 0.25)          # only the 0.95-confidence error, over 4 queries
        self.assertAlmostEqual(m["conf_when_wrong"], 0.725)


class LearnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.res = U.run_underdetermined(factories(), seed=UD_PREREG["seed"], tasks=UD_PREREG["tasks"], ks=UD_PREREG["ks"])

    def cell(self, name, k, q):
        return self.res["cells"][name][str(k)][q]

    def test_naive_extrapolator_exposes_the_hazard(self):
        c = self.cell("naive_affine_extrapolator", 24, "extrap")
        self.assertGreater(c["confident_wrong_rate"], 0.30); self.assertGreater(c["ece"], 0.30)
        self.assertEqual(self.cell("naive_affine_extrapolator", 24, "interp")["correct_rate"], 1.0)

    def test_bayes_reference_is_calibrated_and_safe_variant_never_wrong(self):
        self.assertLessEqual(self.cell("hidden_mod_bayes_vote", 24, "extrap")["ece"], 0.10)
        for k in self.res["ks"]:
            for q in ("interp", "extrap"):
                self.assertEqual(self.cell("hidden_mod_bayes_abstain", k, q)["wrong_rate"], 0.0)
        c = self.cell("hidden_mod_bayes_abstain", 24, "extrap")
        self.assertLess(c["coverage"], 1.0)                              # it abstains where the data cannot decide

    def test_canary_is_silent(self):
        for k in self.res["ks"]:
            for q in ("interp", "extrap"):
                self.assertEqual(self.cell("memorizer", k, q)["correct_rate"], 0.0)

    def test_run_is_deterministic(self):
        again = U.run_underdetermined({"naive_affine_extrapolator": U.NaiveAffineExtrapolator}, seed=UD_PREREG["seed"], tasks=UD_PREREG["tasks"], ks=UD_PREREG["ks"])
        self.assertEqual(again["cells"]["naive_affine_extrapolator"], self.res["cells"]["naive_affine_extrapolator"])

    def test_support_guard_trades_coverage_for_safety(self):
        res = U.run_underdetermined({"g": lambda: U.SupportGuarded(U.NaiveAffineExtrapolator())}, seed=UD_PREREG["seed"], tasks=40, ks=[24])
        self.assertEqual(res["cells"]["g"]["24"]["extrap"]["answered"], 0)
        self.assertEqual(res["cells"]["g"]["24"]["interp"]["correct_rate"], 1.0)


class PreregistrationTests(unittest.TestCase):
    def test_document_matches_code_and_hash(self):
        doc = (ROOT / "ALPHA8_DEV3_1_PREREGISTRATION.md").read_text()
        self.assertEqual(json.loads(re.search(r"```json\n(.*?)\n```", doc, re.S).group(1)), UD_PREREG)
        self.assertIn(S.prereg_hash(UD_PREREG), doc)

    def test_validity_verdicts_pass_and_can_fail(self):
        res = U.run_underdetermined(factories(), seed=UD_PREREG["seed"], tasks=UD_PREREG["tasks"], ks=UD_PREREG["ks"])
        v = {x["id"]: x for x in U.evaluate_ud_preregistration(res, UD_PREREG)}
        self.assertTrue(all(v[i]["passed"] for i in ("V1", "V2", "V3", "V4", "V5", "V6")), {i: v[i] for i in v if not v[i]["passed"]})
        self.assertNotIn("U1", v)
        # an overconfident learner standing in for ASM must fail U1 and U2
        bad = factories(); bad["asm_procedure_cortex"] = U.NaiveAffineExtrapolator
        v = {x["id"]: x for x in U.evaluate_ud_preregistration(U.run_underdetermined(bad, seed=UD_PREREG["seed"], tasks=UD_PREREG["tasks"], ks=UD_PREREG["ks"]), UD_PREREG)}
        self.assertFalse(v["U1"]["passed"]); self.assertFalse(v["U2"]["passed"]); self.assertTrue(v["U3"]["passed"])
        # a calibrated answering learner passes U1-U3, an abstaining one passes U1 and U2 vacuously
        for stand_in in (lambda: U.HiddenModBayesLearner("vote"), lambda: U.HiddenModBayesLearner("abstain")):
            ok = factories(); ok["asm_procedure_cortex"] = stand_in
            v = {x["id"]: x for x in U.evaluate_ud_preregistration(U.run_underdetermined(ok, seed=UD_PREREG["seed"], tasks=UD_PREREG["tasks"], ks=UD_PREREG["ks"]), UD_PREREG)}
            self.assertTrue(all(v[i]["passed"] for i in ("U1", "U2", "U3")), v)
        # a broken reference is caught by the validity checks
        broken = factories(); broken["hidden_mod_bayes_abstain"] = U.NaiveAffineExtrapolator
        v = {x["id"]: x for x in U.evaluate_ud_preregistration(U.run_underdetermined(broken, seed=UD_PREREG["seed"], tasks=UD_PREREG["tasks"], ks=UD_PREREG["ks"]), UD_PREREG)}
        self.assertFalse(v["V3"]["passed"])


class ASMUnderdeterminationRegression(unittest.TestCase):
    """Regression tests for the wrap-around hazard found in DEV3 and measured in DEV3.1 (pre-registered U1-U3)."""

    @classmethod
    def setUpClass(cls):
        cls.res = U.run_underdetermined(
            {"asm": U.ASMHiddenModLearner,                                              # the DEFAULT configuration (abstain since DEV3.3)
             "legacy_off": lambda: U.ASMHiddenModLearner(extrapolation_guard="off"),      # pre-DEV3.2 behaviour
             "guarded": lambda: U.SupportGuarded(U.ASMHiddenModLearner(extrapolation_guard="off"))},   # independent lab-only wrapper
            seed=UD_PREREG["seed"], tasks=UD_PREREG["tasks"], ks=[8, 24])   # full population: small samples make U1 noisy

    def cell(self, name, k, q):
        return self.res["cells"][name][str(k)][q]

    def verdicts(self, name):
        res = {"cells": {"asm_procedure_cortex": self.res["cells"][name]}, "ks": self.res["ks"]}
        a = UD_PREREG["asm_claims"]
        c, ic = self.cell(name, a["k"], "extrap"), self.cell(name, a["k"], "interp")
        return {"U1": c["confident_wrong_rate"] <= a["U1_not_confidently_wrong_when_underdetermined"]["max_confident_wrong_rate_extrap"],
                "U2": c["answered"] == 0 or c["ece"] <= a["U2_calibrated_when_underdetermined"]["max_ece_extrap"],
                "U3": ic["correct_rate"] >= a["U3_learns_the_easy_regime"]["min_correct_rate_interp"]}

    def test_legacy_off_hazard_is_pinned(self):
        # CHARACTERIZATION of the pre-DEV3.2 behaviour, still reachable with extrapolation_guard="off". It must keep failing the bars.
        c = self.cell("legacy_off", 24, "extrap")
        self.assertEqual(c["coverage"], 1.0)                              # it answers every extrapolation query
        self.assertGreaterEqual(c["confident_wrong_rate"], 0.25)          # a large share are wrong while stated confidence is high
        self.assertGreaterEqual(c["conf_when_wrong"], 0.90)
        self.assertGreater(c["ece"], 0.25)

    def test_easy_regime_is_learned_and_scarce_data_is_safe(self):
        self.assertEqual(self.cell("asm", 24, "interp")["correct_rate"], 1.0)
        for q in ("interp", "extrap"):
            self.assertEqual(self.cell("asm", 8, q)["answered"], 0)       # with 8 examples it abstains rather than guess

    def test_default_asm_is_honest_under_underdetermination(self):
        # Was an expectedFailure until DEV3.3 made 'abstain' the default (the tripwire fired as designed).
        v = self.verdicts("asm")
        self.assertTrue(v["U1"] and v["U2"] and v["U3"], v)
        self.assertEqual(self.cell("asm", 24, "extrap")["answered"], 0)    # U2 holds vacuously: the price is no extrapolation answers at all

    def test_support_guard_mitigation_meets_the_bars_in_the_lab(self):
        self.assertEqual(self.verdicts("guarded"), {"U1": True, "U2": True, "U3": True})
        self.assertEqual(self.cell("guarded", 24, "extrap")["answered"], 0)   # at the price of answering nothing outside the trained range


class AdapterTests(unittest.TestCase):
    def test_asm_adapter_uses_one_integer_variable_and_reports_no_errors(self):
        res = U.run_underdetermined({"asm_procedure_cortex": U.ASMHiddenModLearner}, seed=UD_PREREG["seed"], tasks=4, ks=[24])
        self.assertEqual(res["errors"], {})
        self.assertEqual(U.ASMHiddenModLearner._values("affine_hidden_mod", 5), {"x": 5})


if __name__ == "__main__":
    unittest.main()
