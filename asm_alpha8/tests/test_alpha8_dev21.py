"""DEV21 tests: sharing a candidate budget between learned sources (experimental, opt-in).

Part A: `ProcedureCortex(family_sharing=...)` shares `induce`'s family budget between learned families. DEV4 found that
with the default listing order a two-parameter family uses the whole budget, so a relevant family listed after it is
never tried (T3b interference). Part B: `StepLibrary.candidates_for(sharing=...)` orders candidates within a kind.
"""
import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from asm.coding.content import ProblemContext  # noqa: E402
from asm.coding.steps import StepLibrary  # noqa: E402
from asm.learning import structtransfer as T  # noqa: E402
from asm.procedure_cortex import ProcedureCortex  # noqa: E402

SEED = 20261102  # DEV4's pre-registered seed


def norm(s):
    return ast.unparse(ast.parse(s))


class FamilySharingTests(unittest.TestCase):
    def attempt(self, arm, c, mode=None):
        return T.run_attempt(arm, c, 0, SEED, None if mode is None else {"family_sharing": mode})

    def test_the_default_is_listing_and_keeps_dev4_interference(self):
        cortex = ProcedureCortex(":memory:", trust_provider=T.TRUST)
        try:
            self.assertEqual(cortex.family_sharing, "listing")
        finally:
            cortex.close()
        r = self.attempt("mixed", 3)  # default configuration, as DEV4 ran it
        self.assertEqual(r["status"], "unresolved")
        self.assertFalse(r["success"])

    def test_round_robin_reaches_a_relevant_family_listed_after_a_two_parameter_family(self):
        for c in (-8, 3, 8):  # the first, a middle and the last instantiation of the relevant family
            r = self.attempt("mixed", c, "round_robin")
            self.assertTrue(r["success"], (c, r))
            self.assertTrue(str(r["origin"]).startswith("family:"))
            self.assertEqual(r["wrong"], 0)

    def test_a_single_family_is_unchanged(self):
        a, b = self.attempt("relevant", 3, "listing"), self.attempt("relevant", 3, "round_robin")
        self.assertEqual((a["status"], a["candidates"], a["evaluator_calls"]), (b["status"], b["candidates"], b["evaluator_calls"]))

    def test_unrelated_families_still_find_nothing(self):
        r = self.attempt("unrelated", 3, "round_robin")
        self.assertEqual(r["status"], "unresolved")
        self.assertEqual(r["wrong"], 0)

    def test_an_unknown_rule_is_refused(self):
        with self.assertRaises(ValueError):
            ProcedureCortex(":memory:", trust_provider=T.TRUST, family_sharing="random")


GENERIC = [  # a generic step (a call with one argument -> its argument), learned from three fixes, in Call.args
    ("def f(xs):\n    return sorted(list(xs))\n", "def f(xs):\n    return sorted(xs)\n", "g1"),
    ("def g(a):\n    return len(tuple(a))\n", "def g(a):\n    return len(a)\n", "g2"),
    ("def h(b):\n    return set(list(b))\n", "def h(b):\n    return set(b)\n", "g3"),
]
SPECIFIC = [  # a structural step (drop a `not`), learned from two fixes
    ("def k(a):\n    if not a:\n        return 1\n    return 0\n", "def k(a):\n    if a:\n        return 1\n    return 0\n", "s1"),
    ("def q(b):\n    if not b:\n        b = 2\n    return b\n", "def q(b):\n    if b:\n        b = 2\n    return b\n", "s2"),
]
SRC = "def m(v, w, x, y):\n    z = not y\n    return f(str(v), str(w), str(x), repr(y)), z\n"
WANT = "def m(v, w, x, y):\n    z = y\n    return f(str(v), str(w), str(x), repr(y)), z\n"


class StepSharingTests(unittest.TestCase):
    def test_round_robin_gives_every_step_a_turn_before_any_step_gets_another(self):
        lib = StepLibrary()
        lib.learn(GENERIC + SPECIFIC, "test")
        span = (1, SRC.count("\n") + 1)
        key = lib.candidates_for(SRC, "m.py", span, ProblemContext(), limit=2, as_candidates=False, sharing="key")
        rr = lib.candidates_for(SRC, "m.py", span, ProblemContext(), limit=2, as_candidates=False, sharing="round_robin")
        self.assertEqual(len({info["step"] for _, info in key}), 1)  # key order: the generic step fills the budget
        self.assertNotIn(norm(WANT), [norm(p) for p, _ in key])
        self.assertEqual(len({info["step"] for _, info in rr}), 2)   # round robin: one candidate from each step
        self.assertIn(norm(WANT), [norm(p) for p, _ in rr])

    def test_key_order_is_the_default_and_an_unknown_rule_is_refused(self):
        lib = StepLibrary()
        lib.learn(GENERIC + SPECIFIC, "test")
        src, span = SRC, (1, SRC.count("\n") + 1)
        a = lib.candidates_for(src, "m.py", span, ProblemContext(), limit=5, as_candidates=False)
        b = lib.candidates_for(src, "m.py", span, ProblemContext(), limit=5, as_candidates=False, sharing="key")
        self.assertEqual([p for p, _ in a], [p for p, _ in b])
        with self.assertRaises(ValueError):
            lib.candidates_for(src, "m.py", span, ProblemContext(), sharing="random")


RAISED = [  # the raised exception renamed: learned as "a name -> an exception hole" (it matches every name)
    ("def f(x):\n    if x < 0:\n        raise ValueError('neg')\n    return x\n",
     "def f(x):\n    if x < 0:\n        raise TypeError('neg')\n    return x\n", "e1"),
    ("def g(y):\n    if not y:\n        raise KeyError(y)\n    return y\n",
     "def g(y):\n    if not y:\n        raise LookupError(y)\n    return y\n", "e2"),
]
RAISE_SRC = "def m(a, b):\n    c = a + b\n    if c < 0:\n        raise KeyError('neg')\n    return c\n"


class ExceptionSiteTests(unittest.TestCase):
    def changed_lines(self, prog):
        return {i for i, (x, y) in enumerate(zip(RAISE_SRC.splitlines(), prog.splitlines())) if x != y}

    def test_the_raise_guard_keeps_exception_holes_at_the_raised_exception(self):
        lib = StepLibrary()
        lib.learn(RAISED, "test")
        self.assertIn("exc", [t for st in lib.steps.values() for t in st.holes.values()])
        span = (1, RAISE_SRC.count("\n") + 1)
        anywhere = lib.candidates_for(RAISE_SRC, "m.py", span, ProblemContext(), limit=80, as_candidates=False)
        guarded = lib.candidates_for(RAISE_SRC, "m.py", span, ProblemContext(), limit=80, as_candidates=False,
                                     exception_sites="raise")
        self.assertTrue(any(self.changed_lines(p) - {3} for p, _ in anywhere))  # the default rewrites other names too
        self.assertTrue(guarded)
        # only the raise line changes (one candidate is a no-op: the exception filler is called without the current
        # name, so it can offer it again; pre-existing DEV18 behaviour, kept)
        self.assertTrue(all(self.changed_lines(p) <= {3} for p, _ in guarded))
        with self.assertRaises(ValueError):
            lib.candidates_for(RAISE_SRC, "m.py", span, ProblemContext(), exception_sites="nowhere")


class GateLogicTests(unittest.TestCase):
    """The pre-registered decision rules of benchmarks/dev21_evaluate.py and benchmarks/dev21_transfer.py."""

    def setUp(self):
        sys.path.insert(0, str(ROOT / "benchmarks"))
        import dev21_evaluate
        import dev21_transfer
        self.E, self.T = dev21_evaluate, dev21_transfer

    def test_the_exact_sign_test(self):
        self.assertEqual(self.E.sign_test_p(0, 0), 1.0)
        self.assertAlmostEqual(self.E.sign_test_p(5, 0), 1 / 32)
        self.assertAlmostEqual(self.E.sign_test_p(7, 1), 9 / 256)
        self.assertEqual(self.T.mcnemar_one_sided(7, 1), self.E.sign_test_p(7, 1))

    def test_holm_stops_at_the_first_failure(self):
        self.assertEqual(self.E.holm({"a": 0.01, "b": 0.04}), {"a": True, "b": True})    # 0.01 <= .025, 0.04 <= .05
        self.assertEqual(self.E.holm({"a": 0.03, "b": 0.04}), {"a": False, "b": False})  # 0.03 > .025: nothing passes
        self.assertEqual(self.E.holm({"a": 0.001, "b": 0.2}), {"a": True, "b": False})

    def test_a_gate_needs_the_net_gain_and_the_corrected_test(self):
        def rows(arm_only, control_only, both=0):
            out = [{"id": f"x{i}", "control": False, "round_robin": True, "guard": False} for i in range(arm_only)]
            out += [{"id": f"y{i}", "control": True, "round_robin": False, "guard": True} for i in range(control_only)]
            out += [{"id": f"z{i}", "control": True, "round_robin": True, "guard": True} for i in range(both)]
            return out
        v = self.E.gate_verdicts(rows(8, 0, 3))
        self.assertEqual((v["G21-B"]["net"], v["G21-B"]["verdict"]), (8, "passed"))
        self.assertEqual(v["G21-C"]["verdict"], "not passed")  # the guard only lost here
        v = self.E.gate_verdicts(rows(4, 0))
        self.assertEqual(v["G21-B"]["verdict"], "not passed")   # net 4 but p = 1/16 > 0.025 (Holm, first of two)

    def test_shuffled_labels_with_a_repeated_value(self):
        """Amendment A1: shift's three fit labels can repeat (x = 0 and x = -c both give 0); DEV4's derangement raised."""
        import random
        with self.assertRaises(RuntimeError):
            T.derange([0, 0, 5], random.Random(1))
        out = self.T.shuffled([0, 0, 5], random.Random(1))
        self.assertEqual(sorted(out), [0, 0, 5])
        self.assertEqual(sum(a != b for a, b in zip(out, [0, 0, 5])), 2)  # as many positions as possible change
        self.assertEqual(self.T.shuffled([4, 9, 16], random.Random(7)), T.derange([4, 9, 16], random.Random(7)))  # unchanged

    def test_wilson_interval(self):
        self.assertEqual(self.T.wilson(48, 48), (0.926, 1.0))
        self.assertEqual(self.T.wilson(0, 48), (0.0, 0.074))


if __name__ == "__main__":
    unittest.main()
