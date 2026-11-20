"""DEV15 repair operators beyond DEV14's single-site templates.

Why: on 83 real BugsInPy bugs DEV14 accepted a patch for 2. Developer fixes average 3.2 changed lines and the most
common small shapes in that corpus are (from reading the 60 fixes of <= 3 lines):
  - a variable used in place of another one in scope       (PySnooper-3 `output_path` -> `output`, tqdm-8 `l_bar`)
  - an early-return guard at function entry                 (youtube-dl-17 `if param is None: return []`)
  - a statement wrapped in a condition                      (tqdm-4 `if total: total *= unit_scale`)
  - a statement wrapped in try/except for the raised error  (thefuck-9 `except IndexError: pass`)
  - an attribute read made tolerant of absence              (tqdm-6 `self.total` -> `getattr(self, "total", None)`)
  - a clause removed from a boolean condition               (thefuck-15: the developer removed condition B)
  - two coordinated edits in one function
This module generates candidates of those shapes. It does NOT generate string/regex edits, new calls, or arbitrary
code: most remaining real fixes need those, and no code-generating model is used.

Families (each candidate's `reason` starts with its family, so dossiers and benchmarks can count them):
  SITE-BASED (byte-range edits, combinable into pairs): name, drop_clause, getattr
  INSERTIONS (statement-level, not combined):           guard_return, guard_stmt, try_except
  PAIRS: two non-overlapping site-based edits in the same function, from the most suspicious lines.

Deliberately NOT included: deleting a statement. Statement deletion is the classic generator of test-overfitting
patches (it "fixes" a test by removing the behaviour the test exercises), and DEV14 already showed that accepted
patches on real bugs were wrong more often than right.

Ordering (used by faultloc.generate_candidates): most suspicious line first; on a line, DEV14 templates before DEV15
families; all single edits before any pair. Faults DEV14 could repair are therefore tried in the same relative order.
"""
from __future__ import annotations

import ast
import builtins
import re
from dataclasses import dataclass

# Sites from these families are plain byte-range replacements (faultloc.Site); they combine into pairs.
SITE_FAMILIES = ("name", "drop_clause", "getattr")
INSERT_FAMILIES = ("guard_return", "guard_stmt", "try_except")
FAMILY_PRIORITY = {"name": 0, "drop_clause": 1, "getattr": 2, "guard_stmt": 3, "try_except": 4, "guard_return": 5}
MAX_NAME_OPTIONS = 3
MAX_GUARD_PARAMS = 4
MAX_PAIR_SITES = 10
MAX_PAIRS = 36
_ALWAYS_SKIP_NAMES = {"self", "cls", "True", "False", "None"}


@dataclass
class Insertion:
    """A statement-level edit: replace source lines [start_line, end_line] (1-based, inclusive) with `text`."""
    path: str
    start_line: int
    end_line: int
    text: str
    kind: str
    function: str
    anchor_line: int  # the line whose suspiciousness orders this candidate
    note: str

    def describe(self) -> str:
        return f"{self.kind}: {self.note} at line {self.anchor_line}"


def _function_nodes(tree):
    return [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


def _innermost(tree, ranges: list, qname: str):
    """The AST node of `qname` (matched by its line range from DEV9's understanding)."""
    span = next(((a, b) for q, a, b in ranges if q == qname), None)
    if span is None:
        return None
    for n in _function_nodes(tree):
        first = min([n.lineno] + [d.lineno for d in n.decorator_list])
        if first == span[0] or n.lineno == span[0]:
            return n
    return None


def _own_nodes(fn):
    """Nodes of fn's body, excluding nested function/class bodies (their names live in another scope)."""
    out, stack = [], list(fn.body)
    while stack:
        n = stack.pop()
        out.append(n)
        for c in ast.iter_child_nodes(n):
            if isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                continue
            stack.append(c)
    return out


def _params(fn) -> list:
    a = fn.args
    return [x.arg for x in a.posonlyargs + a.args + a.kwonlyargs] + \
        [x.arg for x in (a.vararg, a.kwarg) if x is not None]


def _bound_names(fn) -> dict:
    """name -> first line it is bound in fn (parameters bind at the def line)."""
    bound = {p: fn.lineno for p in _params(fn)}
    for n in _own_nodes(fn):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
            bound[n.id] = min(bound.get(n.id, n.lineno), n.lineno)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for al in n.names:
                nm = (al.asname or al.name).split(".")[0]
                bound[nm] = min(bound.get(nm, n.lineno), n.lineno)
        elif isinstance(n, ast.ExceptHandler) and n.name:
            bound[n.name] = min(bound.get(n.name, n.lineno), n.lineno)
    return bound


def site_edits(source: str, path: str, ranges: list, qname: str, starts: list) -> list:
    """Site-based DEV15 edits in one function, as faultloc.Site objects (imported lazily to avoid a cycle)."""
    from .faultloc import Site
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []
    fn = _innermost(tree, ranges, qname)
    if fn is None:
        return []
    src = source.encode("utf-8")

    def off(line, col):
        return starts[line - 1] + col

    def seg(n) -> str:
        return src[off(n.lineno, n.col_offset):off(n.end_lineno, n.end_col_offset)].decode("utf-8")

    sites = []
    bound = _bound_names(fn)
    own = _own_nodes(fn)
    call_funcs = {id(n.func) for n in own if isinstance(n, ast.Call)}  # `obj.method(...)`: getattr(..., None)() is no fix
    for n in own:
        # NAME: a local/parameter read replaced by another local/parameter already bound at that point
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id in bound and n.id not in _ALWAYS_SKIP_NAMES:
            others = sorted((nm for nm, ln in bound.items() if nm != n.id and ln < n.lineno and nm not in _ALWAYS_SKIP_NAMES),
                            key=lambda nm: (-_similarity(nm, n.id), nm))[:MAX_NAME_OPTIONS]
            if others:
                lo = off(n.lineno, n.col_offset)
                sites.append(Site(path, n.lineno, lo, lo + len(n.id.encode()), "name", n.id, others, qname,
                                  n.col_offset))
        # DROP_CLAUSE: one operand of an and/or removed
        elif isinstance(n, ast.BoolOp) and len(n.values) >= 2 and not (
                n.end_lineno != n.lineno and ('"""' in seg(n) or "'''" in seg(n))):  # flattening would alter a string
            op = " and " if isinstance(n.op, ast.And) else " or "
            parts = []
            for v in n.values:
                t = seg(v)
                if "\n" in t:
                    t = " ".join(x.strip() for x in t.splitlines())
                parts.append(f"({t})" if isinstance(v, (ast.BoolOp, ast.IfExp, ast.Lambda, ast.NamedExpr)) else t)
            opts = [op.join(parts[:i] + parts[i + 1:]) for i in range(len(parts))]
            lo, hi = off(n.lineno, n.col_offset), off(n.end_lineno, n.end_col_offset)
            sites.append(Site(path, n.lineno, lo, hi, "drop_clause", seg(n).replace("\n", " ")[:40], opts, qname,
                              n.col_offset))
        # GETATTR: obj.attr read made tolerant of a missing attribute
        elif isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Load) and isinstance(n.value, ast.Name) \
                and id(n) not in call_funcs \
                and not n.attr.startswith("__") and n.lineno == n.end_lineno:
            lo, hi = off(n.lineno, n.col_offset), off(n.end_lineno, n.end_col_offset)
            sites.append(Site(path, n.lineno, lo, hi, "getattr", seg(n),
                              [f"getattr({n.value.id}, {n.attr!r}, None)"], qname, n.col_offset))
    return sites


def _similarity(a: str, b: str) -> int:
    """Shared prefix/suffix length: `output_path` vs `output`, `l_bar` vs `l_bar_user` rank first."""
    p = 0
    while p < min(len(a), len(b)) and a[p] == b[p]:
        p += 1
    s = 0
    while s < min(len(a), len(b)) - p and a[-1 - s] == b[-1 - s]:
        s += 1
    return p + s


def _simple_statements(fn, lines: list):
    """Statements of fn's own body that occupy whole lines (nothing else shares their lines)."""
    out = []
    for n in _own_nodes(fn):
        if not isinstance(n, (ast.Assign, ast.AugAssign, ast.AnnAssign, ast.Expr, ast.Return)):
            continue
        first, last = lines[n.lineno - 1], lines[n.end_lineno - 1]
        if first[:n.col_offset].strip() or last[n.end_col_offset:].strip().split("#")[0].strip().rstrip(";"):
            continue
        if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant):
            continue  # docstrings and bare literals
        out.append(n)
    return out


def _indent_block(lines: list, a: int, b: int, extra: str) -> list:
    return [(extra + ln if ln.strip() else ln) for ln in lines[a - 1:b]]


def _exception_names(failure_texts) -> list:
    names = []
    for text in failure_texts:
        for m in re.finditer(r"\b([A-Z]\w*(?:Error|Exception))\b", text or ""):
            nm = m.group(1)
            obj = getattr(builtins, nm, None)
            if isinstance(obj, type) and issubclass(obj, Exception) and nm not in names and nm != "AssertionError":
                names.append(nm)
    return names[:3]


def _default_returns(fn) -> list:
    """Return values for a guard: None, plus literal values this function already returns elsewhere."""
    vals = ["None"]
    for n in _own_nodes(fn):
        if isinstance(n, ast.Return) and n.value is not None:
            v = n.value
            if isinstance(v, ast.Constant) and isinstance(v.value, (bool, int, str)) and len(repr(v.value)) <= 12:
                vals.append(repr(v.value))
            elif isinstance(v, (ast.List, ast.Tuple, ast.Dict)) and not getattr(v, "elts", getattr(v, "keys", None)):
                vals.append({ast.List: "[]", ast.Tuple: "()", ast.Dict: "{}"}[type(v)])
    if "[]" not in vals:
        vals.append("[]")
    out = []
    for v in vals:
        if v not in out:
            out.append(v)
    return out[:4]


def insertion_edits(source: str, path: str, ranges: list, qname: str, line_scores: dict, failure_texts=()) -> list:
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []
    fn = _innermost(tree, ranges, qname)
    if fn is None or not fn.body:
        return []
    lines = source.splitlines(keepends=True)
    out = []
    # GUARD_RETURN at function entry (after a docstring)
    body0 = fn.body[1] if (len(fn.body) > 1 and isinstance(fn.body[0], ast.Expr)
                           and isinstance(fn.body[0].value, ast.Constant) and isinstance(fn.body[0].value.value, str)) else fn.body[0]
    if lines[body0.lineno - 1][:body0.col_offset].strip() == "":
        ind = lines[body0.lineno - 1][:body0.col_offset]
        params = [p for p in _params(fn) if p not in _ALWAYS_SKIP_NAMES][:MAX_GUARD_PARAMS]
        for p in params:
            for d in _default_returns(fn):
                guard = f"{ind}if {p} is None:\n{ind}    return {d}\n"
                out.append(Insertion(path, body0.lineno, body0.lineno - 1, guard, "guard_return", qname, fn.lineno,
                                     f"if {p} is None: return {d}"))
    # GUARD_STMT / TRY_EXCEPT around one simple statement on an executed line
    scores = line_scores or {}
    excs = _exception_names(failure_texts)
    for st in _simple_statements(fn, lines):
        if scores.get(st.lineno, 0.0) <= 0.0:
            continue
        ind = lines[st.lineno - 1][:st.col_offset]
        block = _indent_block(lines, st.lineno, st.end_lineno, "    ")
        if not block[-1].endswith("\n"):
            block[-1] += "\n"
        names = []
        for n in ast.walk(st):
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id not in names \
                    and n.id not in _ALWAYS_SKIP_NAMES and not hasattr(builtins, n.id):
                names.append(n.id)
        if isinstance(st, ast.AugAssign) and isinstance(st.target, ast.Name) and st.target.id not in names:
            names.insert(0, st.target.id)
        for nm in names[:3]:
            for cond in (nm, f"{nm} is not None"):
                out.append(Insertion(path, st.lineno, st.end_lineno, f"{ind}if {cond}:\n" + "".join(block), "guard_stmt",
                                     qname, st.lineno, f"wrap in `if {cond}:`"))
        for e in excs:
            out.append(Insertion(path, st.lineno, st.end_lineno,
                                 f"{ind}try:\n" + "".join(block) + f"{ind}except {e}:\n{ind}    pass\n", "try_except",
                                 qname, st.lineno, f"wrap in `try/except {e}: pass`"))
    return out


def apply_insertion(source: str, ins: Insertion) -> str:
    lines = source.splitlines(keepends=True)
    return "".join(lines[:ins.start_line - 1]) + ins.text + "".join(lines[ins.end_line:])


def apply_pair(source: str, a, opt_a: str, b, opt_b: str) -> str | None:
    """Two byte-range edits; None if they overlap."""
    if not (a.end <= b.start or b.end <= a.start):
        return None
    src = source.encode("utf-8")
    for s, o in sorted([(a, opt_a), (b, opt_b)], key=lambda x: -x[0].start):
        src = src[:s.start] + o.encode("utf-8") + src[s.end:]
    return src.decode("utf-8")


def family_of(reason: str) -> str:
    """Edit family from a candidate description ('pair' / DEV15 families / 'single_site' for DEV14 templates)."""
    head = (reason or "").split(":", 1)[0].strip()
    if head == "pair":
        return "pair"
    if head in SITE_FAMILIES or head in INSERT_FAMILIES:
        return head
    return "single_site"
