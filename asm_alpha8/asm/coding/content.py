"""DEV18 content solver: the CONTENT of a repair, taken from the problem itself.

DEV17 found that the shape of a fix transfers between projects but its content (the exact string, name or value) does
not: it has to come from the problem being solved. `ProblemContext` gathers that content, and the filler functions
turn it into ranked candidate values for a typed hole in a learned shape (asm.coding.shapes).

Sources, in the order they are trusted:
  1. the tests that fail (or, for mined history, the test files changed by the fix): their string and number literals,
     and quoted text in failure messages: what the program is EXPECTED to produce;
  2. the module being repaired: its other string constants, names, attributes, and the exceptions it raises/catches;
  3. learned character-level string edits (`StringVocabulary`), from verified real fixes (e.g. `+` -> `*` in a regex).
Every filler carries the operator that produced it, so results can be attributed per source.

String operators (`string_fillers(old, ctx, vocab)`):
  EXTEND   `old` occurs inside a test literal: grow it within that literal to the next word/punctuation boundaries
           (`'push --force'` + test literal `'git push --force-with-lease'` -> `'push --force-with-lease'`)
  VOCAB    apply a learned segment edit at each place its old segment occurs in `old` (or a learned insertion between
           its learned neighbouring characters)
  TEST     a test literal similar to `old` (difflib ratio >= 0.6) replaces it
  MODULE   another constant of the same module similar to `old` replaces it
No language model is involved; nothing here decides acceptance (the tests do). DEV32: `copied_test_strings` finds a
patch that hard-codes the failing tests' data, for the repair workflow's opt-in test_copy_guard.
"""
from __future__ import annotations

import ast
import builtins
import difflib
import functools
import re
from dataclasses import dataclass, field

MAX_LITERALS = 2000
MAX_STR = 300
SIMILARITY = 0.6
COMMON_EXCEPTIONS = ["ValueError", "TypeError", "KeyError", "IndexError", "AttributeError", "StopIteration",
                     "ZeroDivisionError", "OSError", "RuntimeError", "UnicodeDecodeError", "ImportError", "NotImplementedError"]
COMMON_BUILTINS = ["len", "str", "int", "isinstance", "list", "dict", "tuple", "set", "bool", "None", "True", "False",
                   "getattr", "hasattr", "repr", "type", "min", "max", "sorted", "iter", "next", "any", "all"]
_QUOTED = re.compile(r"'([^'\n]{1,200})'|\"([^\"\n]{1,200})\"")
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def literals(source: str, function_names=None) -> tuple:
    """(strings, numbers) appearing in `source`; restricted to the given test functions (and their classes) when names
    are given and found. Docstrings excluded."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return [], []
    roots = [tree]
    if function_names:
        wanted = set(function_names)
        found = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                 and n.name in wanted]
        if found:
            roots = found
    docs = {id(n.body[0].value) for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)) and n.body
            and isinstance(n.body[0], ast.Expr) and isinstance(getattr(n.body[0], "value", None), ast.Constant)}
    strs, nums = [], []
    for r in roots:
        for n in ast.walk(r):
            if isinstance(n, ast.Constant) and id(n) not in docs:
                if isinstance(n.value, str) and 0 < len(n.value) <= MAX_STR:
                    strs.append(n.value)
                elif isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
                    nums.append(n.value)
    return _uniq(strs)[:MAX_LITERALS], _uniq(nums)[:200]


def _uniq(xs):
    seen, out = set(), []
    for x in xs:
        k = (type(x).__name__, x)
        if k not in seen:
            seen.add(k)
            out.append(x)
    return out


@dataclass
class ProblemContext:
    test_strings: list = field(default_factory=list)
    test_numbers: list = field(default_factory=list)
    module_strings: list = field(default_factory=list)
    module_names: list = field(default_factory=list)
    attributes: list = field(default_factory=list)
    exceptions: list = field(default_factory=list)

    @classmethod
    def build(cls, module_source: str, test_sources=(), test_function_names=None, failure_texts=()) -> "ProblemContext":
        ts, tn = [], []
        for src in test_sources:
            s, n = literals(src, test_function_names)
            ts += s
            tn += n
        for text in failure_texts:
            for m in _QUOTED.finditer(text or ""):
                ts.append(m.group(1) or m.group(2))
        ms, _ = literals(module_source)
        names, attrs, excs = [], [], []
        try:
            tree = ast.parse(module_source)
        except SyntaxError:
            tree = ast.Module(body=[], type_ignores=[])
        for n in tree.body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.append(n.name)
            elif isinstance(n, (ast.Assign, ast.AnnAssign)):
                for t in (n.targets if isinstance(n, ast.Assign) else [n.target]):
                    if isinstance(t, ast.Name):
                        names.append(t.id)
            elif isinstance(n, (ast.Import, ast.ImportFrom)):
                names += [(a.asname or a.name).split(".")[0] for a in n.names]
        for n in ast.walk(tree):
            if isinstance(n, ast.Attribute):
                attrs.append(n.attr)
            elif isinstance(n, ast.Raise) and n.exc is not None:
                e = n.exc.func if isinstance(n.exc, ast.Call) else n.exc
                if isinstance(e, ast.Name):
                    excs.append(e.id)
            elif isinstance(n, ast.ExceptHandler) and isinstance(n.type, ast.Name):
                excs.append(n.type.id)
        for text in failure_texts:
            for m in re.finditer(r"\b([A-Z]\w*(?:Error|Exception|Warning|Iteration))\b", text or ""):
                excs.insert(0, m.group(1))
        return cls(_uniq(ts), _uniq(tn), _uniq(ms), _uniq(names), _uniq(attrs), _uniq(excs))

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in ("test_strings", "test_numbers", "module_strings", "module_names",
                                               "attributes", "exceptions")}

    @classmethod
    def from_dict(cls, d) -> "ProblemContext":
        return cls(**{k: list(d.get(k, [])) for k in ("test_strings", "test_numbers", "module_strings", "module_names",
                                                       "attributes", "exceptions")})


class StringVocabulary:
    """Character-level string edits learned from real fixes: (old segment, new segment, left char, right char) with
    counts. Context-free use (VOCAB) applies the segment edit wherever the old segment occurs; insertions (empty old
    segment) are applied only between their learned neighbouring characters."""

    def __init__(self):
        self.edits: dict = {}

    def add(self, old_seg: str, new_seg: str, left: str, right: str) -> None:
        k = (old_seg, new_seg, left[-1:] if not old_seg else "", right[:1] if not old_seg else "")
        self.edits[k] = self.edits.get(k, 0) + 1

    def ranked(self) -> list:
        return sorted(self.edits.items(), key=lambda kv: (-kv[1], kv[0]))

    def to_dict(self) -> dict:
        return {"edits": [[list(k), v] for k, v in self.ranked()]}

    @classmethod
    def from_dict(cls, d) -> "StringVocabulary":
        v = cls()
        for k, c in d["edits"]:
            v.edits[tuple(k)] = c
        return v


_TOKEN = re.compile(r"\s+|\w+|[^\w\s]")


def _extensions(t: str, i: int, j: int, limit: int = 4) -> list:
    """Substrings t[a:b] that contain t[i:j] and grow it by up to `limit` whole tokens (word runs, whitespace runs,
    single punctuation characters) on each side, best first: clean edges (string edge or whitespace) before ragged
    ones, then fewer added tokens."""
    starts = sorted({m.start() for m in _TOKEN.finditer(t)} | {0, len(t)})
    ends = sorted({m.end() for m in _TOKEN.finditer(t)} | {0, len(t)})
    lefts = [i] + [k for k in reversed(starts) if k < i][:limit]
    rights = [j] + [k for k in ends if k > j][:limit]
    out = []
    for la, a in enumerate(lefts):
        for rb, b in enumerate(rights):
            if (a, b) == (i, j):
                continue
            clean = int(a == 0 or t[a - 1].isspace() or a == i) + int(b == len(t) or t[b].isspace() or b == j)
            out.append((-clean, la + rb, a, b))
    return [(a, b) for _, _, a, b in sorted(out)]


def string_fillers(old: str, ctx: ProblemContext, vocab: StringVocabulary | None, limit: int = 12) -> list:
    """[(new_string, operator)] for a string hole whose matched original value is `old`, best first."""
    out, seen = [], {old}

    def add(v, op):
        if isinstance(v, str) and v not in seen and len(v) <= MAX_STR:
            seen.add(v)
            out.append((v, op))
    if len(old) >= 2:
        for t in ctx.test_strings:
            i = t.find(old)
            if i < 0 or t == old:
                continue
            for a, b in _extensions(t, i, i + len(old)):
                add(t[a:b], "extend")
    if vocab is not None:
        for (oseg, nseg, left, right), _ in vocab.ranked():
            if oseg:
                k = old.find(oseg)
                hits = 0
                while k >= 0 and hits < 3:
                    add(old[:k] + nseg + old[k + len(oseg):], "vocab")
                    hits += 1
                    k = old.find(oseg, k + 1)
            elif left or right:
                for k in range(len(old) + 1):
                    if (not left or (k > 0 and old[k - 1] == left)) and (not right or (k < len(old) and old[k] == right)):
                        add(old[:k] + nseg + old[k:], "vocab")
    for t in _similar_strings(old, tuple(ctx.test_strings)):
        add(t, "test")
    for t in _similar_strings(old, tuple(ctx.module_strings)):
        add(t, "module")
    order = {"extend": 0, "test": 1, "vocab": 2, "module": 3}
    out.sort(key=lambda x: order[x[1]])  # stable within an operator
    return out[:limit]


@functools.lru_cache(maxsize=4096)
def _similar_strings(old: str, strings: tuple) -> list:
    """The strings at least SIMILARITY like `old` (and at most 3x+10 as long), most similar first. DEV31 (performance;
    same results): difflib's real_quick_ratio and quick_ratio bound ratio from above, so strings they rule out could
    never reach SIMILARITY (as in difflib.get_close_matches)."""
    sims = []
    for t in strings:
        if t != old and len(t) <= 3 * len(old) + 10:
            m = difflib.SequenceMatcher(None, old, t, autojunk=False)
            if m.real_quick_ratio() >= SIMILARITY and m.quick_ratio() >= SIMILARITY and m.ratio() >= SIMILARITY:
                sims.append((m.ratio(), t))
    return [t for _, t in sorted(sims, key=lambda x: (-x[0], x[1]))]


def _similar_first(names: list, old) -> list:
    if not isinstance(old, str):
        return names
    return _similar_sorted(tuple(names), old)


@functools.lru_cache(maxsize=4096)
def _similar_sorted(names: tuple, old: str) -> tuple:
    """DEV31 (performance; same results): every hole of every learned step re-sorted the module's names."""
    return tuple(sorted(names, key=lambda n: (-difflib.SequenceMatcher(None, n, old, autojunk=False).ratio(), n)))


def name_fillers(old, scope: list, ctx: ProblemContext, limit: int = 10) -> list:
    """[(identifier, operator)] for a name hole: names in scope (similar to the old name first), then module names,
    then common builtins."""
    out, seen = [], {old}
    for group, op in ((_similar_first(scope, old), "scope"), (_similar_first(ctx.module_names, old), "module"),
                      (COMMON_BUILTINS, "builtin")):
        for n in group:
            if n not in seen and _IDENT.match(n):
                seen.add(n)
                out.append((n, op))
    return out[:limit]


def attr_fillers(old, ctx: ProblemContext, limit: int = 10) -> list:
    out, seen = [], {old}
    idents = [s for s in ctx.test_strings if _IDENT.match(s)]
    for group, op in ((_similar_first(ctx.attributes, old), "module"), (_similar_first(idents, old), "test")):
        for n in group:
            if n not in seen:
                seen.add(n)
                out.append((n, op))
    return out[:limit]


def exception_fillers(old, ctx: ProblemContext, limit: int = 6) -> list:
    out, seen = [], {old}
    for group, op in ((ctx.exceptions, "problem"), (COMMON_EXCEPTIONS, "builtin")):
        for n in group:
            obj = getattr(builtins, n, None)
            known = isinstance(obj, type) and issubclass(obj, BaseException)
            if n not in seen and (known or op == "problem") and _IDENT.match(n):
                seen.add(n)
                out.append((n, op))
    return out[:limit]


def number_fillers(old, ctx: ProblemContext, limit: int = 8) -> list:
    out, seen = [], {old}
    base = [old - 1, old + 1] if isinstance(old, int) and not isinstance(old, bool) else []
    for group, op in ((base, "neighbour"), (ctx.test_numbers, "test"), ([0, 1, -1, 2], "small")):
        for n in group:
            if n not in seen and isinstance(n, (int, float)) and not isinstance(n, bool):
                seen.add(n)
                out.append((n, op))
    return out[:limit]


def scope_names(function_source: str) -> list:
    """Parameters and locally bound names of the (first) function in `function_source`."""
    try:
        tree = ast.parse(function_source)
    except SyntaxError:
        return []
    fn = next((n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))), None)
    if fn is None:
        return []
    a = fn.args
    names = [x.arg for x in a.posonlyargs + a.args + a.kwonlyargs] + [x.arg for x in (a.vararg, a.kwarg) if x]
    for n in ast.walk(fn):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
            names.append(n.id)
    return _uniq(names)


MESSAGE_CALLS = {"warn", "warning", "error", "info", "debug", "critical", "exception", "log", "fail"}
_NAME_LIKE = re.compile(r"^-*[A-Za-z_][A-Za-z0-9_-]*$")  # names, keys, options, encodings: `zero`, `--force`, `utf-8`


@functools.lru_cache(maxsize=8)
def _module_strings(source: str) -> frozenset:
    try:
        return frozenset(n.value for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Constant) and isinstance(n.value, str))
    except SyntaxError:
        return frozenset()


def _message_nodes(tree) -> set:
    """ids of the nodes inside error and warning messages: what a `raise` raises, and the arguments of calls to exception
    or warning classes and to warn/log/fail functions."""
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Raise) and n.exc is not None:
            out |= {id(x) for x in ast.walk(n.exc)}
        elif isinstance(n, ast.Call):
            f = n.func
            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
            if name in MESSAGE_CALLS or name.endswith(("Error", "Exception", "Warning")):
                out |= {id(x) for a in n.args + [k.value for k in n.keywords] for x in ast.walk(a)}
    return out


def copied_test_strings(original: str, patched: str, ctx: ProblemContext) -> list:
    """DEV32 guard: the strings a patch writes into the code that are whole literals of the failing tests (or quoted in
    their failure messages) and not already in the module: the test's data hard-coded as the answer (DEV31: `return None`
    became `return 'rtmp://foo.de'`). Allowed: name-like strings (keys, keywords, options, encodings) and error or
    warning messages, which correct fixes copy from their tests."""
    tests = {t for t in ctx.test_strings if not _NAME_LIKE.match(t)} - _module_strings(original)
    if not tests:
        return []
    try:
        tree = ast.parse(patched)
    except SyntaxError:
        return []
    skip = _message_nodes(tree)
    return sorted({n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)
                   and n.value in tests and id(n) not in skip})
