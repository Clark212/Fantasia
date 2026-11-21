import os
import tempfile
import textwrap
import unittest
from pathlib import Path

from asm.coding import CodeUnderstanding, CodingAgent, analyze_function, tree_fingerprint
import ast


def repo(files: dict):
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    for rel, src in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(src))
    return tmp, root


def analyze(files, **kw):
    tmp, root = repo(files)
    with tmp:
        return CodeUnderstanding(**kw).analyze(root)


def fn_report(src):
    return analyze_function(ast.parse(textwrap.dedent(src)).body[0])


def edge(r, caller, callee=None):
    return [(e.callee, e.kind, e.reason) for e in r.call_edges if e.caller == caller
            and (callee is None or e.callee == callee)]


class StructureTests(unittest.TestCase):
    def test_declarations_kinds_decorators_nested_async(self):
        r = analyze({"m.py": """
            import functools
            def top(a, *args, k=1, **kw):
                def inner(): pass
                return inner
            class C:
                @staticmethod
                def s(x): pass
                @property
                def p(self): return 1
                async def am(self): pass
        """})
        f = {x.qname: x for x in r.functions}
        self.assertEqual(f["m.top"].kind, "function")
        self.assertEqual(f["m.top"].params, ["a", "k", "args", "kw"])
        self.assertEqual(f["m.top.inner"].kind, "nested")
        self.assertEqual(f["m.C.s"].kind, "method")
        self.assertEqual(f["m.C.s"].decorators, ["staticmethod"])
        self.assertTrue(f["m.C.am"].is_async)
        self.assertEqual(r.classes[0].methods, {"s": "m.C.s", "p": "m.C.p", "am": "m.C.am"})

    def test_complexity_known_values(self):
        r = analyze({"m.py": """
            def a(x):
                return x
            def b(x, y):
                if x and y:
                    return 1
                for i in x:
                    if i: break
                else:
                    pass
                try:
                    pass
                except ValueError:
                    pass
                return [i for i in x if i]
        """})
        c = {x.name: x.complexity for x in r.functions}
        # a=1 ; b = 1 + if + and + for + for-else + if + except + comprehension(1 + 1 if) = 9
        self.assertEqual((c["a"], c["b"]), (1, 9))

    @unittest.skipUnless(__import__("importlib").util.find_spec("radon"), "radon not installed")
    def test_complexity_matches_radon_on_this_repo_sample(self):
        from radon.complexity import cc_visit
        root = Path(__file__).resolve().parents[1] / "asm" / "coding"
        r = CodeUnderstanding().analyze(root)
        mine = {(m.path, f.line): f.complexity for m in r.modules for f in r.functions if f.path == m.path}
        checked = 0
        for m in r.modules:
            for b in cc_visit((root / m.path).read_text()):
                if getattr(b, "closures", None) or (m.path, b.lineno) not in mine:
                    continue
                self.assertEqual(mine[(m.path, b.lineno)], b.complexity, (m.path, b.name))
                checked += 1
        self.assertGreater(checked, 40)


class CallGraphTests(unittest.TestCase):
    FILES = {
        "pkg/__init__.py": "",
        "pkg/base.py": """
            class Base:
                def __init__(self): self.x = 1
                def shared(self): return self.x
        """,
        "pkg/util.py": """
            def helper(): return 1
            def other(): return helper()
        """,
        "pkg/main.py": """
            from .base import Base
            from . import util
            import pkg.util as u
            from .util import helper as h

            class Child(Base):
                def __init__(self):
                    super().__init__()
                def run(self):
                    self.shared()
                    self.missing()
                    return self.local()
                def local(self): return util.helper()
                def sibling(self): return 1
                def bare(self):
                    return sibling()

            def go(cb):
                c = Child()
                c.run()
                u.other()
                h()
                cb()
                len([])
                unknown_fn()
                os_thing.path.join("a")

            def fact(n):
                def walk(m):
                    return walk(m - 1) if m else 0
                return walk(n) + fact(n - 1)
        """,
    }

    def test_resolution_matrix(self):
        r = analyze(self.FILES)
        self.assertEqual(edge(r, "pkg.main.go", "pkg.main.Child.__init__"), [("pkg.main.Child.__init__", "constructor", None)])
        self.assertIn(("pkg.main.Child.run", "inferred_receiver", None), edge(r, "pkg.main.go"))
        self.assertIn(("pkg.util.other", "module_member", None), edge(r, "pkg.main.go"))
        self.assertIn(("pkg.util.helper", "direct", None), edge(r, "pkg.main.go"))  # alias `h`
        self.assertIn((None, "direct", "local_callable"), edge(r, "pkg.main.go"))  # parameter cb
        self.assertIn((None, "direct", "builtin"), edge(r, "pkg.main.go"))
        self.assertIn((None, "direct", "unknown_name"), edge(r, "pkg.main.go"))
        self.assertIn((None, "method", "dynamic_receiver"), edge(r, "pkg.main.go"))
        # inherited method through a relative import, and super()
        self.assertIn(("pkg.base.Base.shared", "method", None), edge(r, "pkg.main.Child.run"))
        self.assertIn(("pkg.base.Base.__init__", "super", None), edge(r, "pkg.main.Child.__init__"))
        self.assertIn((None, "method", "attribute_not_found_in_class_hierarchy"), edge(r, "pkg.main.Child.run"))
        self.assertIn(("pkg.util.helper", "module_member", None), edge(r, "pkg.main.Child.local"))

    def test_bare_name_in_method_never_resolves_to_sibling_method(self):
        r = analyze(self.FILES)
        # regression: `sibling()` inside a method is NOT self.sibling()
        self.assertEqual(edge(r, "pkg.main.Child.bare"), [(None, "direct", "unknown_name")])

    def test_nested_and_direct_recursion_resolve(self):
        r = analyze(self.FILES)
        self.assertIn(("pkg.main.fact.walk", "direct", None), edge(r, "pkg.main.fact.walk"))
        self.assertIn(("pkg.main.fact.walk", "direct", None), edge(r, "pkg.main.fact"))
        self.assertIn(("pkg.main.fact", "direct", None), edge(r, "pkg.main.fact"))
        self.assertIn(["pkg.main.fact"], r.recursion_groups)
        self.assertIn(["pkg.main.fact.walk"], r.recursion_groups)

    def test_mutual_recursion_group(self):
        r = analyze({"m.py": "def a(): return b()\ndef b(): return c()\ndef c(): return a()\ndef d(): return a()\n"})
        self.assertEqual(r.recursion_groups, [["m.a", "m.b", "m.c"]])

    def test_queries_callers_callees_transitive(self):
        r = analyze({"m.py": "def a(): b()\ndef b(): c()\ndef c(): pass\ndef lone(): pass\n"})
        self.assertEqual(r.callees("m.a"), ["m.b"])
        self.assertEqual(r.callees("m.a", transitive=True), ["m.b", "m.c"])
        self.assertEqual(r.callers("m.c", transitive=True), ["m.a", "m.b"])
        self.assertEqual(r.callers("m.c"), ["m.b"])
        self.assertEqual(r.unreferenced_functions(), ["m.a", "m.lone"])

    def test_module_level_calls_are_attributed_to_module(self):
        r = analyze({"m.py": "def main(): pass\nmain()\n"})
        self.assertEqual(edge(r, "m.<module>"), [("m.main", "direct", None)])
        self.assertEqual(r.unreferenced_functions(), [])


class ModuleGraphTests(unittest.TestCase):
    def test_edges_relative_imports_and_impact(self):
        r = analyze({"p/__init__.py": "", "p/a.py": "from .b import x\n", "p/b.py": "from . import c\n",
                     "p/c.py": "X = 1\n", "p/d.py": "import p.c\n"})
        self.assertEqual(r.module_edges, [("p.a", "p.b"), ("p.b", "p.c"), ("p.d", "p.c")])
        self.assertEqual(r.impacted_modules("p/c.py"), ["p.a", "p.b", "p.d"])
        self.assertEqual(r.impacted_modules("p.a"), [])

    def test_package_init_reexport_is_not_a_cycle_but_symbol_import_is_a_dependency(self):
        r = analyze({"p/__init__.py": "from .a import A\n", "p/a.py": "from . import b\nclass A: pass\n",
                     "p/b.py": "X = 1\n",
                     "r/__init__.py": "def helper(): pass\n", "r/m.py": "from r import helper\n"})
        self.assertEqual(r.module_cycles, [])
        self.assertIn(("p.a", "p.b"), r.module_edges)
        self.assertNotIn(("p.a", "p"), r.module_edges)   # `from . import b` takes a submodule only
        self.assertIn(("r.m", "r"), r.module_edges)       # `from r import helper` reads r's namespace

    def test_genuine_package_level_cycle_is_still_reported(self):
        r = analyze({"p/__init__.py": "from .a import A\n", "p/a.py": "from . import b\nclass A: pass\n",
                     "p/b.py": "from p import A\n"})
        self.assertEqual(r.module_cycles, [["p", "p.a", "p.b"]])

    def test_import_time_vs_lazy_vs_type_checking_cycles(self):
        r = analyze({
            "hard_a.py": "import hard_b\n", "hard_b.py": "import hard_a\n",
            "lazy_a.py": "import lazy_b\n", "lazy_b.py": "def f():\n    import lazy_a\n",
            "tc_a.py": "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import tc_b\n", "tc_b.py": "import tc_a\n"})
        self.assertEqual(r.module_cycles, [["hard_a", "hard_b"]])
        self.assertEqual(sorted(r.lazy_module_cycles), [["lazy_a", "lazy_b"], ["tc_a", "tc_b"]])


class DataFlowTests(unittest.TestCase):
    def test_maybe_and_definitely_unbound(self):
        r = fn_report("""
            def f(a):
                if a:
                    x = 1
                print(x)
                print(never)
                never = 2
        """)
        got = {(d["name"], d["definitely"]) for d in r["maybe_unbound"]}
        self.assertEqual(got, {("x", False), ("never", True)})

    def test_try_finally_has_no_false_unbound_or_unreachable(self):
        r = fn_report("""
            def f():
                try:
                    x = 1
                    return x
                finally:
                    cleanup()
        """)
        self.assertEqual((r["maybe_unbound"], r["unreachable_lines"]), ([], []))
        r = fn_report("""
            def g():
                try:
                    x = compute()
                finally:
                    cleanup()
                return x
        """)
        self.assertEqual(r["maybe_unbound"], [])

    def test_try_except_genuinely_maybe_unbound(self):
        r = fn_report("""
            def f():
                try:
                    x = compute()
                except ValueError:
                    log()
                return x
        """)
        self.assertEqual([d["name"] for d in r["maybe_unbound"]], ["x"])

    def test_dead_and_overwritten_stores(self):
        r = fn_report("""
            def f():
                a = 1
                a = 2
                b = 3
                _ignored = 4
                x, y = pair()
                for i in range(3): pass
                return a
        """)
        self.assertEqual([(d["name"], d["line"]) for d in r["dead_stores"]], [("a", 3), ("b", 5)])

    def test_closure_nonlocal_and_late_binding_are_not_dead(self):
        r = fn_report("""
            def f():
                counter = 0
                def bump():
                    nonlocal counter
                    counter += 1
                late = None
                def g(): return late
                late = 5
                bump()
                return g
        """)
        self.assertEqual(r["dead_stores"], [])
        self.assertEqual(r["maybe_unbound"], [])

    def test_dynamic_scope_suppresses_dead_store_reports(self):
        r = fn_report("def f():\n    secret = 1\n    return locals()\n")
        self.assertTrue(r["dynamic_scope"])
        self.assertEqual(r["dead_stores"], [])

    def test_augassign_walrus_with_match(self):
        r = fn_report("""
            def f(items, cmd):
                total = 0
                for it in items:
                    total += it
                if (n := len(items)) > 2:
                    pass
                with open("f") as fh:
                    pass
                match cmd:
                    case [first, *rest]:
                        return first
                    case _:
                        pass
                return total
        """)
        dead = {d["name"] for d in r["dead_stores"]}
        self.assertEqual(dead, {"n"})  # walrus value never read; total/first used; with/rest not reported kinds
        self.assertEqual(r["maybe_unbound"], [])

    def test_control_flow_unreachable_code(self):
        r = fn_report("""
            def f(xs):
                for x in xs:
                    continue
                    skipped = 1
                while True:
                    pass
                after_loop = 1
        """)
        self.assertEqual(r["unreachable_lines"], [5, 8])

    def test_while_true_with_break_and_loop_else(self):
        r = fn_report("""
            def f(xs):
                while True:
                    if xs: break
                done = 1
                for x in xs:
                    if x: break
                else:
                    never_when_break = 1
                return done
        """)
        self.assertEqual(r["unreachable_lines"], [])

    def test_returns_raises_counted_and_use_def_chain(self):
        tmp, root = repo({"m.py": "def f(c):\n    x = 1\n    if c:\n        x = 2\n    if c is None:\n        raise ValueError\n    return x\n"})
        with tmp:
            rep = CodeUnderstanding().analyze(root)
        f = rep._fn("m.f")
        self.assertEqual((f.returns, f.raises), (1, 1))
        chain = [u for u in rep.use_def("m.f") if u["name"] == "x"]
        self.assertEqual(chain, [{"name": "x", "line": 7, "defs": [2, 4]}])

    def test_huge_function_dataflow_skipped_not_wrong(self):
        body = "\n".join(f"    v{i} = {i}" for i in range(50))
        r = analyze({"m.py": f"def big():\n{body}\n    return 0\n"}, max_cfg_nodes=20)
        f = r.functions[0]
        self.assertEqual((f.dataflow, f.dead_stores), ("skipped_too_large", []))


class ClassTests(unittest.TestCase):
    def test_hierarchy_and_attribute_flow(self):
        r = analyze({"m.py": """
            class A:
                shared = 1
                def __init__(self): self.a = 1
                def read(self): return self.a + self.ghost + self.shared
            class B(A):
                def write(self): self.b = 2
                def use(self): return self.b + self.read()
            class E(Unknown):
                def f(self): return self.mystery
        """})
        c = {x.name: x for x in r.classes}
        self.assertEqual(c["B"].resolved_bases, ["m.A"])
        self.assertEqual(c["E"].external_bases, ["Unknown"])
        self.assertEqual(c["A"].attribute_flow["a"], {"writers": ["__init__"], "readers": ["read"]})
        self.assertEqual(c["A"].read_never_written, ["ghost"])
        self.assertEqual(c["B"].read_never_written, [])      # b is written; others inherited
        self.assertEqual(c["E"].read_never_written, [])      # external base: unknowable, so silent


class RobustnessTests(unittest.TestCase):
    def test_syntax_error_and_bad_encoding_do_not_stop_analysis(self):
        tmp, root = repo({"ok.py": "def f(): pass\n", "bad.py": "def (:\n"})
        (root / "latin.py").write_bytes(b"x = '\xff\xfe'\n")
        with tmp:
            r = CodeUnderstanding().analyze(root)
        codes = sorted(d["path"] for d in r.diagnostics if d["code"] == "parse_error")
        self.assertEqual(codes, ["bad.py", "latin.py"])
        self.assertEqual([f.qname for f in r.functions], ["ok.f"])
        self.assertEqual(r.stats["parsed_modules"], 1)

    def test_never_executes_project_code(self):
        tmp, root = repo({"evil.py": f"open({str(Path(tempfile.gettempdir()) / 'asm_dev9_pwned')!r}, 'w').write('x')\n"})
        flag = Path(tempfile.gettempdir()) / "asm_dev9_pwned"
        flag.unlink(missing_ok=True)
        with tmp:
            CodeUnderstanding().analyze(root)
        self.assertFalse(flag.exists())

    def test_symlinks_and_excluded_dirs_skipped_and_limits_reported(self):
        tmp, root = repo({"a.py": "def a(): pass\n", ".venv/x.py": "def x(): pass\n", "node_modules/y.py": "def y(): pass\n"})
        outside = Path(tempfile.mkdtemp()) / "out.py"
        outside.write_text("def secret(): pass\n")
        os.symlink(outside, root / "link.py")
        (root / "big.py").write_text("x = 1\n" * 100)
        with tmp:
            r = CodeUnderstanding(max_file_bytes=200).analyze(root)
            self.assertEqual([f.qname for f in r.functions], ["a.a"])
            self.assertIn("file_too_large", [d["code"] for d in r.diagnostics])
            r2 = CodeUnderstanding(max_files=1).analyze(root)
            self.assertIn("file_limit", [d["code"] for d in r2.diagnostics])

    def test_deterministic_and_non_mutating(self):
        tmp, root = repo({"a.py": "def a(): b()\ndef b(): a()\n", "p/__init__.py": "", "p/c.py": "import a\n"})
        with tmp:
            before = tree_fingerprint(root)
            d1 = CodeUnderstanding().analyze(root).to_dict()
            d2 = CodeUnderstanding().analyze(root).to_dict()
            self.assertEqual(d1, d2)
            self.assertEqual(tree_fingerprint(root), before)

    def test_agent_entry_point(self):
        tmp, root = repo({"a.py": "def a(): pass\n"})
        with tmp:
            self.assertEqual(CodingAgent().understand(root).stats["functions"], 1)


if __name__ == "__main__":
    unittest.main()
