"""Human-gated candidate verification loop for coding repair proposals."""
from __future__ import annotations

import hashlib
import shutil
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from .diagnostics import FailureAnalyzer
from .patches import PatchProposal, PatchError, apply_proposal
from .testing import TestRunner


@dataclass
class CandidateResult:
    path: str
    accepted_by_tests: bool
    test_result: dict
    patch_preview: str
    original_repository_modified: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


class RepairCoordinator:
    """Diagnose failures and test caller-generated candidates in a disposable copy.

    Candidate generation is delegated to a trusted caller (e.g. a model adapter).
    This class never invents source edits, never writes to the original repository,
    and never auto-accepts or applies a candidate to the user's working tree.
    """
    def __init__(self, test_runner: TestRunner | None = None,
                 failure_analyzer: FailureAnalyzer | None = None,
                 max_copy_bytes: int = 100_000_000):
        self.test_runner = test_runner or TestRunner(timeout_seconds=60)
        self.failure_analyzer = failure_analyzer or FailureAnalyzer()
        self.max_copy_bytes = max_copy_bytes

    def diagnose(self, root: str | Path, test_output: str) -> list[dict]:
        return [item.to_dict() for item in self.failure_analyzer.analyze(test_output, root)]

    def verify_candidates(self, root: str | Path, candidates: list[PatchProposal],
                          targets: list[str] | None = None) -> list[CandidateResult]:
        base = Path(root).resolve(strict=True)
        if not base.is_dir():
            raise NotADirectoryError(str(base))
        total_bytes = 0
        for item in base.rglob("*"):
            if item.is_symlink():
                continue
            if item.is_file():
                total_bytes += item.stat().st_size
                if total_bytes > self.max_copy_bytes:
                    raise ValueError("repository exceeds disposable verification copy limit")
        results = []
        for candidate in candidates[:3]:
            source = base / candidate.path
            if not source.is_file() or source.is_symlink():
                raise PatchError("candidate must target an existing regular repository file")
            raw = source.read_bytes()
            actual = hashlib.sha256(raw).hexdigest()
            if actual != candidate.expected_sha256:
                raise PatchError("stale candidate: source hash changed before verification")
            with tempfile.TemporaryDirectory(prefix="asm_dev7_verify_") as tmp:
                sandbox = Path(tmp) / "repo"
                shutil.copytree(base, sandbox, symlinks=True, ignore=shutil.ignore_patterns(
                    ".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".asm_backups"))
                apply_proposal(sandbox, candidate, backup=False)
                run = self.test_runner.run_pytest(sandbox, targets)
                results.append(CandidateResult(candidate.path, run.passed, run.to_dict(),
                                               candidate.preview(raw.decode("utf-8", "replace")), False))
        return results
