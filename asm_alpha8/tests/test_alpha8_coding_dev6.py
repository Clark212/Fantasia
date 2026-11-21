import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from asm.coding import (CodingAgent, PatchError, PatchProposal, ProcedureStore,
                        TestRunner, apply_proposal)


class PatchTests(unittest.TestCase):
    def test_hash_guarded_atomic_patch_and_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); target = root / "app.py"
            target.write_text("value = 1\n", encoding="utf-8")
            old_hash = hashlib.sha256(target.read_bytes()).hexdigest()
            result = apply_proposal(root, PatchProposal("app.py", old_hash, "value = 2\n", "fix"))
            self.assertEqual(target.read_text(), "value = 2\n")
            self.assertTrue((root / result["backup"]).exists())

    def test_stale_hash_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / "app.py").write_text("new\n")
            with self.assertRaises(PatchError):
                apply_proposal(root, PatchProposal("app.py", "0" * 64, "x\n"))

    def test_path_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(PatchError):
                apply_proposal(tmp, PatchProposal("../outside.py", None, "x"))


class TestRunnerTests(unittest.TestCase):
    def test_runs_only_repo_relative_pytest_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / "tests").mkdir()
            (root / "tests" / "test_ok.py").write_text("def test_ok(): assert 2 + 2 == 4\n")
            result = TestRunner(timeout_seconds=10).run_pytest(root, ["tests/test_ok.py"])
            self.assertTrue(result.passed, result.stdout + result.stderr)
            with self.assertRaises(ValueError):
                TestRunner().run_pytest(root, ["../outside"])


class ProcedureStoreTests(unittest.TestCase):
    def test_only_passed_runs_are_recorded_and_tampering_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "procedures.jsonl"; store = ProcedureStore(path)
            with self.assertRaises(ValueError):
                store.record(task_type="debug", task_summary="x", procedure=["a"],
                             repository_fingerprint="abc", test_result={"passed": False})
            store.record(task_type="debug", task_summary="fix parser", procedure=["reproduce", "test"],
                         repository_fingerprint="abc", test_result={"passed": True, "returncode": 0,
                         "duration_seconds": 0.1})
            self.assertEqual(len(store.list_records()), 1)
            data = json.loads(path.read_text()); data["task_summary"] = "tampered"
            path.write_text(json.dumps(data) + "\n")
            with self.assertRaises(ValueError): store.list_records()


class AgentTests(unittest.TestCase):
    def test_inspect_is_non_mutating_and_exposes_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / "parser.py").write_text("def parse(): return 1\n")
            session = CodingAgent().inspect(root, "Debug parser")
            self.assertEqual(session.plan["task_type"], "debug")
            self.assertFalse(session.policy["automatic_file_writes"])
            self.assertTrue((root / "parser.py").exists())


if __name__ == "__main__": unittest.main()
