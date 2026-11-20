"""DEV8.1 hardening regression tests: one or more tests per new capability."""
import json
import multiprocessing
import os
import socket
import tempfile
import textwrap
import threading
import time
import unittest
import uuid
from pathlib import Path

from asm.coding import Candidate, CodingResearchLoop, FailureLedger, ProcedureStore, tree_fingerprint
from asm.coding.research import (Attempt, RANK_CRITERIA, compare_attempts, compare_outcomes, rank_key)
from asm.coding.sandbox import SafeTestRunner, classify, copy_repo, new_risks, normalized_sha256, scan_risk

GOOD = "def add(a, b): return a + b\n"
BAD = "def add(a, b): return a - b\n"
FORK = "fork" in multiprocessing.get_all_start_methods() and os.name == "posix"


def make_repo(root: Path, src=BAD, tests=None):
    (root / "calc.py").write_text(src)
    (root / "tests").mkdir(exist_ok=True)
    (root / "tests" / "test_calc.py").write_text(tests or (
        "from calc import add\n"
        "def test_add(): assert add(2, 3) == 5\n"
        "def test_zero(): assert add(0, 0) == 0\n"))


def loop(gen, **kw):
    kw.setdefault("test_runner", SafeTestRunner(timeout_seconds=20))
    return CodingResearchLoop(gen, **kw)


def alive(pid: int) -> bool:
    try:
        state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
        return state != "Z"
    except (OSError, IndexError):
        return False


def run_tests(files: dict, **runner_kw):
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    for rel, src in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(src))
    kw = {"timeout_seconds": 20}
    kw.update(runner_kw)
    with tmp:
        return SafeTestRunner(**kw).run_pytest(root)


# =========================================================== 1. time budgets
class TimeBudgetTests(unittest.TestCase):
    def test_thread_generator_timeout_stops_run_quickly(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); make_repo(root)
            r = loop(lambda c: time.sleep(30) or [], generator_timeout_seconds=0.6, time_budget_seconds=60,
                     baseline_runs=1).run(root, "fix")
            self.assertEqual(r.stop_reason, "generator_timeout")
            self.assertLess(r.elapsed_seconds, 8)
            self.assertTrue(any("abandoned" in n for n in r.notes))
            self.assertTrue(r.original_tree_unchanged)

    @unittest.skipUnless(FORK, "needs fork")
    def test_process_generator_timeout_kills_the_generator(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t) / "repo"; root.mkdir(); make_repo(root)
            pidfile = Path(t) / "pid"

            def gen(ctx):
                pidfile.write_text(str(os.getpid()))
                time.sleep(60)
                return []
            r = loop(gen, generator_isolation="process", generator_timeout_seconds=1.0,
                     time_budget_seconds=60, baseline_runs=1).run(root, "fix")
            self.assertEqual(r.stop_reason, "generator_timeout")
            self.assertTrue(any("process killed" in n for n in r.notes))
            time.sleep(0.3)
            self.assertFalse(alive(int(pidfile.read_text())))

    @unittest.skipUnless(FORK, "needs fork")
    def test_process_generator_works_end_to_end_and_propagates_errors(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); make_repo(root)
            r = loop(lambda c: [Candidate("calc.py", GOOD, "ok")], generator_isolation="process",
                     max_rounds=1, baseline_runs=1).run(root, "fix")
            self.assertTrue(r.resolved)

            def boom(c): raise RuntimeError("model crashed")
            r = loop(boom, generator_isolation="process", baseline_runs=1).run(root, "fix")
            self.assertEqual(r.stop_reason, "generator_error")
            self.assertTrue(any("model crashed" in n for n in r.notes))

    def test_global_budget_bounds_a_generator_with_a_longer_own_timeout(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); make_repo(root)
            r = loop(lambda c: time.sleep(60) or [], generator_timeout_seconds=60, time_budget_seconds=4,
                     baseline_runs=1).run(root, "fix")
            self.assertEqual(r.stop_reason, "time_budget")
            self.assertLess(r.budget_overrun_seconds, 2.0)

    def test_hanging_candidate_times_out_is_ledgered_and_does_not_hang_the_run(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t) / "repo"; root.mkdir(); make_repo(root)
            ledger = FailureLedger(Path(t) / "l.jsonl")
            hang = Candidate("calc.py", "import time\ntime.sleep(60)\ndef add(a, b): return a + b\n")
            r = loop(lambda c: [hang], ledger=ledger, candidate_timeout_seconds=1.0, max_rounds=1,
                     baseline_runs=1).run(root, "fix", "t")
            a = r.attempts[0]
            self.assertEqual((a.status, a.budget_cut), ("timed_out", False))
            self.assertLess(r.elapsed_seconds, 15)
            self.assertEqual([x["status"] for x in ledger.records("t")], ["timed_out"])

    def test_budget_cut_candidate_is_not_recorded_as_a_failure(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t) / "repo"; root.mkdir(); make_repo(root)
            ledger = FailureLedger(Path(t) / "l.jsonl")
            slow = Candidate("calc.py", "import time\ntime.sleep(60)\ndef add(a, b): return a + b\n")
            r = loop(lambda c: [slow], ledger=ledger, time_budget_seconds=5, baseline_runs=1).run(root, "fix", "t")
            self.assertEqual(r.stop_reason, "time_budget")
            self.assertTrue(r.attempts[0].budget_cut)
            self.assertEqual(ledger.records("t"), [])  # cut short by us, not a property of the candidate
            self.assertLess(r.budget_overrun_seconds, 2.0)

    def test_baseline_has_its_own_timeout(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            make_repo(root, tests="import time\ndef test_slow(): time.sleep(60)\n")
            called = []
            r = loop(lambda c: called.append(1) or [], baseline_timeout_seconds=1.0,
                     time_budget_seconds=60).run(root, "fix")
            self.assertEqual((r.stop_reason, called), ("baseline_timeout", []))
            self.assertLess(r.elapsed_seconds, 6)

    def test_zero_budget_stops_before_any_work(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); make_repo(root)
            called = []
            r = loop(lambda c: called.append(1) or [], time_budget_seconds=0).run(root, "fix")
            self.assertEqual((r.stop_reason, called, r.attempts), ("time_budget", [], []))

    def test_invalid_option_values_rejected(self):
        for kw in ({"baseline_runs": 0}, {"baseline_runs": 6}, {"confirm_runs": 4},
                   {"generator_isolation": "magic"}, {"generator_timeout_seconds": 0}, {"time_budget_seconds": -1}):
            with self.assertRaises(ValueError):
                CodingResearchLoop(lambda c: [], **kw)


# ============================================================ 2. baseline
class BaselineTests(unittest.TestCase):
    def test_flaky_baseline_is_detected_and_blocks_candidate_evaluation(self):
        marker = Path(tempfile.gettempdir()) / f"asm_flaky_{uuid.uuid4().hex}"
        try:
            with tempfile.TemporaryDirectory() as t:
                root = Path(t)
                make_repo(root, tests=f"import os\nM = {str(marker)!r}\n"
                          "def test_flaky():\n    if os.path.exists(M): return\n    open(M, 'w').close()\n    assert False\n")
                called = []
                r = loop(lambda c: called.append(1) or [], baseline_runs=2).run(root, "fix")
                self.assertEqual((r.stop_reason, called), ("baseline_unstable", []))
                self.assertEqual(r.baseline["flaky_tests"], ["tests/test_calc.py::test_flaky"])
                self.assertFalse(r.baseline["stable"])
        finally:
            marker.unlink(missing_ok=True)

    def test_no_tests_collected_is_not_treated_as_a_repair_task(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); make_repo(root, tests="def helper(): pass\n")
            called = []
            r = loop(lambda c: called.append(1) or []).run(root, "fix")
            self.assertEqual((r.stop_reason, called), ("no_tests_collected", []))

    def test_unusable_baseline_is_reported_as_error(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); make_repo(root)
            (root / "pytest.ini").write_text("[pytest]\naddopts = --definitely-not-an-option\n")
            r = loop(lambda c: [], baseline_runs=1).run(root, "fix")
            self.assertEqual(r.stop_reason, "baseline_error")
            self.assertEqual(r.baseline["runs"][0]["classification"], "usage_error")

    def test_collection_error_baseline_is_repairable_and_credited(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); make_repo(root, src="import missing_module_zz\n" + GOOD)
            r = loop(lambda c: [Candidate("calc.py", GOOD, "drop bad import")], max_rounds=1,
                     baseline_runs=1).run(root, "fix")
            self.assertEqual(r.baseline_failures, ["tests/test_calc.py"])
            self.assertTrue(r.resolved)
            self.assertEqual(r.best.fixed_tests, ["tests/test_calc.py"])

    def test_flaky_pass_is_not_accepted_but_is_with_confirmation_disabled(self):
        marker = Path(tempfile.gettempdir()) / f"asm_first_{uuid.uuid4().hex}"
        src = (f"import os\nM = {str(marker)!r}\n_first = not os.path.exists(M)\n"
               "if _first:\n    open(M, 'w').close()\n"
               "def add(a, b): return a + b if _first else a - b\n")
        try:
            with tempfile.TemporaryDirectory() as t:
                root = Path(t); make_repo(root)
                r = loop(lambda c: [Candidate("calc.py", src)], max_rounds=1, baseline_runs=1).run(root, "fix")
                self.assertEqual(r.attempts[0].status, "unconfirmed_pass")
                self.assertFalse(r.attempts[0].confirmed)
                self.assertFalse(r.resolved)
                marker.unlink(missing_ok=True)
                r = loop(lambda c: [Candidate("calc.py", src)], max_rounds=1, baseline_runs=1,
                         confirm_runs=0).run(root, "fix")
                self.assertEqual(r.attempts[0].status, "passed")  # shows what confirmation protects against
        finally:
            marker.unlink(missing_ok=True)

    def test_baseline_report_records_runs_and_isolation(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); make_repo(root)
            r = loop(lambda c: [Candidate("calc.py", GOOD)], max_rounds=1).run(root, "fix")
            self.assertEqual(len(r.baseline["runs"]), 2)
            self.assertTrue(r.baseline["stable"])
            self.assertEqual(r.baseline["runs"][0]["failed_ids"], ["tests/test_calc.py::test_add"])
            self.assertTrue(r.isolation["env_scrubbed"])
            self.assertFalse(r.isolation["os_sandbox"])  # honesty flag: this is not an OS sandbox


# ================================================================ 3. compare
class ComparisonTests(unittest.TestCase):
    def test_compare_outcomes_unit(self):
        base = {"a": "failed", "b": "passed", "c": "passed", "d": "passed", "col": "error"}
        cand = {"a": "passed", "b": "failed", "c": "skipped", "new": "failed"}
        out = compare_outcomes(base, cand)
        self.assertEqual(out["fixed"], ["a", "col"])
        self.assertEqual(out["regressions"], ["b", "new"])
        self.assertEqual(out["vanished"], ["d"])
        self.assertEqual(out["newly_skipped"], ["c"])

    def test_module_skipped_away_is_rejected_not_accepted_as_a_pass(self):
        tests = ("import pytest\ncalc = pytest.importorskip('calc')\n"
                 "def test_add(): assert calc.add(2, 3) == 5\ndef test_zero(): assert calc.add(0, 0) == 0\n")
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); make_repo(root, tests=tests)
            r = loop(lambda c: [Candidate("calc.py", "raise ModuleNotFoundError('gone')\n")], max_rounds=1,
                     baseline_runs=1).run(root, "fix")
            a = r.attempts[0]
            self.assertEqual(a.status, "rejected_test_loss")
            self.assertEqual(sorted(a.vanished_tests), ["tests/test_calc.py::test_add", "tests/test_calc.py::test_zero"])
            self.assertFalse(r.resolved)

    def test_newly_skipped_test_is_rejected(self):
        tests = ("import pytest\nfrom calc import add, ENABLED\n"
                 "def test_add(): assert add(2, 3) == 5\n"
                 "def test_zero():\n    if not ENABLED: pytest.skip('off')\n    assert add(0, 0) == 0\n")
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); make_repo(root, src="ENABLED = True\n" + BAD, tests=tests)
            r = loop(lambda c: [Candidate("calc.py", "ENABLED = False\n" + GOOD)], max_rounds=1,
                     baseline_runs=1).run(root, "fix")
            self.assertEqual(r.attempts[0].status, "rejected_test_loss")
            self.assertEqual(r.attempts[0].newly_skipped, ["tests/test_calc.py::test_zero"])
            self.assertFalse(r.resolved)

    def test_rank_order_and_explanations(self):
        def A(status="failed", **kw):
            a = Attempt(1, 0, "x.py", "s", status)
            a.n_failed = kw.pop("n_failed", 1)
            for k, v in kw.items():
                setattr(a, k, v)
            return a
        passed = A("passed", n_failed=0, diff_lines=50)
        vanished = A(vanished_tests=["t"])
        regress = A(regressions=["t"])
        skipped = A(newly_skipped=["t"])
        fewer = A(n_failed=1, diff_lines=9)
        more = A(n_failed=2, diff_lines=1)
        small = A(diff_lines=3)
        big = A(diff_lines=30)
        ordered = sorted([vanished, big, regress, more, passed, skipped, small, fewer], key=rank_key)
        self.assertIs(ordered[0], passed)
        self.assertEqual(compare_attempts(passed, regress)["decided_by"], "not_accepted")
        self.assertEqual(compare_attempts(regress, vanished)["decided_by"], "vanished_tests")
        self.assertEqual(compare_attempts(small, regress)["decided_by"], "regressions")
        self.assertEqual(compare_attempts(small, skipped)["decided_by"], "new_skips")
        self.assertEqual(compare_attempts(fewer, more)["decided_by"], "failing_tests")
        self.assertEqual(compare_attempts(small, big)["decided_by"], "diff_lines")
        self.assertEqual(compare_attempts(small, small)["winner"], "tie")
        self.assertEqual(list(RANK_CRITERIA).index("regressions"), 2)

    def test_leaderboard_in_a_real_run_explains_the_ordering(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            make_repo(root, src="def add(a, b): return a - b\ndef mul(a, b): return a * b\n",
                      tests="from calc import add, mul\ndef test_add(): assert add(2, 3) == 5\n"
                            "def test_mul(): assert mul(2, 3) == 6\n")
            breaks = Candidate("calc.py", "def add(a, b): return a + b\ndef mul(a, b): return 0\n")
            nothing = Candidate("calc.py", "def add(a, b): return a - b\ndef mul(a, b): return a * b\n"
                                + "".join(f"def _p{i}(): pass\n" for i in range(6)))
            r = loop(lambda c: [breaks, nothing], max_rounds=1, baseline_runs=1).run(root, "fix")
            self.assertEqual([row["regressions"] for row in r.leaderboard], [0, 1])
            self.assertEqual(r.leaderboard[0]["ahead_of_next_by"], "regressions")
            self.assertIsNone(r.leaderboard[1]["ahead_of_next_by"])


# ========================================================== 4. failure memory
class FailureMemoryTests(unittest.TestCase):
    CALC3 = ("def add(a, b): return a - b\ndef sub(a, b): return a + b\ndef mul(a, b): return a * b\n")
    TESTS3 = ("from calc import add, sub, mul\ndef test_add(): assert add(2, 3) == 5\n"
              "def test_sub(): assert sub(5, 3) == 2\ndef test_mul(): assert mul(2, 3) == 6\n")

    def test_feedback_between_rounds_is_structured_and_factual(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); make_repo(root, src=self.CALC3, tests=self.TESTS3)
            seen = []

            def gen(ctx):
                seen.append(ctx)
                if ctx.round == 1:  # fixes add, breaks mul, leaves sub
                    return [Candidate("calc.py", "def add(a, b): return a + b\ndef sub(a, b): return a + b\n"
                                                 "def mul(a, b): return 0\n")]
                return [Candidate("calc.py", "def add(a, b): return a + b\ndef sub(a, b): return a - b\n"
                                             "def mul(a, b): return a * b\n")]
            r = loop(gen, max_rounds=2, baseline_runs=1).run(root, "fix")
            self.assertTrue(r.resolved)
            fb = seen[1].feedback
            self.assertEqual(fb["tried"][0]["status"], "failed")
            self.assertEqual(fb["tried"][0]["fixed"], ["tests/test_calc.py::test_add"])
            self.assertEqual(fb["still_failing"], ["tests/test_calc.py::test_sub"])
            self.assertEqual(fb["regression_culprits"], [{"test": "tests/test_calc.py::test_mul", "broken_by_attempts": 1}])
            self.assertEqual(fb["partial_progress"], {"tests/test_calc.py::test_add": ["r1#0"]})
            self.assertEqual(fb["budget_remaining"]["rounds"], 1)
            self.assertGreater(fb["budget_remaining"]["seconds"], 0)
            self.assertTrue(fb["protected"]["tests"])
            self.assertIn("pytest.ini", fb["protected"]["config_files"])
            self.assertEqual(seen[0].feedback["tried"], [])
            self.assertEqual(r.feedback["still_failing"], [])  # round 2 fixed everything: nothing left
            self.assertEqual(sorted(r.feedback["partial_progress"]),
                             ["tests/test_calc.py::test_add", "tests/test_calc.py::test_sub"])

    def test_repeated_failure_modes_are_counted(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); make_repo(root)
            gen = lambda c: [Candidate("calc.py", "def add(a, b): return a * b\n"),
                             Candidate("calc.py", "def add(a, b): return (a * b) + 0\n")]
            r = loop(gen, max_rounds=1, baseline_runs=1).run(root, "fix")
            modes = r.feedback["failure_modes"]
            self.assertEqual(len(modes), 1)
            self.assertEqual(modes[0]["count"], 2)
            self.assertTrue(modes[0]["signature"].startswith("AssertionError:"))

    def test_formatting_only_variant_of_a_failed_candidate_is_a_duplicate(self):
        a = Candidate("calc.py", "def add(a, b): return a * b\n")
        b = Candidate("calc.py", "# retry\ndef add(a,   b):\n    return a*b  # same\n")
        with tempfile.TemporaryDirectory() as t:
            root = Path(t) / "repo"; root.mkdir(); make_repo(root)
            ledger = FailureLedger(Path(t) / "l.jsonl")
            r = loop(lambda c: [a, b], ledger=ledger, max_rounds=1, baseline_runs=1).run(root, "fix", "k")
            self.assertEqual([x.status for x in r.attempts], ["failed", "rejected_duplicate"])
            self.assertEqual(normalized_sha256(a.replacement), normalized_sha256(b.replacement))
            r2 = loop(lambda c: [b], ledger=ledger, max_rounds=1, baseline_runs=1).run(root, "fix", "k")
            self.assertEqual(r2.attempts[0].status, "rejected_duplicate")  # across sessions

    def test_formatting_only_variant_is_caught_within_a_session_without_any_ledger(self):
        a = Candidate("calc.py", "def add(a, b): return a * b\n")
        b = Candidate("calc.py", "def add(a,  b):\n    return a*b   # same code\n")
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); make_repo(root)
            r = loop(lambda c: [a, b], max_rounds=1, baseline_runs=1).run(root, "fix")  # no ledger
            self.assertEqual([x.status for x in r.attempts], ["failed", "rejected_duplicate"])

    def test_formatting_only_change_to_current_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); make_repo(root)
            r = loop(lambda c: [Candidate("calc.py", "# note\ndef add(a,b):\n    return a-b\n")],
                     max_rounds=1, baseline_runs=1).run(root, "fix")
            self.assertEqual(r.attempts[0].status, "rejected_invalid")
            self.assertIn("formatting", r.attempts[0].detail)

    def test_failure_from_a_different_repo_state_is_stale_and_does_not_block(self):
        bad = Candidate("calc.py", "def add(a, b): return a * b\n")
        with tempfile.TemporaryDirectory() as t:
            root = Path(t) / "repo"; root.mkdir(); make_repo(root)
            ledger = FailureLedger(Path(t) / "l.jsonl")
            loop(lambda c: [bad], ledger=ledger, max_rounds=1, baseline_runs=1).run(root, "fix", "k")
            (root / "other.py").write_text("X = 1\n")  # repository state changes
            seen = []
            r = loop(lambda c: seen.append(c) or [bad], ledger=ledger, max_rounds=1, baseline_runs=1).run(root, "fix", "k")
            self.assertEqual(r.attempts[0].status, "failed")  # re-evaluated, not skipped as a duplicate
            self.assertTrue(seen[0].prior_failures[0]["stale"])
            self.assertEqual(seen[0].feedback["previous_sessions"]["stale_for_this_repo_state"], 1)

    def test_ledger_records_carry_the_new_evidence_fields(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t) / "repo"; root.mkdir(); make_repo(root)
            ledger = FailureLedger(Path(t) / "l.jsonl")
            loop(lambda c: [Candidate("calc.py", "def add(a, b): return a * b\n", "why")], ledger=ledger,
                 max_rounds=1, baseline_runs=1).run(root, "fix", "k")
            rec = ledger.records("k")[0]
            self.assertEqual(rec["schema"], 2)
            for key in ("normalized_sha256", "repo_fingerprint", "base_sha256", "error_signature", "fixed_tests",
                        "regressions", "round", "reason"):
                self.assertIn(key, rec)
            self.assertEqual(rec["reason"], "why")

    def test_ledger_tolerates_torn_tail_rejects_corruption_and_reads_legacy_records(self):
        with tempfile.TemporaryDirectory() as t:
            lp = Path(t) / "l.jsonl"
            ledger = FailureLedger(lp)
            legacy = {"timestamp": 1.0, "task_id": "k", "path": "calc.py", "replacement_sha256": "abc",
                      "status": "failed", "failed_tests": [], "exceptions": [], "detail": ""}
            legacy["record_sha256"] = FailureLedger._digest(legacy)
            lp.write_text(json.dumps(legacy, sort_keys=True) + "\n" + '{"task_id": "k", "pa')  # torn final line
            self.assertEqual(len(ledger.records()), 1)
            self.assertTrue(ledger.torn_tail)
            self.assertTrue(ledger.has_failed("k", "calc.py", "abc", repo_fingerprint="whatever"))  # legacy blocks
            a = Attempt(1, 0, "calc.py", "def456", "failed")
            ledger.append("k", a, "fp")
            self.assertEqual(len(ledger.records()), 2)  # torn tail healed, new record intact
            lines = lp.read_text().splitlines()
            lp.write_text("garbage\n" + "\n".join(lines[:1]) + "\n")
            with self.assertRaises(ValueError):
                ledger.records()

    def test_concurrent_appends_stay_valid(self):
        with tempfile.TemporaryDirectory() as t:
            ledger = FailureLedger(Path(t) / "l.jsonl")

            def work(n):
                for i in range(10):
                    ledger.append("k", Attempt(1, i, "c.py", f"{n}-{i}", "failed"), "fp")
            threads = [threading.Thread(target=work, args=(n,)) for n in range(8)]
            [x.start() for x in threads]; [x.join() for x in threads]
            self.assertEqual(len(ledger.records()), 80)


# ============================================================== 5. safety
class SandboxTests(unittest.TestCase):
    def test_environment_is_scrubbed_and_home_is_disposable(self):
        probe = f"asm_probe_{uuid.uuid4().hex}"
        os.environ["ASM_SECRET_TOKEN"] = "s3cr3t"
        try:
            run = run_tests({"tests/test_env.py": f"""
                import os
                def test_env():
                    assert "ASM_SECRET_TOKEN" not in os.environ
                    assert os.environ["PYTHONHASHSEED"] == "0"
                    open(os.path.expanduser("~/{probe}"), "w").write("x")
                """})
            self.assertEqual(run.classification, "passed")
            self.assertFalse((Path.home() / probe).exists())
        finally:
            os.environ.pop("ASM_SECRET_TOKEN", None)
            (Path.home() / probe).unlink(missing_ok=True)

    def test_network_isolation_when_available(self):
        report = SafeTestRunner().isolation_report()
        if not report["network"].startswith("isolated") or {n for _, n in socket.if_nameindex()} <= {"lo"}:
            self.skipTest("network namespace isolation unavailable, or host has only loopback")
        files = {"tests/test_net.py": """
            import socket
            def test_only_loopback():
                assert {n for _, n in socket.if_nameindex()} <= {"lo"}
            """}
        self.assertEqual(run_tests(files).classification, "passed")
        self.assertEqual(run_tests(files, network="allow").classification, "tests_failed")

    def test_timeout_kills_grandchildren(self):
        pidfile = Path(tempfile.gettempdir()) / f"asm_gc_{uuid.uuid4().hex}"
        run = run_tests({"tests/test_hang.py": f"""
            import subprocess, time
            def test_hang():
                p = subprocess.Popen(["sleep", "60"])
                open({str(pidfile)!r}, "w").write(str(p.pid))
                time.sleep(60)
            """}, timeout_seconds=2)
        self.assertTrue(run.timed_out)
        pid = int(pidfile.read_text())
        pidfile.unlink()
        time.sleep(0.3)
        self.assertFalse(alive(pid))

    def test_stray_background_process_is_killed_after_a_passing_run(self):
        run = run_tests({"tests/test_stray.py": """
            import subprocess
            def test_leaves_child():
                p = subprocess.Popen(["sleep", "60"])
                print("PID", p.pid, flush=True)
                open("/tmp/asm_stray_pid", "w").write(str(p.pid))
            """})
        pid = int(Path("/tmp/asm_stray_pid").read_text())
        Path("/tmp/asm_stray_pid").unlink()
        self.assertEqual(run.classification, "passed")
        self.assertTrue(run.stray_processes_killed)
        time.sleep(0.3)
        self.assertFalse(alive(pid))

    def test_memory_limit_turns_a_runaway_allocation_into_a_failure(self):
        started = time.monotonic()
        run = run_tests({"tests/test_mem.py": "def test_mem():\n    bytearray(3 * 1024**3)\n"}, memory_mb=512)
        self.assertEqual(run.classification, "tests_failed")
        self.assertIn("MemoryError", run.stdout)
        self.assertLess(time.monotonic() - started, 15)

    def test_cpu_limit_kills_a_busy_loop(self):
        started = time.monotonic()
        run = run_tests({"tests/test_cpu.py": "def test_spin():\n    while True: pass\n"},
                        timeout_seconds=60, cpu_seconds=1)
        self.assertEqual((run.classification, run.exceeded), ("crashed", "cpu"))
        self.assertFalse(run.timed_out)
        self.assertLess(time.monotonic() - started, 20)

    def test_file_size_limit_is_enforced_and_output_is_truncated(self):
        run = run_tests({"tests/test_big.py": """
            def test_cannot_write_big_files():
                try:
                    open("big.bin", "wb").write(b"x" * (5 * 1024 * 1024))
                except OSError:
                    return
                raise AssertionError("size limit not enforced")
            def test_noisy():
                print("y" * 100000)
                assert False
            """}, max_output_mb=2, output_limit=2000)
        self.assertEqual(run.outcome["tests/test_big.py::test_cannot_write_big_files"], "passed")
        self.assertLessEqual(len(run.stdout), 2000)

    def test_symlinks_are_not_copied_so_tests_cannot_write_through_them(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t) / "repo"; root.mkdir(); make_repo(root)
            outside = Path(t) / "outside.txt"
            outside.write_text("original")
            os.symlink(outside, root / "link.txt")
            os.symlink(Path(t), root / "linkdir")
            dest = Path(t) / "copy"
            skipped = copy_repo(root, dest)
            self.assertEqual(skipped, ["link.txt", "linkdir"])
            self.assertFalse((dest / "link.txt").exists() or (dest / "link.txt").is_symlink())
            (root / "tests" / "test_w.py").write_text("def test_w():\n    open('link.txt', 'w').write('PWNED')\n")
            r = loop(lambda c: [], baseline_runs=1).run(root, "fix")
            self.assertEqual(outside.read_text(), "original")
            self.assertEqual(r.baseline["skipped_symlinks"], ["link.txt", "linkdir"])
            self.assertTrue(r.original_tree_unchanged)

    def test_hostile_test_writing_into_its_copy_never_touches_the_original(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); make_repo(root)
            (root / "tests" / "test_x.py").write_text(
                "def test_x():\n    open('calc.py', 'w').write('boom')\n    open('new.txt', 'w').write('x')\n")
            before = tree_fingerprint(root)
            r = loop(lambda c: [], baseline_runs=1).run(root, "fix")
            self.assertEqual(tree_fingerprint(root), before)
            self.assertTrue(r.original_tree_unchanged)

    def test_degrades_gracefully_and_honestly_when_network_isolation_is_unavailable(self):
        saved = SafeTestRunner._net_probe
        SafeTestRunner._net_probe = (None, "unavailable")
        try:
            run = run_tests({"tests/test_ok.py": "def test_ok(): pass\n"})
            self.assertEqual(run.classification, "passed")
            self.assertIn("NOT isolated", run.isolation["network"])
            self.assertIsNone(SafeTestRunner().isolation_report()["network_method"])
        finally:
            SafeTestRunner._net_probe = saved

    def test_process_isolation_without_fork_falls_back_with_a_note(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); make_repo(root)
            with mock.patch("multiprocessing.get_all_start_methods", return_value=["spawn"]):
                r = loop(lambda c: [Candidate("calc.py", GOOD)], generator_isolation="process",
                         max_rounds=1, baseline_runs=1).run(root, "fix")
            self.assertTrue(r.resolved)
            self.assertTrue(any("fork is unavailable" in n for n in r.notes))

    def test_exit_code_classification(self):
        self.assertEqual([classify(c, False, {}, {}, None) for c in (0, 2, 3, 4, 5, 97, 7)],
                         ["passed", "interrupted", "internal_error", "usage_error",
                          "no_tests", "sandbox_error", "unknown_error"])
        # DEV14: exit code 1 means failed tests only when some test actually ran; with no outcome and no counts it is a
        # startup failure (e.g. a broken conftest), which DEV8 misreported as "tests_failed"
        self.assertEqual(classify(1, False, {"t": "failed"}, {}, None), "tests_failed")
        self.assertEqual(classify(1, False, {}, {}, None), "startup_error")
        self.assertEqual(classify(2, False, {"x": "error"}, {}, None), "collection_error")
        self.assertEqual(classify(None, True, {}, {}, None), "timeout")
        self.assertEqual(classify(-9, False, {}, {}, None), "crashed")

    def test_runner_option_validation_and_legacy_conversion(self):
        from asm.coding import TestRunner
        for kw in ({"timeout_seconds": 0}, {"timeout_seconds": 601}, {"network": "maybe"}):
            with self.assertRaises(ValueError):
                SafeTestRunner(**kw)
        legacy = SafeTestRunner.from_legacy(TestRunner(timeout_seconds=7, output_limit=4000))
        self.assertEqual((legacy.timeout_seconds, legacy.output_limit), (7.0, 4000))
        self.assertIs(SafeTestRunner.from_legacy(legacy), legacy)
        with self.assertRaises(ValueError):
            SafeTestRunner().run_pytest(".", ["../escape"])


class CandidateSafetyTests(unittest.TestCase):
    def run_one(self, src, original=BAD, **kw):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); make_repo(root, src=original)
            r = loop(lambda c: [Candidate("calc.py", src)], max_rounds=1, baseline_runs=1, **kw).run(root, "fix")
            return r.attempts[0]

    def test_newly_introduced_dangerous_constructs_are_rejected(self):
        cases = {
            "network": "import socket\n" + GOOD,
            "process": "import subprocess\n" + GOOD,
            "process_call": "import os\nos.system('true')\n" + GOOD,
            "dynamic": "eval('1')\n" + GOOD,
            "destructive": "import shutil\nshutil.rmtree('/nonexistent-zz')\n" + GOOD,
            "unlink": "from pathlib import Path\nPath('x').unlink()\n" + GOOD,
            "native": "import ctypes\n" + GOOD,
        }
        for name, src in cases.items():
            a = self.run_one(src)
            self.assertEqual(a.status, "rejected_risky", name)
            self.assertTrue(a.risk_flags, name)

    def test_preexisting_risky_code_does_not_block_a_fix(self):
        original = "import subprocess\n" + BAD
        a = self.run_one("import subprocess\n" + GOOD, original=original)
        self.assertEqual(a.status, "passed")

    def test_medium_risk_is_flagged_but_not_blocked_and_overrides_work(self):
        a = self.run_one("import os\nTOKEN = os.environ.get('X')\n" + GOOD)
        self.assertEqual(a.status, "passed")
        self.assertIn("environment", a.risk_flags)
        self.assertEqual(self.run_one("import socket\n" + GOOD, allow_risky=True).status, "passed")
        self.assertEqual(self.run_one("import subprocess\n" + GOOD, block_risk_categories={"network"}).status, "passed")

    def test_risk_scan_unit(self):
        self.assertEqual(scan_risk("import socket, os\nos.system('x')\n")["network"], {"import socket"})
        self.assertEqual(new_risks("import socket\n", "import socket\nimport subprocess\n"),
                         {"process": ["import subprocess"]})
        self.assertEqual(scan_risk("def broken(:\n"), {})
        self.assertIn("fs_write_absolute", scan_risk("open('/etc/x', 'w')\n"))
        self.assertNotIn("fs_write_absolute", scan_risk("open('/etc/x')\n"))

    def test_protected_config_suffix_and_size_limits(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); make_repo(root)
            names = ["pytest.ini", "pyproject.toml", "setup.cfg", "tox.ini", "setup.py", "tests/conftest.py",
                     "conftest.py", "README.md", "data.json"]
            r = loop(lambda c: [Candidate(n, "x") for n in names][:8], max_rounds=1, baseline_runs=1,
                     max_candidates_per_round=8).run(root, "fix")
            self.assertEqual({a.status for a in r.attempts}, {"rejected_protected"})
            self.assertIn("configuration", r.attempts[0].detail)
            self.assertIn("suffix", r.attempts[-1].detail)
            r = loop(lambda c: [Candidate("calc.py", GOOD + "# " + "x" * 500)], max_rounds=1, baseline_runs=1,
                     max_candidate_bytes=100).run(root, "fix")
            self.assertEqual(r.attempts[0].status, "rejected_too_large")
            r = loop(lambda c: [Candidate("pytest.ini", "x")], max_rounds=1, baseline_runs=1,
                     protect_config=False, allowed_suffixes=()).run(root, "fix")
            self.assertNotEqual(r.attempts[0].status, "rejected_protected")

    def test_invalid_generator_items_are_skipped_with_a_note(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); make_repo(root)
            r = loop(lambda c: [42, None, ("calc.py", GOOD, "tuple form")], max_rounds=1, baseline_runs=1).run(root, "fix")
            self.assertTrue(r.resolved)
            self.assertEqual(len([n for n in r.notes if "invalid item" in n]), 2)

    def test_procedure_recorded_only_for_confirmed_resolution(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t) / "repo"; root.mkdir(); make_repo(root)
            store = ProcedureStore(Path(t) / "p.jsonl")
            loop(lambda c: [Candidate("calc.py", "def add(a, b): return a * b\n")], procedures=store,
                 max_rounds=1, baseline_runs=1).run(root, "fix")
            self.assertEqual(store.list_records(), [])
            loop(lambda c: [Candidate("calc.py", GOOD)], procedures=store, max_rounds=1, baseline_runs=1).run(root, "fix")
            rec = store.list_records()
            self.assertEqual(len(rec), 1)
            self.assertIn("confirm", " ".join(rec[0]["procedure"]))


if __name__ == "__main__":
    unittest.main()
