import tempfile
import unittest
from pathlib import Path

from asm.coding import CodebaseAnalyzer, CodingTaskPlanner


class AnalyzerTests(unittest.TestCase):
    def test_indexes_symbols_imports_and_calls_without_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pkg").mkdir()
            (root / "pkg" / "__init__.py").write_text("from .core import run\n", encoding="utf-8")
            (root / "pkg" / "core.py").write_text('''import math\n\nclass Engine:\n    """Runs tasks."""\n    def run(self, value):\n        return math.sqrt(value)\n''', encoding="utf-8")
            report = CodebaseAnalyzer().scan(root)
            self.assertEqual(report.scanned_files, 2)
            core = next(f for f in report.files if f.path.endswith("core.py"))
            self.assertEqual([s.name for s in core.symbols], ["Engine", "run"])
            self.assertIn("math", core.imports)
            self.assertIn("math.sqrt", core.calls)
            self.assertTrue(report.dependency_edges)

    def test_syntax_error_is_reported_not_raised(self):
        f = CodebaseAnalyzer().analyze_file("def broken(:\n pass\n", "bad.py")
        self.assertEqual(f.diagnostics[0].code, "ASM-CODE-SYNTAX")
        self.assertEqual(f.diagnostics[0].severity, "error")

    def test_scan_limits_and_exclusions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".venv").mkdir()
            (root / ".venv" / "ignored.py").write_text("x=1")
            (root / "a.py").write_text("x=1")
            report = CodebaseAnalyzer(max_file_bytes=2).scan(root)
            self.assertEqual(report.scanned_files, 0)
            self.assertEqual(report.skipped_files, 1)


class PlannerTests(unittest.TestCase):
    def test_debug_plan_is_explainable_and_non_mutating(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "parser.py").write_text("def parse_token(value):\n return value\n")
            report = CodebaseAnalyzer().scan(root)
            plan = CodingTaskPlanner().plan("Debug the parser error", report)
            self.assertEqual(plan.task_type, "debug")
            self.assertIn("parser.py", plan.relevant_files)
            self.assertTrue(plan.steps)
            self.assertTrue(any("No files" in x for x in plan.cautions))

    def test_empty_task_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = CodebaseAnalyzer().scan(tmp)
            with self.assertRaises(ValueError):
                CodingTaskPlanner().plan("  ", report)


if __name__ == "__main__":
    unittest.main()
