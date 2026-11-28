"""DEV14 tests: evidence-chain integrity, generated inputs beyond the test suite, pre-registration."""
import copy
import json
import tempfile
import textwrap
import unittest
from pathlib import Path

from asm.coding import SafeTestRunner, tree_fingerprint
from asm.coding.faultloc import RepairWorkflow
from asm.coding.integrity import (GENESIS, ChainedWriter, code_hash, environment_provenance, read_records, seal,
                                  verify_chain, verify_dossier)


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


TWO_FAULTS = {"m.py": "def inc(x): return x - 1\ndef dbl(x): return x + x + 1\n",
              "tests/test_m.py": "from m import inc, dbl\ndef test_inc(): assert inc(1) == 2\ndef test_dbl(): assert dbl(3) == 6\n"}
PARTIAL = {"m.py": "def inc(x): return x - 1\ndef other(x): return x * 3 + 7\n",
           "tests/test_m.py": "from m import inc, other\ndef test_inc(): assert inc(1) == 2\ndef test_other(): assert other(1) == 99\n"}


# ===================================================================================== dossier sealing
class DossierIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo = Repo(TWO_FAULTS)
        cls.d = RepairWorkflow().run(cls.repo.root)

    @classmethod
    def tearDownClass(cls):
        cls.repo.tmp.cleanup()

    def sealed(self):
        return json.loads(json.dumps(self.d.to_dict()))

    def test_fresh_dossier_verifies_in_memory_and_after_a_json_round_trip(self):
        self.assertEqual(self.d.status, "resolved")
        self.assertEqual(len(self.d.steps), 2)
        self.assertEqual(self.d.verify(), (True, []))
        self.assertEqual(verify_dossier(self.sealed()), (True, []))

    def test_editing_any_field_is_detected(self):
        for key, value in (("status", "unresolved"), ("diff", ""), ("caveats", ["nothing to see"]), ("notes", ["edited"])):
            d = self.sealed()
            self.assertNotEqual(d[key], value, key)  # the edit must really change something
            d[key] = value
            ok, problems = verify_dossier(d)
            self.assertFalse(ok, key)
            self.assertIn("dossier content differs from its seal", problems)

    def test_editing_a_step_names_the_step(self):
        d = self.sealed()
        d["steps"][1]["confidence"] = "high" if d["steps"][1]["confidence"] != "high" else "low"
        ok, problems = verify_dossier(d)
        self.assertFalse(ok)
        self.assertIn("step 1 differs from its sealed hash", problems)

    def test_deleting_or_reordering_steps_is_detected(self):
        d = self.sealed()
        d["steps"] = d["steps"][:1]
        self.assertIn("step count changed: sealed 2, now 1", verify_dossier(d)[1])
        d = self.sealed()
        d["steps"] = d["steps"][::-1]
        self.assertIn("step 0 differs from its sealed hash", verify_dossier(d)[1])

    def test_forged_provenance_and_missing_seal_are_detected(self):
        d = self.sealed()
        d["integrity"]["provenance"]["python"] = "9.9"
        self.assertFalse(verify_dossier(d)[0])
        d = self.sealed()
        del d["integrity"]
        self.assertEqual(verify_dossier(d), (False, ["no integrity block"]))

    def test_patches_are_bound_to_the_seal(self):
        hashes = self.sealed()["patch_hashes"]
        self.assertEqual(len(hashes), 2)
        self.assertEqual({h["path"] for h in hashes}, {"m.py"})
        self.assertTrue(all(len(h["replacement_sha256"]) == 64 for h in hashes))


class ApplyIntegrityTests(unittest.TestCase):
    def test_a_partial_dossier_edited_to_resolved_is_refused(self):
        with Repo(PARTIAL) as root:
            d = RepairWorkflow().run(root)
            self.assertEqual(d.status, "partial")
            d.status = "resolved"  # tampering
            with self.assertRaises(ValueError) as cm:
                RepairWorkflow.apply_fix(root, d, approved=True)
            self.assertIn("integrity", str(cm.exception))
            self.assertIn("x - 1", (root / "m.py").read_text())  # nothing applied

    def test_swapped_patches_are_refused_even_with_an_untouched_report(self):
        with Repo(TWO_FAULTS) as root:
            d = RepairWorkflow().run(root)
            d._proposals = d._proposals[::-1]
            with self.assertRaises(ValueError) as cm:
                RepairWorkflow.apply_fix(root, d, approved=True)
            self.assertIn("not the ones it was sealed with", str(cm.exception))

    def test_an_unsealed_dossier_is_refused_and_a_valid_one_still_applies(self):
        with Repo(TWO_FAULTS) as root:
            d = RepairWorkflow().run(root)
            seal_block = d._seal
            d._seal = None
            with self.assertRaises(ValueError):
                RepairWorkflow.apply_fix(root, d, approved=True)
            d._seal = seal_block
            RepairWorkflow.apply_fix(root, d, approved=True)
            self.assertEqual(SafeTestRunner(timeout_seconds=30).run_pytest(root).classification, "passed")


# ============================================================================================ provenance
class ProvenanceTests(unittest.TestCase):
    def test_provenance_records_interpreter_tools_and_code(self):
        p = environment_provenance()
        for key in ("python", "implementation", "platform", "pytest", "asm_coding_sha256", "utc"):
            self.assertIn(key, p)
        self.assertEqual(len(p["asm_coding_sha256"]), 64)

    def test_code_hash_is_stable_and_changes_with_any_source_change(self):
        with tempfile.TemporaryDirectory() as t:
            pkg = Path(t) / "pkg"
            pkg.mkdir()
            (pkg / "a.py").write_text("x = 1\n")
            h1, h2 = code_hash(pkg), code_hash(pkg)
            self.assertEqual(h1, h2)
            (pkg / "a.py").write_text("x = 2\n")
            self.assertNotEqual(code_hash(pkg), h1)
            (pkg / "a.py").write_text("x = 1\n")
            self.assertEqual(code_hash(pkg), h1)
            (pkg / "b.py").write_text("")
            self.assertNotEqual(code_hash(pkg), h1)  # adding a file changes it too

    def test_seal_is_deterministic_for_the_same_body_and_provenance(self):
        body = {"status": "resolved", "steps": [{"a": 1}, {"b": 2}]}
        prov = {"python": "3.x"}
        self.assertEqual(seal(body, prov), seal(copy.deepcopy(body), dict(prov)))
        self.assertNotEqual(seal(body, prov)["step_chain"], seal({**body, "steps": body["steps"][::-1]}, prov)["step_chain"])


# ======================================================================================== chained records
class ChainedRecordTests(unittest.TestCase):
    def make(self, t, n=3):
        path = Path(t) / "r.jsonl"
        w = ChainedWriter(path, {"run": "x", "seed": 1})
        for i in range(n):
            w.append({"i": i, "class": "restored"})
        return path, w

    def test_a_new_file_needs_a_manifest_and_links_from_genesis(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(ValueError):
                ChainedWriter(Path(t) / "x.jsonl")
            path, w = self.make(t)
            first = json.loads(path.read_text().splitlines()[0])
            self.assertEqual((first["_kind"], first["_prev"]), ("manifest", GENESIS))
            ok, problems, head = verify_chain(path)
            self.assertEqual((ok, problems, head), (True, [], w.head))

    def test_edits_deletions_reordering_and_torn_tails_are_detected(self):
        with tempfile.TemporaryDirectory() as t:
            path, _ = self.make(t)
            lines = path.read_text().splitlines()
            cases = {
                "edited": lines[:2] + [lines[2].replace('"restored"', '"wrong"')] + lines[3:],
                "deleted": lines[:2] + lines[3:],
                "reordered": [lines[0], lines[2], lines[1], lines[3]],
                "torn": lines[:3] + [lines[3][:20]],
            }
            expect = {"edited": "content does not match its hash", "deleted": "does not link",
                      "reordered": "does not link", "torn": "not valid JSON"}
            for name, ls in cases.items():
                path.write_text("\n".join(ls) + "\n")
                ok, problems, _ = verify_chain(path)
                self.assertFalse(ok, name)
                self.assertIn(expect[name], problems[0], name)

    def test_reopening_continues_the_chain_but_refuses_a_broken_one(self):
        with tempfile.TemporaryDirectory() as t:
            path, _ = self.make(t, 2)
            ChainedWriter(path).append({"i": 99})
            self.assertTrue(verify_chain(path)[0])
            manifest, recs = read_records(path)
            self.assertEqual(manifest, {"run": "x", "seed": 1})
            self.assertEqual([r["i"] for r in recs], [0, 1, 99])
            path.write_text(path.read_text().replace('"i": 1', '"i": 7'))
            with self.assertRaises(ValueError):
                ChainedWriter(path)
            with self.assertRaises(ValueError):
                read_records(path)


if __name__ == "__main__":
    unittest.main()


# ================================================================================= inputs beyond the tests
import ast as _ast  # noqa: E402
import random as _random  # noqa: E402

from asm.coding.faultloc import collect_spectrum  # noqa: E402
from asm.coding.generation import generate_sets, mine_constants, typed_values  # noqa: E402
from asm.coding.patches import PatchProposalBuilder  # noqa: E402
from asm.coding.understanding import CodeUnderstanding  # noqa: E402
from asm.coding.verification import build_inputs, verify_patch  # noqa: E402

GRADE = {"g.py": "def grade(score, bonus):\n    if score >= 90:\n        return 'A'\n    return 'B' if score + bonus > 50 else 'C'\n",
         "tests/test_g.py": "from g import grade\ndef test_g(): assert grade(95, 0) == 'A' and grade(10, 0) == 'C'\n"}


class GenerationUnitTests(unittest.TestCase):
    def test_constants_and_their_neighbours_are_mined_from_the_function_body(self):
        fn = _ast.parse("def f(x, s):\n    if x > 50 and s == 'go':\n        return True\n    return x - 2.5\n").body[0]
        m = mine_constants(fn)
        self.assertTrue({49, 50, 51} <= set(m["nums"]))
        self.assertTrue({1.5, 2.5, 3.5} <= set(m["nums"]))
        self.assertEqual(m["strs"], ["go"])
        self.assertNotIn(True, m["nums"])  # booleans are not numbers here

    def test_typed_values_keep_the_type_exclude_the_original_and_stay_small(self):
        mined = {"nums": [49, 50, 51], "strs": ["go"]}
        rng = _random.Random(1)
        for v in (7, 2.5, "ab", [1, 2, 3], (1, 2), {"a": 1}, True):
            vals = typed_values(v, mined, rng)
            self.assertTrue(vals, v)
            self.assertNotIn(v, vals)
            self.assertTrue(all(type(x) is type(v) for x in vals), v)
            self.assertTrue(all(len(repr(x)) <= 200 for x in vals))
        self.assertIn(50, typed_values(7, mined, rng))         # mined boundary reaches the generated values
        self.assertIn("go", typed_values("ab", mined, rng))
        self.assertTrue(all(abs(x) <= 1000 for x in typed_values(7, mined, rng)))

    def test_generation_is_deterministic_covers_every_argument_and_combines_pairs(self):
        views = [{"k": "lit", "r": "5"}, {"k": "lit", "r": "'x'"}]
        mined = {"nums": [9, 10, 11], "strs": []}
        a = generate_sets(views, mined, 30, seed=3)
        self.assertEqual(a, generate_sets(views, mined, 30, seed=3))
        self.assertLessEqual(len(a), 30)
        touched = {s[0] for sets in a for s in sets}
        self.assertEqual({t for t in touched}, {0, 1})               # both arguments are varied
        self.assertEqual({sets[0][0] for sets in a if len(sets) == 1}, {0, 1})  # ...each one also on its own
        self.assertTrue(any(len(sets) == 2 for sets in a))          # and some inputs vary both at once
        objs = generate_sets([{"k": "obj", "cls": "C", "attrs": {"n": "3"}}], mined, 10, seed=1)
        self.assertTrue(objs and all(s[0][1] == "n" for s in objs))  # object attributes are generated too

    def test_build_inputs_tags_generated_inputs_after_the_recorded_ones(self):
        with Repo(GRADE) as root:
            sp = collect_spectrum(root, None, SafeTestRunner(timeout_seconds=30))
            recs = sp.records["g.py:grade"]
            plain = build_inputs(recs, sp.outcomes)
            gen = build_inputs(recs, sp.outcomes, generate={"mined": {"nums": [50, 51], "strs": []}, "budget": 40, "seed": 0})
            self.assertEqual(gen[: len(plain)], plain)                       # DEV13 inputs unchanged, in order
            extra = gen[len(plain):]
            self.assertTrue(extra and all(i["origin"] == "generated" for i in extra))
            self.assertLessEqual(len(extra), 40)
            ident = {(i["blob"], repr(i["set"]), i.get("donor"), repr(i.get("take"))) for i in gen}
            self.assertEqual(len(ident), len(gen))                                    # no duplicate jobs
            descs = [i["desc"] for i in extra]  # generated inputs never repeat a call already replayed (DEV13's own
            self.assertEqual(len(set(descs)), len(descs))  # perturbations are kept exactly as they were)
            self.assertFalse(set(descs) & {i["desc"] for i in plain})


class GenerationVerificationTests(unittest.TestCase):
    def test_a_change_no_test_input_reaches_is_exposed_only_by_generated_inputs(self):
        with Repo(GRADE) as root:
            sp = collect_spectrum(root, None, SafeTestRunner(timeout_seconds=30))
            funcs = {f.qname: f for f in CodeUnderstanding().analyze(root).functions}
            src = (root / "g.py").read_text()
            prop = PatchProposalBuilder.from_replacement(root, "g.py", src.replace("> 50", "> 51"), "boundary")
            blind = verify_patch(root, "g.grade", ("boundary", prop), [], sp, funcs, gen_budget=0)
            seen = verify_patch(root, "g.grade", ("boundary", prop), [], sp, funcs, gen_budget=100)
            self.assertEqual(blind["footprint"]["boundary"], 0.0)            # DEV13's blind spot
            self.assertEqual(blind["inputs_by_origin"]["generated"], 0)
            self.assertGreater(seen["footprint"]["boundary"], 0.0)
            self.assertEqual(set(seen["changed_by_origin"]["boundary"]), {"generated"})

    def test_generated_inputs_let_alternatives_disagree(self):
        # two edits both pass the only test; they differ only on inputs the test never uses
        files = {"m.py": "def f(x):\n    return x * 3 + 2\n", "tests/test_m.py": "from m import f\ndef test_f(): assert f(2) == 7\n"}
        with Repo(files) as root:
            d = RepairWorkflow().run(root)
            v = d.steps[0]["verification"]
            self.assertGreater(v["inputs_by_origin"]["generated"], 0)        # the workflow generates by default
            self.assertTrue(v["distinguishing"])
            self.assertTrue(all("origin" in x for x in v["distinguishing"]))


class StartupErrorTests(unittest.TestCase):
    """Regression (found probing boltons under pytest 9): a suite whose conftest fails to load was reported as
    'tests_failed' with zero outcomes."""
    BROKEN = {"m.py": "def f(x): return x\n",
              "tests/conftest.py": "def pytest_ignore_collect(path, config):\n    return False\n",
              "tests/test_m.py": "from m import f\ndef test_f(): assert f(1) == 1\n"}

    def test_a_suite_that_never_starts_is_a_startup_error(self):
        with Repo(self.BROKEN) as root:
            run = SafeTestRunner(timeout_seconds=30).run_pytest(root)
            self.assertEqual((run.returncode, run.classification, run.outcome), (1, "startup_error", {}))

    def test_the_workflow_does_not_mistake_it_for_a_clean_or_repairable_suite(self):
        with Repo(self.BROKEN) as root:
            d = RepairWorkflow().run(root)
            self.assertEqual(d.status, "incomplete_spectrum")
            self.assertEqual(d.steps, [])

    def test_a_real_test_failure_is_still_tests_failed(self):
        with Repo({"m.py": "def f(x): return x\n", "tests/test_m.py": "from m import f\ndef test_f(): assert f(1) == 2\n"}) as root:
            self.assertEqual(SafeTestRunner(timeout_seconds=30).run_pytest(root).classification, "tests_failed")


class PatchIdentityTests(unittest.TestCase):
    """Regression (found re-judging DEV13 records): two '0' constants on one line had the same description, so a record
    could not say which of two different programs had been judged."""

    def test_twin_sites_on_one_line_get_distinct_descriptions(self):
        from asm.coding.faultloc import enumerate_sites
        src = "def f(d):\n    return g(d[0].defs, d[0].free) + 2\n"
        descs = [st.describe(o) for st in enumerate_sites(src, "m.py", [("f", 1, 2)]) for o in st.options]
        self.assertIn("const: '0' -> '1' at line 2 col 15", descs)
        self.assertIn("const: '0' -> '1' at line 2 col 26", descs)
        self.assertIn("arith: '+' -> '-' at line 2", descs)  # unambiguous sites keep the old wording

    def test_every_description_in_a_real_file_is_unique(self):
        from asm.coding.faultloc import enumerate_sites
        root = Path(__file__).resolve().parents[1] / "asm" / "coding"
        for name in ("understanding.py", "semantics.py", "faultloc.py"):
            src = (root / name).read_text()
            tree = _ast.parse(src)
            ranges = [(n.name, n.lineno, n.end_lineno) for n in _ast.walk(tree) if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef))]
            descs = [st.describe(o) for st in enumerate_sites(src, name, ranges) for o in st.options]
            self.assertGreater(len(descs), 100, name)
            self.assertEqual(len(descs), len(set(descs)), name)


class CrossoverTests(unittest.TestCase):
    PAIR = {"b.py": "def pick(a, b):\n    return a if len(a) >= len(b) else b\n",
            "tests/test_b.py": "from b import pick\ndef test_1(): assert pick([1, 2], [3]) == [1, 2]\n"
                               "def test_2(): assert pick('x', 'yz') == 'yz'\n"}

    def test_crossover_recombines_real_recorded_arguments(self):
        with Repo(self.PAIR) as root:
            sp = collect_spectrum(root, None, SafeTestRunner(timeout_seconds=30))
            recs = sp.records["b.py:pick"]
            gen = build_inputs(recs, sp.outcomes, generate={"mined": {"nums": [], "strs": []}, "budget": 20, "seed": 0})
            cross = [i for i in gen if i.get("generator") == "crossover"]
            self.assertTrue(cross)
            self.assertTrue(all(i["origin"] == "generated" and i["donor"] != i["blob"] and len(i["take"]) == 1 for i in cross))
            self.assertIn("([1, 2], 'yz')", {i["desc"] for i in cross})   # argument 2 of test_2 placed into test_1's call
            off = build_inputs(recs, sp.outcomes, generate={"mined": {"nums": [], "strs": []}, "budget": 20, "seed": 0,
                                                            "crossover_share": 0})
            self.assertFalse([i for i in off if i.get("generator") == "crossover"])

    def test_the_worker_replays_crossover_inputs(self):
        with Repo(self.PAIR) as root:
            sp = collect_spectrum(root, None, SafeTestRunner(timeout_seconds=30))
            funcs = {f.qname: f for f in CodeUnderstanding().analyze(root).functions}
            src = (root / "b.py").read_text()
            # >= vs > only differs when lengths are equal: ([1, 2], 'yz') is such a crossover input
            prop = PatchProposalBuilder.from_replacement(root, "b.py", src.replace(">=", ">"), "tie")
            v = verify_patch(root, "b.pick", ("tie", prop), [], sp, funcs, gen_budget=20)
            self.assertGreater(v["changed_by_origin"]["tie"].get("generated", 0), 0)
            # the crossover input itself must really be replayed with the donor's argument
            from asm.coding.verification import run_versions
            from asm.coding.patches import apply_proposal
            inputs = build_inputs(sp.records["b.py:pick"], sp.outcomes,
                                  generate={"mined": {"nums": [], "strs": []}, "budget": 20, "seed": 0})
            i = next(k for k, inp in enumerate(inputs) if inp.get("generator") == "crossover" and inp["desc"] == "([1, 2], 'yz')")
            outs = run_versions(root, "b", "pick", {"orig": None, "tie": prop}, inputs, [])
            self.assertEqual(outs["orig"][i]["out"], {"t": "list", "v": [{"t": "int", "v": 1}, {"t": "int", "v": 2}]})
            self.assertEqual(outs["tie"][i]["out"], {"t": "str", "v": "yz"})


# ===================================================================================== project interpreter
import os as _os  # noqa: E402
import sys as _sys  # noqa: E402

from asm.coding.sandbox import check_python, interpreter, run_python_worker, target_python  # noqa: E402

ALT = "asm_alt_python"
PROBE = {"m.py": "import os, sys\n"
                 f"if os.path.basename(sys.executable) != {ALT!r}: raise ImportError('needs the project interpreter')\n"
                 "def inc(x): return x - 1\n",
         "tests/test_m.py": "import os, sys\nfrom m import inc\n"
                            f"def test_interp(): assert os.path.basename(sys.executable) == {ALT!r}\n"
                            "def test_inc(): assert inc(1) == 2\n"}


class InterpreterTests(unittest.TestCase):
    """Real projects pin old Pythons (BugsInPy: 3.6-3.8); tests and replay workers must run under the project's
    interpreter, while ASM itself keeps running under its own."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.alt = Path(self.tmp.name) / ALT
        self.alt.symlink_to(_sys.executable)  # same interpreter, different identity: observable via sys.executable

    def tearDown(self):
        self.tmp.cleanup()

    def test_check_python_rejects_non_interpreters(self):
        with self.assertRaises(ValueError):
            check_python(Path(self.tmp.name) / "missing")
        plain = Path(self.tmp.name) / "plain"
        plain.write_text("x")
        with self.assertRaises(ValueError):
            check_python(plain)
        with self.assertRaises(ValueError):
            SafeTestRunner(python=str(plain))

    def test_runner_python_is_used(self):
        with Repo(PROBE) as root:
            self.assertNotEqual(SafeTestRunner().run_pytest(root).classification, "passed")  # m.py refuses ASM's python
            run = SafeTestRunner(python=str(self.alt)).run_pytest(root)
            self.assertEqual(run.outcome.get("tests/test_m.py::test_interp"), "passed")

    def test_context_applies_and_resets(self):
        self.assertEqual(target_python(), _sys.executable)
        with Repo(PROBE) as root:
            with interpreter(self.alt):
                self.assertEqual(target_python(), str(self.alt))
                run = SafeTestRunner().run_pytest(root)
                self.assertEqual(run.outcome.get("tests/test_m.py::test_interp"), "passed")
            self.assertEqual(target_python(), _sys.executable)
            self.assertNotEqual(SafeTestRunner().run_pytest(root).outcome.get("tests/test_m.py::test_interp"), "passed")

    def test_worker_honours_context_and_explicit_choice(self):
        script = "import os, sys\nopen(sys.argv[1], 'w').write(os.path.basename(sys.executable))\n"
        with tempfile.TemporaryDirectory() as t:
            out = Path(t) / "o.txt"
            with interpreter(self.alt):
                run_python_worker(script, [str(out)], Path(t), timeout=30)
            self.assertEqual(out.read_text(), ALT)
            run_python_worker(script, [str(out)], Path(t), timeout=30)
            self.assertNotEqual(out.read_text(), ALT)
            run_python_worker(script, [str(out)], Path(t), timeout=30, python=str(self.alt))
            self.assertEqual(out.read_text(), ALT)

    def test_workflow_runs_tests_under_runner_python(self):
        # test_interp only passes under the alternative interpreter, so if any run inside the workflow used ASM's
        # interpreter instead, the baseline would show two failures and the repair could not resolve.
        with Repo(PROBE) as root:
            d = RepairWorkflow(SafeTestRunner(python=str(self.alt)), time_budget_seconds=90).run(root)
            self.assertEqual(d.status, "resolved", d.notes)
            self.assertEqual([s["suspect"] for s in d.steps], ["m.inc"])
            # m.py refuses to import under any other interpreter, so replay verification only works if the workers
            # ran under the runner's interpreter too
            self.assertTrue(d.steps[0]["verification"]["available"], d.steps[0]["verification"])
            self.assertNotIn("behaviour_unverified", d.steps[0]["confidence_basis"])


@unittest.skipUnless(_os.environ.get("ASM_TEST_OLD_PYTHON"), "set ASM_TEST_OLD_PYTHON to an older interpreter with pytest")
class OldInterpreterEndToEnd(unittest.TestCase):
    """End to end on a genuinely older Python: tracing plugin, call recording and replay workers must all work there."""

    def test_repair_and_verification_on_old_python(self):
        py = _os.environ["ASM_TEST_OLD_PYTHON"]
        with Repo(TWO_FAULTS) as root:
            runner = SafeTestRunner(python=py)
            spectrum = collect_spectrum(root, None, runner)
            self.assertTrue(spectrum.complete, spectrum.incomplete_reason)
            self.assertTrue(spectrum.records, "no calls were recorded under the old interpreter")
            d = RepairWorkflow(runner, time_budget_seconds=150).run(root)
            self.assertEqual(d.status, "resolved", d.notes)
            self.assertEqual(sorted(s["suspect"] for s in d.steps), ["m.dbl", "m.inc"])


class QualnameFallbackTests(unittest.TestCase):
    """The tracing plugin keys call records by qualified name. code.co_qualname only exists from Python 3.11, so on
    older project interpreters the plugin derives it from the source; it must agree with co_qualname exactly."""

    SRC = textwrap.dedent('''
        import functools
        def top(a): return a
        class K:
            def m(self, x): return x
            @staticmethod
            @functools.lru_cache()
            def s(y): return y
            class Inner:
                def deep(self, z): return z
        def outer(q):
            def inner(r):
                def innermost(t): return t
                return innermost
            return inner
        async def coro(w): return w
        ''')

    def test_fallback_matches_co_qualname(self):
        import types
        from asm.coding.faultloc import TRACE_PLUGIN
        with tempfile.TemporaryDirectory() as t:
            src = Path(t) / "mod.py"
            src.write_text(self.SRC)
            ns = {}
            old = {k: _os.environ.get(k) for k in ("ASM_TRACE_ROOT", "ASM_TRACE_OUT")}
            _os.environ.update(ASM_TRACE_ROOT=t, ASM_TRACE_OUT=str(Path(t) / "o.json"))
            try:
                exec(compile(TRACE_PLUGIN, "asm_trace_plugin", "exec"), ns)
            finally:
                for k, v in old.items():
                    _os.environ.pop(k) if v is None else _os.environ.__setitem__(k, v)
            codes, stack = [], [compile(self.SRC, str(src), "exec")]
            while stack:
                co = stack.pop()
                for c in co.co_consts:
                    if isinstance(c, types.CodeType):
                        codes.append(c)
                        stack.append(c)

            class Old:  # a code object as Python < 3.11 presents it: no co_qualname
                def __init__(self, co):
                    self.co_filename, self.co_firstlineno, self.co_name = co.co_filename, co.co_firstlineno, co.co_name

            pairs = [(c.co_qualname, ns["_qualname"](Old(c))) for c in codes if c.co_name != "<module>"]
            self.assertGreaterEqual(len(pairs), 8)
            self.assertEqual([a for a, _ in pairs], [b for _, b in pairs])


TIED = {"calc.py": "def helper(x): return x + 1\ndef is_big(n): return n > 10\n"
                   "def classify(n):\n    return 'big' if is_big(helper(n)) else 'small'\n",
        "tests/test_c.py": "from calc import classify\ndef test_a(): assert classify(9) == 'big'\n"
                           "def test_b(): assert classify(1) == 'small'\n"}


class PreregisteredRuleR1Tests(unittest.TestCase):
    """R1 outcome on the fresh decoy set: tied_localization is shown but not counted toward the label."""

    def test_tie_is_reported_but_not_counted(self):
        from asm.coding.faultloc import INFORMATIONAL_FLAGS
        self.assertEqual(INFORMATIONAL_FLAGS, frozenset({"tied_localization"}))
        with Repo(TIED) as root:
            d = RepairWorkflow().run(root)
            step = d.steps[0]
            self.assertIn("tied_localization", step["confidence_basis"])
            self.assertNotIn("tied_localization", step["confidence_counted"])
            expected = "low" if len(step["confidence_counted"]) >= 2 else ("medium" if step["confidence_counted"] else "high")
            self.assertEqual(step["confidence"], expected)
            self.assertTrue(any("compensating for a fault elsewhere" in c for c in d.caveats))  # caveat still given
            self.assertIn("tied_localization [informational]", d.to_markdown())


CLASS_TESTS = {"m.py": "def inc(x): return x - 1\n",
               "tests/test_m.py": "from m import inc\nclass TestInc:\n    def test_one(self): assert inc(1) == 2\n"
                                  "    def test_zero(self): assert inc(-1) == 0\n"}


class OldPytestNodeIdTests(unittest.TestCase):
    """pytest < 4 reports class tests as 'f.py::C::()::t'. Plain runs (JUnit) say 'f.py::C::t'. If the plugin keeps the
    old form, the spectrum disagrees with pytest and localization is refused (found on real BugsInPy bugs)."""

    def test_plugin_normalizes_instance_segment(self):
        from asm.coding.faultloc import TRACE_PLUGIN
        with tempfile.TemporaryDirectory() as t:
            ns = {}
            old = {k: _os.environ.get(k) for k in ("ASM_TRACE_ROOT", "ASM_TRACE_OUT")}
            _os.environ.update(ASM_TRACE_ROOT=t, ASM_TRACE_OUT=str(Path(t) / "o.json"))
            try:
                exec(compile(TRACE_PLUGIN, "asm_trace_plugin", "exec"), ns)
            finally:
                for k, v in old.items():
                    _os.environ.pop(k) if v is None else _os.environ.__setitem__(k, v)
        self.assertEqual(ns["_nid"]("tests/a.py::TestX::()::test_y"), "tests/a.py::TestX::test_y")
        self.assertEqual(ns["_nid"]("tests/a.py::TestX::test_y[1]"), "tests/a.py::TestX::test_y[1]")

    @unittest.skipUnless(_os.environ.get("ASM_TEST_OLD_PYTHON"), "set ASM_TEST_OLD_PYTHON")
    def test_class_tests_localize_on_old_python(self):
        with Repo(CLASS_TESTS) as root:
            runner = SafeTestRunner(python=_os.environ["ASM_TEST_OLD_PYTHON"])
            spectrum = collect_spectrum(root, None, runner)
            self.assertTrue(spectrum.complete, spectrum.incomplete_reason)
            self.assertEqual(sorted(spectrum.failing), sorted(runner.run_pytest(root).failed_ids))
            self.assertEqual(RepairWorkflow(runner, time_budget_seconds=120).run(root).status, "resolved")


# tqdm (BugsInPy bug 5): tests live inside the package as pkg/tests/tests_pkg.py. The fault is in the library, but the
# test compares against a constant the old rule let the workflow edit.
TEST_IN_PACKAGE = {"pkg/__init__.py": "", "pkg/core.py": "def size(items):\n    return len(items) - 1\n",
                   "pkg/tests/__init__.py": "",
                   "pkg/tests/tests_pkg.py": "from pkg.core import size\nEXPECTED = True\n"
                                             "def test_size():\n    assert (size([1, 2]) == 2) == EXPECTED\n"}


class TestCodeProtectionTests(unittest.TestCase):
    def test_test_path_rule(self):
        from asm.coding.faultloc import is_test_path
        from asm.coding.research import _is_test_path
        yes = ["tests/a.py", "pkg/tests/tests_pkg.py", "pkg/test/helpers.py", "src/pkg/testing/x.py", "a/test_x.py",
               "a/x_test.py", "a/x_tests.py", "a/tests_x.py", "conftest.py", "pkg/conftest.py"]
        no = ["pkg/core.py", "pkg/contest.py", "pkg/attestation.py", "pkg/latest.py", "pkg/tests.py"]
        for rel in yes:
            self.assertTrue(is_test_path(rel), rel)
            self.assertTrue(_is_test_path(rel), rel)
        for rel in no:
            self.assertFalse(is_test_path(rel), rel)
            self.assertFalse(_is_test_path(rel), rel)
        self.assertTrue(is_test_path("pkg/checks.py", collected={"pkg/checks.py"}))  # any file pytest collected from

    def test_workflow_never_patches_tests_inside_the_package(self):
        with Repo(TEST_IN_PACKAGE) as root:
            before = (root / "pkg/tests/tests_pkg.py").read_text()
            d = RepairWorkflow(time_budget_seconds=90).run(root, ["pkg/tests/tests_pkg.py"])
            self.assertFalse([s for s in d.steps if "tests" in s["path"]], [s["path"] for s in d.steps])
            for it in d.iterations:
                self.assertFalse([s for s in it["suspects"] if "tests" in s["path"]])
            self.assertEqual((root / "pkg/tests/tests_pkg.py").read_text(), before)
            self.assertEqual(d.status, "resolved", d.notes)
            self.assertEqual([s["path"] for s in d.steps], ["pkg/core.py"])

    def test_collected_test_files_are_excluded_even_with_unusual_names(self):
        files = {"m.py": "def inc(x): return x - 1\n",
                 "checks.py": "from m import inc\nWANT = 2\ndef test_inc(): assert inc(1) == WANT\n"}
        with Repo(files) as root:
            d = RepairWorkflow(time_budget_seconds=90).run(root, ["checks.py"])
            self.assertEqual([s["path"] for s in d.steps], ["m.py"])
            self.assertFalse([s for it in d.iterations for s in it["suspects"] if s["path"] == "checks.py"])
