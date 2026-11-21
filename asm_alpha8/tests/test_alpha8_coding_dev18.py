"""DEV18 tests: learned fix shapes whose content is filled in from the problem (content solver), in isolation and in
the repair workflow."""
import ast
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from asm.coding.content import (ProblemContext, StringVocabulary, exception_fillers, literals, name_fillers,
                                string_fillers)
from asm.coding.faultloc import RepairWorkflow
from asm.coding.knowledge import KnowledgeBase
from asm.coding.shapes import ShapeLibrary

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmarks"))


def norm(s):
    return ast.unparse(ast.parse(s))


STRING_FIX = ("def r(cmd):\n    return cmd.replace('push', 'push --force')\n",
              "def r(cmd):\n    return cmd.replace('push', 'push --force-with-lease')\n", "x1")
REGEX_FIX = ("def m(s):\n    return re.match(r'^[a-z]+$', s)\n", "def m(s):\n    return re.match(r'^[a-z]*$', s)\n", "x2")
TRY_FIX = ("def a(parts, i):\n    parts.pop(i)\n    return parts\n",
           "def a(parts, i):\n    try:\n        parts.pop(i)\n    except IndexError:\n        pass\n    return parts\n", "x3")


class ContentTests(unittest.TestCase):
    def test_literals_from_the_named_test_functions_only(self):
        src = "def test_a():\n    assert f() == 'alpha'\n\ndef test_b():\n    assert f() == 'beta'\n"
        self.assertEqual(literals(src, ["test_a"])[0], ["alpha"])
        self.assertEqual(sorted(literals(src)[0]), ["alpha", "beta"])
        self.assertEqual(sorted(literals(src, ["nope"])[0]), ["alpha", "beta"])  # unknown names: whole file

    def test_failure_messages_give_quoted_text_and_exception_names(self):
        ctx = ProblemContext.build("def f(): pass\n", [], None,
                                   ["E   AssertionError: assert 'git pull' == 'git pull --rebase'\nValueError: bad"])
        self.assertIn("git pull --rebase", ctx.test_strings)
        self.assertEqual(ctx.exceptions[0], "ValueError")

    def test_extend_grows_to_token_boundaries_inside_a_test_literal(self):
        ctx = ProblemContext(test_strings=["git push --force-with-lease"])
        vals = [v for v, op in string_fillers("push --force", ctx, None)]
        self.assertIn("push --force-with-lease", vals[:3])
        self.assertTrue(all(op == "extend" for _, op in string_fillers("push --force", ctx, None)))

    def test_vocabulary_edits_and_their_contexts(self):
        v = StringVocabulary()
        v.add("+", "*", "z]", "$")      # a segment replacement: applied wherever the old segment occurs
        v.add("", "?", "s", ":")        # an insertion: only between its learned neighbours
        vals = [x for x, op in string_fillers("^https:\\d+", ProblemContext(), v)]
        self.assertIn("^https:\\d*", vals)
        self.assertIn("^https?:\\d+", vals)

    def test_test_and_module_literals_replace_similar_strings(self):
        ctx = ProblemContext(test_strings=["%Y-%m-%dT%H:%M"], module_strings=["%Y-%m-%d %H:%M:%S"])
        out = string_fillers("%Y-%m-%d %H:%M", ctx, None)
        self.assertEqual(out[0], ("%Y-%m-%dT%H:%M", "test"))
        self.assertIn(("%Y-%m-%d %H:%M:%S", "module"), out)

    def test_names_and_exceptions(self):
        ctx = ProblemContext(module_names=["helper"], exceptions=["ParseError"])
        names = [n for n, _ in name_fillers("outpt", ["output", "x"], ctx)]
        self.assertEqual(names[0], "output")
        self.assertEqual(exception_fillers(None, ctx)[0], ("ParseError", "problem"))


class ShapeTests(unittest.TestCase):
    def lib(self, *ex):
        lib = ShapeLibrary()
        lib.learn(list(ex), "test")
        return lib

    def test_shapes_abstract_carried_values_and_open_introduced_ones(self):
        lib = self.lib(STRING_FIX, REGEX_FIX, TRY_FIX)
        holes = sorted(tuple(sorted(s.holes.values())) for s in lib.shapes.values())
        self.assertIn(("str",), holes)
        self.assertIn(("exc",), holes)
        string_shape = next(s for s in lib.shapes.values() if s.holes == {"c0": "str"})
        self.assertEqual(sorted(set(string_shape.support)), ["x1", "x2"])  # two different fixes, one shape
        self.assertEqual(string_shape.status, "active")
        self.assertEqual(len(lib.vocab.edits), 2)

    def test_exception_comes_from_the_problem_not_from_the_training_fix(self):
        lib = self.lib(TRY_FIX)
        src = "def pick(xs, j):\n    xs.remove(j)\n    return xs\n"
        ctx = ProblemContext.build(src, [], None, ["ValueError: list.remove(x): x not in list"])
        prog, info = lib.candidates_for(src, "m.py", (1, 3), ctx, as_candidates=False)[0]
        self.assertIn("except ValueError", prog)
        self.assertEqual(info["ops"], ["problem"])

    def test_a_string_shape_does_not_fire_on_numbers(self):
        lib = self.lib(STRING_FIX)
        src = "def g():\n    return 41\n"
        self.assertEqual(lib.candidates_for(src, "m.py", (1, 2), ProblemContext(test_strings=["x"]), as_candidates=False), [])

    def test_problem_derived_content_ranks_first(self):
        lib = self.lib(STRING_FIX, REGEX_FIX)
        src = "def get(command):\n    return command.replace('pull', 'pull --rebase')\n"
        ctx = ProblemContext.build(src, ["def test():\n    assert get(C('git pull')) == 'git pull --rebase --autostash'\n"])
        out = lib.candidates_for(src, "m.py", (1, 2), ctx, as_candidates=False)
        self.assertEqual(out[0][1]["ops"], ["extend"])
        self.assertTrue(any("'pull --rebase --autostash'" in p for p, _ in out[:6]))

    def test_seal_round_trip_tamper_and_retirement(self):
        lib = self.lib(STRING_FIX, TRY_FIX)
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "s.json"
            lib.save(p)
            self.assertEqual(ShapeLibrary.load(p).summary(), lib.summary())
            d = json.loads(p.read_text())
            d["body"]["shapes"][0]["status"] = "active"
            d["body"]["shapes"][0]["support"] = ["fake"] * 9
            p.write_text(json.dumps(d))
            with self.assertRaises(ValueError):
                ShapeLibrary.load(p)
        sid = next(iter(lib.shapes))
        for i in range(20):
            lib.record_outcome(sid, False, f"p{i}")
        self.assertEqual(lib.shapes[sid].status, "retired")


class SerializationTests(unittest.TestCase):
    """DEV18 amendment A1: bugs found by the DEV18 self-check in saving and loading learned knowledge."""

    def round_trip(self, obj, cls):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "k.json"
            obj.save(p)
            return cls.load(p)

    def test_a_shape_with_eleven_or_more_variables_survives_save_and_load(self):
        args = ", ".join(f"'{c}'" for c in "abcdefghijk")
        before = f"def f(call):\n    call({args})\n    return 1\n"
        after = f"def f(call):\n    try:\n        call({args})\n    except ValueError:\n        pass\n    return 1\n"
        lib = ShapeLibrary()
        lib.learn([(before, after, "w11")], "test")
        self.assertTrue(any(len(s.var_types) >= 11 for s in lib.shapes.values()))
        back = self.round_trip(lib, ShapeLibrary)  # used to raise: "failed its integrity check"
        self.assertEqual(sorted(back.shapes), sorted(lib.shapes))
        self.assertEqual(back.summary(), lib.summary())
        src = "def h(fn):\n    fn('1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11')\n    return 0\n"
        ctx = ProblemContext(exceptions=["KeyError"])
        mine = lib.candidates_for(src, "m.py", (1, 3), ctx, as_candidates=False)
        self.assertTrue(mine)
        self.assertEqual(back.candidates_for(src, "m.py", (1, 3), ctx, as_candidates=False), mine)

    def test_bytes_and_ellipsis_constants_survive_save_and_load(self):
        bytes_fix = ("def eol(x):\n    return x == b'\\n'\n", "def eol(x):\n    return x == b'\\r\\n'\n", "b1")
        dots_fix = ("def stub(x):\n    ...\n", "def stub(x):\n    return None\n", "e1")
        kb = KnowledgeBase()
        kb.learn([bytes_fix, dots_fix], "test")
        back = self.round_trip(kb, KnowledgeBase)  # Ellipsis used to make saving fail; bytes came back as ints
        for before, after, _ in (bytes_fix, dots_fix):
            progs = [p for _, ps in back.retrieve(before, (1, before.count("\n") + 1)) for p in ps]
            self.assertIn(norm(after), [norm(p) for p in progs])
        lib = ShapeLibrary()
        lib.learn([bytes_fix, dots_fix], "test")
        lback = self.round_trip(lib, ShapeLibrary)  # bytes used to make saving fail
        self.assertEqual(sorted(lback.shapes), sorted(lib.shapes))
        for before, _, _ in (bytes_fix, dots_fix):
            span = (1, before.count("\n") + 1)
            self.assertEqual(lback.candidates_for(before, "m.py", span, ProblemContext(), as_candidates=False),
                             lib.candidates_for(before, "m.py", span, ProblemContext(), as_candidates=False))

    def test_a_whole_f_string_can_be_rewritten_but_not_its_parts(self):
        fix = ("def lead(d):\n    d = f'{d.strip()} '\n    return d\n",
               "def lead(d):\n    d = d and d.strip() + ' '\n    return d\n", "f1")
        kb = KnowledgeBase()
        kb.learn([fix], "test")
        progs = [p for _, ps in kb.retrieve(fix[0], (1, 3)) for p in ps]
        self.assertIn(norm(fix[1]), [norm(p) for p in progs])  # the f-string node itself used to be skipped
        lib = ShapeLibrary()
        lib.learn([fix], "test")
        out = lib.candidates_for(fix[0], "m.py", (1, 3), ProblemContext(), as_candidates=False)
        self.assertIn(norm(fix[1]), [norm(p) for p, _ in out])
        # the documented limit stays: the parts of an f-string are not rewritten in place
        kb2 = KnowledgeBase()
        kb2.learn([("def h():\n    return 'ab'\n", "def h():\n    return 'ac'\n", "s1")], "test")
        inner = "def g(y):\n    return f'ab{y}'\n"
        self.assertEqual([p for _, ps in kb2.retrieve(inner, (1, 2)) for p in ps], [])

    def test_knowledge_saved_by_dev17_still_loads_with_its_seal(self):
        kb = KnowledgeBase.load(ROOT / "benchmarks" / "results" / "dev17" / "knowledge_history.json")
        self.assertGreater(len(kb.entries), 0)


class EarlyStopTests(unittest.TestCase):
    """A2 (performance): stopping at the limit gives exactly the first results of the full search, and builds less."""
    SRC = "def f(a, b, c, d):\n" + "".join(f"    x{i} = g(a, b, c, d) + {i}\n" for i in range(30)) + "    return x0\n"

    def test_a_limited_search_returns_the_first_results_of_the_full_search(self):
        from asm.coding.induction import Procedure
        p = Procedure("expr", ("?", 0), ("Call", (("func", ("Name", (("id", ("=", "h")), ("ctx", ("Load", ()))))),
                                                  ("args", ("[]", (("?", 0),))), ("keywords", ("[]", ())))), 0)
        span = (1, self.SRC.count("\n") + 1)
        built = []

        def fill(binding, node, tree):
            built.append(1)
            return [(("Call", (("func", ("Name", (("id", ("=", n)), ("ctx", ("Load", ()))))), ("args", ("[]", (binding[0],))),
                               ("keywords", ("[]", ())))), {}) for n in ("h", "k")]
        full = p.apply_detailed(self.SRC, span, fill)
        n_full = len(built)
        built.clear()
        for k in (1, 5, 40):
            self.assertEqual(p.apply_detailed(self.SRC, span, fill, max_results=k), full[:k])
        self.assertGreater(len(full), 40)
        built.clear()
        p.apply_detailed(self.SRC, span, fill, max_results=5)
        self.assertLess(len(built), n_full)

    def test_limited_retrieval_returns_the_first_programs_of_the_full_retrieval(self):
        kb = KnowledgeBase()
        kb.learn([STRING_FIX, REGEX_FIX, TRY_FIX], "t")
        src = "def r(cmd):\n" + "".join(f"    cmd = cmd.replace('push', 'push --force') + str({i})\n" for i in range(12)) + "    return cmd\n"
        span = (1, src.count("\n") + 1)
        full = [x for _, ps in kb.retrieve(src, span) for x in ps]
        self.assertGreater(len(full), 3)
        for k in (1, 3, len(full) + 5):
            self.assertEqual([x for _, ps in kb.retrieve(src, span, max_programs=k) for x in ps][:k], full[:k])


class WorkflowTests(unittest.TestCase):
    FILES = {"m.py": "def push_command(script):\n    return script.replace('push', 'push --force')\n",
             "tests/test_m.py": "from m import push_command\n"
                                "def test_lease(): assert push_command('git push') == 'git push --force-with-lease'\n"
                                "def test_other(): assert push_command('git pull') == 'git pull'\n"}

    def run_wf(self, **kw):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for k, v in self.FILES.items():
                (root / k).parent.mkdir(parents=True, exist_ok=True)
                (root / k).write_text(v)
            return RepairWorkflow(**kw).run(root)

    def test_content_from_the_failing_test_completes_a_learned_shape(self):
        unrelated = ("def label(x):\n    return 'item'\n", "def label(x):\n    return 'item:'\n", "u1")
        kb = KnowledgeBase()
        kb.learn([unrelated], "test")
        self.assertNotEqual(self.run_wf().status, "resolved")               # built-in operations: no string edits
        self.assertNotEqual(self.run_wf(knowledge=kb).status, "resolved")   # DEV17: content of the training fix only
        lib = ShapeLibrary()
        lib.learn([unrelated], "test")
        d = self.run_wf(knowledge=kb, shapes=lib)
        self.assertEqual(d.status, "resolved", d.notes)
        st = d.steps[0]
        self.assertEqual(st["edit_family"], "learned")
        self.assertIn("--force-with-lease", st["diff"])
        self.assertIn(st["learned_shape"], lib.shapes)


class FreshMinerTests(unittest.TestCase):
    def test_context_comes_from_the_test_functions_the_fix_changed(self):
        import dev18_mine_fresh as F
        from asm.coding.integrity import ChainedWriter, read_records
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "toy"
            (repo / "pkg").mkdir(parents=True)
            (repo / "tests").mkdir()
            g = lambda *a: subprocess.run(["git", *a], cwd=repo, check=True, capture_output=True)  # noqa: E731
            g("init", "-q")
            g("config", "user.email", "t@example.invalid")
            g("config", "user.name", "t")
            (repo / "pkg/m.py").write_text("def greet(n):\n    return 'hello ' + n\n")
            (repo / "tests/test_m.py").write_text("def test_old():\n    assert 'unrelated'\n")
            g("add", "-A")
            g("commit", "-q", "-m", "init")
            (repo / "pkg/m.py").write_text("def greet(n):\n    return 'hello, ' + n\n")
            (repo / "tests/test_m.py").write_text("def test_old():\n    assert 'unrelated'\n\ndef test_new():\n    assert greet('x') == 'hello, x'\n")
            g("add", "-A")
            g("commit", "-q", "-m", "Fix greeting punctuation")
            w = ChainedWriter(Path(td) / "o.jsonl", {"run": "t"})
            F.mine("toy", "unused", Path(td), w)
            _, recs = read_records(Path(td) / "o.jsonl")
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["test_functions"], ["test_new"])
        self.assertIn("hello, x", recs[0]["context"]["test_strings"])
        self.assertNotIn("unrelated", recs[0]["context"]["test_strings"])


if __name__ == "__main__":
    unittest.main()
