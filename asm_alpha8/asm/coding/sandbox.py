"""DEV8.1 hardened execution layer for candidate evaluation.

What this adds over the DEV7 TestRunner (which is untouched):
- the whole test process GROUP is killed on timeout (grandchildren included)
- scrubbed environment: no inherited secrets, throwaway HOME/TMPDIR, fixed hash seed
- POSIX resource limits (CPU, address space, file size, no core dumps)
- network namespace isolation when `unshare` works, with an explicit report of what is active
- exact per-test outcomes via JUnit XML (passed/failed/error/skipped/xfailed)
- classified exit states (timeout, no tests, collection error, internal error, ...)
- a static risk scan that flags NEWLY introduced dangerous constructs in a candidate
- a repository copier that drops symlinks so tests cannot write through them

Honest scope: this is defense in depth for developer-controlled repos, NOT a security
boundary. Without root-level containers (seccomp, filesystem namespaces) a determined
malicious candidate can still read world-readable files and write anywhere the current
user can. Use a real container/VM for untrusted code.
"""
from __future__ import annotations

import ast
import contextlib
import contextvars
import hashlib
import json
import os
import re
import shutil
import signal
import site
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path

IGNORE_NAMES = (".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".asm_backups")
FAIL_STATES = {"failed", "error"}
REPAIRABLE = {"tests_failed", "collection_error"}

_TRAMPOLINE = r'''
import json, os, sys
lim = json.loads(sys.argv[1])
if lim:
    try:
        import resource
        for k, v in lim.items():
            hard = v + 2 if k == "RLIMIT_CPU" else v  # soft<hard so SIGXCPU is delivered before SIGKILL
            resource.setrlimit(getattr(resource, k), (v, hard))
    except Exception as e:
        sys.stderr.write("asm-sandbox: rlimit setup failed: %r\n" % (e,))
        sys.exit(97)
os.execv(sys.executable, [sys.executable, "-m", "pytest"] + sys.argv[2:])
'''


@dataclass
class SafeRun:
    command: list[str]
    returncode: int | None
    passed: bool
    timed_out: bool
    duration_seconds: float
    stdout: str
    stderr: str
    classification: str  # passed|tests_failed|collection_error|no_tests|timeout|internal_error|usage_error|sandbox_error|crashed|interrupted|unknown_error
    outcome: dict = field(default_factory=dict)  # node id -> passed|failed|error|skipped|xfailed
    counts: dict = field(default_factory=dict)
    exceeded: str | None = None  # cpu | output | None
    isolation: dict = field(default_factory=dict)
    stray_processes_killed: bool = False

    @property
    def failed_ids(self) -> list[str]:
        return sorted(i for i, s in self.outcome.items() if s in FAIL_STATES)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["failed_ids"] = self.failed_ids
        return d


# ------------------------------------------------------------------ parsing
_COUNT = re.compile(r"(\d+)\s+(failed|passed|skipped|errors?|xfailed|xpassed|deselected)")
_LINE = re.compile(r"^(PASSED|FAILED|ERROR|XFAIL|XPASS)\s+(\S+)", re.M)


def parse_counts(text: str) -> dict:
    counts = {"failed": 0, "passed": 0, "skipped": 0, "error": 0, "xfailed": 0, "xpassed": 0, "deselected": 0}
    for number, word in _COUNT.findall(text):
        counts["error" if word.startswith("error") else word] += int(number)
    return counts


def _nodeid_from_classname(base: Path, classname: str, name: str) -> str | None:
    """pytest builds `classname` from the collected node id ('/' -> '.', '.py' dropped), so resolving it against files
    that exist recovers the real node id. The `file` attribute cannot be used for that: it names where the test is
    DEFINED, which differs from where it is collected for inherited/mixin test classes (several tests then collide)."""
    parts = classname.split(".")
    for k in range(len(parts), 0, -1):
        rel = "/".join(parts[:k]) + ".py"
        if (base / rel).is_file():
            return "::".join([rel, *parts[k:], name])
    return None


def parse_junit(path: Path, base: Path | None = None) -> dict | None:
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return None
    out: dict[str, str] = {}
    for tc in root.iter("testcase"):
        file, classname, name = tc.get("file") or "", tc.get("classname") or "", tc.get("name") or ""
        nid = _nodeid_from_classname(base, classname, name) if (base is not None and classname) else None
        if nid is not None:
            pass
        elif file:
            module = file[:-3].replace("/", ".") if file.endswith(".py") else file
            chain = classname[len(module) + 1:].split(".") if classname.startswith(module + ".") else []
            nid = "::".join([file, *[c for c in chain if c], name]) if classname else file
        else:
            nid = f"{classname}::{name}" if classname else name
        kids = {c.tag: c for c in tc}
        if "error" in kids:
            state = "error"
        elif "failure" in kids:
            state = "failed"
        elif "skipped" in kids:
            state = "xfailed" if "xfail" in (kids["skipped"].get("type") or "") else "skipped"
        else:
            state = "passed"
        out[nid] = state
    return out


def outcome_from_text(text: str) -> dict:
    mapping = {"PASSED": "passed", "FAILED": "failed", "ERROR": "error", "XFAIL": "xfailed", "XPASS": "passed"}
    return {nid: mapping[kind] for kind, nid in _LINE.findall(text)}


def classify(returncode, timed_out, outcome, counts, exceeded) -> str:
    if timed_out:
        return "timeout"
    if returncode == 97:
        return "sandbox_error"
    if returncode is not None and returncode < 0:
        return "crashed"
    if returncode == 0:
        return "passed"
    if returncode == 1:
        # exit code 1 with no test outcome and no summary counts: no test ever ran (e.g. a conftest/plugin that fails
        # to load). Reporting that as "tests_failed" would let a broken suite look like a repairable failure.
        if not outcome and not any((counts or {}).values()):
            return "startup_error"
        return "tests_failed"
    if returncode == 2:
        return "collection_error" if any(s == "error" for s in outcome.values()) else "interrupted"
    if returncode == 3:
        return "internal_error"
    if returncode == 4:
        return "usage_error"
    if returncode == 5:
        return "no_tests"
    return "unknown_error"


def _validate_targets(base: Path, targets) -> list[str]:
    safe = []
    for item in targets or ["tests"]:
        path_part = item.split("::", 1)[0]
        selector = item[len(path_part):]
        p = Path(path_part)
        if p.is_absolute() or ".." in p.parts:
            raise ValueError("test targets must be relative paths inside the repository")
        resolved = (base / p).resolve(strict=False)
        if not resolved.is_relative_to(base):
            raise ValueError("test target escapes repository root")
        if not resolved.exists():
            raise FileNotFoundError(item)
        safe.append(p.as_posix() + selector)
    return safe


_TARGET_PYTHON: contextvars.ContextVar = contextvars.ContextVar("asm_target_python", default=None)


def check_python(path) -> str:
    """An interpreter path to run the PROJECT's code under (e.g. a virtualenv's bin/python). Not resolved, because a
    virtualenv is identified by the path of its python symlink."""
    p = Path(path).absolute()
    if not p.is_file() or not os.access(p, os.X_OK):
        raise ValueError(f"not an executable interpreter: {path}")
    return str(p)


@contextlib.contextmanager
def interpreter(path):
    """Within this block, sandboxed test runs and worker scripts that were not given an interpreter explicitly use
    `path` instead of ASM's own interpreter. None = no change. DEV14: real projects pin old Python versions."""
    if path is None:
        yield
        return
    token = _TARGET_PYTHON.set(check_python(path))
    try:
        yield
    finally:
        _TARGET_PYTHON.reset(token)


def target_python() -> str:
    return _TARGET_PYTHON.get() or sys.executable


class SafeTestRunner:
    __test__ = False
    _net_probe: tuple | None = None  # cached (prefix list | None, description)

    def __init__(self, timeout_seconds: float = 60, output_limit: int = 12000, *,
                 memory_mb: int | None = 4096, cpu_seconds: int | None = None, max_output_mb: int = 50,
                 network: str = "auto", scrub_env: bool = True, extra_env_allow: tuple = (),
                 python: str | None = None):
        if not 0 < timeout_seconds <= 600:
            raise ValueError("timeout_seconds must be in (0, 600]")
        if network not in {"auto", "isolate", "allow"}:
            raise ValueError("network must be auto, isolate or allow")
        self.timeout_seconds = float(timeout_seconds)
        self.output_limit = max(1000, int(output_limit))
        self.memory_mb, self.cpu_seconds, self.max_output_mb = memory_mb, cpu_seconds, max_output_mb
        self.network, self.scrub_env, self.extra_env_allow = network, scrub_env, tuple(extra_env_allow)
        self.python = check_python(python) if python is not None else None  # None = target_python() at run time

    @classmethod
    def from_legacy(cls, runner) -> "SafeTestRunner":
        if isinstance(runner, cls):
            return runner
        return cls(timeout_seconds=getattr(runner, "timeout_seconds", 60),
                   output_limit=getattr(runner, "output_limit", 12000))

    # ------------------------------------------------------------ isolation
    @classmethod
    def _network_prefix(cls) -> tuple[list[str] | None, str]:
        if cls._net_probe is not None:
            return cls._net_probe
        result: tuple = (None, "unavailable")
        if os.name == "posix" and shutil.which("unshare"):
            for flags, label in ((["-n"], "unshare -n"), (["-rn"], "unshare -rn")):
                try:
                    if subprocess.run(["unshare", *flags, "true"], capture_output=True, timeout=5).returncode == 0:
                        script = 'ip link set lo up >/dev/null 2>&1; exec "$@"'
                        result = (["unshare", *flags, "sh", "-c", script, "asm-sandbox"], label)
                        break
                except (OSError, subprocess.SubprocessError):
                    continue
        cls._net_probe = result
        return result

    def isolation_report(self) -> dict:
        prefix, label = self._network_prefix()
        net = "allowed" if self.network == "allow" else ("isolated" if prefix else "NOT isolated (unshare unavailable)")
        return {"network": net, "network_method": label if prefix and self.network != "allow" else None,
                "env_scrubbed": self.scrub_env, "process_group_kill": os.name == "posix",
                "memory_limit_mb": self.memory_mb if os.name == "posix" else None,
                "cpu_limit": "timeout+5s" if self.cpu_seconds is None else self.cpu_seconds,
                "max_output_mb": self.max_output_mb if os.name == "posix" else None,
                "fixed_hash_seed": True, "os_sandbox": False}

    def _env(self, home: Path, tmp: Path) -> dict:
        if self.scrub_env:
            keep = {"PATH", "SYSTEMROOT", "WINDIR", "LANG", "LC_ALL", *self.extra_env_allow}
            env = {k: v for k, v in os.environ.items() if k in keep}
            env.update(HOME=str(home), TMPDIR=str(tmp), TEMP=str(tmp), TMP=str(tmp),
                       PYTHONUSERBASE=site.getuserbase(), PYTHONHASHSEED="0")
        else:
            env = {k: v for k, v in os.environ.items()
                   if k in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME", *self.extra_env_allow}}
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        return env

    def _limits(self, timeout: float) -> dict:
        if os.name != "posix":
            return {}
        lim = {"RLIMIT_CORE": 0,
               "RLIMIT_CPU": int(self.cpu_seconds if self.cpu_seconds is not None else timeout + 5),
               "RLIMIT_FSIZE": self.max_output_mb * 1024 * 1024}
        if self.memory_mb:
            lim["RLIMIT_AS"] = self.memory_mb * 1024 * 1024
        return lim

    # ------------------------------------------------------------------ run
    def run_pytest(self, root, targets=None, timeout: float | None = None, *, extra_args=(),
                   env_extra: dict | None = None) -> SafeRun:
        base = Path(root).resolve(strict=True)
        if not base.is_dir():
            raise NotADirectoryError(str(base))
        safe = _validate_targets(base, targets)
        eff = self.timeout_seconds if timeout is None else min(self.timeout_seconds, float(timeout))
        if eff <= 0:
            raise ValueError("effective timeout must be positive")
        prefix, _ = self._network_prefix()
        use_net = prefix is not None and self.network != "allow"
        with tempfile.TemporaryDirectory(prefix="asm_run_") as td:
            td = Path(td)
            home, tmp = td / "home", td / "tmp"
            home.mkdir(); tmp.mkdir()
            junit, out_f, err_f = td / "junit.xml", td / "stdout.txt", td / "stderr.txt"
            args = ["-q", "-p", "no:cacheprovider", "-rfEsxXp", "-o", "junit_family=xunit1",
                    f"--junitxml={junit}", *extra_args, *safe]
            cmd = [self.python or target_python(), "-c", _TRAMPOLINE, json.dumps(self._limits(eff)), *args]
            full = (prefix if use_net else []) + cmd
            started = time.monotonic()
            timed_out = stray = False
            with open(out_f, "wb") as fo, open(err_f, "wb") as fe:
                env = self._env(home, tmp)
                env.update(env_extra or {})
                proc = subprocess.Popen(full, cwd=base, env=env, stdin=subprocess.DEVNULL,
                                        stdout=fo, stderr=fe, shell=False,
                                        start_new_session=(os.name == "posix"))
                try:
                    proc.wait(timeout=eff)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    self._kill_group(proc)
                    proc.wait()
                else:
                    stray = self._kill_group(proc, only_if_alive=True)
            duration = time.monotonic() - started
            out = out_f.read_bytes().decode("utf-8", "replace")
            err = err_f.read_bytes().decode("utf-8", "replace")
            outcome = parse_junit(junit, base) if junit.exists() else None
            if outcome is None:
                outcome = outcome_from_text(out)
            counts = parse_counts(out)
            rc = None if timed_out else proc.returncode
            exceeded = None
            if rc == -signal.SIGXCPU if os.name == "posix" else False:
                exceeded = "cpu"
            if os.name == "posix" and out_f.stat().st_size >= self.max_output_mb * 1024 * 1024 * 0.99:
                exceeded = "output"
            iso = self.isolation_report()
            iso["network"] = "isolated" if use_net else ("allowed" if self.network == "allow" else iso["network"])
            return SafeRun(full if len(full) < 40 else full[:40], rc, rc == 0, timed_out, duration,
                           out[-self.output_limit:], err[-self.output_limit:],
                           classify(rc, timed_out, outcome, counts, exceeded), outcome, counts, exceeded, iso, stray)

    @staticmethod
    def _kill_group(proc, only_if_alive=False) -> bool:
        """Kill the whole process group. Returns True if stray processes were found and killed."""
        if os.name != "posix":
            if not only_if_alive:
                proc.kill()
            return False
        try:
            os.killpg(proc.pid, 0)  # raises if group is gone
        except (ProcessLookupError, PermissionError):
            return False
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            return False
        return True


# ------------------------------------------------------------ candidate safety
_RISK_IMPORTS = {
    "network": {"socket", "urllib", "http", "ftplib", "smtplib", "requests", "httpx", "aiohttp", "telnetlib",
                "xmlrpc", "ssl", "imaplib", "poplib", "socketserver"},
    "process": {"subprocess", "pty"},
    "native": {"ctypes", "cffi", "mmap"},
}
_RISK_CALLS = {
    "process": {"os.system", "os.popen", "os.fork", "os.kill", "os.killpg", "os.execv", "os.execve", "os.execl",
                "os.execvp", "os.spawnl", "os.spawnv", "os.posix_spawn"},
    "destructive_fs": {"os.remove", "os.unlink", "os.rmdir", "os.removedirs", "os.rename", "os.replace",
                       "shutil.rmtree", "shutil.move", "os.chmod", "os.chown", "os.symlink", "os.link"},
    "dynamic_exec": {"eval", "exec", "compile", "__import__", "importlib.import_module"},
}
_RISK_ATTRS = {"destructive_fs": {"unlink", "rmdir", "rmtree"}}
MEDIUM = {"environment", "fs_write_absolute"}
DEFAULT_BLOCK = frozenset({"network", "process", "native", "destructive_fs", "dynamic_exec"})


def _dotted(node) -> str | None:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        return ".".join([node.id, *parts[::-1]])
    return None


def scan_risk(source: str) -> dict[str, set[str]]:
    """Heuristic categories of dangerous constructs. Obfuscation can evade this by design."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        return {}
    found: dict[str, set[str]] = {}

    def add(cat, tok):
        found.setdefault(cat, set()).add(tok)

    for n in ast.walk(tree):
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            mods = [a.name for a in n.names] if isinstance(n, ast.Import) else [n.module or ""]
            for m in mods:
                top = m.split(".")[0]
                for cat, names in _RISK_IMPORTS.items():
                    if top in names:
                        add(cat, f"import {top}")
        elif isinstance(n, ast.Call):
            name = _dotted(n.func)
            if name:
                for cat, names in _RISK_CALLS.items():
                    if name in names:
                        add(cat, name)
                if name == "open" and n.args and isinstance(n.args[0], ast.Constant) \
                        and isinstance(n.args[0].value, str) and n.args[0].value.startswith(("/", "~")):
                    mode = n.args[1].value if len(n.args) > 1 and isinstance(n.args[1], ast.Constant) else ""
                    if any(c in str(mode) for c in "wax+"):
                        add("fs_write_absolute", f"open({n.args[0].value!r})")
            if isinstance(n.func, ast.Attribute):
                for cat, attrs in _RISK_ATTRS.items():
                    if n.func.attr in attrs:
                        add(cat, f".{n.func.attr}()")
        elif isinstance(n, ast.Attribute):
            d = _dotted(n)
            if d in {"os.environ", "os.getenv"}:
                add("environment", d)
    return found


def new_risks(original: str, replacement: str) -> dict[str, list[str]]:
    old, new = scan_risk(original), scan_risk(replacement)
    return {cat: sorted(toks - old.get(cat, set())) for cat, toks in sorted(new.items())
            if toks - old.get(cat, set())}


def normalized_sha256(source: str) -> str:
    try:
        text = ast.unparse(ast.parse(source))
    except (SyntaxError, ValueError, RecursionError):
        text = source
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()


def copy_repo(base: Path, dest: Path) -> list[str]:
    """Copy a repo for disposable verification, DROPPING symlinks. Returns skipped symlink paths."""
    skipped: list[str] = []

    def ignore(dirpath, names):
        drop = []
        for n in names:
            full = os.path.join(dirpath, n)
            if n in IGNORE_NAMES:
                drop.append(n)
            elif os.path.islink(full):
                drop.append(n)
                skipped.append(os.path.relpath(full, base))
        return drop

    shutil.copytree(base, dest, symlinks=True, ignore=ignore)
    return sorted(skipped)


# ------------------------------------------------------- generic sandboxed worker
_TRAMPOLINE_PY = _TRAMPOLINE.replace('[sys.executable, "-m", "pytest"] + sys.argv[2:]', '[sys.executable] + sys.argv[2:]')


def run_python_worker(script: str, argv: list[str], cwd: Path, *, timeout: float, memory_mb: int | None = 1024,
                      cpu_seconds: int | None = None, max_output_mb: int = 20, network: str = "auto",
                      env_extra: dict | None = None, output_limit: int = 8000, python: str | None = None) -> dict:
    """Run a Python worker script under the same defense-in-depth as SafeTestRunner.

    Process-group kill, scrubbed env + throwaway HOME/TMPDIR, rlimits, network namespace when
    available. Not an OS security boundary (see module docstring).
    """
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    runner = SafeTestRunner(timeout_seconds=min(timeout, 600), memory_mb=memory_mb, cpu_seconds=cpu_seconds,
                            max_output_mb=max_output_mb, network=network)
    prefix, _ = runner._network_prefix()
    use_net = prefix is not None and network != "allow"
    with tempfile.TemporaryDirectory(prefix="asm_worker_") as td:
        td = Path(td)
        home, tmp = td / "home", td / "tmp"
        home.mkdir(); tmp.mkdir()
        script_path = td / "worker.py"
        script_path.write_text(script)
        out_f, err_f = td / "stdout.txt", td / "stderr.txt"
        env = runner._env(home, tmp)
        env.update(env_extra or {})
        cmd = [check_python(python) if python else target_python(), "-c", _TRAMPOLINE_PY, json.dumps(runner._limits(timeout)), str(script_path), *argv]
        full = (prefix if use_net else []) + cmd
        started = time.monotonic()
        timed_out = stray = False
        with open(out_f, "wb") as fo, open(err_f, "wb") as fe:
            proc = subprocess.Popen(full, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=fo, stderr=fe,
                                    shell=False, start_new_session=(os.name == "posix"))
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                SafeTestRunner._kill_group(proc)
                proc.wait()
            else:
                stray = SafeTestRunner._kill_group(proc, only_if_alive=True)
        return {"returncode": None if timed_out else proc.returncode, "timed_out": timed_out,
                "duration_seconds": time.monotonic() - started,
                "stdout": out_f.read_bytes().decode("utf-8", "replace")[-output_limit:],
                "stderr": err_f.read_bytes().decode("utf-8", "replace")[-output_limit:],
                "isolation": dict(runner.isolation_report(), network=("isolated" if use_net else
                                  ("allowed" if network == "allow" else runner.isolation_report()["network"]))),
                "stray_processes_killed": stray}
