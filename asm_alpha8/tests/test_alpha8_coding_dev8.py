import tempfile
import unittest
from pathlib import Path

from asm.coding import (Candidate, CodingResearchLoop, FailureLedger, ProcedureStore,
                        TestRunner, tree_fingerprint)


def make_repo(root: Path, src="def add(a, b): return a - b\n", extra_test=""):
    (root / "calc.py").write_text(src)
    (root / "tests").mkdir()
    (root / "tests" / "test_calc.py").write_text(
        "from calc import add\n"
        "def test_add(): assert add(2, 3) == 5\n"
        "def test_zero(): assert add(0, 0) == 0\n" + extra_test)


def loop(gen, **kw):
    kw.setdefault("test_runner", TestRunner(timeout_seconds=20))
    return CodingResearchLoop(gen, **kw)


class ResearchLoopTests(unittest.TestCase):
    def test_baseline_passing_needs_no_repair(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); make_repo(root, "def add(a, b): return a + b\n")
            called = []
            r = loop(lambda c: called.append(1) or []).run(root, "fix add")
            self.assertEqual(r.stop_reason, "no_repair_needed")
            self.assertEqual(called, [])

    def test_selects_passing_candidate_and_never_modifies_original(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); make_repo(root)
            before = tree_fingerprint(root)
            gen = lambda c: [Candidate("calc.py", "def add(a, b): return a * b\n", "wrong"),
                             Candidate("calc.py", "def add(a, b): return a + b\n", "right")]
            r = loop(gen).run(root, "fix add")
            self.assertTrue(r.resolved)
            self.assertEqual(r.best.status, "passed")
            self.assertEqual(r.best.reason, "right")
            self.assertIn("+def add(a, b): return a + b", r.best_preview)
            self.assertTrue(r.original_tree_unchanged)
            self.assertEqual(tree_fingerprint(root), before)
            self.assertIn("a - b", (root / "calc.py").read_text())

    def test_learns_from_failed_round_via_context(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); make_repo(root)
            seen = []
            def gen(ctx):
                seen.append(ctx)
                if ctx.round == 1:
                    return [Candidate("calc.py", "def add(a, b): return a * b\n")]
                self.assertTrue(ctx.prior_failures)  # failure evidence is passed forward
                self.assertEqual(ctx.prior_failures[-1]["status"], "failed")
                return [Candidate("calc.py", "def add(a, b): return a + b\n")]
            r = loop(gen).run(root, "fix add")
            self.assertTrue(r.resolved)
            self.assertEqual(r.rounds_used, 2)
            self.assertEqual(len(seen), 2)

    def test_duplicate_failed_candidate_skipped_within_and_across_sessions(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t) / "repo"; root.mkdir(); make_repo(root)
            ledger = FailureLedger(Path(t) / "ledger.jsonl")
            bad = Candidate("calc.py", "def add(a, b): return a * b\n")
            r1 = loop(lambda c: [bad], ledger=ledger, max_rounds=2).run(root, "fix add", "task1")
            statuses = [a.status for a in r1.attempts]
            self.assertEqual(statuses, ["failed", "rejected_duplicate"])
            r2 = loop(lambda c: [bad], ledger=ledger, max_rounds=1).run(root, "fix add", "task1")
            self.assertEqual(r2.attempts[0].status, "rejected_duplicate")

    def test_regression_is_detected_and_ranked_below_clean_partial(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            (root / "calc.py").write_text("def add(a, b): return a - b\ndef mul(a, b): return a * b\n")
            (root / "tests").mkdir()
            (root / "tests" / "test_calc.py").write_text(
                "from calc import add, mul\n"
                "def test_add(): assert add(2, 3) == 5\n"
                "def test_mul(): assert mul(2, 3) == 6\n")
            fixes_add_breaks_mul = Candidate("calc.py", "def add(a, b): return a + b\ndef mul(a, b): return 0\n")
            does_nothing_useful = Candidate("calc.py", "def add(a, b): return a - b\ndef mul(a, b): return a * b\n" + "".join(f"def _pad{i}(): pass\n" for i in range(6)))
            r = loop(lambda c: [fixes_add_breaks_mul, does_nothing_useful], max_rounds=1).run(root, "fix")
            self.assertFalse(r.resolved)
            a0, a1 = r.attempts
            self.assertEqual(a0.regressions, ["tests/test_calc.py::test_mul"])
            self.assertEqual(a0.fixed_tests, ["tests/test_calc.py::test_add"])
            self.assertEqual(a1.regressions, [])
            self.assertEqual(r.best, a1)  # clean no-regression attempt outranks regressing one
            self.assertEqual(r.stop_reason, "exhausted")

    def test_protected_test_files_cannot_be_edited_to_pass(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); make_repo(root)
            cheat = Candidate("tests/test_calc.py", "def test_add(): pass\n")
            r = loop(lambda c: [cheat], max_rounds=1).run(root, "fix")
            self.assertEqual(r.attempts[0].status, "rejected_protected")
            self.assertFalse(r.resolved)
            self.assertIsNone(r.best)

    def test_invalid_syntax_and_traversal_are_rejected_not_fatal(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); make_repo(root)
            gen = lambda c: [Candidate("calc.py", "def broken(:\n"),
                             Candidate("../outside.py", "x=1\n"),
                             Candidate("calc.py", "def add(a, b): return a - b\n"),  # no-op
                             Candidate("calc.py", "def add(a, b): return a + b\n")]
            r = loop(gen, max_rounds=1).run(root, "fix")
            self.assertEqual([a.status for a in r.attempts],
                             ["rejected_invalid", "rejected_invalid", "rejected_invalid", "passed"])
            self.assertTrue(r.resolved)

    def test_budgets_are_enforced(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); make_repo(root)
            many = lambda c: [Candidate("calc.py", f"def add(a, b): return a * {i + 7}\n") for i in range(8)]
            r = loop(many, max_rounds=1, max_candidates_per_round=2).run(root, "fix")
            self.assertEqual(len(r.attempts), 2)
            with self.assertRaises(ValueError):
                CodingResearchLoop(many, max_rounds=11)
            with self.assertRaises(ValueError):
                CodingResearchLoop(many, max_candidates_per_round=9)
            r = loop(lambda c: [Candidate("calc.py", "def add(a, b): return a * 9\n")],
                     max_rounds=3, time_budget_seconds=0).run(root, "fix", "tb")
            self.assertEqual(r.stop_reason, "time_budget")

    def test_generator_exception_is_reported(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); make_repo(root)
            def boom(ctx): raise RuntimeError("model offline")
            r = loop(boom).run(root, "fix")
            self.assertEqual(r.stop_reason, "generator_error")
            self.assertTrue(any("model offline" in n for n in r.notes))
            self.assertTrue(r.original_tree_unchanged)

    def test_ledger_detects_tampering(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t) / "repo"; root.mkdir(); make_repo(root)
            lp = Path(t) / "ledger.jsonl"
            loop(lambda c: [Candidate("calc.py", "def add(a, b): return a * 3\n")],
                 ledger=FailureLedger(lp), max_rounds=1).run(root, "fix", "x")
            lp.write_text(lp.read_text().replace('"failed"', '"passed"'))
            with self.assertRaises(ValueError):
                FailureLedger(lp).records()

    def test_procedure_recorded_only_when_resolved(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t) / "repo"; root.mkdir(); make_repo(root)
            store = ProcedureStore(Path(t) / "proc.jsonl")
            loop(lambda c: [Candidate("calc.py", "def add(a, b): return a * 3\n")],
                 procedures=store, max_rounds=1).run(root, "fix")
            self.assertEqual(store.list_records(), [])
            loop(lambda c: [Candidate("calc.py", "def add(a, b): return a + b\n")],
                 procedures=store, max_rounds=1).run(root, "fix")
            recs = store.list_records()
            self.assertEqual(len(recs), 1)
            self.assertEqual(recs[0]["task_type"], "repair_research")

    def test_collection_error_never_counts_as_clean(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); make_repo(root)
            # candidate removes `add`, so test collection/import fails
            r = loop(lambda c: [Candidate("calc.py", "def other(): return 1\n")], max_rounds=1).run(root, "fix")
            self.assertEqual(r.attempts[0].status, "failed")
            self.assertGreaterEqual(r.attempts[0].n_failed, 1)
            self.assertFalse(r.resolved)


class ParseTests(unittest.TestCase):
    def test_unparsable_nonzero_run_is_never_clean(self):
        from asm.coding.research import _parse_run
        failed, n_failed, n_passed = _parse_run({"returncode": 2, "stdout": "", "stderr": "usage: boom"})
        self.assertEqual((failed, n_failed, n_passed), ([], 1, 0))
        failed, n_failed, n_passed = _parse_run({"returncode": 1, "stdout":
            "FAILED tests/t.py::a - x\nERROR tests/t.py::b\n2 failed, 3 passed, 1 error in 0.1s", "stderr": ""})
        self.assertEqual(failed, ["tests/t.py::a", "tests/t.py::b"])
        self.assertEqual((n_failed, n_passed), (3, 3))


if __name__ == "__main__":
    unittest.main()


class CodingAgentIntegrationTests(unittest.TestCase):
    def test_agent_research_entry_point_end_to_end(self):
        from asm.coding import CodingAgent
        with tempfile.TemporaryDirectory() as t:
            root = Path(t) / "repo"; root.mkdir(); make_repo(root)
            agent = CodingAgent(test_runner=TestRunner(timeout_seconds=20))
            before = tree_fingerprint(root)
            gen = lambda c: [Candidate("calc.py", "def add(a, b): return a + b\n", "fix")]
            r = agent.research(root, "fix add", gen, ledger_path=Path(t) / "l.jsonl",
                               procedures_path=Path(t) / "p.jsonl", max_rounds=1)
            self.assertTrue(r.resolved)
            self.assertEqual(tree_fingerprint(root), before)
            self.assertEqual(len(ProcedureStore(Path(t) / "p.jsonl").list_records()), 1)
            self.assertEqual(agent.inspect(root, "x").policy["automatic_file_writes"], False)
