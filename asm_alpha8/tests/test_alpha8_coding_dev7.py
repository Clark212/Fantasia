import hashlib
import tempfile
import unittest
from pathlib import Path

from asm.coding import (FailureAnalyzer, PatchError, PatchProposalBuilder,
                        RepairCoordinator, TestRunner)


class FailureAnalyzerTests(unittest.TestCase):
    def test_extracts_failure_and_localizes_production_frame(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = ("________________ test_bad __________________\n"
                      "src/parser.py:18: in parse\n"
                      "tests/test_parser.py:7: in test_bad\n"
                      "ValueError: invalid token\n"
                      "FAILED tests/test_parser.py::test_bad - ValueError: invalid token\n")
            result = FailureAnalyzer().analyze(output, root)
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0].exception, "ValueError")
            self.assertEqual(result[0].likely_source_files, ["src/parser.py"])

    def test_empty_output_returns_no_diagnoses(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(FailureAnalyzer().analyze("", tmp), [])


class ProposalBuilderTests(unittest.TestCase):
    def test_builds_hash_guarded_syntax_checked_proposal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); path = root / "app.py"; path.write_text("x = 1\n")
            proposal = PatchProposalBuilder.from_replacement(root, "app.py", "x = 2\n", "fix")
            self.assertEqual(proposal.expected_sha256, hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertIn("-x = 1", proposal.preview(path.read_text()))
            with self.assertRaises(PatchError):
                PatchProposalBuilder.from_replacement(root, "app.py", "def broken(:\n")


class RepairCoordinatorTests(unittest.TestCase):
    def test_candidate_is_tested_in_copy_not_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / "app.py").write_text("def answer(): return 1\n")
            (root / "tests").mkdir()
            (root / "tests" / "test_app.py").write_text("from app import answer\ndef test_answer(): assert answer() == 2\n")
            proposal = PatchProposalBuilder.from_replacement(
                root, "app.py", "def answer(): return 2\n", "correct return value")
            result = RepairCoordinator(TestRunner(timeout_seconds=10)).verify_candidates(
                root, [proposal], ["tests/test_app.py"])
            self.assertEqual(len(result), 1)
            self.assertTrue(result[0].accepted_by_tests, result[0].test_result)
            self.assertFalse(result[0].original_repository_modified)
            self.assertIn("return 1", (root / "app.py").read_text())

    def test_stale_candidate_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / "app.py").write_text("x=1\n")
            proposal = PatchProposalBuilder.from_replacement(root, "app.py", "x=2\n")
            (root / "app.py").write_text("x=3\n")
            with self.assertRaises(PatchError):
                RepairCoordinator().verify_candidates(root, [proposal])


if __name__ == "__main__":
    unittest.main()
