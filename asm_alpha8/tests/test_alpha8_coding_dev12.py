"""DEV12 tests: spectrum completeness, semantic tie-break, counterexample search, human-answer feedback, confidence."""
import ast
import tempfile
import textwrap
import unittest
from pathlib import Path

from asm.coding import SafeTestRunner, tree_fingerprint
from asm.coding.counterexamples import analyze_candidates, perturb_inputs, perturb_values
from asm.coding.faultloc import FaultLocalizer, RepairWorkflow, collect_spectrum


class Repo:
    def __init__(self, files):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for rel, src in files.items():
            p = self.root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(textwrap.dedent(src))

    def __enter__(self):
        return self.root

    def __exit__(self, *a):
        self.tmp.cleanup()


G = {"g.py": "def g(n):\n    return n * 3 + 2\n", "tests/test_g.py": "from g import g\ndef test_g(): assert g(2) == 7\n"}
HANG = {"m.py": "def f(x):\n    return x - 1\n",
        "tests/test_m.py": "import time\nfrom m import f\ndef test_fail(): assert f(1) == 2\ndef test_hang(): time.sleep(60)\n"}


# ===================================================== A. incomplete spectrum (the review's bug)
class SpectrumCompletenessTests(unittest.TestCase):
    def test_complete_run_is_marked_complete(self):
        with Repo(G) as root:
            sp = collect_spectrum(root, None, SafeTestRunner(timeout_seconds=30))
            self.assertTrue(sp.complete)
            self.assertIsNone(sp.incomplete_reason)

    def test_timed_out_traced_run_is_incomplete_not_empty(self):
        with Repo(HANG) as root:
            sp = collect_spectrum(root, None, SafeTestRunner(timeout_seconds=3), timeout=3)
            self.assertFalse(sp.complete)
            self.assertIn("timed out", sp.incomplete_reason)

    def test_localizer_refuses_to_rank_on_partial_evidence(self):
        with Repo(HANG) as root:
            r = SafeTestRunner(timeout_seconds=3)
            rep = FaultLocalizer(r, use_semantic=False, trace_timeout=3).localize(root)
            self.assertFalse(rep.spectrum_ok)
            self.assertEqual(rep.suspects, [])
            self.assertIn("incomplete spectrum", rep.notes[0])
            self.assertIn("timed out", rep.spectrum_note)

    def test_workflow_reports_incomplete_spectrum_never_no_failures(self):
        # regression test for the reviewed bug: a real failure plus a hanging test used to be reported as "no_failures"
        with Repo(HANG) as root:
            d = RepairWorkflow(SafeTestRunner(timeout_seconds=3), time_budget_seconds=60).run(root)
            self.assertEqual(d.status, "incomplete_spectrum")
            self.assertNotEqual(d.status, "no_failures")
            self.assertEqual(d.steps, [])
            self.assertTrue(any("incomplete spectrum" in n for n in d.notes))

    def test_unusable_traced_run_is_incomplete(self):
        files = dict(G)
        files["pytest.ini"] = "[pytest]\naddopts = --definitely-not-an-option\n"
        with Repo(files) as root:
            sp = collect_spectrum(root, None, SafeTestRunner(timeout_seconds=30))
            self.assertFalse(sp.complete)
            self.assertIn("usage_error", sp.incomplete_reason)

    def test_process_that_dies_mid_run_is_incomplete(self):
        files = {"m.py": "def f(x): return x\n", "tests/test_m.py": "import os\nfrom m import f\ndef test_die(): os._exit(7)\n"}
        with Repo(files) as root:
            sp = collect_spectrum(root, None, SafeTestRunner(timeout_seconds=20))
            self.assertFalse(sp.complete)

    def test_genuinely_passing_suite_is_still_no_failures(self):
        with Repo({"m.py": "def f(x): return x + 1\n", "tests/test_m.py": "from m import f\ndef test_f(): assert f(1) == 2\n"}) as root:
            d = RepairWorkflow(time_budget_seconds=60).run(root)
            self.assertEqual(d.status, "no_failures")


# ============================================================ B. semantic evidence is a tie-breaker
PARITY = {"parity.py": """
    def describe(n):
        return "even" if is_even(n) else "odd"
    def is_even(n):
        return n % 2 == 0 if n >= 0 else True
    def only_in_failing_test(x):
        return x
""", "tests/test_parity.py": """
    from parity import describe, only_in_failing_test
    def test_pos(): assert describe(3) == "odd"
    def test_neg():
        only_in_failing_test(1)
        assert describe(-3) == "odd"
"""}


class SemanticTieBreakTests(unittest.TestCase):
    def test_semantic_evidence_cannot_outvote_coverage_by_default(self):
        with Repo(PARITY) as root:
            rep = FaultLocalizer(use_semantic=True).localize(root)
            order = [s.qname for s in rep.suspects]
            self.assertEqual(rep.semantic_mode, "tiebreak")
            self.assertEqual(order[0], "parity.only_in_failing_test")  # spectrum 1.0 beats the DEV10-flagged function
            self.assertEqual(rep.suspects[order.index("parity.is_even")].sources["semantic"], 1.0)

    def test_weighted_mode_is_available_and_does_let_semantic_evidence_win(self):
        with Repo(PARITY) as root:
            rep = FaultLocalizer(use_semantic=True, semantic_mode="weighted").localize(root)
            self.assertEqual(rep.suspects[0].qname, "parity.is_even")
            self.assertEqual(rep.semantic_mode, "weighted")

    def test_tiebreak_still_orders_exact_ties(self):
        files = {"parity.py": """
            def describe(n):
                return "even" if is_even(n) else "odd"
            def is_even(n):
                return n % 2 == 0 if n >= 0 else True
        """, "tests/test_parity.py": """
            from parity import describe
            def test_pos(): assert describe(3) == "odd"
            def test_neg(): assert describe(-3) == "odd"
        """}
        with Repo(files) as root:
            rep = FaultLocalizer(use_semantic=True).localize(root)
            self.assertEqual(rep.suspects[0].score, rep.suspects[1].score)  # the base evidence really is tied
            self.assertEqual(rep.suspects[0].qname, "parity.is_even")       # and DEV10 only breaks the tie

    def test_score_is_independent_of_semantic_evidence_in_tiebreak_mode(self):
        with Repo(PARITY) as root:
            a = FaultLocalizer(use_semantic=True).localize(root)
            b = FaultLocalizer(use_semantic=False).localize(root)
            self.assertEqual({s.qname: s.score for s in a.suspects}, {s.qname: s.score for s in b.suspects})

    def test_invalid_mode_rejected(self):
        with self.assertRaises(ValueError):
            FaultLocalizer(semantic_mode="magic")


# ================================================================ C. counterexample machinery
class PerturbationTests(unittest.TestCase):
    def test_variants_are_type_preserving_distinct_and_deterministic(self):
        for v in (5, -3, 2.5, "ab", [1, 2, 3], (1, 2), {"a": 1, "b": 2}, True):
            vs = perturb_values(v)
            self.assertTrue(vs, v)
            self.assertTrue(all(x != v for x in vs), v)
            self.assertTrue(all(type(x) is type(v) for x in vs), v)
            self.assertEqual(vs, perturb_values(v))
            self.assertEqual(len({repr(x) for x in vs}), len(vs))
        self.assertEqual(perturb_values(None), [])

    def test_inputs_start_with_the_recorded_ones_vary_one_argument_at_a_time_and_respect_the_limit(self):
        ins = perturb_inputs(["(5, 'x')", "(5, 'x')", "(1, 'y')"])
        self.assertEqual(ins[:2], [(5, "x"), (1, "y")])  # originals first, duplicates removed
        for t in ins[2:]:
            base = [b for b in [(5, "x"), (1, "y")] if sum(a != c for a, c in zip(t, b)) == 1]
            self.assertTrue(base, t)  # exactly one argument differs from some recorded call
        self.assertLessEqual(len(perturb_inputs(["(%d,)" % i for i in range(40)], limit=25)), 25)
        self.assertEqual(perturb_inputs(["not a tuple", "{1: "]), [])

    def test_nonliteral_recordings_are_ignored(self):
        self.assertEqual(perturb_inputs(["(<object at 0x1>,)"]), [])


class CounterexampleSearchTests(unittest.TestCase):
    def test_plugin_records_literal_call_arguments_only_for_plain_functions(self):
        files = {"m.py": """
            class C:
                def meth(self, x): return x
            def plain(a, b=2): return a + b
            def objy(o): return 1
        """, "tests/test_m.py": """
            from m import C, plain, objy
            def test_x():
                plain(1); plain(3, b=4); plain(1)
                C().meth(9)
                objy(object())
        """}
        with Repo(files) as root:
            sp = collect_spectrum(root, None, SafeTestRunner(timeout_seconds=30))
            self.assertEqual(sorted(sp.calls["m.py:plain"]), ["(1, 2)", "(3, 4)"])  # deduplicated, defaults resolved
            self.assertNotIn("m.py:meth", sp.calls)    # methods are skipped
            self.assertNotIn("m.py:objy", sp.calls)    # object-valued arguments are not literal

    def test_methods_are_skipped_even_when_self_has_a_literal_repr(self):
        # an int subclass makes `self` look like a plain number; without the explicit self/cls filter it would be
        # recorded as if the method were a module-level function
        files = {"m.py": "class N(int):\n    def meth(self, x): return int(self) + x\n",
                 "tests/test_m.py": "from m import N\ndef test_x(): assert N(3).meth(4) == 7\n"}
        with Repo(files) as root:
            sp = collect_spectrum(root, None, SafeTestRunner(timeout_seconds=30))
            self.assertNotIn("m.py:meth", sp.calls)

    def test_unavailable_reasons_are_explicit(self):
        with Repo(G) as root:
            self.assertFalse(analyze_candidates(root, "g.C.m", "g", "g.py", ("a", None), [], {}, is_method=True)["available"])
            r = analyze_candidates(root, "g.g", "g", "g.py", ("a", None), [], {})
            self.assertFalse(r["available"])
            self.assertIn("no literal-argument calls", r["reason"])

    def test_disagreeing_candidates_get_concrete_distinguishing_inputs(self):
        with Repo(G) as root:
            d = RepairWorkflow().run(root)
            step = d.steps[0]
            cx = step["counterexamples"]
            self.assertTrue(cx["available"])
            self.assertTrue(cx["distinguishing"])
            ex = cx["distinguishing"][0]
            self.assertNotEqual(ex["accepted_output"], ex["alternative_output"])
            self.assertEqual(ex["original_output"], {"(3,)": "11", "(1,)": "5"}.get(ex["input"], ex["original_output"]))
            self.assertEqual(step["confidence"], "medium")
            self.assertEqual(step["confidence_basis"], ["alternatives_disagree"])
            self.assertTrue(any("add a test stating the intended result" in c for c in d.caveats))
            self.assertIn("behavioural verification", d.to_markdown())

    def test_footprint_measures_how_much_behaviour_each_candidate_changes(self):
        with Repo({"m.py": "def f(n):\n    return n + 1 if n > 5 else 0\n",
                   "tests/test_m.py": "from m import f\ndef test_f(): assert f(5) == 6\n"}) as root:
            d = RepairWorkflow().run(root)
            fp = d.steps[0]["counterexamples"]["footprint"]
            self.assertTrue(fp)
            self.assertTrue(all(0.0 <= v <= 1.0 for v in fp.values()))

    def test_footprint_value_is_exact_when_it_can_be_predicted(self):
        # the bug is `n > 5` for a test calling big(5): recorded input (5,), perturbed to 6, 4, 0, -5, 10.
        # Any fix flips only the answer for input 5, so exactly 1 of 6 tested inputs changes versus the original.
        with Repo({"m.py": "def big(n):\n    return n > 5\n", "tests/test_m.py": "from m import big\ndef test_big(): assert big(5)\n"}) as root:
            cx = RepairWorkflow().run(root).steps[0]["counterexamples"]
            # DEV14 adds generated inputs beyond these; the DEV12 prediction is checked on the DEV12 inputs only
            by = cx["inputs_by_origin"]
            self.assertEqual(by["recorded"] + by["perturbed"], 6)
            for changed in cx["changed_by_origin"].values():
                self.assertEqual(changed.get("recorded", 0) + changed.get("perturbed", 0), 1)

    def test_equivalent_alternatives_agree_everywhere(self):
        with Repo({"m.py": "def big(n):\n    return n > 5\n", "tests/test_m.py": "from m import big\ndef test_big(): assert big(5)\n"}) as root:
            d = RepairWorkflow().run(root)
            cx = d.steps[0]["counterexamples"]
            self.assertTrue(cx["alternatives_agree_everywhere"])
            self.assertEqual(cx["distinguishing"], [])

    def test_nondeterministic_functions_are_not_compared(self):
        files = {"m.py": "import random\ndef f(n):\n    return n + random.randint(0, 0) - 1\n",
                 "tests/test_m.py": "from m import f\ndef test_f(): assert f(2) == 3\n"}
        with Repo(files) as root:
            d = RepairWorkflow().run(root)
            self.assertIn(d.status, {"resolved", "unresolved"})  # must not crash; comparison skipped or restricted

    def test_counterexample_search_can_be_disabled(self):
        with Repo(G) as root:
            d = RepairWorkflow(counterexamples=False).run(root)
            self.assertFalse(d.steps[0]["counterexamples"]["available"])
            self.assertIn("disabled", d.steps[0]["counterexamples"]["reason"])

    def test_original_repository_untouched_by_the_search(self):
        with Repo(G) as root:
            before = tree_fingerprint(root)
            RepairWorkflow().run(root)
            self.assertEqual(tree_fingerprint(root), before)


# ============================================================ D. learning from a human answer
class HumanAnswerTests(unittest.TestCase):
    def test_answering_a_distinguishing_input_selects_the_intended_fix(self):
        with Repo(G) as root:
            first = RepairWorkflow().run(root)
            ex = first.steps[0]["counterexamples"]["distinguishing"][0]
            self.assertEqual(first.steps[0]["description"], "arith: '*' -> '+' at line 2")  # the wrong guess, flagged
            # the human says g(3) must be 10 (the intended formula is n * 3 + 1)
            second = RepairWorkflow().run(root, examples=[{"function": "g.g", "args": (3,), "expected": 10}])
            self.assertEqual(second.status, "resolved")
            self.assertEqual(second.steps[0]["description"], "const: '2' -> '1' at line 2")
            self.assertEqual(second.steps[0]["confidence"], "high")
            self.assertEqual(second.caveats, [])
            self.assertEqual(second.examples, [{"function": "g.g", "args": (3,), "expected": 10}])
            self.assertTrue(any("human-supplied" in n for n in second.notes))
            self.assertTrue(ex["input"])

    def test_examples_exist_only_in_the_working_copy(self):
        with Repo(G) as root:
            d = RepairWorkflow().run(root, examples=[{"function": "g.g", "args": (3,), "expected": 10}])
            self.assertFalse((root / "tests" / "test_asm_counterexamples.py").exists())
            self.assertNotIn("test_asm_counterexamples", d.diff)
            self.assertEqual(tree_fingerprint(root), d.repo_fingerprint)

    def test_contradictory_example_is_never_satisfied_by_a_forced_patch(self):
        with Repo(G) as root:
            d = RepairWorkflow().run(root, examples=[{"function": "g.g", "args": (2,), "expected": 99}])
            # the real test (g(2) == 7) can be fixed; g(2) == 99 contradicts it, so it stays failing and is reported
            self.assertEqual(d.status, "partial")
            self.assertEqual([s["kind"] for s in d.steps], ["partial"])
            self.assertEqual(d.iterations[-1]["failing"], ["tests/test_asm_counterexamples.py::test_asm_counterexample_0"])
            with self.assertRaises(ValueError):
                RepairWorkflow.apply_fix(root, d, approved=True)


# ================================================================== E. confidence labels
class ConfidenceTests(unittest.TestCase):
    def test_unique_untied_fix_is_high_confidence(self):
        shop = {"shop.py": "def label(n):\n    return 'bulk' if n > 10 else 'single'\n",
                "tests/test_shop.py": "from shop import label\ndef test_a(): assert label(10) == 'bulk'\ndef test_b(): assert label(3) == 'single'\n"}
        with Repo(shop) as root:
            d = RepairWorkflow().run(root)
            self.assertEqual((d.steps[0]["confidence"], d.steps[0]["confidence_basis"]), ("high", []))

    def test_one_warning_sign_is_medium_and_two_are_low(self):
        with Repo(G) as root:
            self.assertEqual(RepairWorkflow().run(root).steps[0]["confidence"], "medium")
        files = {"calc.py": """
            def helper(x): return x + 1
            def is_big(n): return n > 10
            def classify(n):
                return "big" if is_big(helper(n)) else "small"
        """, "tests/test_c.py": """
            from calc import classify
            def test_a(): assert classify(9) == "big"
            def test_b(): assert classify(1) == "small"
        """}
        with Repo(files) as root:
            step = RepairWorkflow().run(root).steps[0]
            self.assertIn("tied_localization", step["confidence_basis"])
            self.assertIn(step["confidence"], {"medium", "low"})

    def test_persisting_behavioural_deviation_forces_low(self):
        files = {"parity.py": "def is_even(n):\n    return n % 2 == 0 if n >= 0 else True\n"
                              "def describe(n):\n    return 'even' if is_even(n) else 'odd'\n",
                 "tests/test_parity.py": "from parity import describe\ndef test_pos(): assert describe(3) == 'odd'\n"
                                         "def test_neg(): assert describe(-3) == 'odd'\n"}
        with Repo(files) as root:
            step = RepairWorkflow().run(root).steps[0]
            self.assertIn("behavioural_deviation_persists", step["confidence_basis"])
            self.assertEqual(step["confidence"], "low")


if __name__ == "__main__":
    unittest.main()
