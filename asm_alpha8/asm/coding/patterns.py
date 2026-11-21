"""DEV16 fix-pattern library: abstract edit shapes mined from verified (buggy, fixed) pairs.

`edit_signature(buggy, fixed)` compares two versions of a function's source structurally and returns the abstract
changes, e.g. `Compare.Lt->Compare.LtE`, `Name->Name`, `wrap:Try(IndexError)`, `insert:If+Return`. Names are abstracted
(only their role is kept) and constants keep only their type, so a pattern learned in one project applies in another.

`PatternLibrary` counts signatures over a dataset and answers two questions:
- which edit shapes real fixes use, and how often (a data-driven prior over repair families);
- COVERAGE: for each pair, can ASM's repair space produce the fix at all (`in_repair_space`)? This is the ceiling on
  what any ranking can achieve, and tells which families are worth building next.
No language model is involved here: the library is built from pairs that were verified by running the tests.
"""
from __future__ import annotations

import ast
import json
from collections import Counter

_OPS = (ast.cmpop, ast.operator, ast.boolop, ast.unaryop)


def _abstract(n) -> str:
    if n is None:
        return "None"
    if isinstance(n, ast.Name):
        return "Name"
    if isinstance(n, ast.Constant):
        return f"Const.{type(n.value).__name__}"
    if isinstance(n, ast.Compare):
        return "Compare." + ".".join(type(o).__name__ for o in n.ops)
    if isinstance(n, ast.BinOp):
        return f"BinOp.{type(n.op).__name__}"
    if isinstance(n, ast.BoolOp):
        return f"BoolOp.{type(n.op).__name__}{len(n.values)}"
    if isinstance(n, ast.UnaryOp):
        return f"UnaryOp.{type(n.op).__name__}"
    if isinstance(n, ast.Attribute):
        return "Attr"
    if isinstance(n, ast.Call):
        f = n.func
        return "Call." + (f.id if isinstance(f, ast.Name) and f.id in _BUILTIN_CALLS else "f")
    if isinstance(n, _OPS):
        return type(n).__name__
    return type(n).__name__


_BUILTIN_CALLS = {"len", "isinstance", "getattr", "hasattr", "str", "int", "float", "list", "dict", "set", "tuple",
                  "min", "max", "sorted", "range", "enumerate", "zip", "bool", "repr", "abs", "any", "all", "open"}


def _handler_names(t: ast.Try) -> str:
    out = []
    for h in t.handlers:
        if h.type is None:
            out.append("bare")
        elif isinstance(h.type, ast.Name):
            out.append(h.type.id)
        else:
            out.append(_abstract(h.type))
    return ",".join(out)


def _stmt_sig(s) -> str:
    if isinstance(s, ast.Try):
        return f"Try({_handler_names(s)})"
    if isinstance(s, ast.If):
        inner = "+".join(type(x).__name__ for x in s.body[:2])
        return f"If[{inner}]"
    return type(s).__name__


def _op_dump(x) -> str:
    return "|".join(type(o).__name__ for o in x) if isinstance(x, list) else type(x).__name__


def _same(a, b) -> bool:
    return ast.dump(a) == ast.dump(b)


def _diff(a, b, out: list, depth: int = 0) -> None:
    if depth > 40:
        out.append("deep")
        return
    if type(a) is not type(b):
        out.append(f"{_abstract(a)}->{_abstract(b)}")
        return
    if isinstance(a, ast.AST):
        if isinstance(a, ast.Name) and a.id != b.id:
            out.append("Name->Name")
            return
        if isinstance(a, ast.Constant) and a.value != b.value:
            out.append(f"{_abstract(a)}->{_abstract(b)}")
            return
        if isinstance(a, ast.Attribute) and a.attr != b.attr:
            out.append("Attr.name")
        skip = set()
        op_field = {ast.Compare: "ops", ast.BinOp: "op", ast.BoolOp: "op", ast.UnaryOp: "op"}.get(type(a))
        if op_field and _op_dump(getattr(a, op_field)) != _op_dump(getattr(b, op_field)):
            out.append(f"{_abstract(a)}->{_abstract(b)}")  # operator change, named by the expression it belongs to
            skip.add(op_field)
        for name in a._fields:
            if name in skip:
                continue
            va, vb = getattr(a, name, None), getattr(b, name, None)
            if isinstance(va, list) and isinstance(vb, list):
                _diff_list(va, vb, out, depth + 1)
            elif isinstance(va, ast.AST) or isinstance(vb, ast.AST):
                if va is None or vb is None:
                    out.append(f"{_abstract(va)}->{_abstract(vb)}")
                elif not _same(va, vb):
                    if isinstance(va, _OPS) or isinstance(vb, _OPS):
                        out.append(f"{_abstract(a)}->{_abstract(b)}")
                    else:
                        _diff(va, vb, out, depth + 1)
            elif va != vb and name not in ("lineno", "col_offset", "end_lineno", "end_col_offset", "ctx", "type_comment"):
                out.append(f"{type(a).__name__}.{name}")


def _diff_list(la, lb, out, depth) -> None:
    if len(la) == len(lb):
        for x, y in zip(la, lb):
            if isinstance(x, ast.AST) and isinstance(y, ast.AST):
                if _same(x, y):
                    continue
                if isinstance(x, ast.stmt) and isinstance(y, (ast.If, ast.Try)) and len(y.body) == 1 and _same(y.body[0], x):
                    out.append(f"wrap:{_stmt_sig(y)}")  # one statement wrapped in place (list length unchanged)
                else:
                    _diff(x, y, out, depth)
            elif x != y:
                out.append("value")
        return
    # different lengths: statements or arguments inserted / removed / wrapped
    da, db = [ast.dump(x) if isinstance(x, ast.AST) else repr(x) for x in la], \
        [ast.dump(x) if isinstance(x, ast.AST) else repr(x) for x in lb]
    i = 0
    while i < min(len(da), len(db)) and da[i] == db[i]:
        i += 1
    j = 0
    while j < min(len(da), len(db)) - i and da[-1 - j] == db[-1 - j]:
        j += 1
    removed, added = la[i:len(la) - j], lb[i:len(lb) - j]
    # wrap: one removed statement reappears inside an added If / Try
    if len(added) == 1 and isinstance(added[0], (ast.If, ast.Try)) and removed:
        body = added[0].body
        if [ast.dump(x) for x in body] == [ast.dump(x) for x in removed]:
            out.append(f"wrap:{_stmt_sig(added[0])}")
            return
    for x in removed:
        out.append(f"delete:{_stmt_sig(x) if isinstance(x, ast.stmt) else _abstract(x)}")
    for x in added:
        out.append(f"insert:{_stmt_sig(x) if isinstance(x, ast.stmt) else _abstract(x)}")


def edit_signature(buggy: str, fixed: str) -> list:
    """Abstract changes turning `buggy` into `fixed` (both: source of one function, or of a whole module)."""
    try:
        a, b = ast.parse(buggy), ast.parse(fixed)
    except SyntaxError:
        return ["unparsable"]
    out: list = []
    _diff(a, b, out)
    return out


def signature_key(sig: list) -> str:
    return " & ".join(sorted(sig)) if sig else "none"


class PatternLibrary:
    """Counts of fix signatures, plus per-pair coverage records."""

    def __init__(self):
        self.signatures: Counter = Counter()
        self.atoms: Counter = Counter()
        self.coverage: list = []  # {"id", "key", "in_repair_space", "family"}

    def add(self, pair_id: str, buggy_fn: str, fixed_fn: str, in_repair_space: bool | None = None,
            family: str | None = None) -> str:
        sig = edit_signature(buggy_fn, fixed_fn)
        key = signature_key(sig)
        self.signatures[key] += 1
        self.atoms.update(set(sig))
        self.coverage.append({"id": pair_id, "key": key, "atoms": len(sig), "in_repair_space": in_repair_space,
                              "family": family})
        return key

    def report(self, top: int = 25) -> dict:
        known = [c for c in self.coverage if c["in_repair_space"] is not None]
        fam = Counter(c["family"] for c in known if c["in_repair_space"])
        return {"pairs": len(self.coverage), "distinct_signatures": len(self.signatures),
                "top_signatures": self.signatures.most_common(top), "top_atoms": self.atoms.most_common(top),
                "single_atom_fixes": sum(1 for c in self.coverage if c["atoms"] == 1),
                "in_repair_space": sum(1 for c in known if c["in_repair_space"]), "coverage_checked": len(known),
                "reachable_by_family": dict(fam.most_common()),
                "unreachable_top_signatures": Counter(c["key"] for c in known if not c["in_repair_space"]).most_common(top)}

    def to_json(self) -> str:
        return json.dumps({"signatures": dict(self.signatures), "atoms": dict(self.atoms), "coverage": self.coverage},
                          sort_keys=True)


def in_repair_space(buggy_source: str, fixed_source: str, path: str, qname: str, ranges: list) -> tuple:
    """Can ASM's candidate generation (DEV14 + DEV15 families, every line treated as suspicious) produce a program
    AST-equal to `fixed_source` from `buggy_source`? Returns (bool, family or None, position or None). No tests run."""
    from .faultloc import Suspect, ast_normal, generate_candidates
    from .repair_ops import family_of
    span = next(((a, b) for q, a, b in ranges if q == qname), None)
    if span is None:
        return False, None, None
    target = ast_normal(fixed_source)
    scores = {path: {ln: 1.0 for ln in range(span[0], span[1] + 1)}}
    sus = Suspect(qname, path, span[0], span[1], 1.0, {}, [])
    for k, c in enumerate(generate_candidates(buggy_source, path, sus, ranges, scores, extended=True,
                                              failure_texts=["IndexError KeyError TypeError ValueError AttributeError "
                                                             "ZeroDivisionError StopIteration"])):
        if ast_normal(c.replacement) == target:
            return True, family_of(c.reason), k
    return False, None, None
