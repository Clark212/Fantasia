"""DEV32 tests: the opt-in guard against patches that write the failing tests' data into the code."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
import dev32_mine_bugs as MB  # noqa: E402
import dev32_realbugs as D32  # noqa: E402
from asm.coding.content import ProblemContext, copied_test_strings  # noqa: E402
from asm.coding.faultloc import RepairWorkflow, Spectrum  # noqa: E402
from asm.coding.research import Candidate  # noqa: E402

CTX = ProblemContext(test_strings=["rtmp://foo.de", "19681210", "git push --force-with-lease", "zero", "utf-8", "foo.de",
                                   "Expected a string or bytes value", "already here"])


def fn(body: str) -> str:
    return "def f(x):\n    " + body + "\n"


class GuardRuleTests(unittest.TestCase):
    def test_dev31s_two_wrong_patches_are_caught(self):
        self.assertEqual(copied_test_strings(fn("return None"), fn("return 'rtmp://foo.de'"), CTX), ["rtmp://foo.de"])
        self.assertEqual(copied_test_strings(fn("upload_date = None"), fn("upload_date = '19681210'"), CTX), ["19681210"])

    def test_what_correct_fixes_copy_is_allowed(self):
        cases = [
            (fn("return 'push --force'"), fn("return 'push --force-with-lease'")),  # thefuck-19: part of a test string
            (fn("return None"), fn("return 'zero'")),  # a name-like string (humanize's apnumber(0) == 'zero')
            (fn("return x.decode()"), fn("return x.decode('utf-8')")),  # an encoding name (scrapy-30's fix)
            (fn("pass"), fn("raise TypeError('Expected a string or bytes value')")),  # an error message (pyjwt)
            (fn("pass"), fn("warnings.warn('Expected a string or bytes value')")),
            (fn("pass"), fn("log.error('Expected a string or bytes value: %s' % x)")),
            (fn("pass"), fn("err = ValueError('Expected a string or bytes value')")),
            (fn("return 'already here' if x else None"), fn("return 'already here'")),  # the module has it already
        ]
        for original, patched in cases:
            self.assertEqual(copied_test_strings(original, patched, CTX), [], patched)

    def test_printed_data_is_not_a_message_and_a_domain_is_not_a_name(self):
        self.assertEqual(copied_test_strings(fn("print(x)"), fn("print('rtmp://foo.de')"), CTX), ["rtmp://foo.de"])
        self.assertEqual(copied_test_strings(fn("return None"), fn("return 'foo.de'"), CTX), ["foo.de"])

    def test_unparsable_patch_and_no_test_strings(self):
        self.assertEqual(copied_test_strings(fn("return None"), "def f(:\n", CTX), [])
        self.assertEqual(copied_test_strings(fn("return None"), fn("return 'rtmp://foo.de'"), ProblemContext()), [])


class StubKnowledge:
    """A learned library that proposes one candidate per given body for the function `f` of m.py."""

    def __init__(self, *bodies):
        self.bodies = bodies

    def candidates_for(self, source, path, span, limit=30, deadline=None):
        return [Candidate(path, source.replace("return None", body), f"learned: stub {i}") for i, body in enumerate(self.bodies)]


FILES = {"m.py": "def f(n):\n    return None\n",
         "tests/test_m.py": "from m import f\n\ndef test_f():\n    assert f(1) == 'rtmp://foo.de'\n"}


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        for name, text in FILES.items():
            (Path(self.td.name) / name).parent.mkdir(parents=True, exist_ok=True)
            (Path(self.td.name) / name).write_text(text)

    def tearDown(self):
        self.td.cleanup()

    def test_off_by_default_and_on_it_drops_only_copies(self):
        kb = StubKnowledge("return 'rtmp://foo.de'", "return str(n)")
        source = FILES["m.py"]
        for guard, kept, copied in ((False, 2, []), (True, 1, [["rtmp://foo.de"]])):
            wf = RepairWorkflow(knowledge=kb, test_copy_guard=guard)
            self.assertFalse(RepairWorkflow(knowledge=kb).test_copy_guard)
            spectrum = Spectrum(outcomes={"tests/test_m.py::test_f": "failed"}, lines={}, failures={"tests/test_m.py::test_f": ""})
            cands, dropped = wf._learned_candidates(Path(self.td.name), spectrum, source, "m.py", (1, 2))
            self.assertEqual((len(cands), dropped), (kept, copied))
            if guard:
                self.assertIn("return str(n)", cands[0].replacement)

    def test_the_guard_decides_acceptance_end_to_end(self):
        # nothing built in makes f(1) return the URL; the only learned candidate hard-codes the test's data
        for guard in (False, True):
            d = RepairWorkflow(time_budget_seconds=120, knowledge=StubKnowledge("return 'rtmp://foo.de'"), max_iterations=1,
                               test_copy_guard=guard).run(self.td.name)
            if guard:
                self.assertNotEqual(d.status, "resolved")
                self.assertEqual(d.reasons.get("test_copy"), 1)
                self.assertTrue(any(r["status"] == "test_copy" and "'rtmp://foo.de'" in r["why"] for r in d.rejected))
            else:
                self.assertEqual(d.status, "resolved")
                self.assertIn("'rtmp://foo.de'", d.diff)
                self.assertNotIn("test_copy", d.reasons)


class MinerTests(unittest.TestCase):
    def test_which_commits_are_candidates(self):
        fix, test = ("M", "pkg/a.py"), ("A", "tests/test_a.py")
        self.assertEqual(MB.split_change([fix, test, ("M", "CHANGES.rst"), ("M", "docs/x.py")]), (["pkg/a.py"], ["tests/test_a.py"]))
        for extra in [("M", "tests/conftest.py"), ("A", "tests/data/case.json"), ("M", "tests/helpers.py"), ("M", "setup.py"),
                      ("A", "pkg/new.py"), ("M", "requirements.txt")]:
            self.assertIsNone(MB.split_change([fix, test, extra]), extra)
        self.assertEqual(MB.split_change([fix, ("M", "pkg/b.py"), test])[0], ["pkg/a.py", "pkg/b.py"])
        self.assertIsNone(MB.split_change([fix, ("M", "pkg/b.py"), ("M", "pkg/c.py"), test]))  # three fix files
        self.assertIsNone(MB.split_change([fix]))  # no test
        self.assertIsNone(MB.split_change([test]))  # no fix

    def test_the_bugs_tests_are_the_test_functions_the_fix_adds_or_changes(self):
        before = "def test_a():\n    assert 1\n\nclass TestX:\n    def test_b(self):\n        assert 1\n"
        after = before.replace("        assert 1", "        assert 2") + "\ndef test_c():\n    def test_inner():\n        pass\n"
        self.assertEqual(MB.changed_tests(before, after, "tests/test_m.py"), ["tests/test_m.py::TestX::test_b", "tests/test_m.py::test_c"])

    def test_candidates_in_a_repository(self):
        with tempfile.TemporaryDirectory() as td:
            env = {**os.environ, "GIT_AUTHOR_DATE": "2024-03-01T12:00:00Z", "GIT_COMMITTER_DATE": "2024-03-01T12:00:00Z",
                   "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
            git = lambda *a: subprocess.run(["git", *a], cwd=td, env=env, check=True, capture_output=True)  # noqa: E731

            def commit(message, files):
                for name, text in files.items():
                    (Path(td) / name).parent.mkdir(parents=True, exist_ok=True)
                    (Path(td) / name).write_text(text)
                git("add", "-A")
                git("commit", "-q", "-m", message)
            git("init", "-q")
            commit("start", {"pkg/a.py": "def f():\n    return 1\n", "tests/test_a.py": "def test_f():\n    pass\n"})
            commit("Fix f returning 1", {"pkg/a.py": "def f():\n    return 2\n", "tests/test_a.py": "def test_f():\n    assert 2\n"})
            commit("Add g", {"pkg/a.py": "def f():\n    return 2\n\ndef g():\n    pass\n", "tests/test_a.py": "def test_g():\n    pass\n"})
            commit("Fix a lot", {"pkg/a.py": "def f():\n    return 2\n" + "x = 1\n" * 30, "tests/test_a.py": "def test_h():\n    pass\n"})
            commit("Revert to 1", {"pkg/a.py": "def f():\n    return 1\n", "tests/test_a.py": "def test_f():\n    pass\n"})
            commit("Fix f returning 1 again", {"pkg/a.py": "def f():\n    return 2\n", "tests/test_a.py": "def test_f():\n    assert 2 == 2\n"})
            found = MB.candidates(Path(td))
            # the repeated fix (same lines) is a duplicate: only the first is kept
            self.assertEqual([(c["subject"], c["targets"], c["changed_lines"]) for c in found],
                             [("Fix f returning 1", ["tests/test_a.py::test_f"], 2)])


class ArmTests(unittest.TestCase):
    def test_the_arms(self):
        # DEV31's control and learned arms; the guarded arm differs from the learned arm only by the guard
        self.assertEqual(D32.ARMS, {"control": ("control", 150.0, {}), "learned": ("learned", 150.0, {"phase3_seconds": 150.0}),
                                    "guarded": ("learned", 150.0, {"phase3_seconds": 150.0, "test_copy_guard": True}),
                                    "control_long": ("control", 300.0, {})})


if __name__ == "__main__":
    unittest.main()
