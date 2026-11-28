"""DEV8.1 autonomous coding research loop (hardened).

Bounded rounds of: generate candidates -> screen -> verify in disposable copies ->
compare against a measured, stability-checked baseline -> remember failures -> feed
structured evidence into the next round.

Hardening in DEV8.1 (each has regression tests):
1. Strict wall-clock deadline covering baseline, generator calls and every test run;
   generator timeouts (thread, or killable forked process).
2. Baseline run N times before any candidate is judged; flaky/timeout/no-tests/error
   baselines stop the loop with an explicit reason; passing candidates are re-confirmed.
3. Per-test outcome comparison: fixed, regressions, VANISHED tests, newly skipped tests,
   explained ranking and leaderboard.
4. Failure memory: normalized-AST duplicate detection, repo-fingerprint-scoped ledger
   (stale failures never block), structured feedback (what was tried, what is still
   failing, which tests candidates keep breaking, repeated failure modes, budget left).
5. Safer execution: sandboxed runner (see sandbox.py), protected test/config files,
   suffix/size limits, new-risk scan, symlink-free copies.

Boundaries: ASM has no code-generation model (candidates come from a trusted caller);
the original repository is never modified and the best candidate is returned, never
applied; this is not an OS security boundary for untrusted code.
"""
from __future__ import annotations

import hashlib
import json
import multiprocessing
import os
import re
import signal
import tempfile
import threading
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from .diagnostics import FailureAnalyzer
from .patches import PatchError, PatchProposal, PatchProposalBuilder, apply_proposal
from .procedures import ProcedureStore
from .sandbox import (DEFAULT_BLOCK, FAIL_STATES, MEDIUM, REPAIRABLE, SafeRun, SafeTestRunner,
                      copy_repo, new_risks, normalized_sha256)

_IGNORE = (".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".asm_backups")
_FAILED = re.compile(r"^(?:FAILED|ERROR)\s+(\S+)", re.M)
_COUNT = re.compile(r"(\d+)\s+(failed|passed|error|errors)")
_E_LINE = re.compile(r"^E\s+(.*)$", re.M)
HARD_MAX_ROUNDS = 10
HARD_MAX_CANDIDATES = 8
HARD_MAX_BASELINE_RUNS = 5
PROTECTED_CONFIG = frozenset({"conftest.py", "pytest.ini", "pyproject.toml", "setup.cfg", "tox.ini",
                              "setup.py", ".coveragerc"})
RANK_CRITERIA = ["not_accepted", "vanished_tests", "regressions", "new_skips", "failing_tests",
                 "diff_lines", "duration"]
LEDGER_BLOCKING = {"failed", "timed_out", "rejected_test_loss"}


# --------------------------------------------------------------------- types
@dataclass
class Candidate:
    path: str
    replacement: str
    reason: str = ""


@dataclass
class ResearchContext:
    """Everything a generator is given for one round."""
    task: str
    round: int
    baseline_failures: list[str]
    diagnostics: list[dict]
    prior_failures: list[dict]  # ledger entries (stale flag set) or this session's failed attempts
    feedback: dict = field(default_factory=dict)  # structured, factual evidence (see _build_feedback)


@dataclass
class Attempt:
    round: int
    index: int
    path: str
    replacement_sha256: str
    status: str  # passed | failed | timed_out | unconfirmed_pass | rejected_{invalid,duplicate,protected,risky,too_large,test_loss}
    detail: str = ""
    n_failed: int | None = None
    n_passed: int | None = None
    failed_tests: list[str] = field(default_factory=list)
    fixed_tests: list[str] = field(default_factory=list)
    regressions: list[str] = field(default_factory=list)
    vanished_tests: list[str] = field(default_factory=list)
    newly_skipped: list[str] = field(default_factory=list)
    exceptions: list[str] = field(default_factory=list)
    diff_lines: int = 0
    duration_seconds: float = 0.0
    reason: str = ""
    normalized_sha256: str = ""
    error_signature: str = ""
    risk_flags: dict = field(default_factory=dict)
    confirmed: bool | None = None
    budget_cut: bool = False

    @property
    def verified(self) -> bool:
        return self.status in {"passed", "failed", "timed_out", "unconfirmed_pass", "rejected_test_loss"}

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ResearchResult:
    task: str
    stop_reason: str  # resolved|no_repair_needed|exhausted|time_budget|generator_error|generator_timeout|baseline_unstable|baseline_timeout|baseline_error|no_tests_collected
    baseline_failures: list[str]
    attempts: list[Attempt]
    best: Attempt | None
    best_proposal: PatchProposal | None
    best_preview: str
    rounds_used: int
    original_tree_unchanged: bool
    notes: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    time_budget_seconds: float = 0.0
    baseline: dict = field(default_factory=dict)
    leaderboard: list[dict] = field(default_factory=list)
    feedback: dict = field(default_factory=dict)
    isolation: dict = field(default_factory=dict)

    @property
    def resolved(self) -> bool:
        return self.stop_reason == "resolved"

    @property
    def budget_overrun_seconds(self) -> float:
        return max(0.0, self.elapsed_seconds - self.time_budget_seconds)

    def to_dict(self) -> dict:
        data = {k: v for k, v in asdict(self).items() if k != "best_proposal"}
        data["resolved"] = self.resolved
        data["budget_overrun_seconds"] = self.budget_overrun_seconds
        data["best_proposal"] = self.best_proposal.to_dict() if self.best_proposal else None
        return data


# -------------------------------------------------------------------- ledger
class FailureLedger:
    """Append-only, integrity-checked JSONL record of failed attempts.

    Tamper (hash mismatch / garbage mid-file) raises. A torn final line (crash mid-append)
    is tolerated. Appends are locked and fsynced. Failures only block a candidate when
    recorded against the SAME repository fingerprint (legacy records without one block).
    """
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.torn_tail = False

    @staticmethod
    def _digest(payload: dict) -> str:
        body = {k: v for k, v in payload.items() if k != "record_sha256"}
        return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def append(self, task_id: str, attempt: Attempt, repo_fingerprint: str | None = None,
               base_sha256: str | None = None) -> dict:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema": 2, "timestamp": time.time(), "task_id": task_id, "round": attempt.round,
                   "path": attempt.path, "replacement_sha256": attempt.replacement_sha256,
                   "normalized_sha256": attempt.normalized_sha256, "repo_fingerprint": repo_fingerprint,
                   "base_sha256": base_sha256, "status": attempt.status,
                   "failed_tests": attempt.failed_tests[:20], "fixed_tests": attempt.fixed_tests[:20],
                   "regressions": attempt.regressions[:20], "exceptions": attempt.exceptions[:10],
                   "error_signature": attempt.error_signature, "n_failed": attempt.n_failed,
                   "reason": attempt.reason[:200], "detail": attempt.detail[:300]}
        payload["record_sha256"] = self._digest(payload)
        line = (json.dumps(payload, sort_keys=True) + "\n").encode()
        with self.path.open("ab+") as handle:
            try:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX)
            except (ImportError, OSError):
                pass
            handle.seek(0)
            data = handle.read()
            if data and not data.endswith(b"\n"):
                # torn tail (crash mid-append). We hold the exclusive lock, so no writer is mid-record:
                # drop the incomplete fragment so it cannot become mid-file corruption.
                handle.truncate(data.rfind(b"\n") + 1)
            handle.seek(0, os.SEEK_END)
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
        return payload

    def records(self, task_id: str | None = None) -> list[dict]:
        self.torn_tail = False
        if not self.path.exists():
            return []
        raw = self.path.read_text(encoding="utf-8").splitlines()
        last = max((i for i, l in enumerate(raw) if l.strip()), default=-1)
        out = []
        for i, line in enumerate(raw):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                if i == last:
                    self.torn_tail = True
                    continue
                raise ValueError(f"failure ledger corrupt at line {i + 1}")
            if record.get("record_sha256") != self._digest(record):
                raise ValueError(f"failure ledger integrity failure at line {i + 1}")
            if task_id is None or record["task_id"] == task_id:
                out.append(record)
        return out

    def has_failed(self, task_id: str, path: str, replacement_sha256: str,
                   repo_fingerprint: str | None = None, normalized_sha256: str | None = None) -> bool:
        for r in self.records(task_id):
            if r["path"] != path or r["status"] not in LEDGER_BLOCKING:
                continue
            fp = r.get("repo_fingerprint")
            if fp is not None and repo_fingerprint is not None and fp != repo_fingerprint:
                continue  # recorded against a different repository state: informative, not blocking
            if r["replacement_sha256"] == replacement_sha256 or (
                    normalized_sha256 and r.get("normalized_sha256") == normalized_sha256):
                return True
        return False


# ------------------------------------------------------------------- helpers
def tree_fingerprint(root: str | Path) -> str:
    base = Path(root).resolve(strict=True)
    digest = hashlib.sha256()
    for item in sorted(base.rglob("*")):
        rel = item.relative_to(base)
        if any(part in _IGNORE for part in rel.parts) or item.is_symlink() or not item.is_file():
            continue
        digest.update(rel.as_posix().encode() + b"\0" + hashlib.sha256(item.read_bytes()).digest())
    return digest.hexdigest()


def _is_test_path(rel: str) -> bool:
    # same rule as faultloc.is_test_path (DEV14: test directories at any depth, tests_* / *_tests modules)
    p = Path(rel)
    stem = p.stem
    return bool({"tests", "test", "testing"} & set(p.parts[:-1])) or stem.startswith(("test_", "tests_")) \
        or stem.endswith(("_test", "_tests")) or p.name == "conftest.py"


def _parse_run(run: dict) -> tuple[list[str], int | None, int | None]:
    text = (run.get("stdout") or "") + "\n" + (run.get("stderr") or "")
    failed = sorted(set(_FAILED.findall(text)))
    counts = {"failed": 0, "passed": 0, "error": 0}
    for number, word in _COUNT.findall(text):
        counts["error" if word.startswith("error") else word] += int(number)
    n_failed = counts["failed"] + counts["error"]
    n_passed = counts["passed"]
    if run.get("returncode") not in (0, None) and n_failed == 0 and not failed:
        n_failed = 1  # collection/usage failure with no parsable summary: never count as clean
    return failed, n_failed, n_passed


def compare_outcomes(base: dict, cand: dict) -> dict:
    """Per-test comparison of a candidate run against the baseline run."""
    fixed = sorted(i for i, s in base.items() if s in FAIL_STATES and (
        cand.get(i) == "passed" or (i not in cand and s == "error")))
    regressions = sorted(i for i, s in cand.items() if s in FAIL_STATES and base.get(i) not in FAIL_STATES)
    vanished = sorted(i for i, s in base.items() if s != "error" and i not in cand)
    newly_skipped = sorted(i for i, s in base.items() if s == "passed" and cand.get(i) in {"skipped", "xfailed"})
    return {"fixed": fixed, "regressions": regressions, "vanished": vanished, "newly_skipped": newly_skipped}


def _infer_exceptions(run: SafeRun, exceptions: list[str]) -> list[str]:
    """Plain `assert` failures print `E   assert ...` without naming AssertionError."""
    out = set(exceptions)
    if any(l.startswith("assert ") for l in _E_LINE.findall(run.stdout)):
        out.add("AssertionError")
    return sorted(out)


def _error_signature(run: SafeRun, exceptions: list[str]) -> str:
    lines = _E_LINE.findall(run.stdout)[:6]
    norm = re.sub(r"0x[0-9a-fA-F]+|\d+|/tmp/\S+", "N", " ".join(lines))
    digest = hashlib.sha1(norm.encode()).hexdigest()[:10] if lines else "none"
    return f"{'+'.join(sorted(exceptions)) or 'NoException'}:{digest}"


def rank_key(a: Attempt) -> tuple:
    return (a.status != "passed", len(a.vanished_tests), len(a.regressions), len(a.newly_skipped),
            a.n_failed if a.n_failed is not None else 10 ** 9, a.diff_lines, a.duration_seconds)


def compare_attempts(a: Attempt, b: Attempt) -> dict:
    """Explain which criterion decides between two attempts (a ahead of b means winner == 'a')."""
    ka, kb = rank_key(a), rank_key(b)
    for name, x, y in zip(RANK_CRITERIA, ka, kb):
        if x != y:
            return {"winner": "a" if x < y else "b", "decided_by": name, "a": x, "b": y}
    return {"winner": "tie", "decided_by": None, "a": None, "b": None}


class _Budget(Exception):
    pass


class GeneratorTimeout(Exception):
    pass


def _run_generator(gen, ctx, timeout: float, isolation: str, memory_mb: int | None):
    """Call the generator with a hard timeout. Returns a list of items (Candidate or tuples)."""
    if isolation == "process" and "fork" in multiprocessing.get_all_start_methods() and os.name == "posix":
        mp = multiprocessing.get_context("fork")
        recv, send = mp.Pipe(duplex=False)

        def child(conn):
            try:
                os.setsid()
                if memory_mb:
                    import resource
                    resource.setrlimit(resource.RLIMIT_AS, (memory_mb << 20, memory_mb << 20))
                items = [(c.path, c.replacement, c.reason) if isinstance(c, Candidate) else c for c in gen(ctx)]
                conn.send(("ok", items))
            except BaseException as exc:  # noqa: BLE001 - report everything to the parent
                conn.send(("err", f"{type(exc).__name__}: {exc}"))
            finally:
                conn.close()

        proc = mp.Process(target=child, args=(send,), daemon=True)
        proc.start()
        send.close()
        try:
            if not recv.poll(timeout):
                raise GeneratorTimeout()
            try:
                kind, payload = recv.recv()
            except EOFError:
                raise RuntimeError("generator process died without a result")
            if kind == "err":
                raise RuntimeError(payload)
            return payload
        finally:
            if proc.is_alive():
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError, OSError):
                    pass
                proc.kill()
            proc.join(2)
            recv.close()
    box: dict = {}

    def target():
        try:
            box["r"] = list(gen(ctx))
        except BaseException as exc:  # noqa: BLE001
            box["e"] = exc

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        raise GeneratorTimeout()  # thread cannot be killed; the loop stops and never calls it again
    if "e" in box:
        raise box["e"]
    return box["r"]


# ---------------------------------------------------------------------- loop
class CodingResearchLoop:
    def __init__(self, generator: Callable[[ResearchContext], list], *,
                 ledger: FailureLedger | None = None, procedures: ProcedureStore | None = None,
                 test_runner=None, max_rounds: int = 3, max_candidates_per_round: int = 4,
                 time_budget_seconds: float = 300.0, protect_tests: bool = True, protect_config: bool = True,
                 max_copy_bytes: int = 100_000_000, generator_timeout_seconds: float = 30.0,
                 generator_isolation: str = "thread", generator_memory_mb: int | None = None,
                 candidate_timeout_seconds: float | None = None, baseline_timeout_seconds: float | None = None,
                 baseline_runs: int = 2, confirm_runs: int = 1, max_candidate_bytes: int = 200_000,
                 allowed_suffixes: tuple = (".py",), allow_risky: bool = False,
                 block_risk_categories=DEFAULT_BLOCK, min_step_seconds: float = 0.25):
        if not 1 <= max_rounds <= HARD_MAX_ROUNDS:
            raise ValueError(f"max_rounds must be between 1 and {HARD_MAX_ROUNDS}")
        if not 1 <= max_candidates_per_round <= HARD_MAX_CANDIDATES:
            raise ValueError(f"max_candidates_per_round must be between 1 and {HARD_MAX_CANDIDATES}")
        if not 1 <= baseline_runs <= HARD_MAX_BASELINE_RUNS:
            raise ValueError(f"baseline_runs must be between 1 and {HARD_MAX_BASELINE_RUNS}")
        if not 0 <= confirm_runs <= 3:
            raise ValueError("confirm_runs must be between 0 and 3")
        if generator_isolation not in {"thread", "process"}:
            raise ValueError("generator_isolation must be 'thread' or 'process'")
        if time_budget_seconds < 0 or generator_timeout_seconds <= 0:
            raise ValueError("time budgets must be non-negative and generator timeout positive")
        self.generator = generator
        self.ledger, self.procedures = ledger, procedures
        self.runner = SafeTestRunner.from_legacy(test_runner) if test_runner is not None else SafeTestRunner()
        self.max_rounds, self.max_candidates = max_rounds, max_candidates_per_round
        self.time_budget = float(time_budget_seconds)
        self.protect_tests, self.protect_config = protect_tests, protect_config
        self.max_copy_bytes = max_copy_bytes
        self.generator_timeout = float(generator_timeout_seconds)
        self.generator_isolation, self.generator_memory_mb = generator_isolation, generator_memory_mb
        self.candidate_timeout = float(candidate_timeout_seconds or self.runner.timeout_seconds)
        self.baseline_timeout = float(baseline_timeout_seconds or self.runner.timeout_seconds)
        self.baseline_runs, self.confirm_runs = baseline_runs, confirm_runs
        self.max_candidate_bytes = max_candidate_bytes
        self.allowed_suffixes = tuple(allowed_suffixes)
        self.allow_risky, self.block_categories = allow_risky, frozenset(block_risk_categories)
        self.min_step = float(min_step_seconds)
        self.analyzer = FailureAnalyzer()

    # ---- helpers
    def _check_size(self, base: Path) -> None:
        total = 0
        for item in base.rglob("*"):
            if item.is_symlink() or not item.is_file():
                continue
            if any(part in _IGNORE for part in item.relative_to(base).parts):
                continue
            total += item.stat().st_size
            if total > self.max_copy_bytes:
                raise ValueError("repository exceeds disposable verification copy limit")

    def _run_in_copy(self, base: Path, targets, proposal: PatchProposal | None, timeout: float):
        with tempfile.TemporaryDirectory(prefix="asm_dev8_verify_") as tmp:
            sandbox = Path(tmp) / "repo"
            skipped = copy_repo(base, sandbox)
            if proposal is not None:
                apply_proposal(sandbox, proposal, backup=False)
            return self.runner.run_pytest(sandbox, targets, timeout=timeout), skipped

    def _protected_reason(self, rel: str) -> str | None:
        p = Path(rel)
        if self.protect_tests and _is_test_path(rel):
            return "candidate targets a protected test file"
        if self.protect_config and p.name in PROTECTED_CONFIG:
            return "candidate targets a protected configuration/build file"
        if self.allowed_suffixes and p.suffix not in self.allowed_suffixes:
            return f"file suffix {p.suffix or '(none)'} is not allowed"
        return None

    @staticmethod
    def _coerce(item) -> Candidate | None:
        if isinstance(item, Candidate):
            return item
        if isinstance(item, (tuple, list)) and 2 <= len(item) <= 3 and all(isinstance(x, str) for x in item):
            return Candidate(*item)
        return None

    def _assess_baseline(self, runs: list[SafeRun]):
        classes = [r.classification for r in runs]
        if any(c == "timeout" for c in classes):
            return "baseline_timeout", []
        if any(c == "no_tests" for c in classes):
            return "no_tests_collected", []
        if any(c not in REPAIRABLE | {"passed"} for c in classes):
            return "baseline_error", []
        sets = [set(r.failed_ids) for r in runs]
        if len(set(classes)) > 1 or any(s != sets[0] for s in sets):
            union, inter = set().union(*sets), set.intersection(*sets)
            return "baseline_unstable", sorted(union - inter)
        if classes[0] == "passed":
            return "no_repair_needed", []
        return None, []

    def _build_feedback(self, task_id, attempts, baseline_failed, rnd, remaining, ledger_records, fingerprint):
        tried = [{"round": a.round, "path": a.path, "sha": a.replacement_sha256[:12], "status": a.status,
                  "fixed": a.fixed_tests[:10], "regressions": a.regressions[:10],
                  "vanished": a.vanished_tests[:5], "exceptions": a.exceptions[:5],
                  "error_signature": a.error_signature, "reason": a.reason[:120]} for a in attempts[-20:]]
        fixed_by: dict[str, list[str]] = defaultdict(list)
        culprits: Counter = Counter()
        modes: dict[str, dict] = {}
        rejections: Counter = Counter()
        for a in attempts:
            for t in a.fixed_tests:
                fixed_by[t].append(f"r{a.round}#{a.index}")
            for t in a.regressions:
                culprits[t] += 1
            if a.status.startswith("rejected_"):
                rejections[a.status] += 1
            if a.error_signature and a.status in {"failed", "timed_out"}:
                m = modes.setdefault(a.error_signature, {"signature": a.error_signature, "count": 0,
                                                        "exceptions": a.exceptions[:3], "example_tests": a.failed_tests[:3]})
                m["count"] += 1
        stale = sum(1 for r in ledger_records if r.get("repo_fingerprint") not in (None, fingerprint))
        return {
            "tried": tried,
            "still_failing": sorted(set(baseline_failed) - set(fixed_by)),
            "partial_progress": {t: v for t, v in sorted(fixed_by.items())},
            "regression_culprits": [{"test": t, "broken_by_attempts": n} for t, n in culprits.most_common(10)],
            "failure_modes": sorted(modes.values(), key=lambda m: -m["count"])[:5],
            "rejection_counts": dict(rejections),
            "previous_sessions": {"records": len(ledger_records), "stale_for_this_repo_state": stale},
            "protected": {"tests": self.protect_tests, "config_files": sorted(PROTECTED_CONFIG) if self.protect_config else [],
                          "allowed_suffixes": list(self.allowed_suffixes)},
            "budget_remaining": {"rounds": self.max_rounds - rnd + 1, "seconds": round(max(0.0, remaining), 1)},
        }

    # ---- candidate evaluation
    def _evaluate(self, base, targets, cand: Candidate, rnd, idx, seen, task_id, fingerprint,
                  baseline_outcome, baseline_failed, remaining, proposals) -> Attempt:
        sha = hashlib.sha256(cand.replacement.encode("utf-8", "replace")).hexdigest()
        att = Attempt(rnd, idx, cand.path, sha, "failed", reason=cand.reason,
                      normalized_sha256=normalized_sha256(cand.replacement))
        why = self._protected_reason(cand.path)
        if why:
            att.status, att.detail = "rejected_protected", why
            return att
        if len(cand.replacement.encode("utf-8", "replace")) > self.max_candidate_bytes:
            att.status, att.detail = "rejected_too_large", f"candidate exceeds {self.max_candidate_bytes} bytes"
            return att
        keys = {(cand.path, sha), (cand.path, att.normalized_sha256)}
        if seen & keys or (self.ledger and self.ledger.has_failed(
                task_id, cand.path, sha, fingerprint, att.normalized_sha256)):
            att.status, att.detail = "rejected_duplicate", "identical (or formatting-only variant of a) candidate already failed"
            return att
        seen |= keys
        try:
            prop = PatchProposalBuilder.from_replacement(base, cand.path, cand.replacement, cand.reason)
            if prop.replacement_sha256 == prop.expected_sha256:
                raise PatchError("candidate is identical to current file")
            original = (base / cand.path).read_text(encoding="utf-8")
            if normalized_sha256(original) == att.normalized_sha256:
                raise PatchError("candidate differs only in formatting/comments")
            if not self.allow_risky:
                risks = new_risks(original, cand.replacement)
                att.risk_flags = risks
                blocked = {c: t for c, t in risks.items() if c in self.block_categories}
                if blocked:
                    att.status = "rejected_risky"
                    att.detail = "newly introduced risky constructs: " + "; ".join(
                        f"{c}: {', '.join(t)}" for c, t in blocked.items())
                    return att
            rem = remaining()
            if rem < self.min_step:
                raise _Budget()
            timeout = min(self.candidate_timeout, rem)
            budget_bound = rem < self.candidate_timeout
            run, _ = self._run_in_copy(base, targets, prop, timeout)
            att.duration_seconds = run.duration_seconds
            preview = prop.preview(original)
            att.diff_lines = sum(1 for l in preview.splitlines() if l[:1] in "+-" and not l.startswith(("+++", "---")))
            proposals[id(att)] = (prop, preview)
            if run.timed_out:
                att.status, att.budget_cut = "timed_out", budget_bound
                att.detail = "cut short by the global time budget" if budget_bound else f"exceeded {timeout:.1f}s candidate timeout"
                return att
            counts = run.counts
            if run.classification in REPAIRABLE | {"passed", "no_tests"}:
                att.n_failed = counts.get("failed", 0) + counts.get("error", 0)
                att.n_passed = counts.get("passed", 0)
                cmp = compare_outcomes(baseline_outcome, run.outcome)
                att.failed_tests, att.fixed_tests = run.failed_ids, cmp["fixed"]
                att.regressions, att.vanished_tests, att.newly_skipped = cmp["regressions"], cmp["vanished"], cmp["newly_skipped"]
            else:
                att.detail = f"{run.classification}" + (f" ({run.exceeded} limit)" if run.exceeded else "")
            att.exceptions = _infer_exceptions(run, sorted({d.exception for d in self.analyzer.analyze(
                run.stdout + "\n" + run.stderr, base) if d.exception}))
            att.error_signature = _error_signature(run, att.exceptions)
            if run.classification == "no_tests":
                att.status = "rejected_test_loss"
                att.detail = "no tests ran with this candidate (everything skipped or uncollected)"
                return att
            if not run.passed:
                att.status = "failed"
                return att
            if att.vanished_tests or att.newly_skipped:
                att.status = "rejected_test_loss"
                att.detail = (f"tests vanished: {att.vanished_tests[:3]}" if att.vanished_tests else
                              f"tests newly skipped: {att.newly_skipped[:3]}")
                return att
            att.status, att.confirmed = "passed", (True if self.confirm_runs else None)
            for k in range(self.confirm_runs):
                rem = remaining()
                if rem < self.min_step:
                    att.status, att.confirmed, att.detail = "unconfirmed_pass", False, "budget exhausted before confirmation"
                    break
                again, _ = self._run_in_copy(base, targets, prop, min(self.candidate_timeout, rem))
                if not again.passed:
                    att.status, att.confirmed = "unconfirmed_pass", False
                    att.detail = f"confirmation run {k + 1} was {again.classification} (flaky or order-dependent pass)"
                    break
            return att
        except (PatchError, OSError, UnicodeDecodeError) as exc:
            att.status, att.detail = "rejected_invalid", str(exc)[:300]
            return att

    # ---- main loop
    def run(self, root: str | Path, task: str, task_id: str | None = None,
            targets: list[str] | None = None) -> ResearchResult:
        base = Path(root).resolve(strict=True)
        if not base.is_dir():
            raise NotADirectoryError(str(base))
        task_id = task_id or hashlib.sha256(task.encode()).hexdigest()[:16]
        self._check_size(base)
        before = tree_fingerprint(base)
        started = time.monotonic()
        deadline = started + self.time_budget
        remaining = lambda: deadline - time.monotonic()  # noqa: E731
        notes: list[str] = []
        if self.generator_isolation == "process" and not (
                os.name == "posix" and "fork" in multiprocessing.get_all_start_methods()):
            notes.append("process generator isolation requested but fork is unavailable; using thread isolation "
                         "(a timed-out generator thread cannot be killed)")
        attempts: list[Attempt] = []
        proposals: dict = {}
        info = {"baseline": {}, "isolation": {}}

        def finish(stop, baseline_failed=(), rounds=0, feedback=None):
            verified = [a for a in attempts if a.verified]
            ranked = sorted(verified, key=rank_key)
            best = ranked[0] if ranked else None
            prop, preview = proposals.get(id(best), (None, "")) if best else (None, "")
            board = []
            for i, a in enumerate(ranked[:5]):
                nxt = ranked[i + 1] if i + 1 < len(ranked) else None
                board.append({"round": a.round, "index": a.index, "path": a.path, "status": a.status,
                              "fixed": len(a.fixed_tests), "regressions": len(a.regressions),
                              "vanished": len(a.vanished_tests), "newly_skipped": len(a.newly_skipped),
                              "failing": a.n_failed, "diff_lines": a.diff_lines,
                              "ahead_of_next_by": compare_attempts(a, nxt)["decided_by"] if nxt else None})
            if stop == "resolved" and best and best.status == "passed" and self.procedures:
                self.procedures.record(
                    task_type="repair_research", task_summary=task,
                    procedure=["stable baseline (multiple runs)", f"generate up to {self.max_candidates} candidates per round",
                               "verify each in sandboxed disposable copy", "compare per-test outcomes against baseline",
                               "confirm passing candidate with a fresh run",
                               f"selected candidate for {best.path} (round {best.round})"],
                    repository_fingerprint=before,
                    test_result={"passed": True, "returncode": 0, "duration_seconds": best.duration_seconds})
            unchanged = tree_fingerprint(base) == before
            if not unchanged:
                notes.append("WARNING: original tree fingerprint changed during research")
            return ResearchResult(task, stop, list(baseline_failed), attempts, best, prop, preview, rounds,
                                  unchanged, notes, round(time.monotonic() - started, 3), self.time_budget,
                                  info["baseline"], board, feedback or {}, info["isolation"])

        # ---- 2. reliable baseline
        runs: list[SafeRun] = []
        skipped_links: list[str] = []
        for _ in range(self.baseline_runs):
            rem = remaining()
            if rem < self.min_step:
                return finish("time_budget")
            run, skipped_links = self._run_in_copy(base, targets, None, min(self.baseline_timeout, rem))
            runs.append(run)
            if run.timed_out:
                bound = rem < self.baseline_timeout
                notes.append("baseline cut short by the global time budget" if bound else
                             f"baseline exceeded {self.baseline_timeout:.1f}s timeout")
                info["baseline"] = {"runs": [self._run_row(r) for r in runs], "stable": False}
                return finish("time_budget" if bound else "baseline_timeout")
            if run.classification not in REPAIRABLE | {"passed"}:
                break  # unusable baseline; more runs add nothing
        stop, flaky = self._assess_baseline(runs)
        info["isolation"] = runs[0].isolation
        info["baseline"] = {"runs": [self._run_row(r) for r in runs], "stable": stop != "baseline_unstable",
                            "flaky_tests": flaky, "skipped_symlinks": skipped_links, "fingerprint": before}
        if stop:
            if stop == "baseline_unstable":
                notes.append(f"baseline failing set differs between runs; flaky tests: {flaky[:5]}")
            elif stop == "baseline_error":
                notes.append(f"baseline run was unusable: {runs[-1].classification}")
            return finish(stop)
        baseline_outcome, baseline_failed = runs[0].outcome, runs[0].failed_ids
        diagnostics = [d.to_dict() for d in self.analyzer.analyze(runs[0].stdout + "\n" + runs[0].stderr, base)]

        # ---- rounds
        seen: set = set()
        stop_reason, rounds_used = "exhausted", 0
        try:
            for rnd in range(1, self.max_rounds + 1):
                rem = remaining()
                if rem < self.min_step:
                    stop_reason = "time_budget"
                    break
                rounds_used = rnd
                ledger_records = self.ledger.records(task_id) if self.ledger else []
                feedback = self._build_feedback(task_id, attempts, baseline_failed, rnd, rem, ledger_records, before)
                if self.ledger:
                    prior = [dict(r, stale=r.get("repo_fingerprint") not in (None, before)) for r in ledger_records[-50:]]
                else:
                    prior = [{"path": a.path, "status": a.status, "failed_tests": a.failed_tests,
                              "exceptions": a.exceptions, "detail": a.detail, "stale": False}
                             for a in attempts if a.verified and a.status != "passed"][-50:]
                ctx = ResearchContext(task, rnd, list(baseline_failed), diagnostics, prior, feedback)
                gen_timeout = min(self.generator_timeout, rem)
                try:
                    produced = _run_generator(self.generator, ctx, gen_timeout, self.generator_isolation,
                                              self.generator_memory_mb)
                except GeneratorTimeout:
                    bound = rem < self.generator_timeout
                    notes.append(("generator cut short by the global time budget" if bound else
                                  f"generator exceeded {self.generator_timeout:.1f}s timeout") +
                                 (" (thread abandoned; it may still be running)" if self.generator_isolation == "thread" else " (process killed)"))
                    stop_reason = "time_budget" if bound else "generator_timeout"
                    break
                except Exception as exc:  # noqa: BLE001
                    notes.append(f"generator raised {type(exc).__name__}: {exc}")
                    stop_reason = "generator_error"
                    break
                items = list(produced)[: self.max_candidates]
                round_attempts: list[Attempt] = []
                for idx, item in enumerate(items):
                    cand = self._coerce(item)
                    if cand is None:
                        notes.append(f"round {rnd}: generator returned an invalid item at position {idx}; skipped")
                        continue
                    if remaining() < self.min_step:
                        stop_reason = "time_budget"
                        break
                    att = self._evaluate(base, targets, cand, rnd, idx, seen, task_id, before,
                                         baseline_outcome, baseline_failed, remaining, proposals)
                    attempts.append(att)
                    round_attempts.append(att)
                    if self.ledger and not att.budget_cut and att.status != "passed":
                        self.ledger.append(task_id, att, before, hashlib.sha256(
                            (base / cand.path).read_bytes()).hexdigest() if (base / cand.path).is_file() else None)
                if any(a.status == "passed" for a in round_attempts):
                    stop_reason = "resolved"
                    break
                if stop_reason == "time_budget":
                    break
        except _Budget:
            stop_reason = "time_budget"
        final_feedback = self._build_feedback(task_id, attempts, baseline_failed, min(rounds_used + 1, self.max_rounds),
                                              remaining(), self.ledger.records(task_id) if self.ledger else [], before)
        return finish(stop_reason, baseline_failed, rounds_used, final_feedback)

    @staticmethod
    def _run_row(r: SafeRun) -> dict:
        return {"classification": r.classification, "counts": r.counts, "failed_ids": r.failed_ids,
                "duration_seconds": round(r.duration_seconds, 3)}
