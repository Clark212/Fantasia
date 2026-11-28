"""DEV34 tests: the two fixes to DEV33's regression suite (stable test ids; suite runs bounded by the remaining time)."""
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from asm.coding.faultloc import RepairWorkflow, _stable_id  # noqa: E402
from test_alpha8_dev33 import FILES, RIGHT, WRONG, StubKnowledge  # noqa: E402

LAMBDA_IDS = ("import pytest\nfrom m import f\n\n@pytest.mark.parametrize('g', [lambda n: n], ids=repr)\n"
              "def test_param(g):\n    assert f(2) == 'two' and g(1) == 1\n")


class FixTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        for name, text in FILES.items():
            (Path(self.td.name) / name).parent.mkdir(parents=True, exist_ok=True)
            (Path(self.td.name) / name).write_text(text)

    def tearDown(self):
        self.td.cleanup()

    def run_workflow(self, budget, *modules):
        return RepairWorkflow(time_budget_seconds=budget, knowledge=StubKnowledge(*modules), max_iterations=1,
                              regression_suite=["tests"]).run(self.td.name, ["tests/test_m.py"])

    def test_stable_id(self):
        self.assertEqual(_stable_id("t.py::test[<function <lambda> at 0x7f8d24c3ac00>-kwargs0]"), "t.py::test[<function <lambda> at 0x?>-kwargs0]")
        self.assertEqual(_stable_id("t.py::test_plain[1-2]"), "t.py::test_plain[1-2]")

    def test_a_parametrized_id_with_an_address_is_the_same_test_in_every_run(self):
        # DEV33's feedparser-1: the id changed between runs, so the right patch looked like it broke the test
        (Path(self.td.name) / "tests" / "test_lambda.py").write_text(LAMBDA_IDS)
        d = self.run_workflow(120, WRONG, RIGHT)
        self.assertEqual(d.status, "resolved")
        self.assertIn("'one' if n == 1 else None", d.diff)
        self.assertEqual(d.reasons.get("rejected_regression_suite"), 1)  # only the wrong patch

    def test_suite_runs_are_bounded_by_the_remaining_time(self):
        # DEV33's markdown-it-py-2: a slow suite run after a rejection took the run past its budget
        (Path(self.td.name) / "tests" / "test_slow.py").write_text("import time\n\ndef test_slow():\n    time.sleep(40)\n")
        t0 = time.monotonic()
        self.run_workflow(60, WRONG, RIGHT)  # the baseline suite run takes 40 s; a candidate's would take 40 s more
        self.assertLess(time.monotonic() - t0, 60 + 15)


if __name__ == "__main__":
    unittest.main()
