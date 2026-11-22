"""DEV20 tests: learned edit steps that combine (asm.coding.steps), in isolation and in the repair workflow."""
import ast
import json
import tempfile
import unittest
from pathlib import Path

from asm.coding.content import ProblemContext
from asm.coding.faultloc import RepairWorkflow
from asm.coding.induction import from_term
from asm.coding.steps import StepLibrary, abstract_step, extract_steps


def norm(s):
    return ast.unparse(ast.parse(s))


def position(cands, want):
    return next((i for i, (p, _) in enumerate(cands) if norm(p) == norm(want)), None)


RENAME = ("def f(xs, n):\n    total = 0\n    for x in xs:\n        total += x * n\n    return total / n\n",
          "def f(xs, n):\n    total = 0\n    for x in xs:\n        total += x * size\n    return total / size\n", "r1")
RENAME2 = ("def q(a, m):\n    return a[m] + m\n", "def q(a, m):\n    return a[k] + k\n", "r2")
PAIR1 = ("def g(d, k):\n    return d.get(k, None)\n", "def g(d, k):\n    return d.pop(k, {})\n", "p1")
PAIR2 = ("def h(m, key):\n    return m.get(key, None)\n", "def h(m, key):\n    return m.setdefault(key, {})\n", "p2")
RAISE = ("def h(x):\n    if x < 0:\n        raise ValueError('neg')\n    return x\n",
         "def h(x):\n    if x < 0:\n        raise TypeError('neg')\n    return x\n", "e1")


class ExtractionTests(unittest.TestCase):
    def test_the_same_change_at_several_places_is_one_multi_site_step(self):
        st = extract_steps(RENAME[0], RENAME[1])
        self.assertEqual([(s.kind, s.sites) for s in st], [("expr", 2)])

    def test_different_changes_are_separate_steps_with_their_places(self):
        st = extract_steps(PAIR1[0], PAIR1[1])
        self.assertEqual([(s.ctx, ast.unparse(from_term(s.rhs))) for s in st], [("Call.func", "d.pop"), ("Call.args", "{}")])

    def test_a_docstring_change_is_not_a_step(self):
        st = extract_steps('def k(a):\n    """Old."""\n    return a + 1\n', 'def k(a):\n    """New."""\n    return a + 2\n')
        self.assertEqual(len(st), 1)
        self.assertEqual(st[0].ctx, "BinOp.right")

    def test_a_change_inside_another_changed_region_belongs_to_it(self):
        st = extract_steps("def f(a):\n    return a\n", "def f(a):\n    if a:\n        return a\n    return None\n")
        self.assertEqual(len(st), 1)
        self.assertEqual(st[0].kind, "stmts")

    def test_an_inserted_statement_is_anchored_on_its_neighbour(self):
        st = extract_steps("def f(a):\n    a.sort()\n    return a\n", "def f(a):\n    a = list(a)\n    a.sort()\n    return a\n")
        self.assertEqual(len(st), 1)
        self.assertEqual((st[0].kind, len(st[0].lhs[1]), len(st[0].rhs[1])), ("stmts", 1, 2))

    def test_a_name_introduced_as_a_raised_exception_is_an_exception_hole(self):
        self.assertEqual(abstract_step(extract_steps(RAISE[0], RAISE[1])[0])[2], {"c0": "exc"})
        bare = extract_steps("def f(x):\n    raise ValueError\n", "def f(x):\n    raise KeyError\n")
        self.assertEqual(abstract_step(bare[0])[2], {"c0": "exc"})


class CandidateTests(unittest.TestCase):
    def test_multi_site_rewrites_every_occurrence_of_a_rename(self):
        lib = StepLibrary()
        lib.learn([RENAME, RENAME2], "train")
        src, want = "def area(w, h, side):\n    return w * w + h\n", "def area(w, h, side):\n    return side * side + h\n"
        cands = lib.candidates_for(src, "m.py", (1, 2), ProblemContext(), as_candidates=False)
        i = position(cands, want)
        self.assertIsNotNone(i)
        self.assertEqual(cands[i][1]["kind"], "multi")
        self.assertIsNone(position([c for c in cands if c[1]["kind"] == "single"], want))  # one place at a time cannot

    def test_a_pair_learned_from_two_fixes_reproduces_a_two_change_fix(self):
        lib = StepLibrary()
        lib.learn([PAIR1, PAIR2], "train")
        self.assertEqual(lib.summary()["pairs_usable"], 1)
        src, want = "def look(t, n):\n    return t.get(n, None)\n", "def look(t, n):\n    return t.pop(n, {})\n"
        cands = lib.candidates_for(src, "m.py", (1, 2), ProblemContext(attributes=["pop"]), as_candidates=False)
        i = position(cands, want)
        self.assertIsNotNone(i)
        self.assertEqual(cands[i][1]["kind"], "pair")

    def test_a_pair_seen_once_is_not_used(self):
        lib = StepLibrary()
        lib.learn([PAIR1], "train")
        src = "def look(t, n):\n    return t.get(n, None)\n"
        cands = lib.candidates_for(src, "m.py", (1, 2), ProblemContext(attributes=["pop"]), as_candidates=False)
        self.assertFalse([c for c in cands if c[1]["kind"] == "pair"])

    def test_the_raised_exception_comes_from_the_problem(self):
        lib = StepLibrary()
        lib.learn([RAISE], "train")
        src = "def p(v):\n    if not v:\n        raise ValueError('empty')\n    return v\n"
        cands = lib.candidates_for(src, "m.py", (1, 4), ProblemContext(exceptions=["KeyError"]), as_candidates=False)
        self.assertEqual(norm(cands[0][0]), norm(src.replace("ValueError", "KeyError")))
        self.assertEqual(cands[0][1]["ops"], ["problem"])

    def test_text_outside_the_rewritten_places_is_kept_exactly(self):
        lib = StepLibrary()
        lib.learn([RENAME, RENAME2], "train")
        src = "def area(w, h, side):\n    # keep this comment\n    return w  *  w + h\n"
        cands = lib.candidates_for(src, "m.py", (1, 3), ProblemContext(), as_candidates=False)
        multi = [p for p, info in cands if info["kind"] == "multi" and "return side" in p]
        self.assertEqual(multi, ["def area(w, h, side):\n    # keep this comment\n    return side  *  side + h\n"])

    def test_budget_limits_and_a_full_budget(self):
        lib = StepLibrary()
        lib.learn([RENAME, RENAME2, PAIR1, PAIR2], "train")
        src = "def look(t, n):\n    return t.get(n, None) + n\n"
        self.assertEqual(lib.candidates_for(src, "m.py", (1, 2), ProblemContext(), limit=0), [])
        for lim in (1, 5, 80):
            got = lib.candidates_for(src, "m.py", (1, 2), ProblemContext(), limit=lim, as_candidates=False)
            self.assertLessEqual(len(got), lim)
            self.assertEqual(len({norm(p) for p, _ in got}), len(got))  # no duplicate programs

    def test_seal_round_trip_and_tamper_refusal(self):
        lib = StepLibrary()
        lib.learn([RENAME, RENAME2, PAIR1, PAIR2, RAISE], "train")
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "steps.json"
            lib.save(path)
            back = StepLibrary.load(path)
            self.assertEqual(back.summary(), lib.summary())
            src = "def look(t, n):\n    return t.get(n, None)\n"
            ctx = ProblemContext(attributes=["pop"])
            self.assertEqual(back.candidates_for(src, "m.py", (1, 2), ctx, as_candidates=False),
                             lib.candidates_for(src, "m.py", (1, 2), ctx, as_candidates=False))
            d = json.loads(path.read_text())
            d["body"]["steps"][0]["support"].append("forged")
            path.write_text(json.dumps(d))
            with self.assertRaises(ValueError):
                StepLibrary.load(path)


class WorkflowTests(unittest.TestCase):
    FILES = {"m.py": "def scaled(values, factor, size):\n    return [v * factor for v in values] + [factor]\n",
             "tests/test_m.py": "from m import scaled\n"
                                "def test_size(): assert scaled([1, 2], 3, 10) == [10, 20, 10]\n"}

    def test_a_learned_multi_site_rename_fixes_a_bug_in_the_workflow(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for k, v in self.FILES.items():
                (root / k).parent.mkdir(parents=True, exist_ok=True)
                (root / k).write_text(v)
            self.assertNotEqual(RepairWorkflow().run(root).status, "resolved")  # built-in operations alone
            lib = StepLibrary()
            lib.learn([RENAME, RENAME2], "train")
            d = RepairWorkflow(steps=lib).run(root)
            self.assertEqual(d.status, "resolved", d.notes)
            st = d.steps[0]
            self.assertEqual(st["edit_family"], "learned")
            self.assertIn(st["learned_step"], lib.steps)
            self.assertIn("v * size", (root / "m.py").read_text() + st["diff"])


if __name__ == "__main__":
    unittest.main()
