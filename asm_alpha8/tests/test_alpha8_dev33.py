"""DEV33 tests: the opt-in regression suite, tests beyond the failing ones that an accepted patch must keep passing."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
from asm.coding.faultloc import RepairWorkflow  # noqa: E402
from asm.coding.research import Candidate  # noqa: E402

# f(2) already works; f(1) is the bug. Nothing built in writes 'one', so only the learned candidates can repair it.
FILES = {"m.py": "def f(n):\n    if n == 2:\n        return 'two'\n    return None\n",
         "tests/test_m.py": "from m import f\n\ndef test_one():\n    assert f(1) == 'one'\n",
         "tests/test_other.py": "from m import f\n\ndef test_two():\n    assert f(2) == 'two'\n\ndef test_type():\n    assert f(3) is None or isinstance(f(3), str)\n"}
WRONG = "def f(n):\n    return 'one'\n"  # passes the bug's test, breaks test_two
RIGHT = "def f(n):\n    if n == 2:\n        return 'two'\n    return 'one' if n == 1 else None\n"


class StubKnowledge:
    """A learned library that proposes whole-module replacements, in the given order."""

    def __init__(self, *modules):
        self.modules = modules

    def candidates_for(self, source, path, span, limit=30, deadline=None):
        return [Candidate(path, m, f"learned: stub {i}") for i, m in enumerate(self.modules)]


class RegressionSuiteTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        for name, text in FILES.items():
            (Path(self.td.name) / name).parent.mkdir(parents=True, exist_ok=True)
            (Path(self.td.name) / name).write_text(text)

    def tearDown(self):
        self.td.cleanup()

    def run_workflow(self, suite, *modules):
        return RepairWorkflow(time_budget_seconds=120, knowledge=StubKnowledge(*modules), max_iterations=1,
                              regression_suite=suite).run(self.td.name, ["tests/test_m.py"])

    def test_off_by_default_the_bugs_tests_decide(self):
        self.assertIsNone(RepairWorkflow().regression_suite)
        d = self.run_workflow(None, WRONG, RIGHT)
        self.assertEqual(d.status, "resolved")
        self.assertIn("return 'one'", d.diff)
        self.assertNotIn("rejected_regression_suite", d.reasons)

    def test_a_patch_that_breaks_the_suite_is_rejected_and_the_search_goes_on(self):
        d = self.run_workflow(["tests"], WRONG, RIGHT)
        self.assertEqual(d.status, "resolved")
        self.assertIn("'one' if n == 1 else None", d.diff)
        self.assertEqual(d.reasons.get("rejected_regression_suite"), 1)
        r = next(r for r in d.rejected if r["status"] == "rejected_regression_suite")
        self.assertIn("tests/test_other.py::test_two", r["why"])
        self.assertTrue(any("regression suite: 2 tests pass" in n for n in d.notes))

    def test_only_the_wrong_patch_leaves_nothing_accepted(self):
        d = self.run_workflow(["tests"], WRONG)
        self.assertNotEqual(d.status, "resolved")
        self.assertEqual(d.reasons.get("rejected_regression_suite"), 1)

    def test_a_module_that_cannot_import_does_not_stop_the_suite(self):
        (Path(self.td.name) / "tests" / "test_broken.py").write_text("import a_module_that_does_not_exist\n")
        d = self.run_workflow(["tests"], WRONG, RIGHT)
        self.assertEqual(d.status, "resolved")
        self.assertEqual(d.reasons.get("rejected_regression_suite"), 1)


if __name__ == "__main__":
    unittest.main()
