"""DEV15 tests: repair families beyond single-site templates, import-time verification, constants mined from every
version, and the DEV15 oracle."""
import ast
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from asm.coding import SafeTestRunner
from asm.coding.faultloc import RepairWorkflow, Suspect, collect_spectrum, generate_candidates
from asm.coding.generation import find_function_by_qualname, merge_mined, mine_constants, typed_values
from asm.coding.patches import PatchProposalBuilder
from asm.coding.repair_ops import INSERT_FAMILIES, family_of, insertion_edits, site_edits
from asm.coding.understanding import CodeUnderstanding
from asm.coding.verification import import_time_function, verification_target, verify_patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmarks"))


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


SRC = '''def write(output, data):
    """doc"""
    output_path = str(output)
    if output_path and data or not data:
        total = len(data)
        total *= 2
        with open(output_path, "a") as f:
            f.write(data)
    return []
'''
SUS = Suspect("m.write", "m.py", 1, 9, 1.0, {}, [])
RANGES = [("m.write", 1, 9)]
SCORES = {"m.py": {3: 0.5, 4: 0.5, 5: 0.7, 6: 0.7, 7: 0.9, 8: 0.9}}


def run(files, **kw):
    with Repo(files) as root:
        return RepairWorkflow(**kw).run(root)


# ======================================================================== candidate generation
class GenerationOrderTests(unittest.TestCase):
    def test_default_is_exactly_the_dev14_repair_space(self):
        cands = generate_candidates(SRC, "m.py", SUS, RANGES, SCORES)
        self.assertTrue(cands)
        self.assertTrue(all(family_of(c.reason) == "single_site" for c in cands))

    def test_extended_keeps_dev14_candidates_in_their_relative_order(self):
        old = [c.reason for c in generate_candidates(SRC, "m.py", SUS, RANGES, SCORES)]
        new = [c.reason for c in generate_candidates(SRC, "m.py", SUS, RANGES, SCORES, extended=True)]
        self.assertEqual([r for r in new if r in set(old)], old)
        fams = {family_of(r) for r in new}
        self.assertTrue({"name", "drop_clause", "guard_return", "guard_stmt", "pair"} <= fams, fams)

    def test_every_extended_candidate_parses_and_changes_the_program(self):
        base = ast.unparse(ast.parse(SRC))
        new = generate_candidates(SRC, "m.py", SUS, RANGES, SCORES, extended=True, failure_texts=["IndexError: x"])
        norms = [ast.unparse(ast.parse(c.replacement)) for c in new]
        self.assertNotIn(base, norms)
        self.assertEqual(len(norms), len(set(norms)), "programs must be distinct")

    def test_singles_come_before_pairs(self):
        fams = [family_of(c.reason) for c in generate_candidates(SRC, "m.py", SUS, RANGES, SCORES, extended=True)]
        first_pair = fams.index("pair")
        self.assertTrue(all(f == "pair" for f in fams[first_pair:]))

    def test_test_files_are_never_patched(self):
        self.assertEqual(generate_candidates(SRC, "tests/test_m.py", SUS, RANGES, SCORES, extended=True), [])

    def test_name_swaps_prefer_similar_names_and_skip_names_bound_later(self):
        from asm.coding.faultloc import _offsets
        sites = [s for s in site_edits(SRC, "m.py", RANGES, "m.write", _offsets(SRC.encode())) if s.kind == "name"]
        at7 = next(s for s in sites if s.line == 7 and s.original == "output_path")
        self.assertEqual(at7.options[0], "output")  # shared prefix ranks first
        at3 = [s for s in sites if s.line == 3]
        # only `data` is bound before line 3: `total`/`f` come later and `output_path` is assigned ON line 3
        self.assertEqual([s.options for s in at3], [["data"]])

    def test_no_getattr_rewrite_of_a_method_being_called(self):
        from asm.coding.faultloc import _offsets
        sites = site_edits(SRC, "m.py", RANGES, "m.write", _offsets(SRC.encode()))
        self.assertFalse([s for s in sites if s.kind == "getattr" and s.original == "f.write"])

    def test_try_except_uses_only_builtin_exceptions_seen_in_failures(self):
        ins = insertion_edits(SRC, "m.py", RANGES, "m.write", SCORES["m.py"],
                              ["Traceback\nIndexError: list index out of range", "MyCustomError: x", "AssertionError"])
        excs = {i.note for i in ins if i.kind == "try_except"}
        self.assertTrue(excs and all("IndexError" in e for e in excs), excs)

    def test_guard_return_goes_after_the_docstring(self):
        ins = next(i for i in insertion_edits(SRC, "m.py", RANGES, "m.write", SCORES["m.py"]) if i.kind == "guard_return")
        from asm.coding.repair_ops import apply_insertion
        fn = ast.parse(apply_insertion(SRC, ins)).body[0]
        self.assertIsInstance(fn.body[0].value, ast.Constant)  # docstring still first
        self.assertIsInstance(fn.body[1], ast.If)

    def test_family_of(self):
        self.assertEqual(family_of("compare: '<' -> '<=' at line 3"), "single_site")
        self.assertEqual(family_of("name: 'a' -> 'b' at line 3"), "name")
        self.assertEqual(family_of("pair: x + y"), "pair")
        self.assertEqual(family_of("try_except: wrap at line 3"), "try_except")


# ======================================================================== end-to-end repairs
class ExtendedRepairTests(unittest.TestCase):
    def test_wrong_variable_is_repaired_by_a_name_swap(self):
        d = run({"m.py": "def area(width, height):\n    w = width\n    h = height\n    return w * w\n",
                 "tests/test_m.py": "from m import area\ndef test_a(): assert area(2, 3) == 6\ndef test_sq(): assert area(4, 4) == 16\n"})
        self.assertEqual(d.status, "resolved")
        self.assertEqual(d.steps[0]["edit_family"], "name")
        self.assertTrue(d.verify()[0])

    def test_missing_none_guard_is_repaired_by_an_insertion(self):
        d = run({"m.py": "def norm(s):\n    t = s.strip()\n    return t.lower()\n",
                 "tests/test_m.py": "from m import norm\ndef test_n(): assert norm(' A ') == 'a'\n"
                                    "def test_none(): assert norm(None) is None\n"})
        self.assertEqual(d.status, "resolved")
        self.assertIn(d.steps[0]["edit_family"], INSERT_FAMILIES)

    def test_two_coordinated_edits_are_repaired_by_a_pair(self):
        files = {"m.py": "def f(a, b):\n    return a - b * 2\n",
                 "tests/test_m.py": "from m import f\ndef test_1(): assert f(1, 1) == 4\ndef test_2(): assert f(2, 0) == 2\n"
                                    "def test_3(): assert f(0, 1) == 3\n"}
        self.assertNotEqual(run(files, extended_ops=False).status, "resolved")  # DEV14 cannot repair it
        d = run(files)
        self.assertEqual(d.status, "resolved")
        self.assertEqual(d.steps[0]["edit_family"], "pair")

    def test_where_dev14_resolves_dev15_makes_the_same_repair(self):
        # regression for the phase split: a fault DEV14's templates fix must get exactly DEV14's patch, even when many
        # DEV15 candidates exist on more suspicious lines (found on a fresh-subject smoke run: parse.date_convert)
        files = {"m.py": "def g(a, b, c):\n    x = a + b\n    y = x * c\n    z = y + a\n    return z + 4\n",
                 "tests/test_m.py": "from m import g\ndef test_1(): assert g(1, 2, 3) == 15\ndef test_2(): assert g(0, 0, 0) == 5\n"}
        d14, d15 = run(files, extended_ops=False), run(files)
        self.assertEqual(d14.status, "resolved")
        self.assertEqual((d15.status, d15.diff), (d14.status, d14.diff))
        self.assertEqual(d15.steps[0]["edit_family"], "single_site")

    def test_pairs_are_not_alternatives_to_an_accepted_single_edit(self):
        # minimal-repair rule (found by the DEV12 confidence tests): "fix + one extra edit" is a decoy, not a competing fix
        d = run({"m.py": "def big(n):\n    return n > 5\n", "tests/test_m.py": "from m import big\ndef test_big(): assert big(5)\n"})
        st = d.steps[0]
        self.assertEqual(st["edit_family"], "single_site")
        self.assertFalse([a for a in st["alternatives_passing"] if family_of(a) == "pair"], st["alternatives_passing"])

    def test_dev14_mode_reports_only_single_site_families(self):
        d = run({"m.py": "def inc(x): return x - 1\n",
                 "tests/test_m.py": "from m import inc\ndef test_inc(): assert inc(1) == 2\n"}, extended_ops=False)
        self.assertEqual(d.status, "resolved")
        self.assertEqual(d.steps[0]["edit_family"], "single_site")

    def test_thefuck15_shape_now_shows_that_passing_edits_disagree(self):
        # DEV14 accepted `B not in s` with label HIGH on real bug thefuck-15; the developer dropped clause B. Both pass
        # the tests. DEV15 finds the dropped-clause alternative and an input containing both strings separates them.
        files = {"m.py": "def match(s):\n    return ('did not match any file(s) known to git.' in s\n"
                         "            and \"Did you forget to 'git add'?\" in s)\n",
                 "tests/test_m.py": "from m import match\n"
                                    "def test_y(): assert match(\"error: pathspec 'x' did not match any file(s) known to git.\")\n"
                                    "def test_n(): assert not match('fatal: other')\n"}
        d = run(files)
        self.assertEqual(d.status, "resolved")
        st = d.steps[0]
        self.assertTrue(any(family_of(a) == "drop_clause" for a in st["alternatives_passing"]), st["alternatives_passing"])
        self.assertIn("alternatives_disagree", st["confidence_basis"])
        self.assertNotEqual(st["confidence"], "high")


# ======================================================================== constants mined from every version
class MiningTests(unittest.TestCase):
    def test_long_strings_are_mined(self):
        fn = ast.parse("def f(s):\n    return 'did not match any file(s) known to git.' in s\n").body[0]
        self.assertIn("did not match any file(s) known to git.", mine_constants(fn)["strs"])

    def test_mined_values_come_first_and_pairs_are_joined(self):
        import random
        mined = {"nums": [], "strs": ["alpha beta", "gamma"]}
        vals = typed_values("x", mined, random.Random(0))
        self.assertEqual(vals[0], "alpha beta gamma")
        mined_n = {"nums": [41, 42, 43], "strs": []}
        self.assertEqual(typed_values(5, mined_n, random.Random(0))[:3], [41, 42, 43])

    def test_merge_and_qualname_lookup_survive_line_shifts(self):
        a = "class C:\n    def m(self, x):\n        return x == 'one'\n"
        b = "import os\n\n\n" + a.replace("'one'", "'two'")
        na, nb = find_function_by_qualname(a, "C.m"), find_function_by_qualname(b, "C.m")
        self.assertEqual((na.lineno, nb.lineno), (2, 5))
        self.assertEqual(merge_mined([mine_constants(na), mine_constants(nb)])["strs"], ["one", "two"])
        self.assertIsNone(find_function_by_qualname(a, "C.nope"))


# ======================================================================== import-time verification
REGISTRY = {
    "reg.py": """\
        import re
        RULES = []
        def _add(word, plural):
            RULES.insert(0, (re.compile(word + '$'), plural))
        def pluralize(w):
            for pat, rep in RULES:
                if pat.search(w):
                    return pat.sub(rep, w)
            return w + 's'
        _add('person', 'people')
        _add('child', 'children')
        """,
    "tests/test_reg.py": """\
        from reg import pluralize
        def test_p(): assert pluralize('person') == 'people'
        def test_c(): assert pluralize('child') == 'children'
        def test_x(): assert pluralize('cat') == 'cats'
        def test_s(): assert pluralize('salesperson') == 'salespeople'
        """,
}


class ImportTimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo = Repo(REGISTRY)
        cls.root = cls.repo.root
        cls.spectrum = collect_spectrum(cls.root, None, SafeTestRunner(timeout_seconds=60))
        cls.funcs = {f.qname: f for f in CodeUnderstanding().analyze(cls.root).functions}
        cls.src = (cls.root / "reg.py").read_text()

    @classmethod
    def tearDownClass(cls):
        cls.repo.tmp.cleanup()

    def prop(self, new, why):
        return PatchProposalBuilder.from_replacement(self.root, "reg.py", new, why)

    def test_detection(self):
        self.assertTrue(import_time_function(self.root, self.funcs["reg._add"]))
        self.assertFalse(import_time_function(self.root, self.funcs["reg.pluralize"]))
        self.assertEqual(self.spectrum.records.get("reg.py:_add", []), [])  # never called inside a test

    def test_equivalent_and_wrong_import_time_patches_are_told_apart(self):
        same = self.prop(self.src.replace("word + '$'", "word + r'$'"), "same")
        bad = self.prop(self.src.replace("word + '$'", "'^' + word + '$'"), "anchored")
        cx = verify_patch(self.root, "reg._add", ("same", same), [("anchored", bad)], self.spectrum, self.funcs)
        self.assertTrue(cx["available"])
        self.assertEqual(cx["mode"], "import_state")
        self.assertEqual(cx["footprint"]["same"], 0.0)
        self.assertGreater(cx["footprint"]["anchored"], 0.0)
        self.assertIn("RULES", cx["state_changed"]["anchored"])
        self.assertTrue(any("salesperson" in d["input"] for d in cx["distinguishing"]), cx["distinguishing"])
        self.assertFalse(cx["alternatives_agree_everywhere"])

    def test_compiled_patterns_are_compared_by_pattern_text(self):
        flag = self.prop(self.src.replace("re.compile(word + '$')", "re.compile(word + '$', re.I)"), "flag")
        cx = verify_patch(self.root, "reg._add", ("flag", flag), [], self.spectrum, self.funcs)
        self.assertIn("RULES", cx["state_changed"]["flag"])  # DEV14's encoder saw every Pattern as an empty object

    def test_oracle_import_state_classes(self):
        import dev15_oracle as O
        with Repo(dict(REGISTRY, **{"reg.py": textwrap.dedent(REGISTRY["reg.py"]).replace("word + '$'", "'^' + word + '$'")})) as bad, \
                Repo(dict(REGISTRY, **{"reg.py": textwrap.dedent(REGISTRY["reg.py"]).replace("word + '$'", "word + r'$'")})) as same:
            w = O.classify_patch(self.root, bad, False, ["reg._add"], self.funcs, self.spectrum)
            e = O.classify_patch(self.root, same, False, ["reg._add"], self.funcs, self.spectrum)
        self.assertEqual(w["class"], "wrong")
        self.assertEqual(e["class"], "equivalent")
        self.assertEqual(w["details"]["reg._add"]["mode"], "import_state")


# ======================================================================== oracle: constants from every version
class OracleMiningTests(unittest.TestCase):
    def test_reference_without_the_constant_no_longer_hides_a_wrong_patch(self):
        """thefuck-15 in miniature: reference (developer) dropped clause B; ASM's patch negated it. Mining only the
        reference (DEV14) never builds an input containing B; DEV15 mines the patched version too."""
        import dev14_oracle as O14
        import dev15_oracle as O15
        tests = ("from m import match\n"
                 "def test_y(): assert match('error: did not match any file(s) known to git.')\n"
                 "def test_n(): assert not match('fatal: other')\n")
        fixed = {"m.py": "def match(s):\n    return 'did not match any file(s) known to git.' in s\n", "tests/test_m.py": tests}
        patched = {"m.py": "def match(s):\n    return ('did not match any file(s) known to git.' in s\n"
                           "            and \"Did you forget to 'git add'?\" not in s)\n", "tests/test_m.py": tests}
        with Repo(fixed) as fr, Repo(patched) as pr:
            sp = collect_spectrum(fr, None, SafeTestRunner(timeout_seconds=60))
            funcs = {f.qname: f for f in CodeUnderstanding().analyze(fr).functions}
            old = O14.classify_patch(fr, pr, False, ["m.match"], funcs, sp)
            new = O15.classify_patch(fr, pr, False, ["m.match"], funcs, sp)
        self.assertEqual(old["class"], "equivalent")  # the DEV14 miss, reproduced
        self.assertIn(new["class"], {"wrong", "wrong_generated"})
        self.assertTrue(new["original_ok"] or new["class"] == "wrong")


if __name__ == "__main__":
    unittest.main()
