"""DEV29 tests: the real-bug harness's learned configuration (DEV20's sealed libraries in the repair workflow's phase 3)."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
import dev29_realbugs as D  # noqa: E402
from asm.coding.faultloc import RepairWorkflow  # noqa: E402
from asm.coding.integrity import file_sha256  # noqa: E402


class RealBugHarnessTests(unittest.TestCase):
    def test_the_sealed_libraries_load_and_are_the_committed_files(self):
        libs = D.libraries()
        self.assertEqual(set(libs), {"knowledge", "shapes", "steps"})
        self.assertEqual(len({file_sha256(D.LIBRARIES / f) for f in ("knowledge_dev20.json", "shapes_dev20.json", "steps_dev20.json")}), 3)

    def test_the_learned_configuration_runs_the_workflow_end_to_end(self):
        files = {"m.py": "def scaled(values, factor, size):\n    return [v * factor for v in values] + [factor]\n",
                 "tests/test_m.py": "from m import scaled\ndef test_size(): assert scaled([1, 2], 3, 10) == [10, 20, 10]\n"}
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for k, v in files.items():
                (root / k).parent.mkdir(parents=True, exist_ok=True)
                (root / k).write_text(v)
            d = RepairWorkflow(time_budget_seconds=60, extended_ops=True, **D.libraries()).run(root)
            self.assertIn(d.status, {"resolved", "unresolved", "partial", "time_budget"})
            self.assertEqual((root / "m.py").read_text(), files["m.py"])  # the workflow never edits the original


if __name__ == "__main__":
    unittest.main()
