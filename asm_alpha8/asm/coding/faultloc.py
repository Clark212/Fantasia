"""DEV11 semantic fault localization and verified repair workflow.

Connects the earlier generations into one loop:
- DEV8.1 supplies the sandboxed, stability-checked test execution, candidate verification, regression and
  vanished-test detection, and the failure ledger.
- DEV9 supplies function boundaries and the call graph (affected callers).
- DEV10 supplies behavioural deviations (likely_bug / name-behaviour mismatches) as evidence.
New here: per-test line coverage collection (spectrum-based fault localization), traceback evidence, a
combined suspect ranking with an explainable per-source breakdown, a text-preserving single-site mutation
engine used both for template repair candidates and for seeded-fault benchmarking, a repair workflow that
only ever *proposes*, and an evidence dossier explaining why each candidate was accepted or rejected.

Honest scope: there is no code-generating model. Repair candidates are single-site operator/constant/condition
edits ("template repair"), so only faults of that shape can be repaired. Passing the given tests is evidence,
not proof of correctness; the dossier says what was and was not verified.
"""
from __future__ import annotations

import ast
import difflib
import hashlib
import json
import math
import re
import tempfile
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .patches import PatchProposal, PatchProposalBuilder, apply_proposal
from .repair_ops import family_of
from .research import CodingResearchLoop, Candidate, FailureLedger, compare_outcomes, tree_fingerprint
from .sandbox import SafeTestRunner, copy_repo, interpreter
from .semantics import SemanticAnalyzer
from .counterexamples import analyze_candidates
from .verification import verify_patch
from .understanding import CodeUnderstanding

TRACE_PLUGIN = r'''
import json, os, sys
import pytest
ROOT = os.path.abspath(os.environ["ASM_TRACE_ROOT"]) + os.sep
OUT = os.environ["ASM_TRACE_OUT"]
DATA = {"lines": {}, "outcomes": {}, "failures": {}, "calls": {}, "records": {}}
_lines = None
import ast as _ast, pickle as _pickle, base64 as _b64, hashlib as _hl
CALLS = {}
_seen_calls = {}
RECORDS = {}
_rec_count = {}
_current_test = [None]
def _lit_repr(v, limit=200):
    try:
        r = repr(v)
        if len(r) <= limit:
            _ast.literal_eval(r)
            return r
    except Exception:
        pass
    return None
def _view(args):
    out = []
    for a in args:
        lit = _lit_repr(a)
        if lit is not None:
            out.append({"k": "lit", "r": lit})
        elif hasattr(a, "__dict__") and not isinstance(a, type):
            attrs = {}
            for name, val in list(vars(a).items())[:12]:
                r = _lit_repr(val, 100)
                if r is not None and not name.startswith("__"):
                    attrs[name] = r
            out.append({"k": "obj", "cls": type(a).__qualname__, "attrs": attrs})
        else:
            out.append({"k": "other", "cls": type(a).__qualname__})
    return out
_QN = {}
def _qualname(co):
    # code.co_qualname exists from Python 3.11; on older project interpreters derive it from the source (DEV14)
    q = getattr(co, "co_qualname", None)
    if q:
        return q
    fn = co.co_filename
    if fn not in _QN:
        table = {}
        try:
            with open(fn, encoding="utf-8") as fh:
                tree = _ast.parse(fh.read())
            def walk(node, prefix):
                for ch in _ast.iter_child_nodes(node):
                    if isinstance(ch, (_ast.FunctionDef, _ast.AsyncFunctionDef, _ast.ClassDef)):
                        q2 = prefix + ch.name
                        for ln in [ch.lineno] + [d.lineno for d in ch.decorator_list]:
                            table.setdefault((ln, ch.name), q2)
                        walk(ch, q2 + (".<locals>." if not isinstance(ch, _ast.ClassDef) else "."))
                    else:
                        walk(ch, prefix)
            walk(tree, "")
        except Exception:
            pass
        _QN[fn] = table
    return _QN[fn].get((co.co_firstlineno, co.co_name), co.co_name)
def _record_object(frame):
    co = frame.f_code
    if co.co_flags & 0x0C:  # *args / **kwargs signatures are not replayed
        return
    rel = os.path.relpath(os.path.abspath(co.co_filename), ROOT)
    if _skip(rel):
        return
    key = rel + ":" + _qualname(co)
    tk = (key, _current_test[0])
    if _rec_count.get(key, 0) >= 300 or _rec_count.get(tk, 0) >= 3 or _rec_count.get(key + "#bytes", 0) >= 600000:
        return
    names = co.co_varnames[:co.co_argcount + co.co_kwonlyargcount]
    if names and isinstance(frame.f_locals.get(names[0]), type):
        return  # classmethods: the bound class would be passed twice on replay
    try:
        args = tuple(frame.f_locals.get(a) for a in names)
        blob = _pickle.dumps(args, protocol=4)
        if len(blob) > 40000:
            return
        digest = _hl.sha1(blob).hexdigest()
        bucket = RECORDS.setdefault(key, [])
        if any(r["h"] == digest and r["test"] == _current_test[0] for r in bucket):
            return
        _rec_count[key] = _rec_count.get(key, 0) + 1
        _rec_count[tk] = _rec_count.get(tk, 0) + 1
        _rec_count[key + "#bytes"] = _rec_count.get(key + "#bytes", 0) + len(blob)
        bucket.append({"test": _current_test[0], "h": digest, "pickle": _b64.b64encode(blob).decode(), "view": _view(args)})
    except Exception:
        pass
def _skip(rel):
    parts = rel.split(os.sep)
    stem = os.path.splitext(parts[-1])[0]
    return bool({"tests", "test", "testing"} & set(parts[:-1])) or stem.startswith(("test_", "tests_")) \
        or stem.endswith(("_test", "_tests")) or parts[-1] == "conftest.py"
def _record(frame):
    co = frame.f_code
    names = co.co_varnames[:co.co_argcount + co.co_kwonlyargcount]
    if not names or names[0] in ("self", "cls"):
        return
    rel = os.path.relpath(os.path.abspath(co.co_filename), ROOT)
    if _skip(rel):
        return
    key = rel + ":" + co.co_name
    n = _seen_calls.get(key, 0)
    if n >= 30 or len(CALLS.get(key, [])) >= 12:
        return
    _seen_calls[key] = n + 1
    try:
        r = repr(tuple(frame.f_locals.get(a) for a in names))
        if len(r) <= 300:
            _ast.literal_eval(r)
            if r not in CALLS.setdefault(key, []):
                CALLS[key].append(r)
    except Exception:
        pass
def _local(frame, event, arg):
    if event == "line":
        _lines.add((frame.f_code.co_filename, frame.f_lineno))
    return _local
def _global(frame, event, arg):
    fn = frame.f_code.co_filename
    if fn and not fn.startswith("<") and os.path.abspath(fn).startswith(ROOT):
        if event == "call":
            _record(frame)
            _record_object(frame)
        return _local
    return None
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    global _lines
    _lines = set()
    _current_test[0] = _nid(item.nodeid)
    old = sys.gettrace()
    sys.settrace(_global)
    try:
        yield
    finally:
        sys.settrace(old)
        by_file = {}
        for fn, ln in _lines:
            rel = os.path.relpath(os.path.abspath(fn), ROOT)
            by_file.setdefault(rel, set()).add(ln)
        DATA["lines"][_nid(item.nodeid)] = {k: sorted(v) for k, v in by_file.items()}
def _nid(nodeid):
    # pytest < 4 puts the class instance in node ids ("f.py::C::()::test"); JUnit and pytest >= 4 do not (DEV14)
    return nodeid.replace("::()", "")
_SEVERITY = {"passed": 0, "skipped": 1, "failed": 2, "error": 3}
def _set_outcome(nodeid, outcome, longrepr):
    # several reports can arrive for ONE test (subtests report each failure separately and then a final "passed" call
    # report; teardown can fail after a passing call): the worst outcome wins, never the last one
    prev = DATA["outcomes"].get(nodeid)
    if prev is None or _SEVERITY.get(outcome, 0) > _SEVERITY.get(prev, 0):
        DATA["outcomes"][nodeid] = outcome
    if outcome in ("failed", "error") and nodeid not in DATA["failures"]:
        DATA["failures"][nodeid] = str(longrepr)[-6000:]
def pytest_runtest_logreport(report):
    if report.when == "call" or (report.when == "setup" and report.outcome != "passed"):
        _set_outcome(_nid(report.nodeid), report.outcome, report.longrepr)
    elif report.when == "teardown" and report.outcome == "failed":
        _set_outcome(_nid(report.nodeid), "error", report.longrepr)
def pytest_collectreport(report):
    if report.outcome == "failed":
        DATA["outcomes"][_nid(report.nodeid)] = "error"
        DATA["failures"][_nid(report.nodeid)] = str(report.longrepr)[-6000:]
def _prune_records():
    for key, recs in list(RECORDS.items()):
        failing = [r for r in recs if DATA["outcomes"].get(r["test"]) in ("failed", "error")]
        passing = [r for r in recs if DATA["outcomes"].get(r["test"]) not in ("failed", "error")]
        keep = failing[:20]
        room = 60 - len(keep)
        if len(passing) > room:
            step = len(passing) / room
            passing = [passing[int(i * step)] for i in range(room)]
        RECORDS[key] = keep + passing
def pytest_sessionfinish(session, exitstatus):
    DATA["calls"] = CALLS
    _prune_records()
    DATA["records"] = RECORDS
    with open(OUT, "w") as fh:
        json.dump(DATA, fh)
'''

_FRAME = re.compile(r'File "([^"]+)", line (\d+), in (\S+)')


@dataclass
class Spectrum:
    outcomes: dict  # test id -> passed | failed | error | skipped
    lines: dict  # test id -> {relpath: [line, ...]}
    failures: dict  # test id -> traceback text (native format)
    run: dict = field(default_factory=dict)  # classification / counts of the traced run
    calls: dict = field(default_factory=dict)  # "relpath:function" -> reprs of literal argument tuples seen in tests
    records: dict = field(default_factory=dict)  # "relpath:co_qualname" -> pickled argument tuples with test attribution
    complete: bool = True
    incomplete_reason: str | None = None
    excluded: dict = field(default_factory=dict)  # test id -> why it was removed (instrumentation-sensitive, ...)

    @property
    def failing(self) -> list:
        return sorted(t for t, o in self.outcomes.items() if o in {"failed", "error"})

    @property
    def passing(self) -> list:
        return sorted(t for t, o in self.outcomes.items() if o == "passed")


def collect_spectrum(root: Path, targets, runner: SafeTestRunner, timeout: float = 120.0) -> Spectrum:
    """Run the tests once inside a throwaway copy with the tracing plugin; returns per-test coverage and failures."""
    with tempfile.TemporaryDirectory(prefix="asm_dev11_") as td:
        td = Path(td)
        repo = td / "repo"
        copy_repo(root, repo)
        plugin_dir = td / "plugin"
        plugin_dir.mkdir()
        (plugin_dir / "asm_trace_plugin.py").write_text(TRACE_PLUGIN)
        out = td / "trace.json"
        run = runner.run_pytest(repo, targets, timeout=timeout,
                                extra_args=["-p", "asm_trace_plugin", "--tb=native"],
                                env_extra={"PYTHONPATH": str(plugin_dir), "ASM_TRACE_ROOT": str(repo),
                                           "ASM_TRACE_OUT": str(out)})
        have_trace = out.exists()
        data = json.loads(out.read_text()) if have_trace else {"lines": {}, "outcomes": {}, "failures": {}, "calls": {}}
        failures = {k: v.replace(str(repo) + "/", "") for k, v in data["failures"].items()}
        # A spectrum is only trustworthy if the traced run finished normally and the plugin saw what pytest saw.
        reason = None
        if run.timed_out:
            reason = "the traced test run timed out, so coverage is missing or partial"
        elif run.classification not in {"passed", "tests_failed", "collection_error"}:
            reason = f"the traced test run ended as {run.classification!r}" + (f" ({run.exceeded} limit)" if run.exceeded else "")
        elif not have_trace:
            reason = "the tracing plugin produced no data"
        else:
            plugin_failing = {t for t, o in data["outcomes"].items() if o in {"failed", "error"}}
            if plugin_failing != set(run.failed_ids):
                reason = "the tracing plugin and pytest disagree about which tests failed"
        return Spectrum(data["outcomes"], data["lines"], failures,
                        {"classification": run.classification, "counts": run.counts, "timed_out": run.timed_out},
                        data.get("calls", {}), data.get("records", {}), reason is None, reason)


def reconcile_spectrum(spectrum: Spectrum, plain_failed: set, sensitive: set | None = None) -> set:
    """Remove INSTRUMENTATION-SENSITIVE tests from a traced spectrum: tests whose pass/fail outcome under tracing differs
    from a plain (untraced) run, e.g. clock-dependent tests slowed by sys.settrace, or thread races. Their coverage
    describes a run that does not match reality, so they must not vote in localization. `sensitive` carries a set found
    earlier (later iterations reuse it). Returns the set removed. Marks the spectrum incomplete if no failure is left."""
    traced_failed = set(spectrum.failing)
    found = set(sensitive or set()) | (traced_failed ^ set(plain_failed))
    for t in found:
        if t in spectrum.outcomes or t in spectrum.lines:
            spectrum.excluded[t] = "outcome differs between the traced and plain runs (instrumentation-sensitive or flaky)"
            spectrum.outcomes.pop(t, None)
            spectrum.lines.pop(t, None)
            spectrum.failures.pop(t, None)
    if spectrum.complete and not spectrum.failing and traced_failed:
        spectrum.complete = False
        spectrum.incomplete_reason = "every failing test is instrumentation-sensitive (its outcome changes under tracing)"
    return found


def ochiai(ef: int, ep: int, total_failed: int) -> float:
    denom = math.sqrt(total_failed * (ef + ep)) if total_failed and (ef + ep) else 0.0
    return ef / denom if denom else 0.0


TEST_DIRS = {"tests", "test", "testing"}


def is_test_path(rel: str, collected=()) -> bool:
    """Test code is never a fault suspect and never patched. DEV14: on the real tqdm bug 5 the old rule (top-level
    tests/ or test_*.py only) missed tqdm/tests/tests_tqdm.py, and the workflow 'repaired' the bug by editing the test.
    Now: a tests/test/testing directory at ANY depth, test_*/tests_*/*_test/*_tests module names, conftest.py, and
    every file pytest actually collected tests from (`collected`)."""
    p = Path(rel)
    stem = p.stem
    return bool(TEST_DIRS & set(p.parts[:-1])) or stem.startswith(("test_", "tests_")) or stem.endswith(("_test", "_tests")) \
        or p.name == "conftest.py" or p.as_posix() in collected


@dataclass
class Suspect:
    qname: str
    path: str
    line: int
    end_line: int
    score: float
    sources: dict  # source -> score in [0, 1]
    evidence: list  # human-readable reasons
    top_lines: list = field(default_factory=list)  # [(line, ochiai)] most suspicious executed lines


@dataclass
class LocalizationReport:
    failing_tests: list
    passing_count: int
    suspects: list
    weights: dict
    impacts: dict  # qname -> {"callers": [...], "covering_tests": n}
    notes: list
    line_scores: dict = field(default_factory=dict)  # relpath -> {line: ochiai}
    spectrum_ok: bool = True
    spectrum_note: str | None = None
    semantic_mode: str = "tiebreak"

    def rank_of(self, qname: str, source: str | None = None) -> int | None:
        order = self.suspects if source is None else sorted(
            self.suspects, key=lambda s: (-s.sources.get(source, 0.0), s.path, s.line))
        for i, s in enumerate(order, 1):
            if s.qname == qname:
                return i
        return None


DEFAULT_WEIGHTS = {"spectrum": 0.5, "traceback": 0.35, "semantic": 0.15}
_SEMANTIC_STRENGTH = {"likely_bug": 1.0, "name_behavior_mismatch": 1.0, "predicate_not_boolean": 0.6,
                      "name_implies_pure_but_has_effects": 0.5, "name_implies_effect_but_pure": 0.4,
                      "validator_cannot_fail": 0.4, "static_dynamic_disagreement": 0.3}


class FaultLocalizer:
    def __init__(self, runner: SafeTestRunner | None = None, weights: dict | None = None, use_semantic: bool = True,
                 semantic_top_k: int = 10, trace_timeout: float = 120.0, semantic_mode: str = "tiebreak"):
        if semantic_mode not in {"tiebreak", "weighted"}:
            raise ValueError("semantic_mode must be 'tiebreak' or 'weighted'")
        # DEV11 measured DEV10 evidence at 0/40 on real faults, so it is not allowed to outvote coverage or tracebacks:
        # by default it only orders suspects whose spectrum+traceback scores are exactly tied.
        self.semantic_mode = semantic_mode
        self.runner = runner or SafeTestRunner(timeout_seconds=60)
        self.weights = dict(weights or DEFAULT_WEIGHTS)
        self.use_semantic, self.semantic_top_k, self.trace_timeout = use_semantic, semantic_top_k, trace_timeout

    def localize(self, root: str | Path, targets=None, spectrum: Spectrum | None = None) -> LocalizationReport:
        with interpreter(self.runner.python):  # the project's interpreter, also for semantic probes
            return self._localize(root, targets, spectrum)

    def _localize(self, root: str | Path, targets=None, spectrum: Spectrum | None = None) -> LocalizationReport:
        base = Path(root).resolve(strict=True)
        notes: list = []
        spec = spectrum or collect_spectrum(base, targets, self.runner, self.trace_timeout)
        if not spec.complete:
            return LocalizationReport(spec.failing, len(spec.passing), [], self.weights, {},
                                      [f"incomplete spectrum: {spec.incomplete_reason}; refusing to rank on partial evidence"],
                                      {}, False, spec.incomplete_reason, self.semantic_mode)
        failing = spec.failing
        if not failing:
            return LocalizationReport([], len(spec.passing), [], self.weights, {}, ["no failing tests"], {}, True,
                                      None, self.semantic_mode)
        und = CodeUnderstanding().analyze(base)
        collected = {t.split("::", 1)[0] for t in spec.outcomes}
        is_test = lambda rel: is_test_path(rel, collected)  # noqa: E731
        funcs = [f for f in und.functions if not is_test(f.path)]
        by_file: dict = defaultdict(list)
        for f in funcs:
            by_file[f.path].append(f)

        def function_at(path: str, line: int):
            best = None
            for f in by_file.get(path, []):
                if f.line <= line <= f.end_line and (best is None or (f.end_line - f.line) < (best.end_line - best.line)):
                    best = f
            return best

        # --- spectrum: Ochiai on executed lines, aggregated to functions (max line score)
        total_failed = len(failing)
        counts: dict = defaultdict(lambda: [0, 0])  # (path, line) -> [ef, ep]
        for tid, per_file in spec.lines.items():
            o = spec.outcomes.get(tid)
            if o not in {"failed", "passed"}:
                continue
            for path, lines in per_file.items():
                if is_test(path):
                    continue
                for ln in lines:
                    counts[(path, ln)][0 if o == "failed" else 1] += 1
        line_scores: dict = defaultdict(dict)
        func_spec: dict = defaultdict(float)
        func_lines: dict = defaultdict(list)
        for (path, ln), (ef, ep) in counts.items():
            sc = ochiai(ef, ep, total_failed)
            f = function_at(path, ln)
            if f is None:
                continue
            line_scores[path][ln] = round(sc, 4)
            if sc > func_spec[f.qname]:
                func_spec[f.qname] = sc
            func_lines[f.qname].append((ln, round(sc, 4)))
        # --- traceback: innermost repo (non-test) frame is strongest, decaying outward
        func_tb: dict = defaultdict(float)
        tb_notes: dict = defaultdict(list)
        for tid in failing:
            frames = [(m.group(1), int(m.group(2))) for m in _FRAME.finditer(spec.failures.get(tid, ""))]
            repo_frames = []
            for path, ln in frames:
                rel = path.split("repo/")[-1] if "repo/" in path else path
                if is_test(rel) or rel.startswith("/"):
                    continue
                f = function_at(rel, ln)
                if f:
                    repo_frames.append((f.qname, rel, ln))
            for depth, (q, rel, ln) in enumerate(reversed(repo_frames)):
                w = 0.7 ** depth
                if w > func_tb[q]:
                    func_tb[q] = w
                tb_notes[q].append(f"on the failing stack of {tid.split('::')[-1]} at {rel}:{ln}" +
                                   (" (innermost repository frame)" if depth == 0 else ""))
        candidates = set(func_spec) | set(func_tb)
        if not candidates:
            notes.append("no repository code was executed by the failing tests")
        # --- semantic evidence for the top candidates only (probing executes code, so keep it narrow)
        func_sem: dict = defaultdict(float)
        sem_notes: dict = defaultdict(list)
        pre = sorted(candidates, key=lambda q: -(self.weights["spectrum"] * func_spec[q] + self.weights["traceback"] * func_tb[q]))
        if self.use_semantic and candidates:
            top = set(pre[: self.semantic_top_k])
            try:
                rep = SemanticAnalyzer(per_module_timeout=20, probe_budget_seconds=40).analyze(base, probe_only=top)
                for fnd in rep.findings:
                    if fnd.qname in top and fnd.kind in _SEMANTIC_STRENGTH:
                        v = _SEMANTIC_STRENGTH[fnd.kind]
                        func_sem[fnd.qname] = max(func_sem[fnd.qname], v)
                        sem_notes[fnd.qname].append(f"DEV10 {fnd.kind}: {fnd.message}")
            except Exception as exc:  # semantic evidence is optional; never block localization
                notes.append(f"semantic evidence unavailable: {type(exc).__name__}: {exc}")
        # --- combine
        suspects = []
        info = {f.qname: f for f in funcs}
        for q in candidates:
            f = info[q]
            src = {"spectrum": round(func_spec[q], 4), "traceback": round(func_tb[q], 4), "semantic": round(func_sem[q], 4)}
            score = self.weights["spectrum"] * src["spectrum"] + self.weights["traceback"] * src["traceback"]
            if self.semantic_mode == "weighted":
                score += self.weights["semantic"] * src["semantic"]
            ev = []
            if func_spec[q]:
                ev.append(f"executed by failing tests (Ochiai {func_spec[q]:.2f})")
            ev += tb_notes.get(q, [])[:2] + sem_notes.get(q, [])
            suspects.append(Suspect(q, f.path, f.line, f.end_line, round(score, 4), src, ev,
                                    sorted(func_lines[q], key=lambda t: (-t[1], t[0]))[:5]))
        suspects.sort(key=lambda s: (-s.score, -(s.sources['semantic'] if self.semantic_mode == 'tiebreak' else 0.0), s.path, s.line))
        # --- DEV9 call graph: who is affected if a suspect is wrong, and how many tests exercise it
        impacts = {}
        for s in suspects[:10]:
            callers = und.callers(s.qname, transitive=True)
            covering = sum(1 for tid, per in spec.lines.items()
                           if any(s.line <= ln <= s.end_line for ln in per.get(s.path, [])))
            impacts[s.qname] = {"callers": [c for c in callers if not c.endswith("<module>")][:15], "covering_tests": covering}
        return LocalizationReport(failing, len(spec.passing), suspects, self.weights, impacts, notes,
                                  {k: dict(v) for k, v in line_scores.items()}, True, None, self.semantic_mode)


# ================================================================== mutation engine
@dataclass
class Site:
    path: str
    line: int
    start: int  # absolute byte offsets into the file
    end: int
    kind: str  # arith | compare | bool | const | negate | not
    original: str
    options: list
    function: str | None
    col: int = 0
    ambiguous: bool = False  # another site on the same line has the same kind and token: describe() adds the column

    def describe(self, option: str) -> str:
        where = f"line {self.line} col {self.col}" if self.ambiguous else f"line {self.line}"
        return f"{self.kind}: {self.original!r} -> {option!r} at {where}"


_ARITH = {ast.Add: ("+", ["-", "*"]), ast.Sub: ("-", ["+"]), ast.Mult: ("*", ["+", "//"]),
          ast.FloorDiv: ("//", ["*", "%"]), ast.Mod: ("%", ["//"])}
_CMP = {ast.Lt: ("<", r"<(?!=)", ["<=", ">"]), ast.LtE: ("<=", r"<=", ["<", ">="]),
        ast.Gt: (">", r">(?!=)", [">=", "<"]), ast.GtE: (">=", r">=", [">", "<="]),
        ast.Eq: ("==", r"==", ["!="]), ast.NotEq: ("!=", r"!=", ["=="]),
        ast.In: ("in", r"\bin\b", ["not in"]), ast.NotIn: ("not in", r"\bnot\s+in\b", ["in"]),
        ast.Is: ("is", r"\bis\b(?!\s+not\b)", ["is not"]), ast.IsNot: ("is not", r"\bis\s+not\b", ["is"])}
_KIND_PRIORITY = {"compare": 0, "arith": 1, "negate": 2, "const": 3, "bool": 4, "not": 5}


def _offsets(src: bytes) -> list:
    starts, pos = [0], 0
    for ln in src.splitlines(keepends=True):
        pos += len(ln)
        starts.append(pos)
    return starts


def enumerate_sites(source: str, path: str, ranges: list) -> list:
    """Single-site mutation points inside function bodies. `ranges` = [(qname, start_line, end_line)] from DEV9."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []
    src = source.encode("utf-8")
    starts = _offsets(src)

    def off(line, col):
        return starts[line - 1] + col

    def func_at(line):
        best = None
        for q, a, b in ranges:
            if a <= line <= b and (best is None or (b - a) < (best[2] - best[1])):
                best = (q, a, b)
        return best[0] if best else None

    sites: list = []

    def add(node_line, start, end, kind, original, options):
        q = func_at(node_line)
        if q is not None and options:
            sites.append(Site(path, node_line, start, end, kind, original, options, q, start - starts[node_line - 1]))

    def find_token(lo, hi, pattern):
        m = re.search(pattern.encode(), src[lo:hi])
        return (lo + m.start(), lo + m.end()) if m else None

    skip_ids: set = set()
    for n in ast.walk(tree):  # constants inside f-strings and annotations are not edited
        if isinstance(n, ast.JoinedStr):
            skip_ids |= {id(x) for x in ast.walk(n)}
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for a in n.args.posonlyargs + n.args.args + n.args.kwonlyargs:
                if a.annotation is not None:
                    skip_ids |= {id(x) for x in ast.walk(a.annotation)}
            if n.returns is not None:
                skip_ids |= {id(x) for x in ast.walk(n.returns)}
            for d in n.decorator_list:
                skip_ids |= {id(x) for x in ast.walk(d)}
            if n.body and isinstance(n.body[0], ast.Expr) and isinstance(getattr(n.body[0], "value", None), ast.Constant):
                skip_ids.add(id(n.body[0].value))
    for n in ast.walk(tree):
        if id(n) in skip_ids:
            continue
        if isinstance(n, ast.BinOp) and type(n.op) in _ARITH:
            sym, options = _ARITH[type(n.op)]
            lo, hi = off(n.left.end_lineno, n.left.end_col_offset), off(n.right.lineno, n.right.col_offset)
            tok = find_token(lo, hi, re.escape(sym))
            if tok:
                add(n.lineno, tok[0], tok[1], "arith", sym, options)
        elif isinstance(n, ast.Compare):
            lefts = [n.left] + list(n.comparators[:-1])
            for op, left, right in zip(n.ops, lefts, n.comparators):
                if type(op) in _CMP:
                    sym, pat, options = _CMP[type(op)]
                    lo, hi = off(left.end_lineno, left.end_col_offset), off(right.lineno, right.col_offset)
                    tok = find_token(lo, hi, pat)
                    if tok:
                        add(left.end_lineno, tok[0], tok[1], "compare", sym, options)
        elif isinstance(n, ast.BoolOp):
            sym = "and" if isinstance(n.op, ast.And) else "or"
            for a, b in zip(n.values, n.values[1:]):
                lo, hi = off(a.end_lineno, a.end_col_offset), off(b.lineno, b.col_offset)
                tok = find_token(lo, hi, rf"\b{sym}\b")
                if tok:
                    add(a.end_lineno, tok[0], tok[1], "bool", sym, ["or" if sym == "and" else "and"])
        elif isinstance(n, ast.Constant) and not isinstance(n.value, (str, bytes, float, complex)) and n.value is not None \
                and n.value is not Ellipsis:
            lo, hi = off(n.lineno, n.col_offset), off(n.end_lineno, n.end_col_offset)
            text = src[lo:hi].decode()
            if isinstance(n.value, bool):
                add(n.lineno, lo, hi, "const", text, ["False" if n.value else "True"])
            elif text.isdigit():
                v = n.value
                add(n.lineno, lo, hi, "const", text, [str(v + 1)] + ([str(v - 1)] if v > 0 else []))
        elif isinstance(n, (ast.If, ast.While, ast.IfExp)) and not (
                isinstance(n.test, ast.UnaryOp) and isinstance(n.test.op, ast.Not)):
            t = n.test
            lo, hi = off(t.lineno, t.col_offset), off(t.end_lineno, t.end_col_offset)
            add(t.lineno, lo, hi, "negate", src[lo:hi].decode().replace("\n", " ")[:40], [f"not ({src[lo:hi].decode()})"])
        elif isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.Not):
            lo = off(n.lineno, n.col_offset)
            m = re.match(rb"not\s*", src[lo:])  # only the keyword: `not (X)` must become `(X)`, not `X)`
            if m:
                add(n.lineno, lo, lo + m.end(), "not", src[lo:lo + m.end()].decode(), [""])
    uniq = {}
    for s in sites:
        uniq[(s.start, s.end, s.kind)] = s
    out = sorted(uniq.values(), key=lambda s: (s.start, s.end))
    # DEV14: descriptions must identify a patch uniquely (found when re-judging DEV13 records: two '0' constants on one
    # line had the same description, so a record could not say which program had been judged)
    groups: dict = {}
    for s in out:
        groups.setdefault((s.line, s.kind, s.original), []).append(s)
    for same in groups.values():
        if len(same) > 1:
            for s in same:
                s.ambiguous = True
    return out


def apply_site(source: str, site: Site, option: str) -> str:
    src = source.encode("utf-8")
    return (src[:site.start] + option.encode("utf-8") + src[site.end:]).decode("utf-8")


def ast_normal(source: str) -> str:
    try:
        return ast.unparse(ast.parse(source))
    except (SyntaxError, ValueError):
        return source


def _line_rank(scores: dict, line: int) -> int:
    """1 = the most suspicious distinct score in this file's line scores."""
    distinct = sorted({v for v in scores.values()}, reverse=True)
    v = scores.get(line, 0.0)
    return distinct.index(v) + 1 if v in distinct else len(distinct) + 1


def _meta(scores: dict, line: int, kind: str, family: str, original: str, option: str, extra: dict | None = None) -> dict:
    """DEV16: structured description of a candidate, the input of learned candidate ranking. Purely descriptive;
    generation order and content are unchanged."""
    m = {"kind": kind, "family": family, "line": line, "line_score": round(scores.get(line, 0.0), 4),
         "line_rank": _line_rank(scores, line), "original": original[:40], "option": option[:40]}
    if extra:
        m.update(extra)
    return m


def generate_candidates(source: str, path: str, suspect: Suspect, ranges: list, line_scores: dict,
                        extended: bool = False, failure_texts=(), pairs: bool = True) -> list:
    """Template repair candidates for one suspect function, most suspicious source lines first.
    extended=False is exactly DEV14 (single-site operator / constant / condition edits). extended=True (DEV15) adds the
    repair_ops families on the same line ordering (DEV14 templates first on each line), then two-edit pairs."""
    if is_test_path(path):  # defence in depth: the localizer already excludes test code
        return []
    sites = [s for s in enumerate_sites(source, path, ranges) if s.function == suspect.qname]
    scores = line_scores.get(path, {})
    if not extended:
        sites.sort(key=lambda s: (-scores.get(s.line, 0.0), _KIND_PRIORITY[s.kind], s.start))
        out = []
        for s in sites:
            for opt in s.options:
                new = apply_site(source, s, opt)
                try:
                    ast.parse(new)
                except SyntaxError:
                    continue
                c = Candidate(path, new, s.describe(opt))
                c.meta = _meta(scores, s.line, s.kind, "single_site", s.original, opt)
                out.append(c)
        return out
    from . import repair_ops as R
    starts = _offsets(source.encode("utf-8"))
    ext_sites = R.site_edits(source, path, ranges, suspect.qname, starts)
    singles = []  # (sort key, Candidate)
    for s in sites + ext_sites:
        tier, pri = (0, _KIND_PRIORITY[s.kind]) if s.kind in _KIND_PRIORITY else (1, R.FAMILY_PRIORITY[s.kind])
        for k, opt in enumerate(s.options):
            singles.append(((-scores.get(s.line, 0.0), tier, pri, s.start, k), s, opt, None))
    for ins in R.insertion_edits(source, path, ranges, suspect.qname, scores, failure_texts):
        singles.append(((-scores.get(ins.anchor_line, 0.0), 1, R.FAMILY_PRIORITY[ins.kind], ins.start_line, 0), None, None, ins))
    singles.sort(key=lambda x: x[0])
    out, seen = [], {ast_normal(source)}
    for _, s, opt, ins in singles:
        new = apply_site(source, s, opt) if ins is None else R.apply_insertion(source, ins)
        try:
            norm = ast.unparse(ast.parse(new))
        except SyntaxError:
            continue
        if norm in seen:  # e.g. a guard identical to an existing one: same program, no new evidence
            continue
        seen.add(norm)
        c = Candidate(path, new, s.describe(opt) if ins is None else ins.describe())
        if ins is None:
            c.meta = _meta(scores, s.line, s.kind, "single_site" if s.kind in _KIND_PRIORITY else s.kind, s.original, opt)
        else:
            c.meta = _meta(scores, ins.anchor_line, ins.kind, ins.kind, "", ins.note,
                           {"span": ins.end_line - ins.start_line + 1})
        out.append(c)
    if pairs:
        pool = [(k, s, opt) for k, s, opt, ins in singles if ins is None and k[0] < 0][: R.MAX_PAIR_SITES]
        made = 0
        for i in range(len(pool)):
            for j in range(i + 1, len(pool)):
                if made >= R.MAX_PAIRS:
                    break
                (_, a, oa), (_, b, ob) = pool[i], pool[j]
                if a is b:
                    continue
                new = R.apply_pair(source, a, oa, b, ob)
                if new is None:
                    continue
                try:
                    norm = ast.unparse(ast.parse(new))
                except SyntaxError:
                    continue
                if norm in seen:
                    continue
                seen.add(norm)
                made += 1
                c = Candidate(path, new, f"pair: {a.describe(oa)} + {b.describe(ob)}")
                c.meta = _meta(scores, a.line, f"{a.kind}+{b.kind}", "pair", a.original, oa,
                               {"line2": b.line, "line_score2": round(scores.get(b.line, 0.0), 4), "same_line": a.line == b.line})
                out.append(c)
    return out


# ================================================================ workflow + dossier
LIMITS = [
    "No code-generating model: only template edits are tried (DEV14 single-site operator / constant / condition edits; "
    "DEV15 variable swaps, dropped clauses, getattr fallbacks, guards, try/except wrappers and two-edit pairs within one "
    "function). String/regex edits, new calls and multi-file fixes are outside the repair space.",
    "Passing the given tests is evidence, not proof; behaviour outside those tests is unverified.",
    "Regression protection covers only the test targets that were run.",
    "The original repository is never modified; applying a fix is a separate approved step.",
]


@dataclass
class FixStep:
    iteration: int
    suspect: str
    rank: int
    kind: str  # full | partial
    description: str
    fixed_tests: list
    path: str
    diff: str
    why_accepted: list
    confirmed: bool | None


@dataclass
class Dossier:
    task: str
    status: str  # resolved | partial | unresolved | no_failures | unstable_baseline | incomplete_spectrum | time_budget
    repo_fingerprint: str
    baseline_failing: list
    iterations: list  # per iteration: suspect ranking summary
    steps: list
    rejected: list
    reasons: dict
    diff: str
    impact: dict
    semantic_check: dict
    notes: list
    elapsed_seconds: float
    limits: list = field(default_factory=lambda: list(LIMITS))
    caveats: list = field(default_factory=list)
    examples: list = field(default_factory=list)
    patch_hashes: list = field(default_factory=list)  # [{path, expected_sha256, replacement_sha256}] of the accepted chain
    _proposals: list = field(default_factory=list, repr=False)
    _step_candidates: list = field(default_factory=list, repr=False)
    _seal: dict | None = field(default=None, repr=False)

    def body(self) -> dict:
        d = {k: v for k, v in asdict(self).items() if k not in {"_proposals", "_step_candidates", "_seal"}}
        d["steps"] = [asdict(s) for s in self.steps] if self.steps and not isinstance(self.steps[0], dict) else self.steps
        return json.loads(json.dumps(d, default=str))  # canonical JSON types, so a saved dossier verifies identically

    def seal(self) -> dict:
        from .integrity import seal as _seal
        self._seal = _seal(self.body())
        return self._seal

    def to_dict(self) -> dict:
        d = self.body()
        if self._seal is not None:
            d["integrity"] = self._seal
        return d

    def verify(self) -> tuple:
        from .integrity import verify_dossier
        if self._seal is None:
            return False, ["dossier was never sealed"]
        return verify_dossier(self.to_dict())

    def to_markdown(self) -> str:
        L = [f"# Fault localization & repair dossier", f"**Task:** {self.task}", f"**Status:** {self.status}",
             f"**Elapsed:** {self.elapsed_seconds:.1f}s", ""]
        L += ["## Failing tests at baseline"] + [f"- `{t}`" for t in self.baseline_failing[:15]] + [""]
        for it in self.iterations:
            L += [f"## Suspect ranking (iteration {it['iteration']})", "| rank | function | score | spectrum | traceback | semantic |",
                  "|---|---|---|---|---|---|"]
            for i, s in enumerate(it["suspects"][:8], 1):
                L.append(f"| {i} | `{s['qname']}` | {s['score']:.2f} | {s['sources']['spectrum']:.2f} | "
                         f"{s['sources']['traceback']:.2f} | {s['sources']['semantic']:.2f} |")
            L.append("")
        if self.steps:
            L += ["## Accepted changes"]
            for s in self.steps:
                L += [f"### {s['kind'].title()} fix in `{s['suspect']}` (rank {s['rank']})", f"- change: {s['description']}",
                      f"- behavioural verdict: **{s.get('behavioural_verdict', 'n/a')}** — {s.get('behavioural_note', '')}",
                      f"- confidence: **{s.get('confidence', 'n/a')}** (basis: {', '.join(f + (' [informational]' if f in INFORMATIONAL_FLAGS else '') for f in s.get('confidence_basis', [])) or 'no warning signs'})",
                      f"- other edits that also pass the tests: {len(s.get('alternatives_passing', []))}; "
                      f"suspects tied with this one: {len(s.get('tied_with', []))}",
                      f"- tests fixed: {', '.join(f'`{t}`' for t in s['fixed_tests'][:8])}", "- why accepted:"]
                L += [f"  - {w}" for w in s["why_accepted"]]
                cx = s.get("counterexamples") or {}
                if cx.get("available"):
                    t = cx.get("target", {})
                    L.append(f"- behavioural verification: replayed `{t.get('qname')}`"
                             f"{' (enclosing function of the patched nested function)' if t.get('via_enclosing') else ''} on "
                             f"{cx['inputs_tested']} inputs ({cx.get('inputs_recorded', 0)} recorded); footprint vs original: {cx['footprint']}; "
                             f"differences by component: {cx.get('changed_components')}")
                    for name, ex in (cx.get("changed_on_passing_recorded") or {}).items():
                        if ex:
                            L.append(f"  - WARNING output changes on {len(ex)} input(s) already used by passing tests, e.g. {ex[0]}")
                    for dct in cx.get("distinguishing", [])[:3]:
                        L.append(f"  - input {dct['input']}: chosen → {dct['accepted_output']}, '{dct['alternative']}' → {dct['alternative_output']}")
                elif cx:
                    L.append(f"- counterexample search unavailable: {cx.get('reason')}")
                L += ["```diff", s["diff"].rstrip(), "```", ""]
        L += ["## Rejected candidates", ", ".join(f"{k}: {v}" for k, v in sorted(self.reasons.items())) or "none", ""]
        for r in self.rejected[:12]:
            L.append(f"- `{r['suspect']}` — {r['description']} → **{r['status']}**" + (f" ({r['why']})" if r["why"] else ""))
        if self.impact:
            L += ["", "## Impact (DEV9 call graph + coverage)"]
            for q, v in self.impact.items():
                L.append(f"- `{q}`: {v['covering_tests']} tests execute it; callers: {', '.join(v['callers'][:6]) or 'none'}")
        if self.semantic_check:
            L += ["", "## Behavioural post-check (DEV10)", f"```json\n{json.dumps(self.semantic_check, indent=1)[:1500]}\n```"]
        if self.notes:
            L += ["", "## Notes"] + [f"- {n}" for n in self.notes]
        if self.caveats:
            L += ["", "## Caveats (tests pass, but the evidence is weaker than \"resolved\" suggests)"] + [f"- {c}" for c in self.caveats]
        L += ["", "## What this does not establish"] + [f"- {x}" for x in self.limits]
        return "\n".join(L)


def _problem_context(work: Path, spectrum, module_source: str):
    """DEV18: content for learned shapes from THIS problem: the failing tests' literals, quoted text and exception names
    in their failure messages, and the module's own constants and names."""
    from .content import ProblemContext
    files, names = {}, set()
    for t in spectrum.failing:
        path = t.split("::", 1)[0]
        names.add(t.split("::")[-1].split("[", 1)[0])
        if path not in files:
            try:
                files[path] = (work / path).read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                pass
    return ProblemContext.build(module_source, list(files.values()), names, list(spectrum.failures.values()))


def _ranking_context(spectrum, sus, rank: int, phase: int) -> dict:
    from .repair_ops import _exception_names
    texts = list(spectrum.failures.values())
    tb = {int(m.group(2)) for t in texts for m in _FRAME.finditer(t or "") if m.group(1).endswith(sus.path)}
    return {"suspect_rank": rank, "suspect_score": round(sus.score, 4), "phase": phase, "traceback_lines": tb,
            "exceptions": _exception_names(texts)}


def _unified(path: str, old: str, new: str) -> str:
    return "".join(difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True),
                                        f"a/{path}", f"b/{path}", n=2))


# DEV14 pre-registered rule R1 (benchmarks/preregistration/dev14_fresh_calibration.md), applied to the fresh seed-53
# decoy set: tied_localization fired on 7/42 WRONG decoys and 27/133 correct controls (LR+ 0.82 < 2.0), so it is
# demoted to informational: still reported in the dossier, no longer counted toward the confidence label.
INFORMATIONAL_FLAGS = frozenset({"tied_localization"})


class RepairWorkflow:
    def __init__(self, runner: SafeTestRunner | None = None, localizer: FaultLocalizer | None = None,
                 max_suspects: int = 3, max_iterations: int = 3, candidates_per_round: int = 8, max_rounds: int = 10,
                 time_budget_seconds: float = 180.0, confirm_runs: int = 1, ledger: FailureLedger | None = None,
                 semantic_check: bool = True, counterexamples: bool = True, explore_alternatives: bool = True,
                 max_extra_candidates: int = 30, competing_max_suspects: int = 8, competing_time_seconds: float = 75.0,
                 extended_ops: bool = True, ranker=None, knowledge=None, shapes=None):
        self.counterexamples = counterexamples
        self.ranker = ranker  # DEV16 learned candidate ordering (asm.coding.learned.CandidateRanker); None = DEV15 order
        self.knowledge = knowledge  # DEV17 learned procedures (asm.coding.knowledge.KnowledgeBase): phase 3; None = off
        self.shapes = shapes  # DEV18 learned shapes, content from the problem (asm.coding.shapes.ShapeLibrary); None = off
        self.extended_ops = extended_ops  # DEV15 repair families (repair_ops); False reproduces the DEV14 repair space
        self.explore_alternatives, self.max_extra_candidates = explore_alternatives, max_extra_candidates
        self.competing_max_suspects, self.competing_time = competing_max_suspects, competing_time_seconds
        self.runner = runner or SafeTestRunner(timeout_seconds=60)
        self.localizer = localizer or FaultLocalizer(self.runner)
        self.max_suspects, self.max_iterations = max_suspects, max_iterations
        self.candidates_per_round, self.max_rounds = candidates_per_round, max_rounds
        self.time_budget, self.confirm_runs, self.ledger = time_budget_seconds, confirm_runs, ledger
        self.semantic_check = semantic_check

    def run(self, root: str | Path, targets=None, task: str = "repair failing tests", examples=None) -> Dossier:
        """examples: [{"function": "pkg.mod.func", "args": (..), "expected": value}] -- answers a human gave to a
        distinguishing input from an earlier dossier. They become extra tests in the working copy only (never in the
        original repository), so the repair must satisfy them."""
        with interpreter(self.runner.python):  # tests, replay workers and semantic probes all use the project's python
            return self._run(root, targets, task, examples)

    def _run(self, root: str | Path, targets=None, task: str = "repair failing tests", examples=None) -> Dossier:
        base = Path(root).resolve(strict=True)
        started = time.monotonic()
        fingerprint = tree_fingerprint(base)
        remaining = lambda: self.time_budget - (time.monotonic() - started)  # noqa: E731
        iterations, steps, rejected, notes, proposals, caveats, step_candidates = [], [], [], [], [], [], []
        sensitive: set = set()
        reasons: dict = defaultdict(int)
        impact: dict = {}
        first_failing: list = []
        status = "unresolved"
        with tempfile.TemporaryDirectory(prefix="asm_dev11_work_") as td:
            work = Path(td) / "repo"
            copy_repo(base, work)
            ledger = self.ledger or FailureLedger(Path(td) / "ledger.jsonl")
            if examples:
                lines = ["# generated from human-supplied counterexample answers; exists only in the working copy"]
                for i, ex in enumerate(examples):
                    module, func = ex["function"].rsplit(".", 1)
                    lines += [f"from {module} import {func} as _f{i}",
                              f"def test_asm_counterexample_{i}():", f"    assert _f{i}(*{tuple(ex['args'])!r}) == {ex['expected']!r}"]
                (work / "tests").mkdir(exist_ok=True)
                (work / "tests" / "test_asm_counterexamples.py").write_text("\n".join(lines) + "\n")
                notes.append(f"{len(examples)} human-supplied example(s) were added as tests in the working copy")
            first_loc = None
            if self.ranker is not None:
                notes.append(f"candidate order learned by {self.ranker.provenance}")
            for it in range(1, self.max_iterations + 1):
                if remaining() < 5:
                    status, _ = "time_budget", notes.append("time budget exhausted before localization finished")
                    break
                spectrum = collect_spectrum(work, targets, self.runner, min(120.0, remaining()))
                if not spectrum.complete:
                    status = "incomplete_spectrum"
                    notes.append(f"incomplete spectrum: {spectrum.incomplete_reason}")
                    if it == 1:
                        first_failing = spectrum.failing
                    break
                if it == 1:
                    plain1 = self.runner.run_pytest(work, targets, timeout=min(60.0, max(5.0, remaining())))
                    plain2 = self.runner.run_pytest(work, targets, timeout=min(60.0, max(5.0, remaining())))
                    if set(plain1.failed_ids) != set(plain2.failed_ids):
                        status = "unstable_baseline"
                        notes.append("failing set differs between two plain baseline runs; refusing to localize noise")
                        first_failing = sorted(set(plain1.failed_ids) | set(plain2.failed_ids))
                        break
                    traced_failed = set(spectrum.failing)
                    sensitive = reconcile_spectrum(spectrum, set(plain1.failed_ids))
                    if sensitive:
                        notes.append(f"{len(sensitive)} test(s) excluded from localization because their outcome differs between "
                                     f"the traced and plain runs (instrumentation-sensitive or flaky): {', '.join(sorted(sensitive)[:4])}")
                    if not plain1.failed_ids:
                        # plain runs define what actually fails; a failure seen ONLY under tracing cannot be trusted either way
                        status = "unstable_baseline" if traced_failed else "no_failures"
                        if traced_failed:
                            notes.append("tests failed only in the traced run (flaky or instrumentation-sensitive); refusing to localize noise")
                        first_failing = sorted(traced_failed)
                        break
                    if not spectrum.complete:
                        status = "incomplete_spectrum"
                        notes.append(f"incomplete spectrum: {spectrum.incomplete_reason}")
                        first_failing = sorted(plain1.failed_ids)
                        break
                elif sensitive:
                    reconcile_spectrum(spectrum, set(spectrum.failing), sensitive)
                loc = self.localizer.localize(work, targets, spectrum=spectrum)
                if it == 1:
                    first_failing, first_loc = loc.failing_tests, loc
                    impact = {q: v for q, v in loc.impacts.items()}
                if not loc.failing_tests:
                    status = "resolved" if steps else "no_failures"
                    break
                iterations.append({"iteration": it, "failing": loc.failing_tests,
                                   "suspects": [asdict(s) for s in loc.suspects[:10]], "notes": loc.notes})
                und = CodeUnderstanding().analyze(work)
                ranges_by_file: dict = defaultdict(list)
                for f in und.functions:
                    ranges_by_file[f.path].append((f.qname, f.line, f.end_line))
                accepted = None
                # DEV15: phase 1 is exactly the DEV14 repair space over every suspect; the new families (phase 2) are
                # tried only if phase 1 accepts nothing. Mixing them into one ordering pushed a correct DEV14 fix past
                # the per-suspect candidate cap on a fresh-subject smoke run (parse.date_convert), so DEV15 lost a
                # repair DEV14 makes.
                phases = [1, 2] if self.extended_ops else [1]
                if self.knowledge is not None or self.shapes is not None:
                    phases.append(3)  # DEV17/18: procedures ASM learned itself, only when no built-in operation worked
                for phase in phases:
                    extended_phase = phase >= 2
                    if accepted:
                        break
                    for rank, sus in enumerate([s for s in loc.suspects if s.score > 0][: self.max_suspects], 1):
                        if remaining() < 5:
                            break
                        source = (work / sus.path).read_text(encoding="utf-8")
                        if phase == 3:
                            span = next(((a, b) for q, a, b in ranges_by_file[sus.path] if q == sus.qname), (sus.line, sus.end_line))
                            cands = self.knowledge.candidates_for(source, sus.path, span) if self.knowledge is not None else []
                            if self.shapes is not None:  # DEV18: learned shapes, content filled from this problem
                                pctx = _problem_context(work, spectrum, source)
                                cands += self.shapes.candidates_for(source, sus.path, span, pctx, limit=max(0, 80 - len(cands)))
                        else:
                            cands = generate_candidates(source, sus.path, sus, ranges_by_file[sus.path], loc.line_scores,
                                                        extended=extended_phase, failure_texts=list(spectrum.failures.values()))
                        if phase == 2:  # DEV14 templates were already tried in phase 1
                            cands = [c for c in cands if family_of(c.reason) != "single_site"]
                        if self.ranker is not None and cands and phase < 3:  # DEV16: reorder within this phase only
                            cands = self.ranker.rerank(cands, _ranking_context(spectrum, sus, rank, phase))
                        if not cands:
                            reasons["no_template_sites"] += 1
                            rejected.append({"suspect": sus.qname, "description": "no mutation sites in this function",
                                             "status": "no_candidates", "why": "", "iteration": it})
                            continue

                        def generator(ctx, cands=cands, size=self.candidates_per_round):
                            return cands[(ctx.round - 1) * size: ctx.round * size]
                        task_id = f"{sus.qname}"
                        for attempt_no in range(3):
                            if remaining() < 5:
                                break
                            loop = CodingResearchLoop(
                                generator, test_runner=self.runner, ledger=ledger, max_rounds=min(self.max_rounds, 10),
                                max_candidates_per_round=self.candidates_per_round,
                                time_budget_seconds=max(5.0, remaining() - 2), baseline_runs=1,
                                confirm_runs=self.confirm_runs, protect_tests=True)
                            res = loop.run(work, f"{task} [{sus.qname}]", task_id=task_id, targets=targets)
                            for a in res.attempts:
                                why = a.detail or (f"still failing: {a.failed_tests[:2]}" if a.status == "failed" and a.failed_tests else "")
                                if a.regressions:
                                    why = f"regressions: {a.regressions[:2]}"
                                if a.status != "passed":
                                    reasons[a.status] += 1
                                    rejected.append({"suspect": sus.qname, "description": a.reason, "status": a.status, "why": why,
                                                     "fixed": a.fixed_tests[:3], "regressions": a.regressions[:3],
                                                     "vanished": a.vanished_tests[:3], "iteration": it})
                            passed = [a for a in res.attempts if a.status == "passed"]
                            partial = [a for a in res.attempts if a.status == "failed" and a.fixed_tests and not a.regressions
                                       and not a.vanished_tests and not a.newly_skipped]
                            # choose by evidence order (candidates are generated most-suspicious-first), never by timing noise
                            best = (min(passed, key=lambda a: (a.round, a.index)) if passed else
                                    min(partial, key=lambda a: (-len(a.fixed_tests), a.diff_lines, a.round, a.index))
                                    if partial else None)
                            if best is None:
                                break
                            cand = next(c for c in cands if hashlib.sha256(c.replacement.encode("utf-8", "replace")).hexdigest()
                                        == best.replacement_sha256)
                            prop = PatchProposalBuilder.from_replacement(work, cand.path, cand.replacement, cand.reason)
                            ok, detail, info = self._contract_check(work, prop, sus.qname)
                            if ok:
                                same = passed if passed else [a for a in partial if set(a.fixed_tests) == set(best.fixed_tests)]
                                alt_attempts = [a for a in same if a is not best and a.replacement_sha256 != best.replacement_sha256
                                            and (family_of(best.reason) == "pair" or family_of(a.reason) != "pair")]
                                # DEV15 minimal-repair rule: once a single edit passes, a two-edit program is not a
                                # competing explanation (it is the fix plus an extra edit, i.e. a decoy), so pairs
                                # count as alternatives only when the accepted patch is itself a pair
                                alternatives = [a.reason for a in alt_attempts]
                                alt_pairs = []
                                for a in alt_attempts[:5]:  # proposals for the counterexample search (cands is this suspect's list)
                                    c = next(c for c in cands if hashlib.sha256(c.replacement.encode("utf-8", "replace")).hexdigest()
                                             == a.replacement_sha256)
                                    alt_pairs.append((a.reason, PatchProposalBuilder.from_replacement(work, c.path, c.replacement, c.reason)))
                                if self.explore_alternatives:
                                    sha = lambda c: hashlib.sha256(c.replacement.encode("utf-8", "replace")).hexdigest()  # noqa: E731
                                    seen = {best.replacement_sha256} | {a.replacement_sha256 for a in alt_attempts}
                                    evaluated = {a.replacement_sha256 for a in res.attempts}
                                    pool = [c for c in cands if sha(c) not in evaluated and (
                                        family_of(best.reason) == "pair" or family_of(c.reason) != "pair")][: self.max_extra_candidates]
                                    if self.extended_ops and phase == 1:
                                        # DEV15: alternatives are evidence, not acceptance, so they come from the new
                                        # families too even when a DEV14 template was accepted (thefuck-15: the
                                        # developer's dropped clause is what shows the accepted negation is wrong)
                                        pool += [c for c in generate_candidates(
                                            source, sus.path, sus, ranges_by_file[sus.path], loc.line_scores, extended=True,
                                            failure_texts=list(spectrum.failures.values()))
                                            if family_of(c.reason) not in ("single_site", "pair")][: self.max_extra_candidates]
                                    for c in pool:
                                        if remaining() < 8 or len(alt_pairs) >= 8:
                                            break
                                        p2 = self._quick_pass(work, c, targets, spectrum.outcomes)
                                        if p2 is not None and sha(c) not in seen:
                                            seen.add(sha(c))
                                            alt_pairs.append((c.reason, p2))
                                            alternatives.append(c.reason)
                                accepted = (rank, sus, res, best, detail, info, prop, bool(passed), alternatives, alt_pairs)
                                break
                            reasons["rejected_semantic_contract"] += 1
                            rejected.append({"suspect": sus.qname, "description": best.reason,
                                             "status": "rejected_semantic_contract", "why": detail,
                                             "fixed": best.fixed_tests[:3], "regressions": [], "vanished": [], "iteration": it})
                            best.status, best.detail = "failed", detail  # remember it so the next search skips this candidate
                            ledger.append(task_id, best, tree_fingerprint(work))
                        if accepted:
                            break
                if accepted is None:
                    status = "partial" if steps else ("time_budget" if remaining() < 5 else "unresolved")
                    break
                rank, sus, res, best, contract_detail, contract_info, prop, full, alternatives, alt_pairs = accepted
                tied = [x.qname for x in loc.suspects if x.score == sus.score and x.qname != sus.qname]
                old = (work / prop.path).read_text(encoding="utf-8")
                diff = _unified(prop.path, old, prop.replacement)
                verdict, verdict_note = self._behavioural_verdict(work, prop, sus.qname)  # judged BEFORE the patch lands
                finfos = {f.qname: f for f in und.functions}
                cx = verify_patch(work, sus.qname, (best.reason, prop), alt_pairs, spectrum, finfos) \
                    if self.counterexamples else {"available": False, "reason": "counterexample search disabled"}
                step_candidates.append([(best.reason, prop)] + alt_pairs)
                competing = []
                if self.explore_alternatives and tied:
                    comp_deadline = time.monotonic() + self.competing_time
                    for q in tied[: self.competing_max_suspects]:
                        s2 = next((x for x in loc.suspects if x.qname == q), None)
                        if s2 is None or remaining() < 10 or time.monotonic() > comp_deadline:
                            continue
                        src2 = (work / s2.path).read_text(encoding="utf-8")
                        for c in generate_candidates(src2, s2.path, s2, ranges_by_file[s2.path], loc.line_scores)[: self.max_extra_candidates]:
                            if remaining() < 8 or time.monotonic() > comp_deadline:
                                break
                            if self._quick_pass(work, c, targets, spectrum.outcomes) is not None:
                                competing.append({"suspect": q, "description": c.reason})
                                break  # one demonstration per function is enough
                apply_proposal(work, prop, backup=False)
                proposals.append(prop)
                why = [f"fixes {len(best.fixed_tests)} failing test(s)", "no regressions in the executed tests",
                       "no tests vanished or became skipped", f"DEV10 behavioural contract: {contract_detail}"]
                if full:
                    why += [f"all {best.n_passed} executed tests pass", f"pass reproduced in {self.confirm_runs} fresh confirmation run(s)"
                            if self.confirm_runs else "pass not re-confirmed (confirm_runs=0)"]
                else:
                    why += ["partial: other failing tests remain, so localization continues on the patched copy"]
                steps.append({"iteration": it, "suspect": sus.qname, "rank": rank, "kind": "full" if full else "partial",
                              "description": best.reason, "fixed_tests": best.fixed_tests, "path": prop.path, "diff": diff,
                              "why_accepted": why, "confirmed": best.confirmed, "diff_lines": best.diff_lines,
                              "behavioural_verdict": verdict, "behavioural_note": verdict_note,
                              "edit_family": family_of(best.reason),
                              "learned_procedure": getattr(cand, "meta", {}).get("procedure"),
                              "learned_shape": getattr(cand, "meta", {}).get("shape")})
                steps[-1]["competing_patches"] = competing
                steps[-1]["alternatives_passing"] = alternatives[:8]
                steps[-1]["tied_with"] = tied[:8]
                steps[-1]["counterexamples"] = cx
                steps[-1]["verification"] = cx
                flags = []
                if self.counterexamples and not cx.get("available"):
                    flags.append("behaviour_unverified")
                elif cx.get("available"):
                    moved = cx.get("changed_on_passing_recorded", {}).get(best.reason, [])
                    if moved:
                        caveats.append(f"{sus.qname}: the patch changes behaviour on {len(moved)} recorded input(s) that tests "
                                       f"which passed before the patch already used (e.g. {moved[0]}). Those tests accept the "
                                       "change but may not check it, a typical sign of a patch that compensates for a fault elsewhere")
                        flags.append("behaviour_changed_where_tests_passed")
                if verdict == "still_deviant":
                    caveats.append(f"{sus.qname}: {verdict_note}")
                    flags.append("behavioural_deviation_persists")
                if alternatives:
                    if cx.get("available") and cx.get("alternatives_agree_everywhere"):
                        steps[-1]["alternatives_note"] = (f"{len(alternatives)} other edit(s) also pass the tests but agree with the "
                                                          f"chosen patch on all {cx['inputs_tested']} tested inputs (probably equivalent)")
                    elif cx.get("available") and cx.get("distinguishing"):
                        d0 = cx["distinguishing"][0]
                        caveats.append(f"{sus.qname}: edits that also pass the tests behave differently, e.g. on input {d0['input']} "
                                       f"the chosen patch gives {d0['accepted_output']} but '{d0['alternative']}' gives "
                                       f"{d0['alternative_output']} (original: {d0['original_output']}); add a test stating the intended result")
                        flags.append("alternatives_disagree")
                    else:
                        caveats.append(f"{sus.qname}: {len(alternatives)} other single-site edit(s) also satisfy the tests "
                                       f"(e.g. {alternatives[0]}); the tests do not determine the fix "
                                       f"({cx.get('reason') or 'behaviour could not be compared'})")
                        flags.append("underdetermined")
                if competing:
                    caveats.append(f"{sus.qname}: a different function with equally strong evidence can ALSO be patched to satisfy the "
                                   f"tests ({competing[0]['suspect']}: {competing[0]['description']}), so at least one of the two patches "
                                   "is compensating for a fault elsewhere; the tests cannot tell which function is at fault")
                    flags.append("competing_patches_in_other_functions")
                if tied:
                    others_sem = max((x.sources["semantic"] for x in loc.suspects if x.qname in tied), default=0.0)
                    favoured = (" DEV10 behavioural evidence ordered this suspect first, but that evidence is unvalidated on real faults."
                                if sus.sources["semantic"] > others_sem else "")
                    caveats.append(f"{sus.qname}: coverage and traceback evidence tie it with {len(tied)} other function(s) "
                                   f"({', '.join(tied[:3])}); the patch makes the tests pass but may be compensating for a fault "
                                   f"elsewhere.{favoured}")
                    flags.append("tied_localization")
                counted = [f for f in flags if f not in INFORMATIONAL_FLAGS]
                steps[-1]["confidence"] = "low" if (len(counted) >= 2 or "behavioural_deviation_persists" in counted) else (
                    "medium" if counted else "high")
                steps[-1]["confidence_basis"] = flags  # every flag is still shown...
                steps[-1]["confidence_counted"] = counted  # ...but only these determine the label
                if full:
                    status = "resolved"
                    break
            else:
                status = "partial" if steps else "unresolved"
            if steps and status not in {"resolved", "partial"}:
                status = "partial"
            # ---- cumulative diff + behavioural post-check on the final working copy
            files = sorted({s["path"] for s in steps})
            total_diff = "".join(_unified(p, (base / p).read_text(encoding="utf-8"),
                                          (work / p).read_text(encoding="utf-8")) for p in files)
            sem: dict = {}
            if steps and self.semantic_check and remaining() > 10:
                patched = {s["suspect"] for s in steps}
                try:
                    before = SemanticAnalyzer(per_module_timeout=20, probe_budget_seconds=30).analyze(base, probe_only=patched)
                    after = SemanticAnalyzer(per_module_timeout=20, probe_budget_seconds=30).analyze(work, probe_only=patched)
                    for q in sorted(patched):
                        fb = {f.kind for f in before.findings_for(q)}
                        fa = {f.kind for f in after.findings_for(q)}
                        sem[q] = {"findings_before": sorted(fb), "findings_after": sorted(fa),
                                  "resolved": sorted(fb - fa), "introduced": sorted(fa - fb),
                                  "identified_before": before.function(q).inferred, "identified_after": after.function(q).inferred}
                except Exception as exc:
                    notes.append(f"behavioural post-check unavailable: {type(exc).__name__}: {exc}")
        dossier = Dossier(task, status, fingerprint, first_failing, iterations, steps, rejected, dict(reasons), total_diff,
                          impact, sem, notes, round(time.monotonic() - started, 2), caveats=caveats,
                          examples=list(examples or []))
        dossier._proposals = proposals
        dossier._step_candidates = step_candidates
        dossier.patch_hashes = [{"path": p.path, "expected_sha256": p.expected_sha256, "replacement_sha256": p.replacement_sha256}
                                for p in proposals]
        dossier.seal()
        return dossier

    def _quick_pass(self, work: Path, cand: Candidate, targets, baseline_outcome: dict):
        """Does this single candidate satisfy the tests with no vanished/skipped tests? Returns its proposal or None."""
        try:
            prop = PatchProposalBuilder.from_replacement(work, cand.path, cand.replacement, cand.reason)
        except Exception:
            return None
        with tempfile.TemporaryDirectory(prefix="asm_dev13_alt_") as td:
            sandbox = Path(td) / "repo"
            copy_repo(work, sandbox)
            apply_proposal(sandbox, prop, backup=False)
            run = self.runner.run_pytest(sandbox, targets, timeout=min(self.runner.timeout_seconds, 30))
        if not run.passed:
            return None
        cmp = compare_outcomes(baseline_outcome, run.outcome)
        return None if (cmp["vanished"] or cmp["newly_skipped"]) else prop

    def _behavioural_verdict(self, work: Path, prop: PatchProposal, qname: str) -> tuple:
        """After a patch is accepted on test evidence, ask DEV10 whether the function now behaves as its name claims."""
        if not self.semantic_check:
            return "unchecked", "semantic_check disabled"
        try:
            with tempfile.TemporaryDirectory(prefix="asm_dev11_verdict_") as td:
                patched = Path(td) / "repo"
                copy_repo(work, patched)
                apply_proposal(patched, prop, backup=False)
                before = SemanticAnalyzer(per_module_timeout=20, probe_budget_seconds=30).analyze(work, probe_only={qname})
                after = SemanticAnalyzer(per_module_timeout=20, probe_budget_seconds=30).analyze(patched, probe_only={qname})
            fb = {f.kind for f in before.findings_for(qname)}
            fa = {f.kind for f in after.findings_for(qname)}
            bad = {"likely_bug", "name_behavior_mismatch"}
            if fb & bad and fa & bad:
                f = next(x for x in after.findings_for(qname) if x.kind in bad)
                return "still_deviant", f"tests pass but DEV10 still reports {f.kind}: {f.message}"
            if fb & bad and not fa & bad:
                return "improved", f"DEV10 {sorted(fb & bad)} no longer reported"
            return "unchanged", "no relevant behavioural finding before or after"
        except Exception as exc:
            return "unchecked", f"behavioural check unavailable ({type(exc).__name__})"

    def _contract_check(self, work: Path, prop: PatchProposal, qname: str) -> tuple:
        """DEV10 behavioural contract: a plausible patch must not destroy a function that already behaved like a
        recognised reference, nor introduce new high-severity behavioural findings."""
        if not self.semantic_check:
            return True, "skipped (semantic_check disabled)", {}
        try:
            with tempfile.TemporaryDirectory(prefix="asm_dev11_contract_") as td:
                patched = Path(td) / "repo"
                copy_repo(work, patched)
                apply_proposal(patched, prop, backup=False)
                before = SemanticAnalyzer(per_module_timeout=20, probe_budget_seconds=30).analyze(work, probe_only={qname})
                after = SemanticAnalyzer(per_module_timeout=20, probe_budget_seconds=30).analyze(patched, probe_only={qname})
            fb, fa = before.function(qname), after.function(qname)
            info = {"identified_before": fb.inferred, "identified_after": fa.inferred,
                    "findings_before": sorted({f.kind for f in before.findings_for(qname)}),
                    "findings_after": sorted({f.kind for f in after.findings_for(qname)})}
            was_mismatch = any(f.kind == "name_behavior_mismatch" for f in before.findings_for(qname))
            if fb.inferred and not fa.inferred and fb.behavior and fb.behavior["exact"] and not was_mismatch and not (
                    set(fb.inferred) & set(fa.inferred)):
                return False, f"patch destroys recognised behaviour {fb.inferred} of {qname}", info
            introduced = {f.kind for f in after.findings_for(qname) if f.severity == "high"} - \
                {f.kind for f in before.findings_for(qname) if f.severity == "high"}
            if introduced:
                return False, f"patch introduces high-severity behavioural findings {sorted(introduced)}", info
            return True, "recognised behaviour preserved" if fb.inferred else "no recognised behaviour to preserve", info
        except Exception as exc:  # the contract is evidence; its failure must not silently approve or crash
            return True, f"contract check unavailable ({type(exc).__name__}); not used as evidence", {}

    @staticmethod
    def apply_fix(root: str | Path, dossier: Dossier, approved: bool = False, allow_partial: bool = False) -> list:
        """Apply the dossier's accepted patch chain to the real repository. Requires explicit approval."""
        if not approved:
            raise PermissionError("applying a fix requires explicit approval (approved=True)")
        ok, problems = dossier.verify()  # before the status check: an edited status must not slip past
        if not ok:
            raise ValueError(f"dossier failed its integrity check, refusing to apply: {problems}")
        bound = [{"path": p.path, "expected_sha256": p.expected_sha256, "replacement_sha256": p.replacement_sha256}
                 for p in dossier._proposals]
        if bound != dossier.patch_hashes:
            raise ValueError("the patches attached to this dossier are not the ones it was sealed with")
        if dossier.status != "resolved" and not (allow_partial and dossier.status == "partial"):
            raise ValueError(f"dossier status is {dossier.status!r}; nothing safe to apply")
        if tree_fingerprint(root) != dossier.repo_fingerprint:
            raise ValueError("repository changed since the dossier was produced; re-run the workflow")
        return [apply_proposal(root, p, backup=True) for p in dossier._proposals]
