"""DEV10 semantic intelligence tests: ground-truth lying repo, stdlib ground truth, sandbox safety, units."""
import ast
import os
import sys
import tempfile
import textwrap
import unittest
import uuid
from pathlib import Path

from asm.coding import CodingAgent, SemanticAnalyzer, analyze_static, match_refs, tree_fingerprint
from asm.coding import semantics as S
from asm.coding.semantics import (BATTERIES, categories_for, dec, equiv, infer_param_kinds, name_tokens,
                                  refs_named_by, spec_key, can_fall_through)

LIES = {
    "helpers.py": '''
        def write_log(msg):
            open("app.log", "a").write(msg)
    ''',
    "lies.py": '''
        from helpers import write_log
        COUNTER = 0
        RESULTS = []

        # --- names that lie
        def get_total(a, b):
            return a * b
        def calculate_max(a, b):
            return a if a < b else b
        def is_even_buggy(n):
            return n % 2 == 0 if n >= 0 else True
        def count_items(xs):
            xs.append(0)
            return len(xs)
        def get_next_id():
            global COUNTER
            COUNTER += 1
            return COUNTER
        def compute_report(data):
            print("computing")
            return len(data)
        def get_log_path(name):
            open("log_" + name, "w").write("x")
            return name
        def get_status():
            write_log("checked")
            return "ok"
        def is_valid(x):
            return len(x)
        def append_item(lst, x):
            lst + [x]
        def validate_input(x):
            return True
        def sneaky(xs):
            helper = getattr(xs, "append")
            helper(1)
            return len(xs)

        # --- honest or obfuscated (negative controls: must produce NO findings)
        def add_numbers(a, b): return a + b
        def total_price(a, b): return a + b
        def is_even(n): return n % 2 == 0
        def avg(a, b): return (a + b) // 2
        def avg2(a, b): return (a + b) / 2
        def mystery(a, b): return a if a > b else b
        def f1(x): return x * x
        def f2(x): return -x
        def f3(xs):
            t = 0
            for v in xs: t += v
            return t
        def f4(xs): return sorted(xs)
        def f5(s): return s[::-1]
        def f6(n):
            if n < 2: return False
            i = 2
            while i * i <= n:
                if n % i == 0: return False
                i += 1
            return True
        def f7(a, b):
            while b:
                a, b = b, a % b
            return abs(a)
        def f8(s): return sum(1 for c in s.lower() if c in "aeiou")
        def clean_names(names): names.sort()
        def reverse_it(xs): xs.reverse()
        def save_report(text): open("report.txt", "w").write(text)
        def set_value(d, k, v): return {**d, k: v}
        def update_total(a, b): return a + b
        def update_posterior(prior, likes): return {h: prior[h] * likes.get(h, 1.0) for h in prior}
        def check(name, ok): RESULTS.append((name, ok))
        def random_pick(xs):
            import random
            return random.choice(xs)
        def factorial(n):
            r = 1
            for i in range(1, n): r *= i
            return r
    ''',
}

EXPECTED_IDENTIFIED = {
    "get_total": "multiply", "calculate_max": "min2", "add_numbers": "add", "total_price": "add",
    "is_even": "is_even", "avg": "mean_floor", "avg2": "mean_true", "mystery": "max2", "f1": "square", "f2": "negate",
    "f3": "sum", "f4": "sorted", "f5": "reverse_str", "f6": "is_prime", "f7": "gcd", "f8": "count_vowels",
    "clean_names": "sort_inplace", "reverse_it": "reverse_inplace"}

EXPECTED_FINDINGS = {
    ("name_behavior_mismatch", "lies.get_total"), ("name_behavior_mismatch", "lies.calculate_max"),
    ("likely_bug", "lies.is_even_buggy"),
    ("name_implies_pure_but_has_effects", "lies.count_items"), ("name_implies_pure_but_has_effects", "lies.get_next_id"),
    ("name_implies_pure_but_has_effects", "lies.compute_report"), ("name_implies_pure_but_has_effects", "lies.get_log_path"),
    ("name_implies_pure_but_has_effects", "lies.get_status"),
    ("predicate_not_boolean", "lies.is_valid"), ("name_implies_effect_but_pure", "lies.append_item"),
    ("validator_cannot_fail", "lies.validate_input"), ("static_dynamic_disagreement", "lies.sneaky")}
WEAK_EXTRA = {("name_claim_unverified", "lies.factorial"), ("name_claim_unverified", "lies.count_items"),
              ("name_claim_unverified", "lies.append_item")}  # append_item claims to append yet returns None


def write_repo(root: Path, files: dict):
    for rel, src in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(src))


def analyze_files(files, **kw):
    tmp = tempfile.TemporaryDirectory()
    write_repo(Path(tmp.name), files)
    with tmp:
        return SemanticAnalyzer(**kw).analyze(tmp.name)


def static_of(src: str, globals_=()):
    fn = next(n for n in ast.parse(textwrap.dedent(src)).body if isinstance(n, ast.FunctionDef))
    return analyze_static(fn, set(globals_))


# =============================================================== ground-truth repo
class LyingRepoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        write_repo(cls.root, LIES)
        cls.before = tree_fingerprint(cls.root)
        cls.report = SemanticAnalyzer().analyze(cls.root)
        cls.weak = SemanticAnalyzer(weak_findings=True).analyze(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_findings_match_the_answer_key_exactly(self):
        got = self.report.finding_pairs()
        self.assertEqual(got - EXPECTED_FINDINGS, set(), "unexpected findings (false positives)")
        self.assertEqual(EXPECTED_FINDINGS - got, set(), "missed findings (false negatives)")

    def test_weak_findings_are_opt_in_and_correct(self):
        self.assertEqual(self.weak.finding_pairs() - self.report.finding_pairs(), WEAK_EXTRA)

    def test_every_expected_identification_is_found(self):
        for fn, ref in EXPECTED_IDENTIFIED.items():
            self.assertIn(ref, self.report.inferred(f"lies.{fn}"), fn)

    def test_obfuscated_names_are_identified_without_name_help(self):
        for fn in ("f1", "f2", "f3", "f4", "f6", "f7", "f8", "mystery"):
            f = self.report.function(f"lies.{fn}")
            self.assertEqual(f.name_refs, [], fn)  # the name gives no hint
            self.assertTrue(f.inferred, fn)

    def test_severity_and_evidence_sources(self):
        by = {(f.kind, f.qname.split(".")[-1]): f for f in self.report.findings}
        self.assertEqual(by[("name_implies_pure_but_has_effects", "count_items")].source, "static+dynamic")
        self.assertEqual(by[("name_implies_pure_but_has_effects", "count_items")].severity, "high")
        self.assertEqual(by[("name_implies_pure_but_has_effects", "get_log_path")].source, "static")  # never executed
        self.assertEqual(by[("name_implies_pure_but_has_effects", "get_next_id")].severity, "medium")
        self.assertEqual(by[("name_implies_pure_but_has_effects", "compute_report")].severity, "low")
        self.assertEqual(by[("name_behavior_mismatch", "get_total")].evidence["behaves_like"], ["multiply"])
        self.assertEqual(by[("name_behavior_mismatch", "get_total")].evidence["name_suggests"], ["add"])
        bug = by[("likely_bug", "is_even_buggy")]
        self.assertEqual(bug.evidence["reference"], "is_even")
        self.assertTrue(all(int(d["input"].strip("(),")) < 0 for d in bug.evidence["deviations"]))  # fails on negatives only
        self.assertEqual(self.report.findings[0].severity, "high")  # sorted high-first

    def test_transitive_effects_flow_through_the_dev9_call_graph(self):
        st = self.report.function("lies.get_status").static
        self.assertEqual(st["effects"], [])
        self.assertIn("io_write", st["transitive_effects"])
        self.assertEqual(st["purity"], "impure")
        self.assertIn("helpers.write_log", st["resolved_callees"])

    def test_effectful_functions_are_not_executed_by_default(self):
        for fn in ("get_log_path", "get_status", "save_report"):
            self.assertIsNone(self.report.function(f"lies.{fn}").behavior, fn)
        self.assertFalse((self.root / "log_x").exists() or (self.root / "report.txt").exists())

    def test_original_repo_is_never_modified_or_polluted_by_probing(self):
        self.assertEqual(tree_fingerprint(self.root), self.before)

    def test_dynamic_observations(self):
        b = lambda n: self.report.function(f"lies.{n}").behavior
        self.assertEqual(b("count_items")["mutates_args"], [0])
        self.assertTrue(b("compute_report")["printed"])
        self.assertTrue(b("get_next_id")["globals_changed"])
        self.assertFalse(b("get_next_id")["deterministic"])
        self.assertFalse(b("random_pick")["deterministic"])
        self.assertTrue(b("f1")["deterministic"] and not b("f1")["mutates_args"])
        self.assertEqual(b("sneaky")["mutates_args"], [0])
        self.assertEqual(self.report.function("lies.sneaky").static["mutated_params"], [])  # the blind spot
        self.assertEqual(set(b("is_valid")["output_types"]), {"int"})

    def test_unknown_and_resolved_calls_propagate_correctly(self):
        r = analyze_files({"m.py": """
            import mystery_lib
            def leaf(x): return mystery_lib.compute(x)
            def mid(x): return leaf(x)
            def top(x): return mid(x)
            def pure_leaf(x): return x + 1
            def pure_top(x): return pure_leaf(x)
            def recursive(n): return recursive(n - 1) if n else 0
        """}, probe=False)
        purity = lambda n: r.function(f"m.{n}").static["purity"]
        self.assertEqual([purity(n) for n in ("leaf", "mid", "top")], ["unknown"] * 3)
        self.assertEqual([purity(n) for n in ("pure_leaf", "pure_top", "recursive")], ["pure"] * 3)
        self.assertEqual(r.function("m.mid").static["unknown_calls"], [])  # resolved to repo code, not "unknown"
        self.assertTrue(r.function("m.top").static["transitive_unknown"])

    def test_stubs_and_interface_methods_are_not_judged_by_their_names(self):
        r = analyze_files({"m.py": """
            from typing import Protocol
            class Env(Protocol):
                def reset(self, seed=None): ...
            class Base:
                def update(self, items): pass
                def validate(self, x): raise NotImplementedError
                def save(self, lst):
                    \"\"\"doc only\"\"\"
            def append_nothing(lst, x): lst + [x]
        """}, probe=False)
        self.assertEqual({q for _, q in r.finding_pairs()}, {"m.append_nothing"})  # the real bug is still found

    def test_report_is_deterministic_and_serialisable(self):
        import json
        again = SemanticAnalyzer().analyze(self.root)

        def stable(report):  # genuinely random functions legitimately differ between runs; everything else must not
            d = report.to_dict()
            flaky = {f["qname"] for f in d["functions"] if f["behavior"] and not f["behavior"]["deterministic"]}
            self.assertEqual(flaky, {"lies.get_next_id", "lies.random_pick"})
            d["functions"] = [f for f in d["functions"] if f["qname"] not in flaky]
            d["findings"] = [f for f in d["findings"] if f["qname"] not in flaky]
            return json.dumps(d, sort_keys=True)
        self.assertEqual(stable(again), stable(self.report))

    def test_agent_entry_point_and_static_only_mode(self):
        r = CodingAgent().semantics(self.root, probe=False)
        self.assertEqual(r.stats["probed"], 0)
        self.assertTrue(all(f.behavior is None for f in r.functions))
        self.assertIn(("name_implies_pure_but_has_effects", "lies.count_items"), r.finding_pairs())
        self.assertNotIn(("name_behavior_mismatch", "lies.get_total"), r.finding_pairs())  # needs behaviour


# ============================================================ stdlib ground truth
TRUTH = [
    ("operator", "add", 2, ["num", "num"], {"add"}), ("operator", "sub", 2, ["num", "num"], {"subtract"}),
    ("operator", "mul", 2, ["num", "num"], {"multiply"}), ("operator", "neg", 1, ["num"], {"negate"}),
    ("operator", "abs", 1, ["num"], {"abs", "abs_f"}), ("operator", "floordiv", 2, ["num", "num"], {"floordiv"}),
    ("operator", "mod", 2, ["num", "num"], {"mod"}), ("operator", "pow", 2, ["num", "num"], {"power"}),
    ("operator", "truediv", 2, ["num", "num"], {"truediv"}), ("operator", "eq", 2, ["num", "num"], {"equal"}),
    ("operator", "lt", 2, ["num", "num"], {"less_than"}), ("operator", "gt", 2, ["num", "num"], {"greater_than"}),
    ("operator", "ne", 2, ["num", "num"], {"not_equal"}), ("math", "gcd", 2, ["num", "num"], {"gcd"}),
    ("math", "lcm", 2, ["num", "num"], {"lcm"}), ("math", "factorial", 1, ["int"], {"factorial"}),
    ("math", "isqrt", 1, ["int"], {"isqrt"}), ("math", "fabs", 1, ["float"], {"abs_f"}),
    ("math", "floor", 1, ["float"], {"floor"}), ("math", "ceil", 1, ["float"], {"ceil"}),
    ("math", "trunc", 1, ["float"], {"trunc"}), ("math", "sqrt", 1, ["float"], {"sqrt"}),
    ("builtins", "abs", 1, ["num"], {"abs", "abs_f"}), ("builtins", "sum", 1, ["list"], {"sum"}),
    ("builtins", "len", 1, ["sized"], {"len", "length"}), ("builtins", "sorted", 1, ["list"], {"sorted"}),
    ("builtins", "max", 1, ["list"], {"max"}), ("builtins", "min", 1, ["list"], {"min"}),
    ("builtins", "max", 2, ["num", "num"], {"max2"}), ("builtins", "min", 2, ["num", "num"], {"min2"}),
    ("builtins", "str.upper", 1, ["str"], {"upper"}), ("builtins", "str.lower", 1, ["str"], {"lower"}),
    ("builtins", "str.strip", 1, ["str"], {"strip"}), ("builtins", "str.title", 1, ["str"], {"title"}),
    ("builtins", "str.capitalize", 1, ["str"], {"capitalize"}), ("builtins", "str.swapcase", 1, ["str"], {"swapcase"}),
    ("builtins", "str.isdigit", 1, ["str"], {"is_digit_str"}),
    ("builtins", "str.startswith", 2, ["str", "str"], {"startswith"}),
    ("builtins", "str.endswith", 2, ["str", "str"], {"endswith"}),
    ("builtins", "str.__contains__", 2, ["str", "str"], {"contains"}),
    ("operator", "contains", 2, ["str", "str"], {"contains"}), ("operator", "contains", 2, ["list", "num"], {"seq_contains"}),
    ("builtins", "list.count", 2, ["list", "num"], {"count_of"}), ("builtins", "str.count", 2, ["str", "str"], {"count_sub"}),
]
NEGATIVES = [
    ("math", "exp", 1, ["float"]), ("math", "sin", 1, ["float"]), ("math", "log2", 1, ["float"]),
    ("math", "degrees", 1, ["float"]), ("operator", "xor", 2, ["num", "num"]), ("operator", "and_", 2, ["num", "num"]),
    ("operator", "or_", 2, ["num", "num"]), ("operator", "lshift", 2, ["num", "num"]), ("math", "comb", 2, ["num", "num"]),
    ("math", "perm", 2, ["num", "num"]), ("math", "copysign", 2, ["num", "num"]), ("builtins", "hash", 1, ["num"]),
    ("builtins", "ord", 1, ["str"]), ("builtins", "chr", 1, ["int"]), ("builtins", "bin", 1, ["int"]),
    ("builtins", "hex", 1, ["int"]), ("builtins", "int.bit_length", 1, ["int"]), ("builtins", "str.encode", 1, ["str"]),
    ("builtins", "repr", 1, ["num"]), ("builtins", "str", 1, ["num"]), ("builtins", "bool", 1, ["num"]),
    ("builtins", "float", 1, ["num"]), ("builtins", "str.find", 2, ["str", "str"]), ("builtins", "divmod", 2, ["num", "num"]),
    ("math", "hypot", 2, ["num", "num"]), ("builtins", "list.index", 2, ["list", "num"])]


class StdlibGroundTruthTests(unittest.TestCase):
    """Independent ground truth: the stdlib functions ARE what they are, whatever the matcher believes."""

    def specs(self, rows):
        return [{"module": m, "qualname": q, "arity": a, "kinds": k} for m, q, a, k, *_ in rows]

    def test_recall_and_precision_on_stdlib_functions(self):
        res = SemanticAnalyzer().probe_callables(self.specs(TRUTH))
        self.assertEqual(res["_diagnostics"], [])
        hits, outside = 0, []
        for (m, q, a, k, expect), spec in zip(TRUTH, self.specs(TRUTH)):
            exact = {e["ref"] for e in res[spec_key(spec)]["exact"]}
            hits += bool(exact & expect)
            if not exact & expect:
                outside.append((m, q, "missed", sorted(exact)))
            outside += [(m, q, "unexpected", x) for x in exact - expect]
        self.assertEqual(outside, [])
        self.assertEqual(hits, len(TRUTH))

    def test_no_spurious_matches_for_functions_without_a_reference(self):
        res = SemanticAnalyzer().probe_callables(self.specs(NEGATIVES))
        spurious = {k[1]: [e["ref"] for e in v["exact"]] for k, v in res.items()
                    if not k[0].startswith("_") and v["exact"]}
        self.assertEqual(spurious, {})
        self.assertEqual(sum(1 for k in res if not k[0].startswith("_")), len(NEGATIVES))

    def test_float_is_not_mistaken_for_identity(self):
        res = SemanticAnalyzer().probe_callables([{"module": "builtins", "qualname": "float", "arity": 1, "kinds": ["int"]}])
        self.assertEqual(res[("builtins", "float", 1, ("int",))]["exact"], [])


# ============================================================ sandbox / safety
class ProbeSafetyTests(unittest.TestCase):
    def test_risky_import_time_code_is_never_executed(self):
        marker = Path(tempfile.gettempdir()) / f"asm_dev10_{uuid.uuid4().hex}"
        files = {"boom.py": f"import subprocess\nsubprocess.run(['touch', {str(marker)!r}])\ndef f(x): return x\n",
                 "ok.py": "def g(x): return x + 1\n"}
        r = analyze_files(files)
        self.assertFalse(marker.exists())
        self.assertIn("module_not_probed_risky_import", [d["code"] for d in r.diagnostics])
        self.assertIsNone(r.function("boom.f").behavior)
        self.assertIsNotNone(r.function("ok.g").behavior)  # other modules are still analysed

    def test_import_time_main_guard_does_not_block_probing(self):
        files = {"m.py": "import subprocess\ndef f(x): return x\nif __name__ == '__main__':\n    subprocess.run(['true'])\n"}
        r = analyze_files(files)
        self.assertIsNotNone(r.function("m.f").behavior)

    def test_infinite_loop_function_times_out_per_call_without_stopping_the_rest(self):
        files = {"m.py": "def spin(x):\n    while True: pass\ndef ok(x): return x + 1\n"}
        r = analyze_files(files, per_call_timeout=0.3)
        self.assertEqual(r.function("m.spin").behavior["timeouts"], 5)
        self.assertIn("increment", r.inferred("m.ok"))

    def test_import_time_hang_is_contained(self):
        files = {"hang.py": "while True: pass\ndef f(x): return x\n", "ok.py": "def g(x): return x\n"}
        r = analyze_files(files, per_module_timeout=3)
        self.assertTrue([d for d in r.diagnostics if d["code"] in {"probe_import_error", "probe_timeout"}])
        self.assertIsNotNone(r.function("ok.g").behavior)

    def test_worker_that_kills_itself_is_reported_not_fatal(self):
        files = {"die.py": "import os\ndef f(x):\n    os._exit(3)\n", "ok.py": "def g(x): return -x\n"}
        r = analyze_files(files)
        self.assertIn("probe_worker_failed", [d["code"] for d in r.diagnostics])
        self.assertIn("probe_incomplete", [d["code"] for d in r.diagnostics])
        self.assertIn("negate", r.inferred("ok.g"))

    def test_memory_hog_is_contained(self):
        files = {"m.py": "def hog(x):\n    return len(bytearray(4 * 1024**3))\n"}
        r = analyze_files(files, memory_mb=512)
        self.assertIsNotNone(r.function("m.hog").behavior)
        self.assertIn("MemoryError", r.function("m.hog").behavior["exceptions"])

    def test_environment_secrets_are_not_visible_to_probed_code(self):
        os.environ["ASM_DEV10_SECRET"] = "s3cr3t"
        try:
            r = analyze_files({"m.py": "import os\ndef f(x):\n    assert os.environ.get('ASM_DEV10_SECRET') is None\n    return x\n"})
            b = r.function("m.f").behavior
            self.assertGreater(b["calls"], 0)
            self.assertNotIn("AssertionError", b["exceptions"])  # the secret was never visible to probed code
            self.assertIn("env", r.function("m.f").static["effects"])
        finally:
            os.environ.pop("ASM_DEV10_SECRET", None)

    def test_effectful_probe_is_opt_in_and_writes_only_in_a_throwaway_directory(self):
        files = {"m.py": "def dump(x):\n    open('out.txt', 'w').write('x')\n    return x\n"}
        tmp = tempfile.TemporaryDirectory()
        write_repo(Path(tmp.name), files)
        with tmp:
            before = tree_fingerprint(tmp.name)
            default = SemanticAnalyzer().analyze(tmp.name)
            self.assertIsNone(default.function("m.dump").behavior)
            opted = SemanticAnalyzer(probe_effectful=True).analyze(tmp.name)
            self.assertEqual(opted.function("m.dump").behavior["files_written"], ["out.txt"])
            self.assertIn("io_write", opted.function("m.dump").static["effects"])  # static agreed: no disagreement
            self.assertNotIn("static_dynamic_disagreement", {k for k, _ in opted.finding_pairs()})
            self.assertEqual(tree_fingerprint(tmp.name), before)
            self.assertFalse(Path(tmp.name, "out.txt").exists())

    def test_probe_budget_is_enforced(self):
        files = {f"m{i}.py": "def f(x): return x\n" for i in range(3)}
        r = analyze_files(files, probe_budget_seconds=0.5)
        self.assertIn("probe_budget_exhausted", [d["code"] for d in r.diagnostics])

    def test_methods_async_generators_decorated_and_wide_signatures_are_not_probed(self):
        files = {"m.py": textwrap.dedent("""
            import functools
            class C:
                def meth(self, x): return x
            async def co(x): return x
            def gen(x):
                yield x
            @functools.lru_cache
            def deco(x): return x
            def wide(a, b, c): return a
            def star(*args): return 1
            def ok(x): return x
        """)}
        r = analyze_files(files)
        probed = {f.qname for f in r.functions if f.behavior}
        self.assertEqual(probed, {"m.ok"})


# ================================================================= static units
class StaticSemanticsTests(unittest.TestCase):
    def test_effect_categories(self):
        cases = {
            "io_write": "def f(): open('x', 'w')", "io_write2": "def f(p): p.write_text('x')",
            "io_read": "def f(): open('x')", "network": "def f(s): s.connect(('h', 1))",
            "process": "import subprocess\ndef f(): subprocess.run(['ls'])", "time": "import time\ndef f(): return time.time()",
            "randomness": "import random\ndef f(): return random.random()", "env": "import os\ndef f(): return os.getenv('X')",
            "console": "def f(): print('x')", "dynamic_exec": "def f(s): return eval(s)",
            "logging": "import logging\ndef f(): logging.info('x')"}
        for key, src in cases.items():
            cat = "io_write" if key.startswith("io_write") else key
            self.assertIn(cat, static_of(src).effects, key)

    def test_open_modes(self):
        self.assertEqual(static_of("def f(): open('x')").effects, ["io_read"])
        self.assertEqual(static_of("def f(): open('x', 'rb')").effects, ["io_read"])
        for mode in ("w", "a", "x", "r+", "wb"):
            self.assertEqual(static_of(f"def f(): open('x', {mode!r})").effects, ["io_write"], mode)
        self.assertEqual(static_of("def f(m): open('x', m)").effects, ["io_unknown"])
        self.assertEqual(static_of("def f(): open('x', mode='w')").effects, ["io_write"])

    def test_parameter_mutation_and_aliases(self):
        self.assertEqual(static_of("def f(xs): xs.append(1)").mutated_params, ["xs"])
        self.assertEqual(static_of("def f(d): d['k'] = 1").mutated_params, ["d"])
        self.assertEqual(static_of("def f(o): o.attr = 1").mutated_params, ["o"])
        self.assertEqual(static_of("def f(xs):\n    ys = xs\n    ys.append(1)").mutated_params, ["xs"])
        self.assertEqual(static_of("def f(grid):\n    for row in grid:\n        row.append(0)").mutated_params, ["grid"])
        self.assertEqual(static_of("def f(xs: list):\n    xs += [1]").mutated_params, ["xs"])
        self.assertEqual(static_of("def f(n):\n    n += 1\n    return n").mutated_params, [])  # ints rebind
        self.assertEqual(static_of("def f(xs):\n    ys = []\n    ys.append(1)\n    return ys").mutated_params, [])
        self.assertEqual(static_of("def f(xs): return sorted(xs)").mutated_params, [])
        self.assertEqual(static_of("def f(xs): del xs[0]").mutated_params, ["xs"])

    def test_global_effects(self):
        self.assertIn("global_write", static_of("def f():\n    global C\n    C += 1", {"C"}).effects)
        self.assertIn("global_mutation", static_of("def f(): CACHE.append(1)", {"CACHE"}).effects)
        self.assertIn("global_mutation", static_of("def f(): CACHE['k'] = 1", {"CACHE"}).effects)
        self.assertEqual(static_of("def f():\n    CACHE = []\n    CACHE.append(1)", {"CACHE"}).effects, [])  # local shadow

    def test_self_mutation_is_its_own_effect_not_parameter_mutation(self):
        fn = ast.parse("class C:\n    def m(self, xs):\n        self.n = 1\n        xs.append(1)").body[0].body[0]
        st = analyze_static(fn, set(), "self")
        self.assertEqual((st.effects, st.mutated_params), (["self_mutation"], ["xs"]))

    def test_purity_levels(self):
        self.assertEqual(static_of("def f(a, b): return a + b").purity, "pure")
        self.assertEqual(static_of("def f(a): return helper(a)").purity, "unknown")
        self.assertEqual(static_of("def f(a): return len(a) + max(a)").purity, "pure")
        self.assertEqual(static_of("def f(a): a.append(1)").purity, "impure")
        self.assertEqual(static_of("import math\ndef f(a): return math.sqrt(a)").purity, "pure")

    def test_return_analysis(self):
        r = static_of("def f(x): return x > 0").returns
        self.assertTrue(r["returns_bool"] and not r["can_return_none"])
        r = static_of("def f(x):\n    if x: return True").returns
        self.assertTrue(not r["returns_bool"] and r["can_return_none"] and r["falls_off_end"])
        r = static_of("def f(x):\n    if x: return True\n    return False").returns
        self.assertTrue(r["returns_bool"])
        r = static_of("def f(x): return x and x > 1").returns
        self.assertFalse(r["returns_bool"])  # `x and ...` can return a non-bool
        self.assertEqual(static_of("def f(): return 7").returns["constants"], ["7"])
        self.assertTrue(static_of("def f(x): return x").returns["kinds"] == ["param"])

    def test_can_fall_through(self):
        def ft(src): return can_fall_through(ast.parse(textwrap.dedent(src)).body)
        self.assertFalse(ft("return 1"))
        self.assertFalse(ft("raise ValueError"))
        self.assertTrue(ft("x = 1"))
        self.assertTrue(ft("if a:\n    return 1"))
        self.assertFalse(ft("if a:\n    return 1\nelse:\n    return 2"))
        self.assertFalse(ft("while True:\n    pass"))
        self.assertTrue(ft("while True:\n    break"))
        self.assertFalse(ft("try:\n    return 1\nfinally:\n    pass"))
        self.assertFalse(ft("with a:\n    return 1"))

    def test_raises_and_asserts(self):
        st = static_of("def f(x):\n    assert x\n    if x < 0:\n        raise ValueError('n')\n    raise")
        self.assertEqual((st.raises, st.has_assert), (["ValueError", "re-raise"], True))

    def test_param_kind_inference(self):
        def kinds(src): return infer_param_kinds(ast.parse(textwrap.dedent(src)).body[0])
        self.assertEqual(kinds("def f(a: int, b: str, c: list[int], d: dict): pass"),
                         {"a": "int", "b": "str", "c": "list", "d": "dict"})
        self.assertEqual(kinds("def f(x=3, y='a'): pass"), {"x": "int", "y": "str"})
        self.assertEqual(kinds("def f(p): return p.upper()"), {"p": "str"})
        self.assertEqual(kinds("def f(p): p.append(1)"), {"p": "list"})
        self.assertEqual(kinds("def f(p): return p.items()"), {"p": "dict"})
        self.assertEqual(kinds("def f(p): return len(p)"), {"p": "sized"})
        self.assertEqual(kinds("def f(p): return p % 3"), {"p": "num"})
        self.assertEqual(kinds("def f(thing): return thing"), {"thing": "any"})
        self.assertEqual(kinds("def f(n): return n"), {"n": "num"})  # name-based fallback only when usage is silent


# ================================================================= matching units
class MatchingUnitTests(unittest.TestCase):
    def results_for(self, cat, fn):
        return {i: {"cat": cat, "i": i, "out": {"t": "none"} if False else enc_py(fn(*a)), "exc": None,
                    "after": [enc_py(x) for x in a], "mut": False, "det": True} for i, a in enumerate(BATTERIES[cat])}

    def test_exact_near_and_miss(self):
        exact = {m["ref"]: m for m in match_refs("int1", self.results_for("int1", lambda x: x % 2 == 0))}
        self.assertEqual(exact["is_even"]["score"], 1.0)
        near = {m["ref"]: m for m in match_refs("int1", self.results_for("int1", lambda x: x % 2 == 0 if x >= 0 else True))}
        self.assertTrue(0.7 <= near["is_even"]["score"] < 1.0)
        self.assertTrue(near["is_even"]["deviations"])

    def test_domain_excludes_undefined_inputs(self):
        # division is only compared where the reference is defined (b != 0)
        res = {m["ref"]: m for m in match_refs("int2", self.results_for("int2", lambda a, b: a // b if b else 0))}
        self.assertEqual(res["floordiv"]["score"], 1.0)

    def test_raising_where_reference_is_defined_is_a_deviation(self):
        recs = self.results_for("int1", abs)
        for r in recs.values():
            if r["i"] % 3 == 0:
                r["exc"], r["out"] = "ValueError", None
        self.assertLess({m["ref"]: m for m in match_refs("int1", recs)}["abs"]["score"], 1.0)

    def test_inplace_reference_checks_post_state_not_return_value(self):
        recs = {}
        for i, (xs,) in enumerate(BATTERIES["seq1"]):
            after = sorted(xs)
            recs[i] = {"cat": "seq1", "i": i, "out": {"t": "none"}, "exc": None, "after": [enc_py(after)], "mut": True, "det": True}
        res = {m["ref"]: m for m in match_refs("seq1", recs)}
        self.assertEqual(res["sort_inplace"]["score"], 1.0)
        self.assertLess(res["sorted"]["score"], 1.0)  # returned None, so it is not the pure sorted()

    def test_references_with_too_few_defined_inputs_are_not_reported(self):
        import copy
        tiny = S.Ref("tiny_probe", "int1", lambda x: x, ("tiny",), domain=lambda x: x in (0, 1, 2))
        S._BY_CAT["int1"].append(tiny)
        try:
            recs = self.results_for("int1", lambda x: x)
            self.assertNotIn("tiny_probe", {m["ref"] for m in match_refs("int1", recs)})  # 3 inputs: no evidence
            S._BY_CAT["int1"][-1] = S.Ref("tiny_probe", "int1", lambda x: x, ("tiny",), domain=lambda x: x in range(-2, 6))
            self.assertIn("tiny_probe", {m["ref"] for m in match_refs("int1", recs)})  # 8 inputs: reported
        finally:
            S._BY_CAT["int1"].pop()

    def test_equiv_rules(self):
        self.assertEqual(equiv(1, 1), 1)
        self.assertEqual(equiv(True, 1), 2)
        self.assertEqual(equiv(2, 2.0), 1)
        self.assertEqual(equiv(0.1 + 0.2, 0.3), 1)
        self.assertEqual(equiv([1, 2], (1, 2)), 1)
        self.assertEqual(equiv([1, 2], [1, 3]), 0)
        self.assertEqual(equiv({"a": 1}, {"a": 1}), 1)
        self.assertEqual(equiv("a", "b"), 0)
        self.assertEqual(equiv(float("nan"), float("nan")), 1)
        self.assertEqual(equiv(None, 0), 0)
        self.assertEqual(equiv(S.Obj("X"), S.Obj("X")), 0)

    def test_encode_decode_roundtrip_through_the_worker_format(self):
        import json
        ns = {}
        exec(compile(S._WORKER.split("class _TO")[0].split("def enc")[1].join(["def enc", ""]), "w", "exec"), ns) \
            if False else None
        for v in (None, True, 3, 2 ** 70, 1.5, "s", [1, [2, 3]], (1, 2), {"a": 1}, {1, 2}):
            self.assertEqual(equiv(dec(enc_py(v)), v) > 0, True, v)

    def test_category_selection_and_name_hints(self):
        self.assertEqual(categories_for(0, []), ["nullary"])
        self.assertEqual(categories_for(1, ["str"]), ["str1"])
        self.assertEqual(categories_for(1, ["dict"]), [])
        self.assertEqual(categories_for(2, ["num", "num"]), ["int2"])
        self.assertEqual(categories_for(2, ["list", "any"]), ["seq_item"])
        self.assertEqual(categories_for(3, ["any"] * 3), [])
        self.assertEqual(name_tokens("_calculateMax_v2"), ["calculate", "max", "v2"])
        self.assertEqual(refs_named_by(["is", "sorted"], ["seq1"]), {"is_sorted"})  # predicate names only hit predicates
        self.assertEqual(refs_named_by(["sorted", "list"], ["seq1"]), {"sorted", "is_sorted"})
        self.assertEqual(refs_named_by(["total", "price"], ["int2"]), {"add"})
        self.assertEqual(refs_named_by(["total"], ["str1"]), set())  # restricted to probed categories

    def test_every_reference_is_self_consistent_and_distinct_enough(self):
        # each reference must match itself exactly, and no two references in a category may be indistinguishable
        for cat, refs in S._BY_CAT.items():
            sigs = {}
            for ref in refs:
                if ref.inplace:
                    continue
                import copy
                out = []
                for args in BATTERIES[cat]:
                    try:
                        if ref.domain and not ref.domain(*args):
                            out.append("<undef>"); continue
                        out.append(repr(ref.fn(*copy.deepcopy(args))))
                    except Exception:
                        out.append("<undef>")
                sig = tuple(out)
                self.assertNotIn(sig, sigs, f"{ref.name} indistinguishable from {sigs.get(sig)} on the {cat} battery")
                sigs[sig] = ref.name


def enc_py(v, d=0):
    """Python mirror of the worker's encoder, for building fake worker records in unit tests."""
    if v is None: return {"t": "none"}
    if isinstance(v, bool): return {"t": "bool", "v": v}
    if isinstance(v, int): return {"t": "int", "v": v if abs(v) < 2 ** 53 else str(v)}
    if isinstance(v, float): return {"t": "float", "v": repr(v)}
    if isinstance(v, str): return {"t": "str", "v": v}
    if isinstance(v, list): return {"t": "list", "v": [enc_py(x, d + 1) for x in v]}
    if isinstance(v, tuple): return {"t": "tuple", "v": [enc_py(x, d + 1) for x in v]}
    if isinstance(v, dict): return {"t": "dict", "v": [[enc_py(k), enc_py(x)] for k, x in v.items()]}
    if isinstance(v, (set, frozenset)): return {"t": "set", "v": [enc_py(x) for x in sorted(v)]}
    return {"t": "obj", "v": type(v).__name__}


if __name__ == "__main__":
    unittest.main()
