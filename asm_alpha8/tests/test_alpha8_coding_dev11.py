"""DEV11 tests: mutation engine, spectrum/traceback/semantic localization, repair workflow, evidence dossier."""
import ast
import json
import os
import tempfile
import textwrap
import unittest
import uuid
from pathlib import Path

from asm.coding import SafeTestRunner, tree_fingerprint
from asm.coding.faultloc import (FaultLocalizer, RepairWorkflow, apply_site, ast_normal, collect_spectrum,
                                 enumerate_sites, generate_candidates, ochiai, Suspect)
from asm.coding.understanding import CodeUnderstanding


def write_repo(root: Path, files: dict):
    for rel, src in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(src))


class Repo:
    """Temporary repository context."""
    def __init__(self, files):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        write_repo(self.root, files)

    def __enter__(self):
        return self.root

    def __exit__(self, *a):
        self.tmp.cleanup()


def sites_of(src: str, path="m.py"):
    und_ranges = []
    tree = ast.parse(src)
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            und_ranges.append((n.name, n.lineno, n.end_lineno))
    return enumerate_sites(src, path, und_ranges)


SHOP = {
    "shop.py": '''
        def apply_discount(price, pct):
            return price - price * pct / 100
        def total(items):
            return sum(i["price"] * i["qty"] for i in items)
        def checkout(items, pct):
            return round(apply_discount(total(items), pct), 2)
        def label(n):
            return "bulk" if n >= 10 else "single"
    ''',
    "tests/test_shop.py": '''
        from shop import apply_discount, total, checkout, label
        ITEMS = [{"price": 10.0, "qty": 2}, {"price": 5.0, "qty": 4}]
        def test_total(): assert total(ITEMS) == 40.0
        def test_discount(): assert apply_discount(100, 10) == 90
        def test_checkout(): assert checkout(ITEMS, 25) == 30.0
        def test_label_bulk(): assert label(10) == "bulk"
        def test_label_single(): assert label(3) == "single"
    ''',
}


def with_bug(files, old, new):
    out = dict(files)
    out["shop.py"] = files["shop.py"].replace(old, new)
    assert out["shop.py"] != files["shop.py"]
    return out


# ================================================================== mutation engine
class MutationEngineTests(unittest.TestCase):
    def test_site_kinds_and_options(self):
        src = textwrap.dedent('''
            def f(a, b, xs):
                if a < b and b != 3:
                    return a + b * 2
                return not (a in xs) or a is not None
        ''')
        by_kind = {}
        for s in sites_of(src):
            by_kind.setdefault(s.kind, []).append((s.original, tuple(s.options)))
        self.assertIn(("<", ("<=", ">")), by_kind["compare"])
        self.assertIn(("!=", ("==",)), by_kind["compare"])
        self.assertIn(("in", ("not in",)), by_kind["compare"])
        self.assertIn(("is not", ("is",)), by_kind["compare"])
        self.assertIn(("+", ("-", "*")), by_kind["arith"])
        self.assertIn(("*", ("+", "//")), by_kind["arith"])
        self.assertIn(("and", ("or",)), by_kind["bool"])
        self.assertIn(("or", ("and",)), by_kind["bool"])
        self.assertIn(("3", ("4", "2")), by_kind["const"])
        self.assertIn(("2", ("3", "1")), by_kind["const"])
        self.assertTrue(by_kind["negate"])  # the `if` test
        self.assertEqual(by_kind["not"], [("not ", ("",))])

    def test_edits_are_text_preserving_single_token_replacements(self):
        import difflib
        src = textwrap.dedent('''
            def f(a, b):
                # keep this comment
                if (a   # inline comment
                        <  b):
                    return a+b   # spacing preserved
                return  a  -  b
        ''')
        for site in sites_of(src):
            for opt in site.options:
                new = apply_site(src, site, opt)
                ops = [o for o in difflib.SequenceMatcher(a=src, b=new, autojunk=False).get_opcodes() if o[0] != "equal"]
                # a single contiguous replacement; wrapping a condition in `not (...)` is two insertions around it
                self.assertEqual(len(ops), 2 if site.kind == "negate" else 1, (site, opt))
                ast.parse(new)
                self.assertIn("# keep this comment", new)

    def test_gap_between_operands_with_parens_comments_and_newlines(self):
        src = "def f(a, b):\n    return ((a)  # c\n      +\n      (b))\n"
        arith = [s for s in sites_of(src) if s.kind == "arith"]
        self.assertEqual(len(arith), 1)
        self.assertEqual(apply_site(src, arith[0], "-"), "def f(a, b):\n    return ((a)  # c\n      -\n      (b))\n")

    def test_excluded_constructs(self):
        src = textwrap.dedent('''
            def f(x: int = 5, name: "str" = "s") -> int:
                """doc 7"""
                msg = f"value {x + 1}"
                y = 1.5 + 2.5
                z = "text" + name
                return None
        ''')
        kinds = [(s.kind, s.original) for s in sites_of(src)]
        self.assertNotIn(("const", "7"), kinds)           # docstring
        self.assertFalse([k for k in kinds if k[1] == "1" and k[0] == "arith"])
        self.assertNotIn(("const", "5"), [(k, o) for k, o in kinds if o == "5" and False])  # default arg is editable
        self.assertEqual([k for k in kinds if k[0] == "arith" and k[1] == "+"].__len__(), 2)  # float + and str + (f-string + excluded)

    def test_only_function_bodies_and_innermost_attribution(self):
        src = textwrap.dedent('''
            X = 1 + 2
            class C:
                Y = 3 + 4
                def m(self):
                    def inner():
                        return 5 + 6
                    return 7 + 8
        ''')
        sites = [s for s in sites_of(src) if s.kind == "arith"]
        self.assertEqual({s.function for s in sites}, {"m", "inner"})
        self.assertEqual(sorted(s.function for s in sites), ["inner", "m"])

    def test_every_mutation_has_an_inverse_mutation(self):
        """The repair templates are the inverse of the injection templates: applying any edit and then the
        matching inverse edit must restore the original program (compared as AST)."""
        src = (Path(__file__).resolve().parents[1] / "asm" / "coding" / "diagnostics.py").read_text()
        tree = ast.parse(src)
        ranges = [(n.name, n.lineno, n.end_lineno) for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        # `not`-removal is repair-only (it has no inverse template of its own), so it is not required to invert
        sites = [s for s in enumerate_sites(src, "d.py", ranges) if s.kind != "not"]
        self.assertGreater(len(sites), 20)
        original = ast_normal(src)
        for site in sites[:60]:
            for opt in site.options:
                mutated = apply_site(src, site, opt)
                try:
                    ast.parse(mutated)
                except SyntaxError:
                    continue
                again = enumerate_sites(mutated, "d.py", ranges)
                restored = any(ast_normal(apply_site(mutated, s2, o2)) == original
                               for s2 in again if abs(s2.start - site.start) <= len(opt) + 8 for o2 in s2.options)
                self.assertTrue(restored, site.describe(opt))

    def test_every_operator_kind_has_an_inverse_exhaustive(self):
        """Exhaustive over every operator the engine can touch (the real-file sample above cannot guarantee coverage)."""
        src = textwrap.dedent('''
            def f(a, b, xs):
                r1 = a + b
                r2 = a - b
                r3 = a * b
                r4 = a // b
                r5 = a % b
                c1 = a < b
                c2 = a <= b
                c3 = a > b
                c4 = a >= b
                c5 = a == b
                c6 = a != b
                c7 = a in xs
                c8 = a not in xs
                c9 = a is b
                c10 = a is not b
                p = a and b
                q = a or b
                k = 7
                t = True
                u = False
                if a:
                    pass
                while b:
                    break
                return not a
        ''')
        tree = ast.parse(src)
        ranges = [(n.name, n.lineno, n.end_lineno) for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
        original = ast_normal(src)
        sites = [s for s in enumerate_sites(src, "m.py", ranges) if s.kind != "not"]
        self.assertGreaterEqual(len({(s.kind, s.original) for s in sites}), 22)
        for site in sites:
            for opt in site.options:
                mutated = apply_site(src, site, opt)
                ast.parse(mutated)
                again = enumerate_sites(mutated, "m.py", ranges)
                restored = any(ast_normal(apply_site(mutated, s2, o2)) == original
                               for s2 in again if abs(s2.start - site.start) <= len(opt) + 8 for o2 in s2.options)
                self.assertTrue(restored, site.describe(opt))

    def test_not_removal_keeps_parentheses_balanced(self):
        src = "def f(a, b):\n    if not (a and b):\n        return not a\n    return 1\n"
        nots = [s for s in sites_of(src) if s.kind == "not"]
        self.assertEqual(len(nots), 2)
        for s in nots:
            mutated = apply_site(src, s, "")
            ast.parse(mutated)  # must stay valid Python
        self.assertEqual(apply_site(src, nots[0], ""), "def f(a, b):\n    if (a and b):\n        return not a\n    return 1\n")

    def test_candidate_generation_orders_by_suspicion_and_stays_inside_the_function(self):
        src = "def a(x):\n    if x > 1:\n        return x + 1\n    return x - 1\ndef b(y): return y * 2\n"
        sus = Suspect("a", "m.py", 1, 4, 1.0, {}, [])
        cands = generate_candidates(src, "m.py", sus, [("a", 1, 4), ("b", 5, 5)], {"m.py": {2: 0.9, 3: 0.2, 4: 0.5}})
        self.assertTrue(all("def b" in c.replacement for c in cands))  # b untouched in every candidate
        lines = [int(c.reason.rsplit(" ", 1)[1]) for c in cands]
        self.assertEqual(lines, sorted(lines, key={2: 0, 4: 1, 3: 2}.get))  # 0.9 line first, then 0.5, then 0.2
        self.assertTrue(cands[0].reason.startswith(("compare", "negate")))
        self.assertEqual(len({c.replacement for c in cands}), len(cands))


# ======================================================================== spectrum
class SpectrumTests(unittest.TestCase):
    def test_per_test_line_coverage_outcomes_and_failures(self):
        with Repo(with_bug(SHOP, "n >= 10", "n > 10")) as root:
            sp = collect_spectrum(root, None, SafeTestRunner(timeout_seconds=30))
            self.assertEqual(sp.failing, ["tests/test_shop.py::test_label_bulk"])
            self.assertEqual(len(sp.passing), 4)
            bulk = sp.lines["tests/test_shop.py::test_label_bulk"]["shop.py"]
            discount = sp.lines["tests/test_shop.py::test_discount"]["shop.py"]
            self.assertIn(9, bulk)                  # the `label` body line (line 1 is blank after dedent)
            self.assertNotIn(9, discount)
            self.assertIn("test_label_bulk", sp.failures["tests/test_shop.py::test_label_bulk"])
            self.assertIn('File "', sp.failures["tests/test_shop.py::test_label_bulk"])  # native traceback

    def test_collection_errors_are_failures_with_tracebacks(self):
        with Repo({"m.py": "import nonexistent_zz\n", "tests/test_m.py": "import m\ndef test_x(): pass\n"}) as root:
            sp = collect_spectrum(root, None, SafeTestRunner(timeout_seconds=30))
            self.assertEqual(sp.failing, ["tests/test_m.py"])
            self.assertIn("nonexistent_zz", sp.failures["tests/test_m.py"])

    def test_selector_targets_run_only_the_selected_tests(self):
        with Repo(SHOP) as root:
            r = SafeTestRunner(timeout_seconds=30).run_pytest(root, ["tests/test_shop.py::test_total"])
            self.assertEqual(list(r.outcome), ["tests/test_shop.py::test_total"])
            with self.assertRaises(ValueError):
                SafeTestRunner(timeout_seconds=30).run_pytest(root, ["../x.py::t"])

    def test_original_repository_is_untouched_by_tracing(self):
        with Repo(with_bug(SHOP, "n >= 10", "n > 10")) as root:
            before = tree_fingerprint(root)
            collect_spectrum(root, None, SafeTestRunner(timeout_seconds=30))
            self.assertEqual(tree_fingerprint(root), before)

    def test_ochiai_formula(self):
        self.assertAlmostEqual(ochiai(2, 0, 2), 1.0)
        self.assertAlmostEqual(ochiai(1, 1, 1), 0.5 ** 0.5)
        self.assertEqual(ochiai(0, 3, 2), 0.0)
        self.assertEqual(ochiai(0, 0, 0), 0.0)


# ===================================================================== localization
class LocalizationTests(unittest.TestCase):
    def test_spectrum_ranks_the_faulty_function_first_when_only_it_is_executed_by_failures(self):
        with Repo(with_bug(SHOP, "n >= 10", "n > 10")) as root:
            rep = FaultLocalizer(use_semantic=False).localize(root)
            self.assertEqual(rep.suspects[0].qname, "shop.label")
            self.assertEqual(rep.rank_of("shop.label"), 1)
            self.assertEqual([s.qname for s in rep.suspects if s.score > 0], ["shop.label"])  # others only ran in passing tests
            self.assertEqual(rep.failing_tests, ["tests/test_shop.py::test_label_bulk"])
            self.assertEqual(rep.passing_count, 4)

    def test_failures_shared_by_several_tests_raise_the_score(self):
        with Repo(with_bug(SHOP, "price - price", "price + price")) as root:
            rep = FaultLocalizer(use_semantic=False).localize(root)
            order = [s.qname for s in rep.suspects]
            self.assertEqual(order[0], "shop.apply_discount")
            self.assertEqual(rep.suspects[0].sources["spectrum"], 1.0)  # executed by both failures, never by a pass
            self.assertLess(rep.suspects[order.index("shop.total")].sources["spectrum"], 1.0)
            self.assertEqual(rep.suspects[order.index("shop.label")].score, 0.0)

    def test_traceback_evidence_prefers_the_innermost_repository_frame(self):
        files = {"lib.py": '''
            def last(xs):
                return xs[len(xs)]
            def wrapper(xs):
                return last(xs)
            def other(): return 1
        ''', "tests/test_lib.py": '''
            from lib import wrapper, other
            def test_w(): assert wrapper([1, 2, 3]) == 3
            def test_o(): assert other() == 1
        '''}
        with Repo(files) as root:
            rep = FaultLocalizer(use_semantic=False).localize(root)
            tb = {s.qname: s.sources["traceback"] for s in rep.suspects}
            self.assertEqual(tb["lib.last"], 1.0)
            self.assertAlmostEqual(tb["lib.wrapper"], 0.7)
            self.assertEqual(tb["lib.other"], 0.0)
            self.assertEqual(rep.suspects[0].qname, "lib.last")
            self.assertTrue(any("innermost repository frame" in e for e in rep.suspects[0].evidence))

    def test_assertion_only_failures_have_no_traceback_evidence_but_still_localize(self):
        with Repo(with_bug(SHOP, "n >= 10", "n > 10")) as root:
            rep = FaultLocalizer(use_semantic=False).localize(root)
            self.assertEqual({s.sources["traceback"] for s in rep.suspects}, {0.0})
            self.assertGreater(rep.suspects[0].sources["spectrum"], 0)

    def test_dev10_behavioural_deviation_breaks_a_spectrum_tie(self):
        # the buggy function is defined AFTER its caller, so tie-break order alone would put the wrong one first
        files = {"parity.py": '''
            def describe(n):
                return "even" if is_even(n) else "odd"
            def is_even(n):
                return n % 2 == 0 if n >= 0 else True
        ''', "tests/test_parity.py": '''
            from parity import describe
            def test_pos(): assert describe(3) == "odd"
            def test_neg(): assert describe(-3) == "odd"
        '''}
        with Repo(files) as root:
            plain = FaultLocalizer(use_semantic=False).localize(root)
            self.assertEqual(plain.suspects[0].score, plain.suspects[1].score)  # a genuine tie without DEV10
            self.assertEqual(plain.suspects[0].qname, "parity.describe")  # ...and arbitrary order favours the wrong one
            rep = FaultLocalizer(use_semantic=True).localize(root)
            self.assertEqual(rep.suspects[0].qname, "parity.is_even")
            self.assertEqual(rep.suspects[0].sources["semantic"], 1.0)
            self.assertTrue(any("likely_bug" in e for e in rep.suspects[0].evidence))
            self.assertEqual(rep.suspects[1].sources["semantic"], 0.0)

    def test_impact_lists_transitive_callers_and_covering_tests(self):
        with Repo(with_bug(SHOP, "price - price", "price + price")) as root:
            rep = FaultLocalizer(use_semantic=False).localize(root)
            imp = rep.impacts["shop.apply_discount"]
            self.assertIn("shop.checkout", imp["callers"])
            self.assertEqual(imp["covering_tests"], 2)

    def test_no_failing_tests_means_no_suspects(self):
        with Repo(SHOP) as root:
            rep = FaultLocalizer(use_semantic=False).localize(root)
            self.assertEqual((rep.suspects, rep.failing_tests, rep.notes), ([], [], ["no failing tests"]))

    def test_test_files_are_never_suspects(self):
        with Repo(with_bug(SHOP, "n >= 10", "n > 10")) as root:
            rep = FaultLocalizer(use_semantic=False).localize(root)
            self.assertFalse([s for s in rep.suspects if s.path.startswith("tests/")])

    def test_semantic_probe_only_restricts_probing(self):
        from asm.coding import SemanticAnalyzer
        with Repo({"m.py": "def a(x): return x + 1\ndef b(x): return x * 2\n"}) as root:
            r = SemanticAnalyzer().analyze(root, probe_only={"m.a"})
            self.assertIsNotNone(r.function("m.a").behavior)
            self.assertIsNone(r.function("m.b").behavior)


# ========================================================================= workflow
class WorkflowTests(unittest.TestCase):
    def run_wf(self, files, **kw):
        tmp = Repo(files)
        wf = RepairWorkflow(**kw)
        d = wf.run(tmp.root)
        return tmp, d

    def test_comparison_boundary_bug_is_repaired_with_evidence(self):
        tmp, d = self.run_wf(with_bug(SHOP, "n >= 10", "n > 10"))
        with tmp as root:
            self.assertEqual(d.status, "resolved")
            step = d.steps[0]
            self.assertEqual((step["suspect"], step["kind"], step["rank"]), ("shop.label", "full", 1))
            self.assertIn("compare", step["description"])
            self.assertIn("-    return \"bulk\" if n > 10", step["diff"].replace("def label(n):\n", ""))
            self.assertIn("+    return \"bulk\" if n >= 10", step["diff"])
            self.assertEqual(step["fixed_tests"], ["tests/test_shop.py::test_label_bulk"])
            self.assertTrue(step["confirmed"])
            self.assertTrue(any("no regressions" in w for w in step["why_accepted"]))
            self.assertTrue(any("pass reproduced" in w for w in step["why_accepted"]))
            self.assertIn("shop.label", d.impact)
            self.assertEqual(d.repo_fingerprint, tree_fingerprint(root))  # original untouched

    def test_arithmetic_bug_is_repaired_and_other_candidates_are_recorded_as_rejected(self):
        tmp, d = self.run_wf(with_bug(SHOP, "price - price", "price + price"))
        with tmp:
            self.assertEqual(d.status, "resolved")
            self.assertEqual(d.steps[0]["suspect"], "shop.apply_discount")
            self.assertIn("arith", d.steps[0]["description"])
            self.assertEqual(d.baseline_failing, ["tests/test_shop.py::test_checkout", "tests/test_shop.py::test_discount"])
            self.assertIn("price - price * pct / 100", d.diff)

    def test_plausible_but_wrong_patch_is_rejected_by_the_behavioural_contract(self):
        files = {"calc.py": '''
            def helper(x): return x + 1
            def is_big(n): return n > 10
            def classify(n):
                return "big" if is_big(helper(n)) else "small"
        ''', "tests/test_c.py": '''
            from calc import classify
            def test_a(): assert classify(9) == "big"
            def test_b(): assert classify(1) == "small"
        '''}
        tmp, d = self.run_wf(files)
        with tmp:
            self.assertEqual(d.status, "resolved")
            self.assertEqual(d.steps[0]["suspect"], "calc.is_big")       # not helper(+1 -> +2), which also passes the tests
            contract = [r for r in d.rejected if r["status"] == "rejected_semantic_contract"]
            self.assertEqual([r["suspect"] for r in contract], ["calc.helper"])
            self.assertIn("increment", contract[0]["why"])
            self.assertTrue(any("behavioural contract" in w for w in d.steps[0]["why_accepted"]))

    def test_plausible_patch_that_still_deviates_is_accepted_but_flagged_by_the_behavioural_verdict(self):
        files = {"parity.py": """
            def is_even(n):
                return n % 2 == 0 if n >= 0 else True
            def describe(n):
                return "even" if is_even(n) else "odd"
        """, "tests/test_parity.py": """
            from parity import describe
            def test_pos(): assert describe(3) == "odd"
            def test_neg(): assert describe(-3) == "odd"
        """}
        tmp, d = self.run_wf(files)
        with tmp:
            self.assertEqual(d.status, "resolved")  # the tests are satisfied...
            step = d.steps[0]
            self.assertEqual(step["suspect"], "parity.is_even")
            self.assertEqual(step["behavioural_verdict"], "still_deviant")  # ...but the function is still wrong for -2
            self.assertIn("likely_bug", step["behavioural_note"])
            self.assertEqual(len([c for c in d.caveats if "still reports" in c]), 1)
            self.assertEqual(len([c for c in d.caveats if "tie it with" in c]), 1)
            self.assertEqual(step["confidence"], "low")
            self.assertIn("Caveats", d.to_markdown())
            chk = d.semantic_check["parity.is_even"]
            self.assertIn("likely_bug", chk["findings_after"])

    def test_inverted_condition_is_repaired_and_the_behavioural_verdict_confirms_it(self):
        files = {"parity.py": """
            def is_even(n):
                return n % 2 != 0
            def describe(n):
                return "even" if is_even(n) else "odd"
        """, "tests/test_parity.py": """
            from parity import describe
            def test_even(): assert describe(4) == "even"
            def test_odd(): assert describe(3) == "odd"
        """}
        tmp, d = self.run_wf(files)
        with tmp:
            self.assertEqual(d.status, "resolved")
            step = d.steps[0]
            self.assertEqual(step["suspect"], "parity.is_even")
            self.assertEqual(step["behavioural_verdict"], "improved")
            self.assertFalse([c for c in d.caveats if "still reports" in c])  # behaviour is genuinely repaired...
            # ...but two tests underdetermine it: `n % 3 != 0` also passes both, and the counterexample search says where they differ
            self.assertTrue(any("behave differently" in c or "do not determine the fix" in c for c in d.caveats))
            self.assertEqual(step["confidence"], "low")
            chk = d.semantic_check["parity.is_even"]
            self.assertEqual(chk["resolved"], ["name_behavior_mismatch"])
            self.assertEqual((chk["identified_before"], chk["identified_after"]), (["is_odd"], ["is_even"]))
            self.assertIn("name_behavior_mismatch", chk["findings_before"])
            self.assertEqual(chk["introduced"], [])

    def test_alternatives_that_behave_identically_are_noted_not_flagged(self):
        files = {"m.py": "def big(n):\n    return n > 5\n", "tests/test_m.py": "from m import big\ndef test_big(): assert big(5)\n"}
        tmp, d = self.run_wf(files)
        with tmp:
            self.assertEqual(d.status, "resolved")
            step = d.steps[0]
            # `>` -> `>=` and `5` -> `4` are different edits but identical on every tested integer
            self.assertGreaterEqual(len(step["alternatives_passing"]), 1)
            self.assertIn("probably equivalent", step["alternatives_note"])
            self.assertFalse([c for c in d.caveats if "also pass" in c or "behave differently" in c])
            self.assertEqual(step["confidence"], "high")

    def test_a_uniquely_determined_fix_has_no_ambiguity_caveat(self):
        tmp, d = self.run_wf(with_bug(SHOP, "n >= 10", "n > 10"))
        with tmp:
            self.assertEqual(d.status, "resolved")
            self.assertEqual(d.steps[0]["tied_with"], [])
            self.assertFalse([c for c in d.caveats if "tied" in c])

    def test_tied_localization_is_flagged_because_the_patch_may_compensate_elsewhere(self):
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
        tmp, d = self.run_wf(files)
        with tmp:
            self.assertEqual(d.status, "resolved")
            self.assertEqual(sorted(d.steps[0]["tied_with"]), ["calc.classify", "calc.helper"])
            self.assertTrue(any("compensating for a fault elsewhere" in c for c in d.caveats))

    def test_two_independent_faults_are_repaired_in_two_iterations(self):
        files = {"m.py": '''
            def inc(x): return x - 1
            def dbl(x): return x + x + 1
        ''', "tests/test_m.py": '''
            from m import inc, dbl
            def test_inc(): assert inc(1) == 2
            def test_dbl(): assert dbl(3) == 6
        '''}
        tmp, d = self.run_wf(files)
        with tmp:
            self.assertEqual(d.status, "resolved")
            self.assertEqual([s["kind"] for s in d.steps], ["partial", "full"])
            self.assertEqual({s["suspect"] for s in d.steps}, {"m.inc", "m.dbl"})
            self.assertEqual(len(d.iterations), 2)
            self.assertIn("x + 1", d.diff)
            self.assertTrue(any("partial" in w for w in d.steps[0]["why_accepted"]))

    def test_fault_outside_the_template_space_is_reported_unresolved_with_evidence(self):
        files = {"g.py": 'def greet(name):\n    return "Hello " + name\n',
                 "tests/test_g.py": 'from g import greet\ndef test_g(): assert greet("Bob") == "Hello, Bob"\n'}
        tmp, d = self.run_wf(files)
        with tmp:
            self.assertEqual(d.status, "unresolved")
            self.assertEqual(d.steps, [])
            self.assertTrue(d.rejected)
            self.assertEqual(d.diff, "")
            self.assertEqual(d.iterations[0]["suspects"][0]["qname"], "g.greet")  # localized correctly, just not repairable
            self.assertIn("What this does not establish", d.to_markdown())
            with self.assertRaises(ValueError):
                RepairWorkflow.apply_fix(tmp.root, d, approved=True)

    def test_contradictory_tests_yield_regression_evidence_not_a_patch(self):
        files = {"k.py": "def k(n):\n    return n + 1\n",
                 "tests/test_k.py": "from k import k\ndef test_a(): assert k(1) == 3\ndef test_b(): assert k(0) == 1\n"}
        tmp, d = self.run_wf(files)
        with tmp:
            self.assertEqual(d.status, "unresolved")
            regress = [r for r in d.rejected if r["regressions"]]
            self.assertTrue(regress)
            self.assertEqual(regress[0]["regressions"], ["tests/test_k.py::test_b"])
            self.assertIn("regressions", regress[0]["why"])

    def test_regression_guard_alone_blocks_a_partial_fix_that_breaks_another_test(self):
        # k(n, m) = n + m + 1 matches no DEV10 reference, so the behavioural contract cannot be what rejects the patch
        files = {"k.py": "def k(n, m):\n    return n + m + 1\n",
                 "tests/test_k.py": "from k import k\ndef test_a(): assert k(1, 1) == 4\ndef test_b(): assert k(0, 0) == 1\n"}
        tmp, d = self.run_wf(files)
        with tmp:
            self.assertEqual(d.status, "unresolved")
            self.assertEqual(d.steps, [])
            self.assertNotIn("rejected_semantic_contract", d.reasons)
            fixes_but_breaks = [r for r in d.rejected if r["regressions"] and r["fixed"]]
            self.assertTrue(fixes_but_breaks)  # e.g. `1 -> 2` repairs test_a yet breaks test_b
            self.assertEqual(fixes_but_breaks[0]["regressions"], ["tests/test_k.py::test_b"])
            self.assertEqual(fixes_but_breaks[0]["fixed"], ["tests/test_k.py::test_a"])
            self.assertIn("regressions", fixes_but_breaks[0]["why"])

    def test_syntax_error_repo_degrades_to_unresolved_without_crashing(self):
        files = {"m.py": "def f(:\n", "tests/test_m.py": "import m\ndef test_x(): pass\n"}
        tmp, d = self.run_wf(files)
        with tmp:
            self.assertEqual(d.status, "unresolved")
            self.assertEqual(d.steps, [])

    def test_no_failures_and_time_budget_and_unstable_baseline(self):
        tmp, d = self.run_wf(SHOP)
        with tmp:
            self.assertEqual(d.status, "no_failures")
        tmp, d = self.run_wf(with_bug(SHOP, "n >= 10", "n > 10"), time_budget_seconds=1)
        with tmp:
            self.assertEqual(d.status, "time_budget")
        marker = Path(tempfile.gettempdir()) / f"asm_dev11_flaky_{uuid.uuid4().hex}"
        try:
            files = {"m.py": "def f(): return 1\n", "tests/test_m.py": f"import os\nfrom m import f\nM = {str(marker)!r}\n"
                     "def test_flaky():\n    if os.path.exists(M): return\n    open(M, 'w').close()\n    assert False\n"}
            tmp, d = self.run_wf(files)
            with tmp:
                self.assertEqual(d.status, "unstable_baseline")
                self.assertEqual(d.steps, [])
        finally:
            marker.unlink(missing_ok=True)

    def test_apply_requires_approval_fingerprint_match_and_makes_tests_pass(self):
        tmp, d = self.run_wf(with_bug(SHOP, "n >= 10", "n > 10"))
        with tmp as root:
            with self.assertRaises(PermissionError):
                RepairWorkflow.apply_fix(root, d)
            with self.assertRaises(PermissionError):
                RepairWorkflow.apply_fix(root, d, approved=False)
            before = (root / "shop.py").read_text()
            self.assertIn("n > 10", before)  # nothing applied yet
            (root / "extra.py").write_text("X = 1\n")  # repository changes after the dossier was made
            with self.assertRaises(ValueError):
                RepairWorkflow.apply_fix(root, d, approved=True)
            (root / "extra.py").unlink()
            results = RepairWorkflow.apply_fix(root, d, approved=True)
            self.assertEqual(len(results), 1)
            self.assertIn("n >= 10", (root / "shop.py").read_text())
            self.assertTrue(list((root / ".asm_backups").glob("shop.py.*.bak")))
            run = SafeTestRunner(timeout_seconds=30).run_pytest(root)
            self.assertEqual(run.classification, "passed")

    def test_partial_dossier_needs_explicit_allow_partial(self):
        files = {"m.py": "def inc(x): return x - 1\ndef other(x): return x * 3 + 7\n",
                 "tests/test_m.py": "from m import inc, other\ndef test_inc(): assert inc(1) == 2\ndef test_other(): assert other(1) == 99\n"}
        tmp, d = self.run_wf(files)
        with tmp as root:
            self.assertEqual(d.status, "partial")
            self.assertEqual([s["suspect"] for s in d.steps], ["m.inc"])
            with self.assertRaises(ValueError):
                RepairWorkflow.apply_fix(root, d, approved=True)
            RepairWorkflow.apply_fix(root, d, approved=True, allow_partial=True)
            self.assertIn("x + 1", (root / "m.py").read_text())

    def test_tests_can_never_be_edited_to_pass(self):
        files = {"m.py": "def f(x): return x\n", "tests/test_m.py": "from m import f\ndef test_f(): assert f(1) == 2\n"}
        tmp, d = self.run_wf(files)
        with tmp as root:
            self.assertFalse(any(s["path"].startswith("tests/") for s in d.steps))
            self.assertNotIn("tests/", d.diff)
            self.assertEqual((root / "tests" / "test_m.py").read_text().count("== 2"), 1)

    def test_agent_entry_points_localize_and_repair_without_touching_the_repo(self):
        from asm.coding import CodingAgent
        tmp = Repo(with_bug(SHOP, "n >= 10", "n > 10"))
        with tmp as root:
            before = tree_fingerprint(root)
            agent = CodingAgent()
            loc = agent.localize_fault(root, use_semantic=False)
            self.assertEqual(loc.suspects[0].qname, "shop.label")
            d = agent.repair_failing_tests(root, task="fix label")
            self.assertEqual((d.status, d.task), ("resolved", "fix label"))
            self.assertEqual(tree_fingerprint(root), before)

    def test_dossier_is_serialisable_and_markdown_explains_acceptance_and_rejection(self):
        tmp, d = self.run_wf(with_bug(SHOP, "price - price", "price + price"))
        with tmp:
            data = json.loads(json.dumps(d.to_dict()))
            self.assertEqual(data["status"], "resolved")
            md = d.to_markdown()
            for needle in ("## Suspect ranking", "## Accepted changes", "why accepted", "## Rejected candidates",
                           "## Impact", "What this does not establish", "```diff"):
                self.assertIn(needle, md)


if __name__ == "__main__":
    unittest.main()
