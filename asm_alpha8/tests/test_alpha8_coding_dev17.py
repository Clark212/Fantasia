"""DEV17 tests: ASM learns new repair procedures from examples (induction), keeps them as evidence-backed knowledge
(knowledge base lifecycle), and applies them to problems its built-in operations cannot solve."""
import ast
import json
import tempfile
import unittest
from pathlib import Path

from asm.coding.faultloc import RepairWorkflow
from asm.coding.induction import Procedure, executable, extract_edits, generalize, induce, variables
from asm.coding.knowledge import RETIRE_MIN_FIRES, KnowledgeBase


def norm(s):
    return ast.unparse(ast.parse(s))


POP = [("def a(parts, i):\n    parts.pop(i)\n    return parts\n",
        "def a(parts, i):\n    try:\n        parts.pop(i)\n    except IndexError:\n        pass\n    return parts\n", "e1"),
       ("def b(xs, k):\n    xs.pop(k)\n    log(xs)\n",
        "def b(xs, k):\n    try:\n        xs.pop(k)\n    except IndexError:\n        pass\n    log(xs)\n", "e2")]
REGEX = [("def e(s):\n    return re.match(r'^[a-z]+$', s)\n", "def e(s):\n    return re.match(r'^[a-z]*$', s)\n", "r1"),
         ("def f(s):\n    return re.findall(r'\\d+', s)\n", "def f(s):\n    return re.findall(r'\\d*', s)\n", "r2")]


class InductionTests(unittest.TestCase):
    def test_edit_kinds(self):
        kinds = lambda b, a: sorted({e.kind for e in extract_edits(b, a)})  # noqa: E731
        self.assertEqual(kinds("def f(a):\n    return a < 1\n", "def f(a):\n    return a <= 1\n"), ["expr"])
        self.assertEqual(kinds(*POP[0][:2]), ["stmts"])
        self.assertEqual(kinds(*REGEX[0][:2]), ["expr", "string"])
        guard = extract_edits("def f(x):\n    y = x.a\n    return y\n", "def f(x):\n    if x is None:\n        return None\n    y = x.a\n    return y\n")
        self.assertEqual([e.kind for e in guard], ["stmts"])
        self.assertEqual(len(guard[0].lhs[1]), 1)  # anchored on the statement the guard was inserted before
        self.assertEqual(extract_edits("def f():\n    return 1\n", "def f():\n    return 1\n"), [])

    def test_anti_unification_shares_variables_between_pattern_and_replacement(self):
        e1 = extract_edits(*POP[0][:2])[0]
        e2 = extract_edits(*POP[1][:2])[0]
        rule = generalize([e1, e2])
        self.assertTrue(executable(rule))
        kind, lhs, rhs, _ = rule
        self.assertTrue(variables(rhs) <= variables(lhs))
        self.assertIn("pop", json.dumps(lhs))  # agreed by both instances: stays concrete
        self.assertNotIn('"parts"', json.dumps(lhs))  # differed: became a variable

    def test_rules_whose_replacement_invents_unbound_values_are_not_executable(self):
        self.assertFalse(executable(("expr", ("?", 0), ("?", 0), 0)))  # bare-variable pattern matches everything
        self.assertFalse(executable(("expr", ("Name", (("id", ("=", "x")),)), ("?", 3), 0)))

    def test_learned_procedure_applies_to_unseen_code_and_edits_only_the_match(self):
        procs = {p.describe(): p for p, ids in induce(POP) if len(ids) == 2}
        p = next(v for k, v in procs.items() if ".pop(" in k)
        unseen = ("X = 1  # keep this comment\n\nclass Q:\n    def drop(self, stack, j):\n        stack.pop(j)\n"
                  "        return stack\n")
        outs = p.apply(unseen, (4, 6))
        self.assertEqual(len(outs), 1)
        self.assertTrue(outs[0].startswith("X = 1  # keep this comment\n"))
        self.assertIn("except IndexError", outs[0])
        self.assertEqual(p.apply(unseen, (1, 2)), [])  # outside the given function: nothing

    def test_string_procedure_from_two_regex_fixes(self):
        p = next(p for p, ids in induce(REGEX) if p.kind == "string" and len(ids) == 2)
        out = p.apply("def g(t):\n    return re.search(r'[0-9]+x', t)\n", (1, 2))
        self.assertEqual(out, ["def g(t):\n    return re.search(r'[0-9]*x', t)\n"])  # still a raw literal
        doc = 'def h():\n    """a+b"""\n    return 1\n'
        self.assertEqual(p.apply(doc, (1, 3)), [])  # docstrings are never edited

    def test_rewritten_window_keeps_multiline_strings_and_elif_chains(self):
        # regressions found by the DEV17 self-reproduction diagnostic (toolz interpose, semver match)
        before = 'def f(seq):\n    """Doc\n\n    more\n    """\n    x = g(seq)\n    next(x)\n    return x\n'
        after = ('def f(seq):\n    """Doc\n\n    more\n    """\n    x = g(seq)\n    try:\n        next(x)\n'
                 '    except StopIteration:\n        return iter([])\n    return x\n')
        outs = [o for p, _ in induce([(before, after, "i")]) for o in p.apply(before, (1, 8))]
        self.assertIn(norm(after), [norm(o) for o in outs])
        self.assertTrue(all('"""Doc\n\n    more\n    """' in o for o in outs))
        b2 = "def m(p, e):\n    if p == 'x':\n        v = 1\n    elif p[0] in ('<', '>'):\n        v = 2\n    else:\n        v = 3\n    return v\n"
        a2 = b2.replace("elif p[0] in", "elif p and p[0] in")
        outs = [o for p, _ in induce([(b2, a2, "j")]) for o in p.apply(b2, (1, 8))]
        self.assertIn(norm(a2), [norm(o) for o in outs])
        self.assertTrue(all(norm(o) is not None for o in outs))

    def test_decorated_definitions_and_borrowed_parentheses(self):
        # regressions: semver Version.parse (decorator duplicated), more_itertools run_length.decode (lost parentheses)
        b1 = "class C:\n    @classmethod\n    def p(cls, v):\n        return v\n"
        a1 = "class C:\n    @classmethod\n    def p(cls, v: int) -> int:\n        return v\n"
        outs = [o for p, _ in induce([(b1, a1, "k")]) for o in p.apply(b1, (2, 4))]
        self.assertIn(norm(a1), [norm(o) for o in outs])
        self.assertTrue(all(o.count("@classmethod") == 1 for o in outs))
        b2 = "def decode(it):\n    return chain.from_iterable(repeat(k, n) for k, n in it)\n"
        a2 = "def decode(it):\n    return chain.from_iterable(starmap(repeat, it))\n"
        outs = [o for p, _ in induce([(b2, a2, "l")]) for o in p.apply(b2, (1, 2))]
        self.assertIn(norm(a2), [norm(o) for o in outs])

    def test_procedure_round_trip(self):
        for p, _ in induce(POP + REGEX):
            q = Procedure.from_dict(json.loads(json.dumps(p.to_dict())))
            self.assertEqual(q.id, p.id)


class KnowledgeLifecycleTests(unittest.TestCase):
    def test_discover_corroborate_validate_preserve(self):
        kb = KnowledgeBase()
        kb.learn(POP[:1], "test")
        self.assertTrue(kb.entries and all(e.status == "candidate" for e in kb.entries.values()))
        kb.learn(POP[1:], "test")  # a second independent example of the same change
        self.assertTrue(any(e.status == "active" and len(e.support) == 2 for e in kb.entries.values()))
        held = [("def c(st, n):\n    st.pop(n)\n", "def c(st, n):\n    try:\n        st.pop(n)\n    except IndexError:\n        pass\n", "h1")]
        kb.validate(held)
        self.assertTrue(any(e.validation["hits"] == 1 for e in kb.entries.values()))
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "kb.json"
            kb.save(path)
            kb2 = KnowledgeBase.load(path)
            self.assertEqual(kb2.summary(), kb.summary())
            d = json.loads(path.read_text())
            d["body"]["entries"][0]["status"] = "active"
            d["body"]["entries"][0]["validation"]["hits"] = 99
            path.write_text(json.dumps(d))
            with self.assertRaises(ValueError):
                KnowledgeBase.load(path)

    def test_procedures_that_keep_failing_are_retired(self):
        kb = KnowledgeBase()
        kb.learn([("def d(m):\n    return m.total\n", "def d(m):\n    return getattr(m, 'total', None)\n", "g1")], "test")
        ent = next(iter(kb.entries.values()))
        for i in range(RETIRE_MIN_FIRES):
            kb.record_outcome(ent.id, False, f"p{i}")
        self.assertEqual(ent.status, "retired")
        self.assertEqual(kb.retrieve("def z(q):\n    return q.n\n", (1, 2)), [])  # retired knowledge is not used

    def test_field_success_promotes_and_a_better_procedure_supersedes(self):
        kb = KnowledgeBase()
        kb.learn(POP, "test")
        general = [e for e in kb.entries.values() if ".pop(" not in e.procedure.describe()]
        specific = [e for e in kb.entries.values() if ".pop(" in e.procedure.describe() and len(e.support) == 2]
        self.assertTrue(general and specific)
        held = [("def c(st, n):\n    st.pop(n)\n    st.add(n)\n",
                 "def c(st, n):\n    try:\n        st.pop(n)\n    except IndexError:\n        pass\n    st.add(n)\n", "h1")]
        kb.validate(held)
        # both reproduce the fix; the general one also fires on st.add(n), so it costs more and is superseded
        sup = [e for e in kb.entries.values() if e.status == "superseded"]
        self.assertTrue(sup)
        self.assertTrue(all(e.replaced_by in kb.entries for e in sup))

    def test_relearning_with_a_new_example_generalizes(self):
        kb = KnowledgeBase()
        kb.learn(REGEX[:1], "a")
        before = {e.procedure.describe() for e in kb.entries.values()}
        kb.learn(REGEX[1:], "b")
        joint = [e for e in kb.entries.values() if e.procedure.kind == "string" and len(e.support) == 2]
        self.assertTrue(joint)
        self.assertNotIn(joint[0].procedure.describe(), before)  # a NEW, more general procedure
        self.assertEqual(sorted(joint[0].sources), ["a", "b"])


class LearnedRepairTests(unittest.TestCase):
    FILES = {"m.py": "import re\n\ndef words(text):\n    return re.findall(r'[a-z]+', text) or ['']\n\n"
                     "def ident(s):\n    return bool(re.match(r'^[a-z_][a-z0-9_]+$', s))\n",
             "tests/test_m.py": "from m import ident\ndef test_one_letter(): assert ident('x')\ndef test_long(): assert ident('ab_1')\n"
                                "def test_bad(): assert not ident('1a')\n"}

    def _run(self, **kw):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for k, v in self.FILES.items():
                (root / k).parent.mkdir(parents=True, exist_ok=True)
                (root / k).write_text(v)
            return RepairWorkflow(**kw).run(root)

    def test_a_bug_no_built_in_operation_fixes_is_fixed_by_a_learned_procedure(self):
        self.assertNotEqual(self._run().status, "resolved")  # DEV16 cannot change a string
        kb = KnowledgeBase()
        kb.learn(REGEX, "test")
        d = self._run(knowledge=kb)
        self.assertEqual(d.status, "resolved", d.notes)
        st = d.steps[0]
        self.assertEqual(st["edit_family"], "learned")
        self.assertIn("[a-z0-9_]*$", st["diff"])
        self.assertTrue(st["learned_procedure"] in kb.entries)
        kb.record_outcome(st["learned_procedure"], True, "ident-regex")  # a person confirmed it: field evidence
        self.assertEqual(kb.entries[st["learned_procedure"]].field["hits"], 1)

    def test_knowledge_is_only_consulted_after_built_in_operations_fail(self):
        files = {"m.py": "def inc(x): return x - 1\n", "tests/test_m.py": "from m import inc\ndef test_inc(): assert inc(1) == 2\n"}
        kb = KnowledgeBase()
        kb.learn(REGEX, "test")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "tests").mkdir()
            for k, v in files.items():
                (root / k).write_text(v)
            d = RepairWorkflow(knowledge=kb).run(root)
        self.assertEqual(d.steps[0]["edit_family"], "single_site")


class OnlineCycleTests(unittest.TestCase):
    def test_experience_with_one_problem_solves_a_later_unfamiliar_one(self):
        """encounter -> fail -> learn from the revealed fix -> the next problem of that kind is solvable."""
        problems = [("def p1(cfg):\n    return cfg.timeout\n", "def p1(cfg):\n    return getattr(cfg, 'timeout', None)\n", "q1"),
                    ("def p2(opts):\n    return opts.retries + 1\n", "def p2(opts):\n    return getattr(opts, 'retries', None) + 1\n", "q2")]
        kb = KnowledgeBase()
        solved = []
        for before, after, pid in problems:
            outs = [o for _, progs in kb.retrieve(before, (1, before.count("\n") + 1)) for o in progs]
            solved.append(any(norm(o) == norm(after) for o in outs))
            kb.learn([(before, after, pid)], "revealed")
        self.assertEqual(solved, [False, True])


if __name__ == "__main__":
    unittest.main()


class MinerTests(unittest.TestCase):
    def test_only_small_single_function_fix_commits_become_examples(self):
        import subprocess
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "benchmarks"))
        import dev17_mine_history as M
        from asm.coding.integrity import ChainedWriter, read_records
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "toy"
            repo.mkdir()
            g = lambda *a: subprocess.run(["git", *a], cwd=repo, check=True, capture_output=True)  # noqa: E731
            g("init", "-q")
            g("config", "user.email", "t@example.invalid")
            g("config", "user.name", "t")
            (repo / "pkg").mkdir()
            src = "def f(a):\n    '''doc'''\n    return a < 3\n\ndef h(x):\n    return x\n"

            def commit(text, msg, extra=None):
                (repo / "pkg" / "m.py").write_text(text)
                if extra:
                    (repo / "pkg" / "tests").mkdir(exist_ok=True)
                    (repo / "pkg" / "tests" / "test_m.py").write_text(extra)
                g("add", "-A")
                g("commit", "-q", "-m", msg)
            commit(src, "initial")
            commit(src.replace("a < 3", "a <= 3"), "Fix boundary in f", "def test(): pass\n")     # example
            commit(src.replace("a < 3", "a <= 3").replace("'''doc'''", "'''better doc'''"), "fix docs")  # docstring only
            commit(src.replace("a < 3", "a <= 2").replace("return x", "return -x"), "fix two functions")  # two functions
            commit(src.replace("a < 3", "a > 4"), "refactor")  # no fix message
            w = ChainedWriter(Path(td) / "out.jsonl", {"run": "test"})
            counts = M.mine("toy", "unused", Path(td), w)
            _, recs = read_records(Path(td) / "out.jsonl")
        self.assertEqual(counts["examples"], 1)
        r = recs[0]
        self.assertEqual((r["qualname"], r["message"]), ("f", "Fix boundary in f"))
        self.assertIn("a < 3", r["before"])
        self.assertIn("a <= 3", r["after"])
