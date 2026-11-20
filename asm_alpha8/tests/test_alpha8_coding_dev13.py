"""DEV13 tests: object/method/nested replay, state and side-effect comparison, controlled nondeterminism,
overfit-pattern replicas, confidence flags."""
import tempfile
import textwrap
import unittest
from pathlib import Path

from asm.coding import SafeTestRunner, tree_fingerprint
from asm.coding.faultloc import RepairWorkflow, collect_spectrum
from asm.coding.patches import PatchProposalBuilder
from asm.coding.understanding import CodeUnderstanding
from asm.coding.verification import MAX_INPUTS, build_inputs, render, verification_target, verify_patch


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


def prepare(root: Path, runner=None):
    sp = collect_spectrum(root, None, runner or SafeTestRunner(timeout_seconds=30))
    funcs = {f.qname: f for f in CodeUnderstanding().analyze(root).functions}
    return sp, funcs


def patch(root: Path, rel: str, old: str, new: str, name: str):
    src = (root / rel).read_text()
    assert old in src, old
    return name, PatchProposalBuilder.from_replacement(root, rel, src.replace(old, new, 1), name)


CART = {"shop.py": """
    class Cart:
        def __init__(self, tax):
            self.tax = tax
            self.items = []
        def add(self, price):
            self.items.append(price)
            return len(self.items)
        def total(self):
            return sum(self.items) * (1 + self.tax)
    def outer(n):
        def inner(k):
            return k * n
        return inner(3) + 1
""", "tests/test_shop.py": """
    from shop import Cart, outer
    def test_cart():
        c = Cart(0.1); c.add(10); c.add(5)
        assert c.total() > 0
        assert outer(2) == 7
"""}


# ============================================================== 1. recording (objects, methods, nested)
class RecordingTests(unittest.TestCase):
    def test_methods_receivers_nested_functions_and_defaults_are_recorded(self):
        with Repo(CART) as root:
            sp, _ = prepare(root)
            keys = set(sp.records)
            self.assertIn("shop.py:Cart.total", keys)
            self.assertIn("shop.py:Cart.add", keys)
            self.assertIn("shop.py:outer.<locals>.inner", keys)
            view = sp.records["shop.py:Cart.total"][0]["view"]
            self.assertEqual((view[0]["k"], view[0]["cls"], view[0]["attrs"]["tax"]), ("obj", "Cart", "0.1"))
            self.assertEqual(sp.records["shop.py:Cart.total"][0]["test"], "tests/test_shop.py::test_cart")

    def test_frozen_stdlib_modules_are_not_recorded(self):
        with Repo(CART) as root:
            sp, _ = prepare(root)
            self.assertFalse([k for k in sp.records if k.startswith("<")])
            self.assertFalse([k for k in sp.calls if k.startswith("<")])

    def test_unpicklable_arguments_and_unsupported_signatures_are_skipped(self):
        files = {"m.py": """
            def with_lambda(f): return f(1)
            def with_gen(g): return next(g)
            def star(*args): return len(args)
            def kw(**kw): return len(kw)
            def fine(x): return x
            class K:
                @classmethod
                def make(cls, x): return x
        """, "tests/test_m.py": """
            from m import with_lambda, with_gen, star, kw, fine, K
            def test_x():
                with_lambda(lambda v: v); with_gen((v for v in [1])); star(1, 2); kw(a=1); fine(3); K.make(4)
        """}
        with Repo(files) as root:
            sp, _ = prepare(root)
            self.assertEqual(set(sp.records), {"m.py:fine"})  # lambda, generator, *args, **kw, classmethod: not replayable

    def test_per_test_sampling_keeps_the_failing_tests_inputs(self):
        calls = "\n".join(f"def test_p{i}(): assert f({i}) is not None" for i in range(70))
        files = {"m.py": "def f(x): return x\n", "tests/test_m.py": f"from m import f\n{calls}\ndef test_zz_fail(): assert f(999) == 0\n"}
        with Repo(files) as root:
            sp, _ = prepare(root)
            tests = {r["test"] for r in sp.records["m.py:f"]}
            self.assertIn("tests/test_m.py::test_zz_fail", tests)  # recorded last, still kept
            self.assertLessEqual(len(sp.records["m.py:f"]), 60)

    def test_recorded_inputs_carry_the_outcome_of_the_tests_that_used_them(self):
        files = {"m.py": "def f(x): return x\n", "tests/test_m.py": "from m import f\ndef test_a(): assert f(1) == 1\ndef test_b(): assert f(2) == 3\n"}
        with Repo(files) as root:
            sp, _ = prepare(root)
            inputs = build_inputs(sp.records["m.py:f"], sp.outcomes)
            rec = {i["desc"]: i["outcomes"] for i in inputs if i["origin"] == "recorded"}
            self.assertEqual(rec, {"(1,)": ["passed"], "(2,)": ["failed"]})


class JunitNodeIdTests(unittest.TestCase):
    """Regression: found on cachetools. Tests inherited from a mixin defined in tests/__init__.py used to collapse onto
    ids like 'tests/__init__.py::test_x' (JUnit's `file` names where a test is defined, not where it is collected)."""
    MIXIN = {"m.py": "def f(x): return x\n", "tests/__init__.py": """
        from m import f
        class Mixin:
            def test_one(self): assert f(1) == 1
            def test_two(self): assert f(2) == 2
    """, "tests/test_a.py": "import unittest\nfrom tests import Mixin\nclass A(Mixin, unittest.TestCase): pass\n",
         "tests/test_b.py": "import unittest\nfrom tests import Mixin\nclass B(Mixin, unittest.TestCase): pass\n"}

    def test_inherited_tests_get_distinct_real_node_ids(self):
        with Repo(self.MIXIN) as root:
            run = SafeTestRunner(timeout_seconds=30).run_pytest(root)
            self.assertEqual(run.counts["passed"], 4)
            self.assertEqual(sorted(run.outcome), ["tests/test_a.py::A::test_one", "tests/test_a.py::A::test_two",
                                                   "tests/test_b.py::B::test_one", "tests/test_b.py::B::test_two"])

    def test_reconstructed_ids_can_be_run_as_targets(self):
        with Repo(self.MIXIN) as root:
            r = SafeTestRunner(timeout_seconds=30)
            sub = r.run_pytest(root, ["tests/test_b.py::B::test_two"])
            self.assertEqual((sub.classification, list(sub.outcome)), ("passed", ["tests/test_b.py::B::test_two"]))


class SpectrumFidelityTests(unittest.TestCase):
    """Regressions found on cachetools (pytest 9): failing subtests were overwritten by the final 'passed' report, and
    clock-dependent tests fail only under sys.settrace."""

    def test_failing_subtest_marks_the_test_failed_in_the_spectrum(self):
        files = {"m.py": "def f(x): return x\n", "tests/test_m.py": """
            import unittest
            from m import f
            class T(unittest.TestCase):
                def test_sub(self):
                    for v in (1, 2):
                        with self.subTest(v=v):
                            self.assertEqual(f(v), 1)
        """}
        with Repo(files) as root:
            sp = collect_spectrum(root, None, SafeTestRunner(timeout_seconds=30))
            self.assertTrue(sp.complete, sp.incomplete_reason)
            self.assertEqual(sp.outcomes["tests/test_m.py::T::test_sub"], "failed")

    def test_teardown_failure_is_a_failure_in_the_spectrum(self):
        files = {"m.py": "def f(x): return x\n", "tests/test_m.py": """
            import pytest
            from m import f
            @pytest.fixture
            def res():
                yield 1
                raise RuntimeError("teardown broke")
            def test_t(res): assert f(res) == 1
        """}
        with Repo(files) as root:
            sp = collect_spectrum(root, None, SafeTestRunner(timeout_seconds=30))
            self.assertTrue(sp.complete, sp.incomplete_reason)
            self.assertEqual(sp.outcomes["tests/test_m.py::test_t"], "error")

    TRACE_ONLY = {"calc.py": "def label(n):\n    return 'bulk' if n > 10 else 'single'\n", "tests/test_calc.py": """
        import sys
        from calc import label
        def test_bulk(): assert label(10) == 'bulk'
        def test_single(): assert label(3) == 'single'
        def test_slow_under_tracing(): assert sys.gettrace() is None   # like a TTL test slowed by instrumentation
    """}

    def test_instrumentation_sensitive_tests_are_excluded_and_the_real_fault_still_repaired(self):
        with Repo(self.TRACE_ONLY) as root:
            d = RepairWorkflow().run(root)
            self.assertEqual(d.status, "resolved")
            self.assertEqual(d.steps[0]["suspect"], "calc.label")
            self.assertTrue(any("traced and plain runs" in n and "test_slow_under_tracing" in n for n in d.notes))
            self.assertNotIn("tests/test_calc.py::test_slow_under_tracing", d.baseline_failing)

    def test_failure_seen_only_under_tracing_is_refused_not_repaired(self):
        files = {"calc.py": "def f(x): return x\n", "tests/test_calc.py": "import sys\nfrom calc import f\n"
                 "def test_ok(): assert f(1) == 1\ndef test_traced(): assert sys.gettrace() is None\n"}
        with Repo(files) as root:
            d = RepairWorkflow().run(root)
            self.assertEqual(d.status, "unstable_baseline")
            self.assertEqual(d.steps, [])

    def test_reconcile_unit(self):
        from asm.coding.faultloc import Spectrum, reconcile_spectrum
        sp = Spectrum({"a": "failed", "b": "failed", "c": "passed"}, {"a": {}, "b": {}, "c": {}}, {"a": "x", "b": "y"})
        removed = reconcile_spectrum(sp, {"a", "c"})   # b fails only traced, c fails only plain
        self.assertEqual(removed, {"b", "c"})
        self.assertEqual(sp.failing, ["a"])
        self.assertTrue(sp.complete)
        self.assertIn("traced and plain", sp.excluded["b"])
        sp2 = Spectrum({"b": "failed"}, {"b": {}}, {})
        reconcile_spectrum(sp2, set())
        self.assertFalse(sp2.complete)


# ======================================================================== 2. inputs and targets
class InputTests(unittest.TestCase):
    def test_object_attributes_and_literal_arguments_are_perturbed_and_labelled(self):
        with Repo(CART) as root:
            sp, _ = prepare(root)
            inputs = build_inputs(sp.records["shop.py:Cart.add"], sp.outcomes)
            descs = [i["desc"] for i in inputs]
            self.assertTrue(any(i["origin"] == "perturbed" for i in inputs))
            self.assertTrue(any("tax=" in d for d in descs))
            self.assertTrue(any("Cart{" in d for d in descs))
            self.assertLessEqual(len(inputs), MAX_INPUTS)

    def test_nested_functions_resolve_to_their_outermost_enclosing_function(self):
        with Repo(CART) as root:
            _, funcs = prepare(root)
            target, via = verification_target("shop.outer.inner", funcs)
            self.assertEqual((target.qname, via), ("shop.outer", True))
            target, via = verification_target("shop.Cart.total", funcs)
            self.assertEqual((target.qname, via), ("shop.Cart.total", False))

    def test_render_is_human_readable(self):
        self.assertEqual(render({"t": "int", "v": 8}), "8")
        self.assertEqual(render({"t": "str", "v": "a"}), "'a'")
        self.assertEqual(render({"t": "tuple", "v": [{"t": "int", "v": 1}]}), "(1,)")
        self.assertEqual(render({"t": "obj", "cls": "Cart", "state": {"tax": {"t": "float", "v": "0.1"}}}), "Cart(tax=0.1)")
        self.assertEqual(render({"t": "none"}), "None")


# ======================================================================= 3. object / method / nested replay
class ReplayTests(unittest.TestCase):
    def test_method_on_a_recorded_object_is_replayed_and_changes_are_attributed_to_passing_tests(self):
        with Repo(CART) as root:
            sp, funcs = prepare(root)
            v = verify_patch(root, "shop.Cart.total", patch(root, "shop.py", "(1 + self.tax)", "(1 - self.tax)", "tax sign"),
                             [], sp, funcs)
            self.assertTrue(v["available"])
            self.assertEqual((v["target"]["kind"], v["target"]["via_enclosing"]), ("method", False))
            self.assertGreater(v["footprint"]["tax sign"], 0.5)
            self.assertEqual(v["changed_on_passing_recorded"]["tax sign"], ["(Cart{tax=0.1, items=[10, 5]},)"])
            self.assertIn("out", v["changed_components"]["tax sign"])

    def test_nested_function_is_verified_through_its_enclosing_function(self):
        with Repo(CART) as root:
            sp, funcs = prepare(root)
            v = verify_patch(root, "shop.outer.inner", patch(root, "shop.py", "return k * n", "return k + n", "inner op"),
                             [], sp, funcs)
            self.assertTrue(v["available"])
            self.assertEqual((v["target"]["qname"], v["target"]["via_enclosing"]), ("shop.outer", True))
            self.assertGreater(v["footprint"]["inner op"], 0)

    def test_a_behaviour_preserving_patch_has_zero_footprint(self):
        with Repo(CART) as root:
            sp, funcs = prepare(root)
            acc = patch(root, "shop.py", "sum(self.items) * (1 + self.tax)", "(1 + self.tax) * sum(self.items)", "commuted")
            v = verify_patch(root, "shop.Cart.total", acc, [], sp, funcs)
            self.assertTrue(v["available"])
            self.assertEqual(v["footprint"]["commuted"], 0.0)
            self.assertEqual(v["changed_on_passing_recorded"]["commuted"], [])

    def test_unavailable_when_nothing_replayable_was_recorded(self):
        files = {"m.py": "def f(g): return g(1)\n", "tests/test_m.py": "from m import f\ndef test_x(): assert f(lambda v: v) == 1\n"}
        with Repo(files) as root:
            sp, funcs = prepare(root)
            v = verify_patch(root, "m.f", patch(root, "m.py", "g(1)", "g(2)", "x"), [], sp, funcs)
            self.assertFalse(v["available"])
            self.assertIn("no replayable calls", v["reason"])


# ====================================================================== 4. state and side effects
STATE = {"fx.py": """
    import os
    COUNT = 0
    def mutate(xs):
        xs.append(1)
        return len(xs)
    def say(x):
        print("saw", x)
        return x
    def write(x):
        with open("out.txt", "w") as fh:
            fh.write("v1")
        return x
    def bump(x):
        global COUNT
        COUNT += 1
        return x
    def boom(x):
        return x
""", "tests/test_fx.py": """
    from fx import mutate, say, write, bump, boom
    def test_all():
        assert mutate([5]) == 2 and say(3) == 3 and write(2) == 2 and bump(4) == 4 and boom(1) == 1
"""}


class StateComparisonTests(unittest.TestCase):
    def components(self, qname, old, new):
        with Repo(STATE) as root:
            sp, funcs = prepare(root)
            v = verify_patch(root, qname, patch(root, "fx.py", old, new, "p"), [], sp, funcs)
            self.assertTrue(v["available"], v)
            return v

    def test_argument_mutation_is_compared(self):
        v = self.components("fx.mutate", "xs.append(1)", "xs.append(2)")
        self.assertEqual(set(v["changed_components"]["p"]), {"after"})  # same return value; only the argument differs

    def test_printed_output_is_compared(self):
        v = self.components("fx.say", 'print("saw", x)', 'print("seen", x)')
        self.assertEqual(set(v["changed_components"]["p"]), {"stdout"})

    def test_files_written_are_compared(self):
        v = self.components("fx.write", 'fh.write("v1")', 'fh.write("v2")')
        self.assertEqual(set(v["changed_components"]["p"]), {"files"})

    def test_module_globals_are_compared(self):
        v = self.components("fx.bump", "COUNT += 1", "COUNT += 2")
        self.assertEqual(set(v["changed_components"]["p"]), {"globals"})

    def test_exceptions_are_compared(self):
        v = self.components("fx.boom", "def boom(x):\n    return x\n", "def boom(x):\n    raise ValueError('no')\n")
        self.assertEqual(set(v["changed_components"]["p"]), {"exc", "out"})

    def test_side_effects_do_not_leak_between_inputs_or_into_the_original_repo(self):
        with Repo(STATE) as root:
            before = tree_fingerprint(root)
            sp, funcs = prepare(root)
            v = verify_patch(root, "fx.write", patch(root, "fx.py", 'fh.write("v1")', 'fh.write("v1")', "same"), [], sp, funcs)
            self.assertEqual(v["footprint"]["same"], 0.0)  # files and globals restored between runs
            self.assertEqual(tree_fingerprint(root), before)
            self.assertFalse((root / "out.txt").exists())


# ============================================================================ 5. nondeterminism
NOISE = {"nd.py": """
    import random, time, uuid, os
    def r(x): return x + random.randint(0, 0)
    def rf(x): return random.random() > 2
    def clock(x): return int(time.time()) - int(time.time()) + x
    def ident(x): return len(str(uuid.uuid4())) + x
    def rand_bytes(x): return len(os.urandom(4)) + x
    def raw_clock(x): return time.time_ns() % 1000
    def roll(x): return x + random.randint(1, 1000)
    def stamp(x): return time.time() + x
""", "tests/test_nd.py": """
    from nd import r, rf, clock, ident, rand_bytes, raw_clock, roll, stamp
    def test_all():
        assert r(3) == 3 and rf(1) is False and clock(2) == 2 and ident(1) == 37 and rand_bytes(1) == 5
        raw_clock(1)
        assert roll(1) > 1 and stamp(1) > 1
"""}


class NondeterminismTests(unittest.TestCase):
    def verify(self, qname, old, new):
        with Repo(NOISE) as root:
            sp, funcs = prepare(root)
            return verify_patch(root, qname, patch(root, "nd.py", old, new, "p"), [], sp, funcs)

    def test_randomness_time_uuid_and_urandom_become_comparable(self):
        for q, old, new in (("nd.r", "x + random.randint(0, 0)", "x + 1 + random.randint(0, 0)"),
                            ("nd.clock", "int(time.time()) - int(time.time()) + x", "int(time.time()) - int(time.time()) + x + 1"),
                            ("nd.ident", "len(str(uuid.uuid4())) + x", "len(str(uuid.uuid4())) + x + 1"),
                            ("nd.rand_bytes", "len(os.urandom(4)) + x", "len(os.urandom(4)) + x + 1")):
            v = self.verify(q, old, new)
            self.assertTrue(v["available"], (q, v))
            self.assertEqual(v["excluded_nondeterministic"], 0, q)
            self.assertEqual(v["footprint"]["p"], 1.0, q)

    def test_values_that_depend_on_the_random_draw_or_the_clock_are_reproducible(self):
        # unlike randint(0, 0) or len(uuid4()), these outputs change with every draw / clock reading unless the
        # worker re-seeds randomness and resets its clock before EACH run
        for q, old, new in (("nd.roll", "x + random.randint(1, 1000)", "x + 1 + random.randint(1, 1000)"),
                            ("nd.stamp", "time.time() + x", "time.time() + x + 1")):
            v = self.verify(q, old, new)
            self.assertTrue(v["available"], (q, v))
            self.assertEqual(v["excluded_nondeterministic"], 0, q)
            self.assertEqual(v["footprint"]["p"], 1.0, q)

    def test_unseeded_random_calls_agree_between_identical_patches(self):
        v = self.verify("nd.rf", "random.random() > 2", "random.random() > 2.0")
        self.assertTrue(v["available"])
        self.assertEqual(v["footprint"]["p"], 0.0)

    def test_uncontrolled_nondeterminism_is_excluded_and_reported_not_compared(self):
        v = self.verify("nd.raw_clock", "time.time_ns() % 1000", "time.time_ns() % 999")
        self.assertFalse(v["available"])
        self.assertGreater(v["excluded_nondeterministic"], 0)
        self.assertIn("deterministically", v["reason"])


# ====================================================================== 6. overfit-pattern replicas
COMPENSATE = {"pipeline.py": """
    def parse(text):
        return text.split(",")[1:]
    def count(text):
        return len(parse(text)) + 1 - 1
""", "tests/test_pipeline.py": """
    from pipeline import count
    def test_count(): assert count("a,b,c") == 3
"""}
WEAK = {"price.py": """
    def price(qty):
        return qty * 10 - 1
""", "tests/test_price.py": """
    from price import price
    def test_exact(): assert price(2) == 20
    def test_weak(): assert price(3) > 0
"""}


class OverfitPatternTests(unittest.TestCase):
    def test_compensating_patch_in_another_tied_function_is_flagged(self):
        # pattern 1: the fault is in parse() ([1:] drops an item), but count() ("+ 1 - 1" -> "+ 2 - 1") also satisfies the test
        with Repo(COMPENSATE) as root:
            d = RepairWorkflow().run(root)
            self.assertEqual(d.status, "resolved")
            step = d.steps[0]
            self.assertIn("competing_patches_in_other_functions", step["confidence_basis"])
            # DEV14 pre-registered rule R1 demoted tied_localization to informational: competing + tied was "low" in
            # DEV13, the competing flag alone now gives "medium" (the tie is still listed in the basis)
            self.assertIn("tied_localization", step["confidence_basis"])
            self.assertEqual(step["confidence_counted"], ["competing_patches_in_other_functions"])
            self.assertEqual(step["confidence"], "medium")
            self.assertTrue(step["competing_patches"])
            self.assertNotEqual(step["competing_patches"][0]["suspect"], step["suspect"])
            self.assertTrue(any("compensating for a fault elsewhere" in c for c in d.caveats))

    def test_a_unique_suspect_has_no_competing_patch_flag(self):
        files = {"m.py": "def label(n):\n    return 'bulk' if n > 10 else 'single'\n",
                 "tests/test_m.py": "from m import label\ndef test_a(): assert label(10) == 'bulk'\ndef test_b(): assert label(3) == 'single'\n"}
        with Repo(files) as root:
            step = RepairWorkflow().run(root).steps[0]
            self.assertEqual(step["competing_patches"], [])
            self.assertNotIn("competing_patches_in_other_functions", step["confidence_basis"])

    def test_patch_that_changes_behaviour_on_inputs_passing_tests_used_is_flagged(self):
        # the correct fix changes price(3), an input a passing (weakly asserting) test used; a warning, not a verdict
        with Repo(WEAK) as root:
            d = RepairWorkflow().run(root)
            self.assertEqual(d.status, "resolved")
            step = d.steps[0]
            self.assertIn("behaviour_changed_where_tests_passed", step["confidence_basis"])
            self.assertTrue(any("tests which passed before the patch already used" in c for c in d.caveats))
            self.assertEqual(step["verification"]["changed_on_passing_recorded"][step["description"]], ["(3,)"])
            self.assertIn("WARNING output changes", d.to_markdown())

    def test_no_such_flag_when_no_passing_test_used_the_function(self):
        files = {"m.py": "def f(x):\n    return x * 10 - 1\n", "tests/test_m.py": "from m import f\ndef test_f(): assert f(2) == 20\n"}
        with Repo(files) as root:
            step = RepairWorkflow().run(root).steps[0]
            self.assertNotIn("behaviour_changed_where_tests_passed", step["confidence_basis"])

    def test_exhaustive_search_finds_alternatives_beyond_the_first_successful_round(self):
        files = {"m.py": "def big(n):\n    return n > 5\n", "tests/test_m.py": "from m import big\ndef test_big(): assert big(5)\n"}
        with Repo(files) as root:
            on = RepairWorkflow(candidates_per_round=1).run(root).steps[0]
            off = RepairWorkflow(candidates_per_round=1, explore_alternatives=False).run(root).steps[0]
            self.assertEqual(off["alternatives_passing"], [])   # the loop stopped at its first passing candidate
            self.assertTrue(on["alternatives_passing"])         # the exhaustive pass found the other one


# ========================================================================== 7. confidence flags
class FlagTests(unittest.TestCase):
    def test_unverifiable_behaviour_is_a_flag_not_silence(self):
        files = {"m.py": "def f(g):\n    return g(1) - 1\n", "tests/test_m.py": "from m import f\ndef test_x(): assert f(lambda v: v) == 1\n"}
        with Repo(files) as root:
            step = RepairWorkflow().run(root).steps[0]
            self.assertFalse(step["verification"]["available"])
            self.assertIn("behaviour_unverified", step["confidence_basis"])
            self.assertNotEqual(step["confidence"], "high")

    def test_fully_verified_unique_fix_is_high_confidence(self):
        files = {"m.py": "def label(n):\n    return 'bulk' if n > 10 else 'single'\n",
                 "tests/test_m.py": "from m import label\ndef test_a(): assert label(10) == 'bulk'\ndef test_b(): assert label(3) == 'single'\n"}
        with Repo(files) as root:
            step = RepairWorkflow().run(root).steps[0]
            self.assertTrue(step["verification"]["available"])
            self.assertEqual((step["confidence"], step["confidence_basis"]), ("high", []))

    def test_method_repair_end_to_end_is_verified(self):
        src = """
            class Account:
                def __init__(self, balance):
                    self.balance = balance
                def withdraw(self, amount):
                    if amount >= self.balance:
                        return False
                    self.balance -= amount
                    return True
        """
        files = {"acct.py": src, "tests/test_acct.py": """
            from acct import Account
            def test_exact_balance():
                a = Account(10)
                assert a.withdraw(10) is True
                assert a.balance == 0
            def test_overdraw():
                a = Account(10)
                assert a.withdraw(11) is False
        """}
        with Repo(files) as root:
            d = RepairWorkflow().run(root)
            self.assertEqual(d.status, "resolved")
            step = d.steps[0]
            self.assertEqual(step["suspect"], "acct.Account.withdraw")
            self.assertTrue(step["verification"]["available"])
            self.assertEqual(step["verification"]["target"]["kind"], "method")
            self.assertIn("compare", step["description"])


if __name__ == "__main__":
    unittest.main()
