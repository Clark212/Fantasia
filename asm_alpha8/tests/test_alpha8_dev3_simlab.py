import json
import re
import tempfile
import unittest
from pathlib import Path

from asm.learning import ExperienceLog
from asm.learning import simlab as S
from asm.learning.simlab_prereg import PREREG

ROOT = Path(__file__).resolve().parents[1]
SEED = 11


def standard_factories(asm=False):
    f = {
        "memorizer": S.MemorizerLearner,
        "majority": S.MajorityLearner,
        "rulesearch_abstain": lambda: S.RuleSearchLearner("abstain"),
        "rulesearch_vote": lambda: S.RuleSearchLearner("vote"),
        "rulesearch_guess": lambda: S.RuleSearchLearner("guess"),
        "shuffled_rulesearch_abstain": lambda: S.ShuffledControl(S.RuleSearchLearner("abstain")),
    }
    if asm:
        f["asm_procedure_cortex"] = S.ASMProcedureLearner
    return f


def small_run(factories=None, tasks=12, ks=(2, 4, 12, 24), **kw):
    return S.run_benchmark(factories or standard_factories(), seed=SEED, tasks_per_family=tasks, ks=list(ks), **kw)


class EnvironmentTests(unittest.TestCase):
    def test_tasks_are_deterministic_and_well_formed(self):
        for family in S.FAMILIES:
            a, b = S.make_suite(family, 15, SEED), S.make_suite(family, 15, SEED)
            self.assertEqual([t.truth for t in a], [t.truth for t in b])
            for t in a:
                hyps = S.hypothesis_params(family, t.public)
                self.assertIn(dict(t.truth), hyps)                       # truth lies inside the declared class
                self.assertFalse(set(t.queries) & set(t.pool))           # queries never in the pool
                self.assertGreaterEqual(len(t.queries), 2)
                labels = [(x, t.label(x)) for x in t.pool]
                consistent = [h for h in hyps if all(S.evaluate_rule(family, t.public, h, x) == y for x, y in labels)]
                for q in t.queries:                                       # every scored query is determined by the pool
                    self.assertEqual(len({S.evaluate_rule(family, t.public, h, q) for h in consistent}), 1)

    def test_different_seeds_give_different_suites(self):
        self.assertNotEqual([t.truth for t in S.make_suite("affine_mod", 10, 1)], [t.truth for t in S.make_suite("affine_mod", 10, 2)])

    def test_shots_are_nested_and_cover_the_pool(self):
        for family in S.FAMILIES:
            t = S.make_task(family, 3, SEED)
            shots = S.draw_shots(t, 24, SEED)
            self.assertEqual(S.draw_shots(t, 8, SEED), shots[:8])         # budget k is a prefix of budget kmax
            self.assertEqual({x for x, _ in shots[:len(t.pool)]}, set(t.pool))   # one full pass covers every pool input
            self.assertTrue(all(y == t.label(x) for x, y in shots))

    def test_unknown_family_rejected(self):
        with self.assertRaises(ValueError):
            S.hypothesis_params("nope", {})


class MetricTests(unittest.TestCase):
    def test_calibration_hand_values(self):
        c = S.calibration_metrics([(True, 1.0), (False, 1.0)])
        self.assertAlmostEqual(c["ece"], 0.5); self.assertAlmostEqual(c["brier"], 0.5); self.assertAlmostEqual(c["mean_confidence"], 1.0)
        c = S.calibration_metrics([(True, 0.5), (False, 0.5)])
        self.assertAlmostEqual(c["ece"], 0.0); self.assertAlmostEqual(c["brier"], 0.25)
        c = S.calibration_metrics([(True, 0.9)] * 9 + [(False, 0.9)])
        self.assertAlmostEqual(c["ece"], 0.0, places=9)
        self.assertEqual(S.calibration_metrics([]), {"ece": 0.0, "brier": 0.0, "mean_confidence": 0.0})

    def test_summary_counts_abstention_as_not_correct(self):
        rows = [(True, True, 1.0), (True, False, 1.0), (False, False, 0.0), (False, False, 0.0)]
        m = S.summarize(rows)
        self.assertEqual((m["n"], m["answered"], m["correct"]), (4, 2, 1))
        self.assertAlmostEqual(m["coverage"], 0.5); self.assertAlmostEqual(m["precision"], 0.5)
        self.assertAlmostEqual(m["correct_rate"], 0.25); self.assertAlmostEqual(m["wrong_rate"], 0.25)

    def test_bootstrap(self):
        same = S.paired_bootstrap([0.5] * 10, [0.5] * 10, seed=1)
        self.assertEqual((same["mean"], same["lo"], same["hi"]), (0.0, 0.0, 0.0))
        better = S.paired_bootstrap([0.9] * 10 + [0.8] * 10, [0.1] * 20, seed=1)
        self.assertGreater(better["lo"], 0.6)
        worse = S.paired_bootstrap([0.1] * 20, [0.9] * 20, seed=1)
        self.assertLess(worse["hi"], 0.0)                                 # sign matters
        self.assertEqual(S.paired_bootstrap([0.2, 0.4, 0.9], [0.1, 0.5, 0.2], seed=3), S.paired_bootstrap([0.2, 0.4, 0.9], [0.1, 0.5, 0.2], seed=3))
        with self.assertRaises(ValueError):
            S.paired_bootstrap([1.0], [1.0, 2.0])


class ProtocolTests(unittest.TestCase):
    def test_fresh_learner_per_task_and_budget(self):
        made = []

        class Counting(S.MajorityLearner):
            def __init__(self):
                self.fit_calls = 0
                made.append(self)

            def fit(self, ctx, shots):
                self.fit_calls += 1
                super().fit(ctx, shots)

        S.run_benchmark({"m": Counting}, seed=SEED, tasks_per_family=5, ks=[2, 4, 8], families=["boolean_4", "xor_4"])
        self.assertEqual(len(made), 5 * 3 * 2)                            # tasks x budgets x families
        self.assertEqual({m.fit_calls for m in made}, {1})                # each instance fitted exactly once: no state can carry over

    def test_memorizer_canary_is_silent_in_real_protocol_and_fires_on_a_leak(self):
        res = small_run({"memorizer": S.MemorizerLearner}, tasks=8)
        for fam in S.FAMILIES:
            for k in res["ks"]:
                self.assertEqual(res["cells"]["memorizer"][fam][str(k)]["correct_rate"], 0.0)
        t = S.make_task("boolean_4", 0, SEED)
        leaky_shots = [(q, t.label(q)) for q in t.queries]                # deliberately leak the answers
        rows = S.score_task(S.MemorizerLearner(), t, leaky_shots, t.queries)
        self.assertGreater(S.summarize(rows)["correct_rate"], 0.0)

    def test_benchmark_is_deterministic_and_persists_a_verifiable_suite(self):
        with tempfile.TemporaryDirectory() as d:
            la, lb = ExperienceLog(Path(d) / "a.jsonl", fsync=False), ExperienceLog(Path(d) / "b.jsonl", fsync=False)
            a = small_run({"majority": S.MajorityLearner}, tasks=6, log=la)
            b = small_run({"majority": S.MajorityLearner}, tasks=6, log=lb)
            self.assertEqual(a["cells"], b["cells"])
            self.assertEqual(a["suite_log_head_hash"], b["suite_log_head_hash"])
            expected = sum(len(t.pool) + len(t.queries) for f in S.FAMILIES for t in S.make_suite(f, 6, SEED))
            self.assertEqual(a["suite_log_entries"], expected)
            self.assertTrue(la.verify()["ok"])
            first = next(la.records())
            self.assertEqual((first.source, first.evidence_status), ("simulation", "labeled"))


class ReferenceLearnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.res = small_run()

    def cell(self, learner, fam, k):
        return self.res["cells"][learner][fam][str(k)]

    def test_safe_reference_learner_is_never_wrong_and_learns(self):
        for fam in S.FAMILIES:
            for k in self.res["ks"]:
                self.assertEqual(self.cell("rulesearch_abstain", fam, k)["wrong_rate"], 0.0)
            self.assertGreaterEqual(self.cell("rulesearch_abstain", fam, 24)["correct_rate"], 0.95)

    def test_learning_improves_with_experience(self):
        for fam in S.FAMILIES:
            self.assertGreater(self.cell("rulesearch_abstain", fam, 24)["correct_rate"], self.cell("rulesearch_abstain", fam, 2)["correct_rate"] - 1e-9)
        self.assertGreater(self.cell("rulesearch_abstain", "boolean_4", 24)["correct_rate"], self.cell("rulesearch_abstain", "boolean_4", 2)["correct_rate"])

    def test_calibration_metric_separates_honest_from_overconfident(self):
        for fam in ("boolean_4", "xor_4"):
            honest, over = self.cell("rulesearch_vote", fam, 4)["ece"], self.cell("rulesearch_guess", fam, 4)["ece"]
            self.assertGreater(over - honest, 0.10)

    def test_controls_behave_as_controls(self):
        for fam in S.FAMILIES:
            self.assertLessEqual(self.cell("shuffled_rulesearch_abstain", fam, 24)["correct_rate"], 0.25)
            self.assertGreater(self.cell("rulesearch_abstain", fam, 24)["correct_rate"] - self.cell("majority", fam, 24)["correct_rate"], 0.15)

    def test_guess_mode_always_answers_even_when_no_hypothesis_fits(self):
        res = S.run_benchmark({"g": lambda: S.ShuffledControl(S.RuleSearchLearner("guess"))}, seed=SEED,
                              tasks_per_family=10, ks=[24], families=["boolean_4"])
        c = res["cells"]["g"]["boolean_4"]["24"]
        self.assertEqual(c["coverage"], 1.0)                              # fallback path: answers despite inconsistent evidence
        self.assertEqual(c["mean_confidence"], 1.0)                       # and claims certainty


    def test_abstention_costs_correctness_but_not_safety(self):
        c = self.cell("rulesearch_abstain", "boolean_4", 2)
        self.assertLess(c["coverage"], 1.0); self.assertEqual(c["wrong_rate"], 0.0)


class PreregistrationTests(unittest.TestCase):
    def test_document_and_code_are_identical_and_hash_recorded(self):
        doc = (ROOT / "ALPHA8_DEV3_PREREGISTRATION.md").read_text()
        block = re.search(r"```json\n(.*?)\n```", doc, re.S).group(1)
        self.assertEqual(json.loads(block), PREREG)
        self.assertIn(S.prereg_hash(PREREG), doc)

    def test_verdicts_pass_for_good_learners_and_can_fail(self):
        good = small_run(standard_factories(asm=False), tasks=12)
        verdicts = {v["id"]: v for v in S.evaluate_preregistration(good, PREREG)}
        self.assertTrue(all(verdicts[h]["passed"] for h in ("H1", "H2", "H3", "H4", "H5", "H6")), verdicts)
        self.assertNotIn("A1", verdicts)                                   # no ASM learner supplied, no ASM verdict

        class AlwaysFalse(S.Learner):
            name = "always_false"
            def fit(self, ctx, shots): pass
            def predict(self, x): return False, 1.0                       # confident, usually wrong

        bad = standard_factories(); bad["asm_procedure_cortex"] = AlwaysFalse
        v = {x["id"]: x for x in S.evaluate_preregistration(small_run(bad, tasks=12), PREREG)}
        self.assertFalse(v["A1"]["passed"]); self.assertFalse(v["A2"]["passed"]); self.assertFalse(v["A3"]["passed"])
        broken = standard_factories(); broken["rulesearch_abstain"] = lambda: S.RuleSearchLearner("guess")
        v = {x["id"]: x for x in S.evaluate_preregistration(small_run(broken, tasks=12), PREREG)}
        self.assertFalse(v["H1"]["passed"])                                # an unsafe "reference" is caught
        leaky = standard_factories(); leaky["memorizer"] = lambda: _LeakyMemorizer()
        v = {x["id"]: x for x in S.evaluate_preregistration(small_run(leaky, tasks=12), PREREG)}
        self.assertFalse(v["H3"]["passed"])                                # a canary that cheats is caught


class _LeakyMemorizer(S.Learner):
    name = "memorizer"
    def fit(self, ctx, shots): self.ctx = ctx
    def predict(self, x):
        t = S.make_task(self.ctx["family"], int(self.ctx["task_id"].split("-")[1]), SEED)
        return t.label(x), 1.0                                             # peeks at ground truth


class ASMAdapterTests(unittest.TestCase):
    def test_adapter_runs_without_errors_and_is_safe_when_data_is_scarce(self):
        res = S.run_benchmark({"asm_procedure_cortex": S.ASMProcedureLearner}, seed=SEED, tasks_per_family=3, ks=[2, 24])
        self.assertEqual(res["errors"], {})                                # adapter exceptions are never swallowed silently
        for fam in S.FAMILIES:
            c = res["cells"]["asm_procedure_cortex"][fam]["2"]
            self.assertEqual(c["wrong_rate"], 0.0)                         # with 2 examples it must not answer wrongly

    def test_adapter_reports_errors_instead_of_hiding_them(self):
        learner = S.ASMProcedureLearner()
        learner.fit({"family": "affine_mod", "public": {"m": 29}, "task_id": "affine_mod-9999"}, [(1, 10**13)])   # invalid expected value
        self.assertGreater(learner.errors, 0)
        self.assertTrue(learner.error_samples)


if __name__ == "__main__":
    unittest.main()
