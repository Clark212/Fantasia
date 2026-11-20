"""Evidence-first coding workflow coordinator; no autonomous code invention."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from .analyzer import CodebaseAnalyzer
from .planner import CodingTaskPlanner
from .testing import TestRunner
from .research import CodingResearchLoop, FailureLedger, ResearchResult
from .procedures import ProcedureStore
from .understanding import CodeUnderstanding, UnderstandingReport
from .semantics import SemanticAnalyzer, SemanticReport
from .faultloc import FaultLocalizer, RepairWorkflow, Dossier, LocalizationReport


@dataclass
class CodingSession:
    repository: dict
    plan: dict
    policy: dict

    def to_dict(self) -> dict:
        return asdict(self)


class CodingAgent:
    """Coordinates analysis, planning, bounded tests, and evidence capture.

    The caller supplies proposed source text. ASM can review and test it, but
    this coordinator does not silently generate or apply source modifications.
    """
    def __init__(self, analyzer=None, planner=None, test_runner=None):
        self.analyzer = analyzer or CodebaseAnalyzer()
        self.planner = planner or CodingTaskPlanner()
        self.test_runner = test_runner or TestRunner()

    def inspect(self, root: str | Path, task: str) -> CodingSession:
        report = self.analyzer.scan(root)
        plan = self.planner.plan(task, report)
        return CodingSession(report.summary(), plan.to_dict(), {
            "automatic_file_writes": False,
            "test_execution_requires_explicit_call": True,
            "test_runner_isolation": "subprocess timeout and argument allowlist; not an OS sandbox",
            "patch_policy": "single-file, expected-hash guarded, backup by default",
        })

    def understand(self, root: str | Path, **limits) -> UnderstandingReport:
        """DEV9 static deep analysis (CFG, data flow, call graph, classes, module deps). Never executes code."""
        return CodeUnderstanding(**limits).analyze(root)

    def semantics(self, root: str | Path, **options) -> SemanticReport:
        """DEV10 semantic analysis: static effects + sandboxed behavioural probing + name-vs-behaviour findings."""
        return SemanticAnalyzer(**options).analyze(root)

    def localize_fault(self, root: str | Path, targets=None, **options) -> LocalizationReport:
        """DEV11: rank suspect functions for the failing tests (spectrum + traceback + DEV10 evidence)."""
        return FaultLocalizer(self.test_runner and __import__("asm.coding.sandbox", fromlist=["SafeTestRunner"]).SafeTestRunner.from_legacy(self.test_runner),
                              **options).localize(root, targets)

    def repair_failing_tests(self, root: str | Path, targets=None, task: str = "repair failing tests", examples=None,
                             **options) -> Dossier:
        """DEV11: localize, try template repairs in the sandbox, verify, and return an evidence dossier.
        Never modifies `root`; apply separately with RepairWorkflow.apply_fix(..., approved=True)."""
        return RepairWorkflow(**options).run(root, targets, task, examples)

    def research(self, root: str | Path, task: str, generator, *, targets: list[str] | None = None,
                 ledger_path: str | Path | None = None, procedures_path: str | Path | None = None,
                 **loop_options) -> ResearchResult:
        """DEV8 bounded generate/verify/compare/learn loop. Never modifies `root`.

        `generator` is a trusted callable (ResearchContext -> list[Candidate]); ASM has
        no built-in code-generation model. The best candidate is returned, not applied.
        """
        loop = CodingResearchLoop(
            generator, test_runner=self.test_runner,
            ledger=FailureLedger(ledger_path) if ledger_path else None,
            procedures=ProcedureStore(procedures_path) if procedures_path else None,
            **loop_options)
        return loop.run(root, task, targets=targets)

    def test(self, root: str | Path, targets: list[str] | None = None):
        return self.test_runner.run_pytest(root, targets)
