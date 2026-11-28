"""DEV10 semantic code intelligence: what code DOES, versus what its names suggest.

Three evidence sources are combined:
1. STATIC semantics: effects (I/O, network, process, randomness, time, globals, mutation of
   parameters), parameter roles, return behaviour, raises -- propagated through the DEV9 call graph.
2. DYNAMIC probing: candidate functions are executed on fixed input batteries inside the DEV8.1
   sandbox (disposable copy, rlimits, scrubbed env, network namespace where available) and their
   observed behaviour is recorded (outputs, determinism, argument mutation, printing, files, globals).
3. BEHAVIOURAL FINGERPRINTING: observed outputs are compared with a library of reference
   behaviours (add, max, sorted, is_prime, ...), identifying what a function computes regardless of its name.

Findings contrast these with the function's name (name/behaviour mismatches, near-miss bugs,
predicates that are not boolean, "getters" with side effects, static/dynamic disagreements).

Honest scope: heuristic and finite-evidence. A fingerprint match means "agrees with the reference on
every probe input", never proof of equivalence. Probing runs only module-level functions of arity 0-2
without statically detected destructive effects; methods, async code and generators are not probed.
Not an OS security boundary: probing executes repository code (see sandbox.py).
"""
from __future__ import annotations

import ast
import itertools
import json
import math
import operator
import re
import tempfile
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .sandbox import copy_repo, run_python_worker, scan_risk
from .understanding import CodeUnderstanding

# ------------------------------------------------------------------- static semantics
_PURE_BUILTINS = frozenset({
    "abs", "all", "any", "ascii", "bin", "bool", "bytes", "callable", "chr", "complex", "dict", "divmod", "enumerate",
    "filter", "float", "format", "frozenset", "hash", "hex", "id", "int", "isinstance", "issubclass", "iter", "len",
    "list", "map", "max", "min", "next", "oct", "ord", "pow", "range", "repr", "reversed", "round", "set", "slice",
    "sorted", "str", "sum", "tuple", "type", "zip", "hasattr", "getattr", "vars", "object", "property", "staticmethod",
    "classmethod", "super", "memoryview", "bytearray"})
_PURE_MODULES = frozenset({"math", "operator", "itertools", "statistics", "string", "fractions", "decimal", "cmath",
                           "bisect", "textwrap", "unicodedata", "collections", "re", "copy"})
_PURE_DOTTED = frozenset({"json.dumps", "json.loads", "functools.reduce", "functools.partial", "functools.lru_cache",
                          "functools.wraps", "functools.cmp_to_key", "functools.total_ordering", "os.path.join",
                          "os.path.basename", "os.path.dirname", "os.path.splitext", "os.path.abspath",
                          "os.path.normpath", "os.path.split", "dataclasses.dataclass", "dataclasses.field",
                          "dataclasses.asdict", "typing.cast", "hashlib.sha256", "hashlib.md5", "hashlib.sha1",
                          "bisect.insort", "bisect.insort_left", "bisect.insort_right"})
_MUTATING_METHODS = frozenset({
    "append", "extend", "insert", "pop", "remove", "clear", "update", "add", "discard", "sort", "reverse", "setdefault",
    "popitem", "write", "writelines", "appendleft", "extendleft", "popleft", "rotate", "fill", "put", "push", "seek",
    "truncate", "intersection_update", "difference_update", "symmetric_difference_update", "__setitem__",
    "__delitem__"})
_PURE_METHODS = frozenset({
    "join", "split", "rsplit", "splitlines", "strip", "lstrip", "rstrip", "upper", "lower", "title", "capitalize",
    "swapcase", "replace", "startswith", "endswith", "find", "rfind", "index", "count", "format", "encode", "decode",
    "isdigit", "isalpha", "isalnum", "isspace", "isupper", "islower", "get", "items", "keys", "values", "copy", "union",
    "intersection", "difference", "symmetric_difference", "issubset", "issuperset", "zfill", "center", "ljust", "rjust",
    "partition", "rpartition", "casefold", "removeprefix", "removesuffix", "bit_length", "conjugate", "hex", "tolist",
    "isdisjoint", "most_common", "total_seconds", "strftime", "isoformat", "fromkeys", "hexdigest", "digest",
    "expandtabs", "translate", "maketrans", "isdecimal", "isnumeric", "istitle", "isidentifier"})
_IO_READ_METHODS = frozenset({"read", "readline", "readlines", "read_text", "read_bytes", "exists", "iterdir", "glob",
                              "rglob", "is_file", "is_dir", "stat", "listdir", "scandir"})
_IO_WRITE_METHODS = frozenset({"write_text", "write_bytes", "mkdir", "unlink", "touch", "rename", "rmdir",
                               "symlink_to", "makedirs"})
_NET_METHODS = frozenset({"connect", "sendall", "recv", "accept", "listen", "bind", "sendto", "recvfrom"})
_LOG_METHODS = frozenset({"debug", "info", "warning", "error", "critical", "exception"})
_EFFECT_PREFIX = (
    ("network", ("socket.", "urllib.", "requests.", "httpx.", "http.client.", "smtplib.", "ftplib.", "aiohttp.")),
    ("process", ("subprocess.", "os.system", "os.popen", "os.exec", "os.spawn", "os.fork", "multiprocessing.")),
    ("randomness", ("random.", "secrets.", "numpy.random.", "np.random.", "uuid.uuid", "os.urandom")),
    ("time", ("time.time", "time.sleep", "time.monotonic", "time.perf_counter", "time.process_time",
              "datetime.datetime.now", "datetime.now", "datetime.utcnow", "datetime.datetime.utcnow",
              "datetime.date.today", "date.today", "datetime.today")),
    ("io_write", ("os.remove", "os.unlink", "os.rename", "os.replace", "os.mkdir", "os.makedirs", "os.rmdir",
                  "os.removedirs", "os.chmod", "os.chown", "os.symlink", "os.link", "shutil.", "json.dump",
                  "pickle.dump", "sqlite3.")),
    ("io_read", ("os.listdir", "os.walk", "os.stat", "os.scandir", "json.load", "pickle.load", "glob.glob",
                 "os.path.exists", "os.path.isfile", "os.path.isdir", "os.path.getsize", "os.getcwd")),
    ("env", ("os.getenv", "os.environ")),
    ("logging", ("logging.",)),
    ("dynamic_exec", ("eval", "exec", "compile", "__import__", "importlib.import_module")),
)
HARD_EFFECTS = frozenset({"io_write", "network", "process", "dynamic_exec"})
PURITY_BREAKING = frozenset({"io_write", "io_read", "network", "process", "randomness", "time", "env", "global_write",
                             "global_mutation", "console", "logging", "dynamic_exec", "env_write", "io_unknown",
                             "self_mutation"})
_ANN_KINDS = (("bool", "bool"), ("int", "int"), ("float", "float"), ("str", "str"), ("bytes", "str"),
              ("dict", "dict"), ("Mapping", "dict"), ("list", "list"), ("List", "list"), ("Sequence", "list"),
              ("Iterable", "list"), ("tuple", "list"), ("Tuple", "list"), ("set", "list"))
_NAME_KIND = {"n": "num", "i": "num", "j": "num", "k": "num", "x": "num", "y": "num", "a": "num", "b": "num",
              "num": "num", "count": "num", "m": "num", "s": "str", "text": "str", "word": "str", "string": "str",
              "name": "str", "line": "str", "xs": "list", "nums": "list", "items": "list", "lst": "list",
              "arr": "list", "values": "list", "seq": "list", "numbers": "list", "d": "dict", "mapping": "dict"}


def dotted(node) -> str | None:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        return ".".join([node.id, *parts[::-1]])
    return None


def is_stub(fn) -> bool:
    """Interface/abstract/placeholder bodies: only a docstring, `pass`, `...` or `raise NotImplementedError`."""
    body = list(fn.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]
    if not body:
        return True
    for st in body:
        if isinstance(st, ast.Pass):
            continue
        if isinstance(st, ast.Expr) and isinstance(st.value, ast.Constant) and st.value.value is Ellipsis:
            continue
        if isinstance(st, ast.Raise) and st.exc is not None and \
                (dotted(st.exc.func) if isinstance(st.exc, ast.Call) else dotted(st.exc)) == "NotImplementedError":
            continue
        return False
    return True


def can_fall_through(body: list) -> bool:
    """True if control can reach the end of this statement list without returning/raising."""
    for st in body:
        if isinstance(st, (ast.Return, ast.Raise)):
            return False
        if isinstance(st, ast.If):
            if not can_fall_through(st.body) and st.orelse and not can_fall_through(st.orelse):
                return False
        elif isinstance(st, ast.While):
            if isinstance(st.test, ast.Constant) and st.test.value is True and not any(
                    isinstance(n, ast.Break) for n in ast.walk(st)):
                return False
        elif isinstance(st, (ast.With, ast.AsyncWith)):
            if not can_fall_through(st.body):
                return False
        elif isinstance(st, ast.Try):
            main = can_fall_through(st.body + st.orelse) or any(can_fall_through(h.body) for h in st.handlers)
            if st.finalbody and not can_fall_through(st.finalbody):
                return False
            if not main:
                return False
        elif hasattr(ast, "Match") and isinstance(st, ast.Match):
            if st.cases and all(not can_fall_through(c.body) for c in st.cases) and any(
                    isinstance(c.pattern, ast.MatchAs) and c.pattern.pattern is None and c.guard is None
                    for c in st.cases):
                return False
    return True


def _boolish(e) -> bool:
    if isinstance(e, ast.Constant):
        return isinstance(e.value, bool)
    if isinstance(e, ast.Compare):
        return True
    if isinstance(e, ast.UnaryOp) and isinstance(e.op, ast.Not):
        return True
    if isinstance(e, ast.BoolOp):
        return all(_boolish(v) for v in e.values)
    if isinstance(e, ast.Call):
        n = dotted(e.func)
        return n in {"isinstance", "issubclass", "hasattr", "callable", "bool", "any", "all"} or \
            (isinstance(e.func, ast.Attribute) and (e.func.attr.startswith(("is", "has", "startswith", "endswith"))
                                                    and e.func.attr in {"isdigit", "isalpha", "isalnum", "isspace",
                                                                        "isupper", "islower", "startswith", "endswith",
                                                                        "issubset", "issuperset", "isdisjoint"}))
    if isinstance(e, ast.IfExp):
        return _boolish(e.body) and _boolish(e.orelse)
    return False


def _walk_own(node):
    """Walk a function body without descending into nested function/class definitions."""
    stack = list(ast.iter_child_nodes(node))
    while stack:
        n = stack.pop()
        yield n
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        stack.extend(ast.iter_child_nodes(n))


def _annotation_kind(ann) -> str | None:
    """Classify a type annotation by its OUTER type (list[int] is a list, not an int)."""
    if isinstance(ann, ast.Constant) and isinstance(ann.value, str):
        try:
            ann = ast.parse(ann.value, mode="eval").body
        except SyntaxError:
            return None
    if isinstance(ann, ast.Subscript):
        ann = ann.value
    if isinstance(ann, ast.BinOp):  # unions: int | str -> unknown
        return None
    name = dotted(ann) if isinstance(ann, (ast.Name, ast.Attribute)) else None
    if not name:
        return None
    base = name.split(".")[-1]
    for key, kind in _ANN_KINDS:
        if base == key:
            return kind
    return None


def infer_param_kinds(fn) -> dict[str, str]:
    """kind in {int, float, str, bool, list, dict, num, sized, any}, from annotations, defaults and usage."""
    a = fn.args
    params = [x for x in a.posonlyargs + a.args + a.kwonlyargs]
    defaults = dict(zip([p.arg for p in (a.posonlyargs + a.args)][::-1][:len(a.defaults)][::-1], a.defaults))
    defaults.update({p.arg: d for p, d in zip(a.kwonlyargs, a.kw_defaults) if d is not None})
    kinds: dict[str, str] = {}
    for p in params:
        name, hints = p.arg, set()
        if p.annotation is not None:
            kind = _annotation_kind(p.annotation)
            if kind:
                hints.add(kind)
        d = defaults.get(name)
        if isinstance(d, ast.Constant) and d.value is not None:
            hints.add({"bool": "bool", "int": "int", "float": "float", "str": "str"}.get(type(d.value).__name__, "any"))
        for n in _walk_own(fn):
            if isinstance(n, ast.Call):
                f = n.func
                if isinstance(f, ast.Name) and f.id in {"len", "sorted", "reversed", "enumerate", "sum", "max", "min"} \
                        and n.args and isinstance(n.args[0], ast.Name) and n.args[0].id == name:
                    hints.add("sized")
                if isinstance(f, ast.Name) and f.id == "range" and any(
                        isinstance(x, ast.Name) and x.id == name for x in n.args):
                    hints.add("int")
                if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == name:
                    if f.attr in {"upper", "lower", "strip", "split", "join", "startswith", "endswith", "replace",
                                  "title", "isdigit", "format", "encode"}:
                        hints.add("str")
                    elif f.attr in {"append", "extend", "sort", "reverse", "insert", "pop", "index"}:
                        hints.add("list")
                    elif f.attr in {"items", "keys", "values", "get", "setdefault"}:
                        hints.add("dict")
            elif isinstance(n, (ast.For, ast.comprehension)) and isinstance(n.iter, ast.Name) and n.iter.id == name:
                hints.add("sized")
            elif isinstance(n, ast.Subscript) and isinstance(n.value, ast.Name) and n.value.id == name:
                hints.add("sized")
            elif isinstance(n, ast.BinOp) and any(isinstance(x, ast.Name) and x.id == name for x in (n.left, n.right)):
                other = n.right if isinstance(n.left, ast.Name) and n.left.id == name else n.left
                if isinstance(other, ast.Constant):
                    hints.add("str" if isinstance(other.value, str) else "num")
                elif isinstance(n.op, (ast.Mod, ast.Pow, ast.FloorDiv, ast.Div, ast.Sub, ast.Mult)):
                    hints.add("num")
            elif isinstance(n, ast.Compare) and any(isinstance(x, ast.Name) and x.id == name
                                                    for x in [n.left, *n.comparators]):
                others = [x for x in [n.left, *n.comparators] if not (isinstance(x, ast.Name) and x.id == name)]
                if any(isinstance(x, ast.Constant) and isinstance(x.value, (int, float)) and
                       not isinstance(x.value, bool) for x in others):
                    hints.add("num")
        hints.discard("any")
        concrete = hints - {"sized"}
        if len(concrete) == 1:
            kinds[name] = next(iter(concrete))
        elif "sized" in hints and not concrete:
            kinds[name] = "sized"
        elif concrete == {"list", "sized"} or concrete == {"str", "list"}:
            kinds[name] = "sized"
        else:
            kinds[name] = _NAME_KIND.get(name, "any") if not hints else "any"
    return kinds


@dataclass
class StaticSemantics:
    effects: list[str]
    effect_lines: dict
    unknown_calls: list[str]
    purity: str  # pure | unknown | impure
    mutated_params: list[str]
    param_roles: dict
    param_kinds: dict
    returns: dict
    raises: list[str]
    has_assert: bool
    resolved_callees: list[str] = field(default_factory=list)
    transitive_effects: list[str] = field(default_factory=list)
    transitive_unknown: bool = False


def analyze_static(fn, module_globals: set[str], class_receiver: str | None = None) -> StaticSemantics:
    a = fn.args
    params = [x.arg for x in a.posonlyargs + a.args + a.kwonlyargs] + [x.arg for x in (a.vararg, a.kwarg) if x]
    kinds = infer_param_kinds(fn)
    aliases: dict[str, str] = {p: p for p in params}
    declared_global: set[str] = set()
    stores: set[str] = set(params)
    own = list(_walk_own(fn))
    for n in own:
        if isinstance(n, ast.Global):
            declared_global |= set(n.names)
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
            stores.add(n.id)

    def root_of(e):
        while isinstance(e, (ast.Attribute, ast.Subscript)):
            e = e.value
        return e.id if isinstance(e, ast.Name) else None

    for _ in range(2):  # alias propagation (flow-insensitive)
        for n in own:
            if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
                r = root_of(n.value)
                if r in aliases and isinstance(n.value, (ast.Name, ast.Subscript, ast.Attribute)):
                    aliases[n.targets[0].id] = aliases[r]
            elif isinstance(n, (ast.For, ast.comprehension)) and isinstance(n.target, ast.Name):
                r = root_of(n.iter)
                if r in aliases:
                    aliases[n.target.id] = aliases[r]

    effects: dict[str, set[int]] = defaultdict(set)
    unknown: list[str] = []
    mutated: set[str] = set()
    used: set[str] = set()
    returned: set[str] = set()

    def add(cat, line):
        effects[cat].add(line)

    local_names = stores - declared_global
    for n in own:
        line = getattr(n, "lineno", 0)
        if isinstance(n, ast.Name) and n.id in params and isinstance(n.ctx, ast.Load):
            used.add(n.id)
        if isinstance(n, ast.Call):
            name = dotted(n.func)
            f = n.func
            if name == "open":
                mode = None
                if len(n.args) > 1:
                    mode = n.args[1]
                for k in n.keywords:
                    if k.arg == "mode":
                        mode = k.value
                if mode is None:
                    add("io_read", line)
                elif isinstance(mode, ast.Constant) and isinstance(mode.value, str):
                    add("io_write" if any(c in mode.value for c in "wax+") else "io_read", line)
                else:
                    add("io_unknown", line)
                continue
            if name in {"print"}:
                add("console", line)
                continue
            if name == "input":
                add("io_read", line)
                add("console", line)
                continue
            if name in {"setattr", "delattr"} and n.args:
                r = root_of(n.args[0])
                if r in aliases:
                    mutated.add(aliases[r])
                continue
            matched = False
            if name:
                for cat, prefixes in _EFFECT_PREFIX:
                    if name in prefixes or any(name.startswith(p) for p in prefixes if p.endswith(".")) or \
                            (not any(p.endswith(".") for p in prefixes) and name in prefixes):
                        add(cat, line)
                        matched = True
                        break
                    if cat == "dynamic_exec" and name in prefixes:
                        add(cat, line)
                        matched = True
                        break
            if matched:
                continue
            if isinstance(f, ast.Attribute):
                m = f.attr
                recv = root_of(f.value)
                if m in _MUTATING_METHODS and recv in aliases and aliases[recv] == class_receiver:
                    add("self_mutation", line)
                    continue
                if m in _MUTATING_METHODS and recv in aliases:
                    mutated.add(aliases[recv])
                    if m in {"write", "writelines"}:
                        add("io_write", line)
                    continue
                if m in _MUTATING_METHODS and recv in module_globals and recv not in local_names:
                    add("global_mutation", line)
                    continue
                if m in _MUTATING_METHODS and recv is not None and recv in local_names:
                    continue  # mutating a local object
                if m in _IO_WRITE_METHODS:
                    add("io_write", line)
                    continue
                if m in _IO_READ_METHODS:
                    add("io_read", line)
                    continue
                if m in _NET_METHODS:
                    add("network", line)
                    continue
                if m in {"now", "utcnow", "today"}:
                    add("time", line)
                    continue
                if m in _LOG_METHODS and recv in {"logging", "logger", "log", "LOGGER", "_log", "_logger"}:
                    add("logging", line)
                    continue
                if m in _PURE_METHODS or m in {"write"}:
                    continue
                if name and (name.split(".")[0] in _PURE_MODULES or name in _PURE_DOTTED):
                    continue
                unknown.append(name or f"?.{m}")
            elif isinstance(f, ast.Name):
                if f.id in _PURE_BUILTINS or f.id in {"print"}:
                    continue
                unknown.append(f.id)  # may later be resolved via the call graph
            else:
                unknown.append("<dynamic callee>")
        elif isinstance(n, (ast.Assign, ast.AugAssign, ast.AnnAssign, ast.Delete)):
            targets = n.targets if isinstance(n, (ast.Assign, ast.Delete)) else [n.target]
            for t in targets:
                for sub in ast.walk(t):
                    if isinstance(sub, (ast.Subscript, ast.Attribute)) and isinstance(sub.ctx, (ast.Store, ast.Del)):
                        r = root_of(sub)
                        if dotted(sub) in {"os.environ"} or (isinstance(sub, ast.Subscript) and dotted(sub.value) == "os.environ"):
                            add("env_write", line)
                        elif r in aliases and aliases[r] == class_receiver:
                            add("self_mutation", line)
                        elif r in aliases:
                            mutated.add(aliases[r])
                        elif r in module_globals and r not in local_names:
                            add("global_mutation", line)
                if isinstance(n, ast.AugAssign) and isinstance(n.target, ast.Name):
                    nm = n.target.id
                    if nm in declared_global:
                        add("global_write", line)
                    elif nm in params and kinds.get(nm) in {"list", "dict"}:
                        mutated.add(nm)
                elif isinstance(t, ast.Name) and t.id in declared_global:
                    add("global_write", line)
        elif isinstance(n, ast.Attribute) and dotted(n) in {"os.environ", "sys.argv"} and isinstance(n.ctx, ast.Load):
            add("env", line)
        elif isinstance(n, ast.Return) and n.value is not None:
            for sub in ast.walk(n.value):
                if isinstance(sub, ast.Name) and sub.id in params:
                    returned.add(sub.id)

    # returns / raises
    ret_kinds: list[str] = []
    for n in own:
        if isinstance(n, ast.Return):
            v = n.value
            if v is None or (isinstance(v, ast.Constant) and v.value is None):
                ret_kinds.append("none")
            elif isinstance(v, ast.Constant) and isinstance(v.value, bool):
                ret_kinds.append("bool_const")
            elif _boolish(v):
                ret_kinds.append("bool_expr")
            elif isinstance(v, ast.Constant):
                ret_kinds.append("const")
            elif isinstance(v, ast.Name) and v.id in params:
                ret_kinds.append("param")
            else:
                ret_kinds.append("value")
    falls = can_fall_through(fn.body)
    returns = {"n": len(ret_kinds), "kinds": sorted(set(ret_kinds)),
               "returns_bool": bool(ret_kinds) and all(k in {"bool_const", "bool_expr"} for k in ret_kinds) and not falls,
               "can_return_none": "none" in ret_kinds or falls, "falls_off_end": falls,
               "returns_only_constants": bool(ret_kinds) and all(k in {"const", "bool_const", "none"} for k in ret_kinds),
               "constants": sorted({repr(n.value.value) if isinstance(n.value, ast.Constant) else "None"
                                    for n in own if isinstance(n, ast.Return)
                                    and (n.value is None or isinstance(n.value, ast.Constant))})}
    raises = sorted({(dotted(n.exc.func) if isinstance(n.exc, ast.Call) else dotted(n.exc)) or "?"
                     for n in own if isinstance(n, ast.Raise) and n.exc is not None}
                    | ({"re-raise"} if any(isinstance(n, ast.Raise) and n.exc is None for n in own) else set()))
    has_assert = any(isinstance(n, ast.Assert) for n in own)
    roles = {}
    for p in params:
        r = []
        if p in mutated:
            r.append("mutated")
        if p in returned:
            r.append("returned")
        r.append("read" if p in used else "unused")
        roles[p] = r
    eff = sorted(effects)
    purity = "impure" if (set(eff) & PURITY_BREAKING or mutated) else ("unknown" if unknown else "pure")
    return StaticSemantics(eff, {k: sorted(v) for k, v in sorted(effects.items())}, sorted(set(unknown)), purity,
                           sorted(mutated), roles, kinds, returns, raises, has_assert)


# ------------------------------------------------------- reference behaviour library
@dataclass(frozen=True)
class Ref:
    name: str
    cat: str
    fn: object
    aliases: tuple
    domain: object = None
    inplace: bool = False
    pred: bool = False
    strict: bool = False


INT1 = [-9, -7, -4, -2, -1, 0, 1, 2, 3, 4, 5, 6, 7, 10, 11, 12]
NAT1 = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 16, 17, 25, 29, 97]
FLT1 = [-2.5, -1.5, -0.5, 0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 4.0, 9.0, 10.25]
_A, _B = [-5, -2, 0, 1, 3, 4, 7], [-3, -1, 0, 2, 3, 5]
INT2 = [(a, b) for a in _A for b in _B] + [(3, 3), (0, 0), (-2, -2), (7, 7)]
SEQ1 = [[], [0], [5], [1, 2, 3], [3, 1, 2], [-1, -2, -3], [2, 2, 2], [1, -1, 1], [10, 20, 30, 40], [4, 4, 1, 1],
        [7, 3, 9, 3, 7], [0, 0, 5]]
STR1 = ["", "a", "abc", "Hello World", "  pad  ", "racecar", "AbC", "a b  c", "123", "hello world foo", "Level"]
STR2 = [("ab", "cd"), ("", "x"), ("x", ""), ("hello", "ell"), ("abc", "abc"), ("Abc", "abc"), ("abc", "ab"),
        ("abc", "bc"), ("abcd", "d"), ("", ""), ("aaa", "a")]
STRINT = [("ab", 3), ("x", 0), ("", 5), ("abc", 1), ("xy", 2)]
SEQ_ITEM = [(s, i) for s in ([], [1, 2, 3], [3, 1, 3], [5], [2, 2, 2, 7]) for i in (0, 1, 2, 3, 7)]
BATTERIES = {"nullary": [()], "int1": [(x,) for x in INT1], "nat1": [(x,) for x in NAT1],
             "flt1": [(x,) for x in FLT1], "int2": INT2, "seq1": [(s,) for s in SEQ1],
             "str1": [(s,) for s in STR1], "str2": STR2, "strint": STRINT, "seq_item": SEQ_ITEM}
REFS: list[Ref] = []


def _r(name, cat, fn, *aliases, domain=None, inplace=False, pred=False, strict=False):
    REFS.append(Ref(name, cat, fn, tuple(aliases), domain, inplace, pred, strict))


def _isprime(n):
    return n > 1 and all(n % d for d in range(2, int(n ** 0.5) + 1))


def _fib(n):
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a


_r("identity", "int1", lambda x: x, "identity", "echo", "passthrough", strict=True)
_r("negate", "int1", lambda x: -x, "negate", "neg", "opposite")
_r("abs", "int1", abs, "abs", "absolute", "magnitude")
_r("square", "int1", lambda x: x * x, "square", "sq", "squared")
_r("cube", "int1", lambda x: x ** 3, "cube", "cubed")
_r("double", "int1", lambda x: 2 * x, "double", "twice", "doubled")
_r("half_floor", "int1", lambda x: x // 2, "half", "halve")
_r("half_true", "int1", lambda x: x / 2, "half", "halve")
_r("increment", "int1", lambda x: x + 1, "increment", "inc", "succ", "next")
_r("decrement", "int1", lambda x: x - 1, "decrement", "dec", "pred", "prev", "previous")
_r("is_even", "int1", lambda x: x % 2 == 0, "even", pred=True)
_r("is_odd", "int1", lambda x: x % 2 == 1, "odd", pred=True)
_r("is_positive", "int1", lambda x: x > 0, "positive", "pos", pred=True)
_r("is_negative", "int1", lambda x: x < 0, "negative", pred=True)
_r("is_zero", "int1", lambda x: x == 0, "zero", pred=True)
_r("sign", "int1", lambda x: (x > 0) - (x < 0), "sign", "signum")
_r("factorial", "nat1", math.factorial, "factorial", "fact", domain=lambda n: n <= 12)
_r("fibonacci", "nat1", _fib, "fib", "fibonacci", domain=lambda n: n <= 25)
_r("is_prime", "nat1", _isprime, "prime", pred=True)
_r("isqrt", "nat1", math.isqrt, "isqrt", "intsqrt")
_r("digit_sum", "nat1", lambda n: sum(map(int, str(n))), "digit", "digits", "digitsum")
_r("triangular", "nat1", lambda n: n * (n + 1) // 2, "triangular", "triangle")
_r("popcount", "nat1", lambda n: bin(n).count("1"), "popcount", "bitcount", "bits", "ones")
_r("is_power_of_two", "nat1", lambda n: n > 0 and n & (n - 1) == 0, "pow2", "power_of_two", pred=True)
_r("floor", "flt1", math.floor, "floor")
_r("ceil", "flt1", math.ceil, "ceil", "ceiling")
_r("trunc", "flt1", math.trunc, "trunc", "truncate")
_r("round_even", "flt1", round, "round")
_r("sqrt", "flt1", math.sqrt, "sqrt", "squareroot", "root")
_r("abs_f", "flt1", abs, "abs", "fabs", "absolute")
_r("square_f", "flt1", lambda x: x * x, "square", "sq")
_r("half_f", "flt1", lambda x: x / 2, "half", "halve")
_r("reciprocal", "flt1", lambda x: 1 / x, "reciprocal", "inverse", "recip")
_r("add", "int2", operator.add, "add", "sum", "plus", "total", "combine")
_r("subtract", "int2", operator.sub, "sub", "subtract", "minus", "diff", "difference")
_r("subtract_rev", "int2", lambda a, b: b - a, "rsub")
_r("multiply", "int2", operator.mul, "mul", "multiply", "times", "product", "prod")
_r("floordiv", "int2", operator.floordiv, "floordiv", "idiv", "intdiv", "quotient", "div", "divide")
_r("truediv", "int2", operator.truediv, "truediv", "ratio", "div", "divide")
_r("mod", "int2", operator.mod, "mod", "modulo", "remainder", "rem")
_r("power", "int2", operator.pow, "pow", "power", "exponent", domain=lambda a, b: b >= 0 and abs(a) <= 10)
_r("max2", "int2", max, "max", "maximum", "larger", "bigger", "biggest", "largest")
_r("min2", "int2", min, "min", "minimum", "smaller", "smallest", "lesser", "lowest")
_r("gcd", "int2", math.gcd, "gcd", "hcf")
_r("lcm", "int2", math.lcm, "lcm")
_r("absdiff", "int2", lambda a, b: abs(a - b), "absdiff", "distance", "gap")
_r("equal", "int2", operator.eq, "equal", "equals", "eq", "same", pred=True)
_r("less_than", "int2", operator.lt, "lt", "less", "lessthan", pred=True)
_r("greater_than", "int2", operator.gt, "gt", "greater", "greaterthan", pred=True)
_r("not_equal", "int2", operator.ne, "ne", "differ", "notequal", pred=True)
_r("first", "int2", lambda a, b: a, "fst", "left")
_r("second", "int2", lambda a, b: b, "snd", "right")
_r("mean_floor", "int2", lambda a, b: (a + b) // 2, "mean", "avg", "average", "midpoint", "mid")
_r("mean_true", "int2", lambda a, b: (a + b) / 2, "mean", "avg", "average", "midpoint", "mid")
_r("sum_squares2", "int2", lambda a, b: a * a + b * b, "sumsq", "sum_squares")
_ne = lambda s: len(s) > 0  # noqa: E731
_r("sum", "seq1", sum, "sum", "total", "sigma")
_r("product", "seq1", lambda s: math.prod(s), "product", "prod")
_r("max", "seq1", max, "max", "maximum", "largest", "biggest", "highest", "top", domain=_ne)
_r("min", "seq1", min, "min", "minimum", "smallest", "lowest", domain=_ne)
_r("len", "seq1", len, "len", "length", "size", "count", "number")
_r("sorted", "seq1", sorted, "sorted", "sort", "ordered", "order")
_r("reversed", "seq1", lambda s: s[::-1], "reverse", "reversed", "flip")
_r("unique_ordered", "seq1", lambda s: list(dict.fromkeys(s)), "unique", "dedupe", "dedup", "distinct", "uniq")
_r("first_elem", "seq1", lambda s: s[0], "first", "head", "front", domain=_ne)
_r("last_elem", "seq1", lambda s: s[-1], "last", "final", "back", domain=_ne)
_r("mean_seq", "seq1", lambda s: sum(s) / len(s), "mean", "avg", "average", domain=_ne)
_r("count_positive", "seq1", lambda s: sum(1 for x in s if x > 0), "npos", "count_positive")
_r("count_even", "seq1", lambda s: sum(1 for x in s if x % 2 == 0), "count_even")
_r("sum_even", "seq1", lambda s: sum(x for x in s if x % 2 == 0), "sum_even")
_r("sum_positive", "seq1", lambda s: sum(x for x in s if x > 0), "sum_positive")
_r("any_positive", "seq1", lambda s: any(x > 0 for x in s), "any_positive", pred=True)
_r("all_positive", "seq1", lambda s: all(x > 0 for x in s), "all_positive", pred=True)
_r("is_sorted", "seq1", lambda s: all(a <= b for a, b in zip(s, s[1:])), "sorted", "ordered", "ascending", pred=True)
_r("is_palindrome_list", "seq1", lambda s: s == s[::-1], "palindrome", pred=True)
_r("cumsum", "seq1", lambda s: list(itertools.accumulate(s)), "cumsum", "cumulative", "running")
_r("sum_squares", "seq1", lambda s: sum(x * x for x in s), "sumsq", "sum_squares")
_r("value_range", "seq1", lambda s: max(s) - min(s), "range", "spread", domain=_ne)
_r("list_copy", "seq1", lambda s: list(s), "copy", "clone", "identity")
_r("sorted_desc", "seq1", lambda s: sorted(s, reverse=True), "descending", "sorted_desc")
_r("evens", "seq1", lambda s: [x for x in s if x % 2 == 0], "evens", "even_numbers")
_r("odds", "seq1", lambda s: [x for x in s if x % 2 == 1], "odds", "odd_numbers")
_r("positives", "seq1", lambda s: [x for x in s if x > 0], "positives", "positive_numbers")
_r("doubled", "seq1", lambda s: [2 * x for x in s], "doubled", "double_all")
_r("squares", "seq1", lambda s: [x * x for x in s], "squares", "square_all")
_r("count_distinct", "seq1", lambda s: len(set(s)), "distinct_count", "nunique")
_r("contains_duplicates", "seq1", lambda s: len(set(s)) != len(s), "duplicates", "dupes", pred=True)
_r("sort_inplace", "seq1", sorted, "sort", "sort_inplace", inplace=True)
_r("reverse_inplace", "seq1", lambda s: s[::-1], "reverse", "reverse_inplace", inplace=True)
_r("upper", "str1", str.upper, "upper", "uppercase", "capitalize_all", "shout")
_r("lower", "str1", str.lower, "lower", "lowercase")
_r("reverse_str", "str1", lambda s: s[::-1], "reverse", "reversed", "flip")
_r("length", "str1", len, "len", "length", "size", "count")
_r("strip", "str1", str.strip, "strip", "trim", "clean")
_r("title", "str1", str.title, "title", "titlecase")
_r("capitalize", "str1", str.capitalize, "capitalize")
_r("swapcase", "str1", str.swapcase, "swapcase")
_r("is_palindrome", "str1", lambda s: s == s[::-1], "palindrome", pred=True)
_r("count_vowels", "str1", lambda s: sum(c in "aeiouAEIOU" for c in s), "vowels", "count_vowels")
_r("word_count", "str1", lambda s: len(s.split()), "words", "word_count")
_r("first_char", "str1", lambda s: s[0], "first", "initial", domain=lambda s: len(s) > 0)
_r("last_char", "str1", lambda s: s[-1], "last", domain=lambda s: len(s) > 0)
_r("is_digit_str", "str1", str.isdigit, "digit", "digits", "numeric", pred=True)
_r("remove_spaces", "str1", lambda s: s.replace(" ", ""), "despace", "remove_spaces", "squash")
_r("chars_list", "str1", list, "chars", "characters", "explode")
_r("concat", "str2", lambda a, b: a + b, "concat", "concatenate", "join", "append", "add")
_r("concat_rev", "str2", lambda a, b: b + a, "prepend")
_r("contains", "str2", lambda a, b: b in a, "contains", "includes", "has", pred=True)
_r("startswith", "str2", str.startswith, "startswith", "starts", pred=True)
_r("endswith", "str2", str.endswith, "endswith", "ends", pred=True)
_r("equal_ci", "str2", lambda a, b: a.lower() == b.lower(), "equal_ci", "iequals", "same_ignore_case", pred=True)
_r("equal_str", "str2", lambda a, b: a == b, "equal", "equals", "same", pred=True)
_r("count_sub", "str2", lambda a, b: a.count(b), "count_sub", "occurrences", domain=lambda a, b: b != "")
_r("repeat", "strint", lambda s, n: s * n, "repeat", "times", "multiply")
_r("seq_contains", "seq_item", lambda s, x: x in s, "contains", "includes", "has", "member", pred=True)
_r("count_of", "seq_item", lambda s, x: s.count(x), "count", "occurrences", "frequency")
_r("index_of_or_minus1", "seq_item", lambda s, x: s.index(x) if x in s else -1, "index", "find", "position")
_r("with_appended", "seq_item", lambda s, x: s + [x], "append", "with_item", "plus")
_r("without_item", "seq_item", lambda s, x: [v for v in s if v != x], "remove", "without", "discard", "exclude")
_r("take_first_n", "seq_item", lambda s, n: s[:n], "take", "head", "first")
_r("drop_first_n", "seq_item", lambda s, n: s[n:], "drop", "skip", "tail")
_r("at_index", "seq_item", lambda s, i: s[i], "at", "get", "nth", "item", domain=lambda s, i: 0 <= i < len(s))
_BY_CAT: dict[str, list[Ref]] = defaultdict(list)
for _ref in REFS:
    _BY_CAT[_ref.cat].append(_ref)


def categories_for(arity: int, kinds: list[str]) -> list[str]:
    if arity == 0:
        return ["nullary"]
    if arity == 1:
        k = kinds[0]
        return {"int": ["int1", "nat1"], "num": ["int1", "nat1", "flt1"], "float": ["flt1"], "bool": [],
                "str": ["str1"], "list": ["seq1"], "sized": ["seq1", "str1"], "dict": []}.get(
            k, ["int1", "nat1", "flt1", "seq1", "str1"])
    if arity == 2:
        a, b = kinds
        num, anyk = {"num", "int", "float"}, {"any"}
        if a in num and b in num:
            return ["int2"]
        if a == "str" and b == "str":
            return ["str2"]
        if a in {"str", "sized"} and b in num | {"any"} and a == "str":
            return ["strint", "str2"] if b == "any" else ["strint"]
        if a in {"list", "sized"} and (b in num or b in anyk):
            return ["seq_item"]
        if a in anyk and b in anyk:
            return ["int2", "str2", "seq_item", "strint"]
        if a in anyk and b in num:
            return ["int2", "seq_item", "strint"]
        if a in num and b in anyk:
            return ["int2"]
        if a == "sized" and b == "sized":
            return ["str2"]
    return []


# ------------------------------------------------------------------ probing worker
_WORKER = r'''
import sys, os, json, importlib, io, copy, signal, contextlib, ast, types, time
job = json.load(open(sys.argv[1])); out_path = sys.argv[2]
sys.dont_write_bytecode = True
if job.get("root"): sys.path.insert(0, job["root"])
os.chdir(job["cwd"]); sys.setrecursionlimit(400)
res = open(out_path, "a", buffering=1)
def emit(o): res.write(json.dumps(o) + "\n"); res.flush()
def enc(v, d=0):
    if v is None: return {"t": "none"}
    if isinstance(v, bool): return {"t": "bool", "v": v}
    if isinstance(v, int): return {"t": "int", "v": v if abs(v) < 2**53 else str(v)}
    if isinstance(v, float): return {"t": "float", "v": repr(v)}
    if isinstance(v, str): return {"t": "str", "v": v[:2000]}
    if d > 4: return {"t": "obj", "v": type(v).__name__}
    if isinstance(v, list): return {"t": "list", "v": [enc(x, d + 1) for x in v[:200]]}
    if isinstance(v, tuple): return {"t": "tuple", "v": [enc(x, d + 1) for x in v[:200]]}
    if isinstance(v, dict): return {"t": "dict", "v": [[enc(k, d + 1), enc(x, d + 1)] for k, x in list(v.items())[:100]]}
    if isinstance(v, (set, frozenset)): return {"t": "set", "v": sorted((enc(x, d + 1) for x in list(v)[:100]), key=json.dumps)}
    return {"t": "obj", "v": type(v).__name__}
class _TO(BaseException): pass
def _alarm(s, f): raise _TO()
signal.signal(signal.SIGALRM, _alarm)
def call(fn, args, tmo):
    signal.setitimer(signal.ITIMER_REAL, tmo)
    try: return ("ok", fn(*args), None)
    except _TO: return ("exc", None, "Timeout")
    except BaseException as e: return ("exc", None, type(e).__name__)
    finally: signal.setitimer(signal.ITIMER_REAL, 0)
def snap(mod):
    out = {}
    for k, v in list(vars(mod).items()):
        if k.startswith("__") or callable(v) or isinstance(v, types.ModuleType): continue
        try: out[k] = repr(v)[:200]
        except BaseException: out[k] = "?"
    return out
tmo = job["call_timeout"]
for m in job["modules"]:
    try:
        signal.setitimer(signal.ITIMER_REAL, job["import_timeout"])
        mod = importlib.import_module(m["module"])
        signal.setitimer(signal.ITIMER_REAL, 0)
    except BaseException as e:
        signal.setitimer(signal.ITIMER_REAL, 0)
        emit({"module": m["module"], "import_error": type(e).__name__ + ": " + str(e)[:120]}); continue
    for f in m["functions"]:
        key = {"module": m["module"], "qualname": f["qualname"], "id": f.get("id", f["qualname"])}
        try:
            fn = mod
            for part in f["qualname"].split("."): fn = getattr(fn, part)
        except BaseException as e:
            emit(dict(key, error="lookup: " + type(e).__name__)); continue
        before_g, before_files = snap(mod), set(os.listdir("."))
        results, printed, timeouts, t0 = [], 0, 0, time.monotonic()
        for bat in f["batteries"]:
            for i, rep in enumerate(bat["inputs"]):
                if timeouts >= 5 or time.monotonic() - t0 > job["function_budget"]: break
                args = ast.literal_eval(rep)
                a1, a2 = copy.deepcopy(args), copy.deepcopy(args)
                before = json.dumps([enc(x) for x in args])
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    r1 = call(fn, a1, tmo); r2 = call(fn, a2, tmo)
                printed += len(buf.getvalue())
                if r1[2] == "Timeout": timeouts += 1
                o1 = json.dumps(enc(r1[1])) if r1[0] == "ok" else None
                o2 = json.dumps(enc(r2[1])) if r2[0] == "ok" else None
                after = [enc(x) for x in a1]
                results.append({"cat": bat["cat"], "i": i, "out": json.loads(o1) if o1 else None, "exc": r1[2],
                                "after": after, "mut": json.dumps(after) != before,
                                "det": (o1 == o2 and r1[2] == r2[2])})
        emit(dict(key, results=results, printed=printed, timeouts=timeouts,
                  files_new=sorted(set(os.listdir(".")) - before_files)[:5], globals_changed=snap(mod) != before_g))
emit({"done": True})
'''


class Obj:
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return f"<{self.name}>"


def dec(e):
    t = e["t"]
    if t == "none":
        return None
    if t in {"bool", "str"}:
        return e["v"]
    if t == "int":
        return int(e["v"])
    if t == "float":
        return float(e["v"])
    if t == "list":
        return [dec(x) for x in e["v"]]
    if t == "tuple":
        return tuple(dec(x) for x in e["v"])
    if t == "dict":
        out = {}
        for k, v in e["v"]:
            key = dec(k)
            out[tuple(key) if isinstance(key, list) else key] = dec(v)
        return out
    if t == "set":
        return {tuple(x) if isinstance(x, list) else x for x in map(dec, e["v"])}
    return Obj(e.get("v", "?"))


def equiv(a, b) -> int:
    """0 = different, 1 = equal, 2 = equal except bool-vs-number type."""
    if isinstance(a, bool) != isinstance(b, bool):
        if isinstance(a, (int, float)) and isinstance(b, (int, float)) and a == b:
            return 2
        return 0
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b):
            return 1
        return 1 if (a == b or math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12)) else 0
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        if len(a) != len(b):
            return 0
        worst = 1
        for x, y in zip(a, b):
            v = equiv(x, y)
            if not v:
                return 0
            worst = max(worst, v)
        return worst
    if isinstance(a, dict) and isinstance(b, dict):
        return 1 if a.keys() == b.keys() and all(equiv(a[k], b[k]) for k in a) else 0
    if isinstance(a, Obj) or isinstance(b, Obj):
        return 0
    return 1 if a == b else 0


def _short(v):
    r = repr(v)
    return r if len(r) <= 60 else r[:57] + "..."


def match_refs(cat: str, results: dict) -> list[dict]:
    """results: input index -> worker record. Returns one entry per reference with >= 6 defined probe inputs."""
    import copy
    inputs = BATTERIES[cat]
    out = []
    for ref in _BY_CAT.get(cat, []):
        domain = ok = notes = 0
        devs = []
        for i, args in enumerate(inputs):
            if ref.domain is not None:
                try:
                    if not ref.domain(*args):
                        continue
                except Exception:
                    continue
            try:
                expected = ref.fn(*copy.deepcopy(args))
            except Exception:
                continue
            domain += 1
            r = results.get(i)
            if r is None or r["exc"]:
                devs.append({"input": _short(args), "expected": _short(expected),
                             "got": "missing" if r is None else f"raised {r['exc']}"})
                continue
            got = dec(r["after"][0]) if ref.inplace else dec(r["out"])
            v = equiv(got, expected)
            if v and ref.strict and type(got) is not type(expected):
                v = 0  # e.g. float(3) == 3 numerically but is not an identity function
            if v:
                ok += 1
                notes += v == 2
            else:
                devs.append({"input": _short(args), "expected": _short(expected), "got": _short(got)})
        if domain >= 6:
            out.append({"ref": ref.name, "cat": cat, "score": round(ok / domain, 3), "domain": domain,
                        "type_notes": notes, "deviations": devs[:5], "pred": ref.pred})
    return out


def name_tokens(name: str) -> list[str]:
    name = name.strip("_")
    parts = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name).lower().split("_")
    return [p for p in parts if p]


def refs_named_by(tokens: list[str], cats: list[str]) -> set[str]:
    """Reference behaviours whose alias words appear in the function's name (restricted to probed categories)."""
    predicate = bool(tokens) and tokens[0] in {"is", "has", "can", "should"}
    joined = "_".join(tokens)
    hit = set()
    for ref in REFS:
        if ref.cat not in cats:
            continue
        if predicate and not ref.pred:
            continue
        if any(a in tokens or a == joined or (("_" in a) and a in joined) for a in ref.aliases):
            hit.add(ref.name)
    return hit


# ------------------------------------------------------------------------- report
PURE_VERBS = frozenset({"get", "compute", "calculate", "calc", "count", "is", "has", "can", "should", "to", "as", "total",
                        "sum", "avg", "mean", "max", "min", "len", "contains", "compare", "equals", "format", "parse",
                        "find", "lookup"})
MUTATOR_VERBS = frozenset({"set", "update", "add", "append", "remove", "delete", "clear", "push", "insert", "register",
                           "write", "save", "dump", "store", "reset", "put"})
VALIDATOR_VERBS = frozenset({"validate", "check", "verify", "ensure", "assert"})
PRED_VERBS = frozenset({"is", "has", "can", "should"})
# "add"/"set"/"update" also mean arithmetic or construction; only treated as mutators when the first parameter looks like a container
AMBIGUOUS_MUTATOR_VERBS = frozenset({"add", "set", "update"})
_SEVERITY = {"high": 0, "medium": 1, "low": 2}


@dataclass
class Finding:
    kind: str
    qname: str
    path: str
    line: int
    severity: str
    source: str  # static | dynamic | static+dynamic
    message: str
    evidence: dict = field(default_factory=dict)


@dataclass
class FunctionSemantics:
    qname: str
    path: str
    line: int
    name: str
    tokens: list
    static: dict
    behavior: dict | None = None
    inferred: list = field(default_factory=list)
    name_refs: list = field(default_factory=list)


@dataclass
class SemanticReport:
    root: str
    functions: list
    findings: list
    stats: dict
    diagnostics: list
    isolation: dict

    def function(self, qname: str) -> FunctionSemantics:
        for f in self.functions:
            if f.qname == qname:
                return f
        raise KeyError(qname)

    def findings_for(self, qname: str) -> list:
        return [f for f in self.findings if f.qname == qname]

    def finding_pairs(self) -> set:
        return {(f.kind, f.qname) for f in self.findings}

    def inferred(self, qname: str) -> list:
        return list(self.function(qname).inferred)

    def to_dict(self) -> dict:
        return {"root": self.root, "functions": [asdict(f) for f in self.functions],
                "findings": [asdict(f) for f in self.findings], "stats": self.stats,
                "diagnostics": self.diagnostics, "isolation": self.isolation}


def _module_import_risk(tree) -> dict:
    """Risky CALLS that would execute at IMPORT time (module level and class bodies, not method bodies).

    Merely importing subprocess/socket is harmless; calling into them at import time is not.
    """
    from .sandbox import _RISK_CALLS, _RISK_IMPORTS
    aliases: dict = {}
    for st in tree.body:
        if isinstance(st, ast.Import):
            for a in st.names:
                top = a.name.split(".")[0]
                for cat, names in _RISK_IMPORTS.items():
                    if top in names:
                        aliases[a.asname or top] = cat
        elif isinstance(st, ast.ImportFrom) and st.module:
            top = st.module.split(".")[0]
            for cat, names in _RISK_IMPORTS.items():
                if top in names:
                    for a in st.names:
                        aliases[a.asname or a.name] = cat
    call_cats = {name: cat for cat, names in _RISK_CALLS.items() for name in names}
    found: dict = {}
    for st in tree.body:
        if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Import, ast.ImportFrom)):
            continue
        if isinstance(st, ast.If) and "__name__" in ast.dump(st.test):
            continue
        nodes = []
        if isinstance(st, ast.ClassDef):
            for sub in st.body:
                if not isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    nodes.extend(ast.walk(sub))
        else:
            nodes = list(ast.walk(st))
        for n in nodes:
            if isinstance(n, ast.Call):
                name = dotted(n.func)
                if not name:
                    continue
                root = name.split(".")[0]
                if root in aliases:
                    found.setdefault(aliases[root], set()).add(name)
                elif name in call_cats:
                    found.setdefault(call_cats[name], set()).add(name)
    return found


def _index_functions(tree, module: str) -> dict:
    out: dict = {}

    def collect(body, prefix, class_q, kind):
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                q = f"{prefix}.{node.name}"
                out[q] = (node, class_q, kind)
                collect(node.body, q, None, "nested")
            elif isinstance(node, ast.ClassDef) and kind != "nested":
                q = f"{prefix}.{node.name}"
                collect(node.body, q, q, "method")
    collect(tree.body, module, None, "function")
    return out


def spec_key(spec: dict) -> tuple:
    """Stable key for a probe_callables spec (module, qualname, arity, kinds)."""
    return (spec["module"], spec["qualname"], spec["arity"], tuple(spec.get("kinds") or ["any"] * spec["arity"]))


class SemanticAnalyzer:
    def __init__(self, probe: bool = True, max_probe_functions: int = 200, probe_budget_seconds: float = 120.0,
                 per_module_timeout: float = 30.0, per_call_timeout: float = 1.0, memory_mb: int | None = 1024,
                 probe_effectful: bool = False, network: str = "auto", near_threshold: float = 0.7,
                 weak_findings: bool = False):
        self.weak_findings = weak_findings
        self.probe, self.max_probe_functions = probe, max_probe_functions
        self.probe_budget, self.per_module_timeout = probe_budget_seconds, per_module_timeout
        self.per_call_timeout, self.memory_mb = per_call_timeout, memory_mb
        self.probe_effectful, self.network, self.near = probe_effectful, network, near_threshold

    # ------------------------------------------------------------------ execution
    def _exec_jobs(self, by_module: dict, root: Path | None, diags: list, deadline: float):
        """Run probe jobs in the sandbox, one worker per module. Returns ({(module, qualname): raw}, isolation)."""
        raw: dict = {}
        isolation: dict = {}
        with tempfile.TemporaryDirectory(prefix="asm_sem_") as td:
            td = Path(td)
            repo_copy = None
            if root is not None:
                repo_copy = td / "repo"
                skipped = copy_repo(root, repo_copy)
                if skipped:
                    diags.append({"code": "symlinks_not_copied", "paths": skipped[:10]})
            for n, (module, funcs) in enumerate(sorted(by_module.items())):
                remaining = deadline - time.monotonic()
                if remaining < 1.0:
                    diags.append({"code": "probe_budget_exhausted", "module": module})
                    break
                cwd = td / f"cwd{n}"
                cwd.mkdir()
                job = {"root": str(repo_copy) if repo_copy else None, "cwd": str(cwd),
                       "call_timeout": self.per_call_timeout, "import_timeout": 10.0, "function_budget": 8.0,
                       "modules": [{"module": module, "functions": funcs}]}
                jp, op = td / f"job{n}.json", td / f"out{n}.jsonl"
                jp.write_text(json.dumps(job))
                op.write_text("")
                run = run_python_worker(_WORKER, [str(jp), str(op)], cwd, timeout=min(self.per_module_timeout, remaining),
                                        memory_mb=self.memory_mb, network=self.network)
                isolation = run["isolation"]
                if run["timed_out"]:
                    diags.append({"code": "probe_timeout", "module": module})
                elif run["returncode"] not in (0, None):
                    diags.append({"code": "probe_worker_failed", "module": module, "returncode": run["returncode"],
                                  "stderr": run["stderr"][-200:]})
                for line in op.read_text().splitlines():
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if "import_error" in rec:
                        diags.append({"code": "probe_import_error", "module": rec["module"], "message": rec["import_error"]})
                    elif "error" in rec:
                        diags.append({"code": "probe_lookup_error", "module": rec["module"], "qualname": rec["qualname"],
                                      "message": rec["error"]})
                    elif "results" in rec:
                        raw[(rec["module"], rec.get("id", rec["qualname"]))] = rec
        return raw, isolation

    def _behavior(self, cats: list, rec: dict) -> dict:
        by_cat: dict = defaultdict(dict)
        for r in rec["results"]:
            by_cat[r["cat"]][r["i"]] = r
        types, exc = defaultdict(int), defaultdict(int)
        mutated: set = set()
        for r in rec["results"]:
            if r["exc"]:
                exc[r["exc"]] += 1
            else:
                types[type(dec(r["out"])).__name__] += 1
            args = BATTERIES[r["cat"]][r["i"]]
            for idx, e in enumerate(r["after"]):
                if idx < len(args) and not equiv(dec(e), args[idx]):
                    mutated.add(idx)
        usable = [c for c in cats if by_cat[c] and sum(1 for r in by_cat[c].values() if not r["exc"]) / len(BATTERIES[c]) >= 0.6]
        matches = [m for c in cats if by_cat[c] for m in match_refs(c, by_cat[c])]
        exact = [m for m in matches if m["score"] == 1.0]
        near = sorted((m for m in matches if self.near <= m["score"] < 1.0), key=lambda m: -m["score"])
        per_cat = defaultdict(int)
        for m in exact:
            per_cat[m["cat"]] += 1
        return {"probed": True, "calls": len(rec["results"]), "categories": cats, "usable_categories": usable,
                "deterministic": all(r["det"] for r in rec["results"]) if rec["results"] else True,
                "mutates_args": sorted(mutated), "printed": rec["printed"] > 0, "files_written": rec["files_new"],
                "globals_changed": rec["globals_changed"], "exceptions": dict(sorted(exc.items())),
                "timeouts": rec["timeouts"], "output_types": dict(sorted(types.items())),
                "exact": [{"ref": m["ref"], "cat": m["cat"], "type_notes": m["type_notes"]} for m in exact],
                "near": [{"ref": m["ref"], "cat": m["cat"], "score": m["score"], "deviations": m["deviations"]}
                         for m in near[:3]],
                "ambiguous": any(v > 1 for v in per_cat.values())}

    def probe_callables(self, specs: list) -> dict:
        """Probe importable callables (e.g. stdlib) in the sandbox. spec: {module, qualname, arity, kinds?}."""
        by_module: dict = defaultdict(list)
        cats_of: dict = {}
        for s in specs:
            kinds = s.get("kinds") or ["any"] * s["arity"]
            cats = s.get("cats") or categories_for(s["arity"], kinds)
            cats_of[str(spec_key(s))] = cats
            by_module[s["module"]].append({"qualname": s["qualname"], "id": str(spec_key(s)), "batteries": [
                {"cat": c, "inputs": [repr(a) for a in BATTERIES[c]]} for c in cats]})
        diags: list = []
        raw, iso = self._exec_jobs(by_module, None, diags, time.monotonic() + self.probe_budget)
        by_id = {str(spec_key(s)): spec_key(s) for s in specs}
        return {by_id[k[1]]: self._behavior(cats_of[k[1]], v) for k, v in raw.items()} | {
            "_diagnostics": diags, "_isolation": iso}

    # ------------------------------------------------------------------- analysis
    def analyze(self, root: str | Path, probe_only: set | None = None) -> SemanticReport:
        base = Path(root).resolve(strict=True)
        und = CodeUnderstanding().analyze(base)
        diags: list = list(und.diagnostics)
        index: dict = {}
        trees: dict = {}
        module_globals: dict = {}
        for m in und.modules:
            if m.parse_error:
                continue
            try:
                tree = ast.parse((base / m.path).read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError, ValueError, RecursionError):
                continue
            trees[m.module] = tree
            for q, v in _index_functions(tree, m.module).items():
                index[q] = v + (m.path,)
            names = set()
            for st in tree.body:
                if isinstance(st, ast.Assign):
                    names |= {t.id for t in st.targets if isinstance(t, ast.Name)}
                elif isinstance(st, ast.AnnAssign) and isinstance(st.target, ast.Name):
                    names.add(st.target.id)
            module_globals[m.module] = names

        statics: dict = {}
        finfo = {f.qname: f for f in und.functions}
        for q, (node, class_q, kind, path) in index.items():
            recv = None
            if kind == "method" and node.args.args and not any(
                    isinstance(d, ast.Name) and d.id == "staticmethod" for d in node.decorator_list):
                recv = node.args.args[0].arg
            mod = finfo[q].module if q in finfo else q.split(".")[0]
            statics[q] = analyze_static(node, module_globals.get(mod, set()), recv)
        self._propagate(und, statics)

        behaviors: dict = {}
        probed_cats: dict = {}
        stats = {"functions": len(index), "probed": 0, "probe_candidates": 0}
        if self.probe:
            targets = self._select_targets(index, statics, trees, finfo, diags)
            if probe_only is not None:
                targets = [t for t in targets if t[0] in probe_only]
            stats["probe_candidates"] = len(targets)
            by_module: dict = defaultdict(list)
            for q, cats in targets[: self.max_probe_functions]:
                by_module[finfo[q].module].append({"qualname": q[len(finfo[q].module) + 1:], "id": q, "batteries": [
                    {"cat": c, "inputs": [repr(a) for a in BATTERIES[c]]} for c in cats], "_q": q})
                probed_cats[q] = cats
            jobs = {m: [{k: v for k, v in f.items() if k != "_q"} for f in fs] for m, fs in by_module.items()}
            raw, iso = self._exec_jobs(jobs, base, diags, time.monotonic() + self.probe_budget)
            for m, fs in by_module.items():
                for f in fs:
                    rec = raw.get((m, f["_q"]))
                    if rec is None:
                        diags.append({"code": "probe_incomplete", "qname": f["_q"]})
                    else:
                        behaviors[f["_q"]] = self._behavior(probed_cats[f["_q"]], rec)
            stats["probed"] = len(behaviors)
        else:
            iso = {}

        fsems = []
        for q, (node, class_q, kind, path) in sorted(index.items()):
            st = statics[q]
            beh = behaviors.get(q)
            toks = name_tokens(node.name)
            cats = beh["categories"] if beh else []
            fsems.append(FunctionSemantics(
                q, path, node.lineno, node.name, toks, asdict(st), beh,
                sorted({m["ref"] for m in beh["exact"]}) if beh else [],
                sorted(refs_named_by(toks, cats)) if beh else []))
        findings = self._findings(fsems, statics, index)
        kinds = defaultdict(int)
        for f in findings:
            kinds[f.kind] += 1
        stats.update({"findings": len(findings), "findings_by_kind": dict(sorted(kinds.items())),
                      "functions_identified": sum(1 for f in fsems if f.inferred),
                      "purity": {p: sum(1 for s in statics.values() if s.purity == p) for p in ("pure", "unknown", "impure")}})
        return SemanticReport(str(base), fsems, findings, stats, diags, iso)

    def _propagate(self, und, statics: dict) -> None:
        adj = defaultdict(set)
        for e in und.call_edges:
            if e.callee and e.caller in statics and e.callee in statics:
                adj[e.caller].add(e.callee)
        trans = {q: set(s.effects) - {"self_mutation"} for q, s in statics.items()}
        unk = {}
        for q, s in statics.items():
            resolved = set()
            for c in adj[q]:
                parts = c.split(".")
                resolved.add(parts[-1])
                if parts[-1] == "__init__" and len(parts) > 1:
                    resolved.add(parts[-2])
            remaining = [u for u in s.unknown_calls if u.split(".")[-1] not in resolved]
            s.resolved_callees = sorted(adj[q])
            s.unknown_calls = sorted(remaining)
            unk[q] = bool(remaining)
        changed = True
        while changed:
            changed = False
            for q in statics:
                for c in adj[q]:
                    if not trans[c] <= trans[q]:
                        trans[q] |= trans[c]
                        changed = True
                    if unk[c] and not unk[q]:
                        unk[q] = True
                        changed = True
        for q, s in statics.items():
            s.transitive_effects = sorted(trans[q])
            s.transitive_unknown = unk[q]
            breaking = (set(s.effects) | trans[q]) & PURITY_BREAKING
            s.purity = "impure" if (breaking or s.mutated_params) else ("unknown" if unk[q] else "pure")

    def _select_targets(self, index, statics, trees, finfo, diags) -> list:
        risky_modules: set = set()
        for mod, tree in trees.items():
            risks = _module_import_risk(tree)
            from .sandbox import DEFAULT_BLOCK
            if set(risks) & DEFAULT_BLOCK:
                risky_modules.add(mod)
                diags.append({"code": "module_not_probed_risky_import", "module": mod,
                              "risks": {c: sorted(t) for c, t in risks.items() if c in DEFAULT_BLOCK}})
        out = []
        for q, (node, class_q, kind, path) in sorted(index.items()):
            if kind != "function" or isinstance(node, ast.AsyncFunctionDef) or node.decorator_list:
                continue
            a = node.args
            if a.vararg or a.kwarg or any(d is None for d in a.kw_defaults) and a.kwonlyargs:
                continue
            params = a.posonlyargs + a.args
            if len(params) > 2 or q not in finfo or finfo[q].module in risky_modules:
                continue
            st = statics[q]
            if not self.probe_effectful and HARD_EFFECTS & (set(st.effects) | set(st.transitive_effects)):
                continue
            if any(isinstance(n, (ast.Yield, ast.YieldFrom)) for n in _walk_own(node)):
                continue
            kinds = [st.param_kinds.get(p.arg, "any") for p in params]
            cats = categories_for(len(params), kinds)
            if cats:
                out.append((q, cats))
        return out

    # --------------------------------------------------------------------- findings
    def _findings(self, fsems: list, statics: dict, index: dict) -> list:
        out: list = []

        def add(f: FunctionSemantics, kind, severity, source, message, **evidence):
            out.append(Finding(kind, f.qname, f.path, f.line, severity, source, message, evidence))

        for f in fsems:
            st, beh, toks = statics[f.qname], f.behavior, f.tokens
            if not toks:
                continue
            verb = toks[0]
            node, class_q, kind, _ = index[f.qname]
            params = [p.arg for p in node.args.posonlyargs + node.args.args]
            effects = set(st.effects) | set(st.transitive_effects)
            dyn_mut = [params[i] for i in (beh["mutates_args"] if beh else []) if i < len(params)]
            mutated = sorted(set(st.mutated_params) | set(dyn_mut))
            dyn_effect = bool(beh and (beh["mutates_args"] or beh["printed"] or beh["files_written"] or beh["globals_changed"]))

            # A: names that promise purity but the code has effects
            if verb in PURE_VERBS:
                high = {"io_write", "process", "env_write"} | ({"network"} if verb not in {"get", "find", "lookup"} else set())
                hit_high = sorted(effects & high)
                if mutated or hit_high:
                    src = "static+dynamic" if (dyn_mut and st.mutated_params) or (beh and beh["files_written"] and hit_high) \
                        else ("dynamic" if dyn_mut and not st.mutated_params else "static")
                    add(f, "name_implies_pure_but_has_effects", "high", src,
                        f"'{f.name}' reads like a pure query but " + ("mutates its argument(s) " + ", ".join(mutated)
                                                                       if mutated else "performs " + ", ".join(hit_high)),
                        mutated_params=mutated, effects=hit_high)
                elif effects & {"global_write", "global_mutation"}:
                    add(f, "name_implies_pure_but_has_effects", "medium",
                        "static+dynamic" if beh and beh["globals_changed"] else "static",
                        f"'{f.name}' reads like a pure query but modifies module-level state",
                        effects=sorted(effects & {"global_write", "global_mutation"}))
                elif effects & {"console", "logging"}:
                    add(f, "name_implies_pure_but_has_effects", "low",
                        "static+dynamic" if beh and beh["printed"] else "static",
                        f"'{f.name}' reads like a pure query but writes to console/log", effects=sorted(effects & {"console", "logging"}))

            # B: predicates that are not boolean
            if verb in PRED_VERBS:
                observed = [t for t, n in (beh["output_types"].items() if beh else [])]
                nonbool = sorted(set(observed) - {"bool"})
                if beh and sum(beh["output_types"].values()) >= 5:
                    if nonbool:
                        add(f, "predicate_not_boolean", "medium",
                            "static+dynamic" if not st.returns["returns_bool"] else "dynamic",
                            f"'{f.name}' is named like a predicate but returns {', '.join(nonbool)}",
                            observed_types=beh["output_types"], static_returns_bool=st.returns["returns_bool"])
                elif not st.returns["returns_bool"]:
                    add(f, "predicate_not_boolean", "medium", "static",
                        f"'{f.name}' is named like a predicate but does not return a boolean on every path",
                        return_kinds=st.returns["kinds"], falls_off_end=st.returns["falls_off_end"])

            # C: mutator names whose bodies have no effect
            first_kind = st.param_kinds.get(params[0], "any") if params else "any"
            container_like = first_kind in {"list", "dict", "sized"}
            returns_nothing = st.returns["n"] == 0 or st.returns["kinds"] == ["none"]
            stub = is_stub(node)  # interface/placeholder bodies say nothing about intent
            if not stub and verb in MUTATOR_VERBS and (verb not in AMBIGUOUS_MUTATOR_VERBS or container_like) \
                    and st.purity == "pure" and not effects and returns_nothing and not dyn_effect and params:
                add(f, "name_implies_effect_but_pure", "medium", "static+dynamic" if beh else "static",
                    f"'{f.name}' is named like a mutator but neither changes anything nor returns anything",
                    return_kinds=st.returns["kinds"])

            # D: validators that cannot fail
            if not stub and verb in VALIDATOR_VERBS and not st.raises and not st.has_assert and not st.unknown_calls \
                    and not effects and not mutated \
                    and not st.transitive_unknown and len(st.returns["constants"]) <= 1 \
                    and (st.returns["n"] == 0 or st.returns["returns_only_constants"]):
                add(f, "validator_cannot_fail", "medium", "static",
                    f"'{f.name}' never raises and always returns the same constant, so it can never reject input",
                    constants=st.returns["constants"])

            if beh:
                exact = {m["ref"] for m in beh["exact"]}
                named = set(f.name_refs)
                near_named = [m for m in beh["near"] if m["ref"] in named]
                # E: behaviour contradicts what the name claims
                if named and exact and not (named & exact):
                    add(f, "name_behavior_mismatch", "high", "dynamic",
                        f"'{f.name}' is named like {', '.join(sorted(named))} but behaves like {', '.join(sorted(exact))} "
                        f"on every probe input", name_suggests=sorted(named), behaves_like=sorted(exact))
                # F: near-miss of the named behaviour = probable bug
                elif named and not (named & exact) and near_named:
                    m = near_named[0]
                    add(f, "likely_bug", "high", "dynamic",
                        f"'{f.name}' agrees with {m['ref']} on {m['score']:.0%} of probe inputs but deviates on others",
                        reference=m["ref"], score=m["score"], deviations=m["deviations"])
                # G: named behaviour claimed but nothing matches
                elif self.weak_findings and named and not exact and not near_named:
                    from_usable = [r for r in REFS if r.name in named and r.cat in beh["usable_categories"]]
                    if from_usable:
                        add(f, "name_claim_unverified", "low", "dynamic",
                            f"'{f.name}' is named like {', '.join(sorted(named))} but matches no reference behaviour closely",
                            name_suggests=sorted(named), usable_categories=beh["usable_categories"])
                # H: static analysis missed what actually happened
                gaps = []
                if beh["mutates_args"] and not st.mutated_params:
                    gaps.append("argument mutated at runtime but not detected statically")
                if beh["printed"] and "console" not in effects:
                    gaps.append("printed output not detected statically")
                if beh["files_written"] and "io_write" not in effects:
                    gaps.append("wrote files not detected statically")
                if beh["globals_changed"] and not effects & {"global_write", "global_mutation"}:
                    gaps.append("module state changed but not detected statically")
                if not beh["deterministic"] and not effects & {"randomness", "time", "env", "io_read", "global_write",
                                                               "global_mutation", "io_unknown"} and not st.unknown_calls:
                    gaps.append("nondeterministic behaviour not explained by static analysis")
                elif not beh["deterministic"] and st.purity == "pure":
                    gaps.append("nondeterministic although statically pure")
                if gaps:
                    add(f, "static_dynamic_disagreement", "medium", "static+dynamic",
                        f"'{f.name}': " + "; ".join(gaps), gaps=gaps)
        out.sort(key=lambda x: (_SEVERITY[x.severity], x.path, x.line, x.kind))
        return out
