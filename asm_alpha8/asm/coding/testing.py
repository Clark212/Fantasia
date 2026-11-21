"""Bounded Python test invocation for developer-controlled repositories.

This uses subprocess timeouts and an argument allowlist, not an OS security
sandbox. Tests execute repository code with the current user's permissions.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class TestRun:
    command: list[str]
    returncode: int | None
    passed: bool
    timed_out: bool
    duration_seconds: float
    stdout: str
    stderr: str

    def to_dict(self) -> dict:
        return asdict(self)


class TestRunner:
    __test__ = False  # prevent pytest from treating this helper as a test case
    def __init__(self, timeout_seconds: int = 60, output_limit: int = 12000):
        if timeout_seconds < 1 or timeout_seconds > 600:
            raise ValueError("timeout_seconds must be between 1 and 600")
        self.timeout_seconds = timeout_seconds
        self.output_limit = max(1000, output_limit)

    def run_pytest(self, root: str | Path, targets: list[str] | None = None) -> TestRun:
        base = Path(root).resolve(strict=True)
        if not base.is_dir():
            raise NotADirectoryError(str(base))
        safe_targets = []
        for item in targets or ["tests"]:
            p = Path(item)
            if p.is_absolute() or ".." in p.parts:
                raise ValueError("test targets must be relative paths inside the repository")
            resolved = (base / p).resolve(strict=False)
            if not resolved.is_relative_to(base):
                raise ValueError("test target escapes repository root")
            if not resolved.exists():
                raise FileNotFoundError(item)
            safe_targets.append(p.as_posix())
        command = [sys.executable, "-m", "pytest", "-q", *safe_targets]
        env = {k: v for k, v in os.environ.items() if k in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME"}}
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        started = time.monotonic()
        try:
            proc = subprocess.run(command, cwd=base, env=env, capture_output=True,
                                  text=True, timeout=self.timeout_seconds, shell=False)
            duration = time.monotonic() - started
            return TestRun(command, proc.returncode, proc.returncode == 0, False, duration,
                           proc.stdout[-self.output_limit:], proc.stderr[-self.output_limit:])
        except subprocess.TimeoutExpired as exc:
            duration = time.monotonic() - started
            out = exc.stdout or ""
            err = exc.stderr or ""
            if isinstance(out, bytes): out = out.decode("utf-8", "replace")
            if isinstance(err, bytes): err = err.decode("utf-8", "replace")
            return TestRun(command, None, False, True, duration,
                           out[-self.output_limit:], err[-self.output_limit:])
