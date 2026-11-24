"""DEV17 procedure induction: ASM learns NEW repair operations from examples of fixes.

Through DEV16 every repair operation was written by a programmer (repair_ops.py). Here ASM constructs them itself:
given (before, after) versions of functions, it finds what changed, generalizes the change, and compiles it into an
executable rewrite procedure that can be applied to code it has never seen. No language model is involved.

1. EDIT EXTRACTION (`extract_edits`). The before/after ASTs are walked in parallel to the smallest region that contains
   every difference:
   - an EXPRESSION edit: one subtree replaced by another (`a < b` -> `a <= b`, `x.n` -> `getattr(x, 'n', None)`);
   - a STATEMENT-WINDOW edit: a run of statements replaced (wrapping in try/if, inserting a guard before an anchor
     statement, deleting or rewriting statements);
   - a STRING edit: one string constant changed by a single contiguous replacement (`'[a-z]+'` -> `'[^"]+'`).
   Each expression edit is also recorded with 1 and 2 enclosing levels of context, so evidence can decide how much
   context a rule needs.
2. GENERALIZATION (`generalize`). Several instances of the same kind of change are ANTI-UNIFIED: positions where all
   instances agree are kept, positions where they differ become variables (holes), and the same tuple of differing values
   becomes the SAME variable on both sides, so the replacement can reuse what the pattern bound. A single instance is
   generalized too: identifiers and constants carried unchanged from before to after become variables, while what changed
   stays concrete.
3. COMPILATION (`Procedure`). A rule is executable only if every variable in its replacement is bound by its pattern,
   and its pattern is not a bare variable. `Procedure.apply(source, function_range)` finds every match inside the
   function and returns one rewritten program per match, editing only the matched region (the rest of the file keeps
   its exact text).

Terms: an AST node is ("Node", ((field, term), ...)); a list is ("[]", (term, ...)); a primitive is ("=", value);
a variable is ("?", k). Positions (lineno, col_offset, ...) are never part of a term.
"""
from __future__ import annotations

import ast
import difflib
import functools
import hashlib
import json
from dataclasses import dataclass, field

_POS = {"lineno", "col_offset", "end_lineno", "end_col_offset", "type_comment"}
MAX_STRING_CONTEXT = 3


# ------------------------------------------------------------------------------------------------- terms
def to_term(x):
    if isinstance(x, ast.AST):
        return (type(x).__name__, tuple((f, to_term(getattr(x, f, None))) for f in x._fields if f not in _POS))
    if isinstance(x, list):
        return ("[]", tuple(to_term(i) for i in x))
    return ("=", x)


def from_term(t):
    head, body = t
    if head == "[]":
        return [from_term(i) for i in body]
    if head == "=":
        return body
    if head == "?":
        raise ValueError("cannot build an AST from a term with unbound variables")
    cls = getattr(ast, head)
    node = cls(**{f: from_term(v) for f, v in body})
    return node


def is_var(t) -> bool:
    return isinstance(t, tuple) and len(t) == 2 and t[0] == "?"


def variables(t) -> set:
    if is_var(t):
        return {t[1]}
    out = set()
    for _, c in _children(t):
        out |= variables(c)
    return out


def _children(t):
    """(key, child) pairs of a structured term; primitives and variables have none."""
    head, body = t
    if head in ("=", "?"):
        return []
    if head == "[]":
        return list(enumerate(body))
    return list(body)


def term_size(t) -> int:
    return 1 + sum(term_size(c) for _, c in _children(t))


def term_key(t) -> str:
    return hashlib.sha256(json.dumps(t, default=repr).encode()).hexdigest()[:16]


def _const_to_json(v):
    if isinstance(v, bytes):
        return {"$const": "bytes", "v": v.hex()}
    if isinstance(v, complex):
        return {"$const": "complex", "v": [v.real, v.imag]}
    if v is Ellipsis:
        return {"$const": "ellipsis"}
    return v


def term_to_json(t):
    """A term as JSON-safe nested lists. DEV18 bug fix (found by the DEV18 self-check): constants JSON cannot hold
    (bytes, complex, Ellipsis) are written as tagged objects, so a saved procedure or shape loads back unchanged (bytes
    used to come back as a tuple of ints, and complex/Ellipsis made saving fail). Terms without such constants serialize
    exactly as before, so existing sealed files keep their seals."""
    if isinstance(t, tuple):
        if len(t) == 2 and t[0] == "=":
            return ["=", list(t[1]) if isinstance(t[1], tuple) else _const_to_json(t[1])]
        return [term_to_json(x) for x in t]
    return t


def term_from_json(x):
    """Inverse of `term_to_json` (lists back to tuples, tagged constants back to their values)."""
    if isinstance(x, list):
        return tuple(term_from_json(i) for i in x)
    if isinstance(x, dict) and "$const" in x:
        kind = x["$const"]
        if kind == "bytes":
            return bytes.fromhex(x["v"])
        if kind == "complex":
            return complex(*x["v"])
        if kind == "ellipsis":
            return Ellipsis
    return x


# ------------------------------------------------------------------------------------------------- edits
@dataclass
class Edit:
    kind: str          # expr | stmts | string
    lhs: tuple         # term (expr: node term; stmts: ("[]", stmts); string: ("=", (old, left, right)))
    rhs: tuple
    level: int = 0     # expression context levels added above the minimal changed node
    meta: dict = field(default_factory=dict)


def _differs(a, b) -> bool:
    return a != b


def _locate(a, b, path=()):
    """Smallest differing region between terms a and b: (path, a_sub, b_sub, kind). kind 'list' when the region is a
    pair of unequal-length lists (statement windows), else 'node'."""
    if a == b:
        return None
    if a[0] != b[0] or a[0] in ("=", "?"):
        return path, a, b, "node"
    if a[0] == "[]":
        if len(a[1]) != len(b[1]):
            return path, a, b, "list"
        diffs = [i for i, (x, y) in enumerate(zip(a[1], b[1])) if x != y]
        if len(diffs) == 1:
            return _locate(a[1][diffs[0]], b[1][diffs[0]], path + (diffs[0],))
        return path, a, b, "list"
    fa, fb = dict(a[1]), dict(b[1])
    diffs = [f for f in fa if fa[f] != fb.get(f)]
    if len(diffs) == 1:
        return _locate(fa[diffs[0]], fb[diffs[0]], path + (diffs[0],))
    return path, a, b, "node"


def _get(t, path):
    for k in path:
        t = t[1][k] if t[0] == "[]" else dict(t[1])[k]
    return t


_EXPR_HEADS = {n.__name__ for n in (ast.BoolOp, ast.NamedExpr, ast.BinOp, ast.UnaryOp, ast.Lambda, ast.IfExp, ast.Dict,
                                    ast.Set, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp, ast.Await,
                                    ast.Yield, ast.YieldFrom, ast.Compare, ast.Call, ast.FormattedValue, ast.JoinedStr,
                                    ast.Constant, ast.Attribute, ast.Subscript, ast.Starred, ast.Name, ast.List,
                                    ast.Tuple, ast.Slice)}
_STMT_HEADS = {n.__name__ for n in vars(ast).values() if isinstance(n, type) and issubclass(n, ast.stmt)}


def _string_edit(old: str, new: str):
    sm = difflib.SequenceMatcher(None, old, new, autojunk=False)
    ops = [o for o in sm.get_opcodes() if o[0] != "equal"]
    if len(ops) != 1:
        return None
    _, i1, i2, j1, j2 = ops[0]
    return old[i1:i2], new[j1:j2], old[max(0, i1 - MAX_STRING_CONTEXT):i1], old[i2:i2 + MAX_STRING_CONTEXT]


def extract_edits(before: str, after: str) -> list:
    """Edits turning `before` into `after` (each: the source of ONE function). Several context levels are returned
    for expression edits; [] if there is no single differing region or a side does not parse."""
    try:
        ta, tb = to_term(ast.parse(before)), to_term(ast.parse(after))
    except SyntaxError:
        return []
    loc = _locate(ta, tb)
    if loc is None:
        return []
    path, a, b, kind = loc

    def stmt_list(x):
        return x[0] == "[]" and all(i[0] in _STMT_HEADS for i in x[1])
    # climb to the nearest expression or statement node, or to a STATEMENT list; other lists (comparison operators,
    # call arguments) are not edit regions, so climbing continues through them (a `<` -> `<=` change is an edit of the
    # enclosing Compare)
    if kind == "list" and not (stmt_list(a) and stmt_list(b)):
        kind = "node"
    while path and kind == "node" and a[0] not in _EXPR_HEADS | _STMT_HEADS:
        path = path[:-1]
        a, b = _get(ta, path), _get(tb, path)
        if stmt_list(a) and stmt_list(b) and len(a[1]) != len(b[1]):
            kind = "list"
    out = []
    if kind == "list" and a[0] == "[]" and all(x[0] in _STMT_HEADS for x in a[1] + b[1]):
        la, lb = list(a[1]), list(b[1])
        i = 0
        while i < min(len(la), len(lb)) and la[i] == lb[i]:
            i += 1
        j = 0
        while j < min(len(la), len(lb)) - i and la[-1 - j] == lb[-1 - j]:
            j += 1
        ra, rb = la[i:len(la) - j], lb[i:len(lb) - j]
        if not ra:  # pure insertion: anchor on the next statement (or the previous one at the end of a block)
            if i < len(la):
                ra, rb = [la[i]], rb + [la[i]]
            elif i > 0:
                ra, rb = [la[i - 1]], [la[i - 1]] + rb
            else:
                return []
        out.append(Edit("stmts", ("[]", tuple(ra)), ("[]", tuple(rb))))
        return out
    if a[0] in _STMT_HEADS and b[0] in _STMT_HEADS and a[0] != b[0]:  # one statement replaced by another (wrap)
        out.append(Edit("stmts", ("[]", (a,)), ("[]", (b,))))
        return out
    if a[0] == "Constant" and b[0] == "Constant":
        va, vb = dict(a[1])["value"][1], dict(b[1])["value"][1]
        if isinstance(va, str) and isinstance(vb, str):
            se = _string_edit(va, vb)
            if se:
                old, new, left, right = se
                out.append(Edit("string", ("=", (old, left, right)), ("=", new)))
    if a[0] in _EXPR_HEADS and b[0] in _EXPR_HEADS:
        out.append(Edit("expr", a, b, 0))
        p = path
        for level in (1, 2):  # the same change with enclosing context
            while p:
                p = p[:-1]
                pa = _get(ta, p)
                if pa[0] in _EXPR_HEADS:
                    out.append(Edit("expr", pa, _get(tb, p), level))
                    break
                if pa[0] in _STMT_HEADS or pa[0] == "[]":
                    p = ()
                    break
    elif a[0] in _STMT_HEADS and b[0] in _STMT_HEADS:
        out.append(Edit("stmts", ("[]", (a,)), ("[]", (b,))))
    return out


# --------------------------------------------------------------------------------------------- generalization
def _au(terms: list, table: dict):
    """Anti-unify a list of terms; equal tuples of differing values map to the same variable."""
    first = terms[0]
    if all(t == first for t in terms):
        return first
    heads = {t[0] for t in terms}
    if len(heads) == 1 and first[0] not in ("=", "?"):
        if first[0] == "[]":
            if len({len(t[1]) for t in terms}) == 1:
                return ("[]", tuple(_au([t[1][i] for t in terms], table) for i in range(len(first[1]))))
        else:
            fields = [f for f, _ in first[1]]
            if all([f for f, _ in t[1]] == fields for t in terms):
                return (first[0], tuple((f, _au([dict(t[1])[f] for t in terms], table)) for f in fields))
    key = json.dumps(terms, default=repr)
    if key not in table:
        table[key] = ("?", len(table))
    return table[key]


def _abstract_carried(lhs, rhs):
    """Single-instance generalization: primitive leaves (identifiers, constants) that occur on BOTH sides become
    variables; leaves that appear on one side only (what the fix changed or introduced) stay concrete."""
    def leaves(t, acc):
        if t[0] == "=":
            if isinstance(t[1], (str, int)) and not isinstance(t[1], bool) and t[1] is not None:
                acc.add(t[1])
        elif t[0] != "?":
            for _, c in _children(t):
                leaves(c, acc)
        return acc
    common = leaves(lhs, set()) & leaves(rhs, set())
    mapping = {v: ("?", 1000 + i) for i, v in enumerate(sorted(common, key=repr))}

    def sub(t):
        if t[0] == "=" and not isinstance(t[1], bool) and t[1] in mapping and isinstance(t[1], (str, int)):
            return mapping[t[1]]
        if t[0] in ("=", "?"):
            return t
        if t[0] == "[]":
            return ("[]", tuple(sub(c) for c in t[1]))
        return (t[0], tuple((f, sub(v)) for f, v in t[1]))
    return sub(lhs), sub(rhs)


def _renumber(lhs, rhs):
    order: dict = {}

    def walk(t):
        if is_var(t):
            order.setdefault(t[1], len(order))
            return ("?", order[t[1]])
        if t[0] == "=":
            return t
        if t[0] == "[]":
            return ("[]", tuple(walk(c) for c in t[1]))
        return (t[0], tuple((f, walk(v)) for f, v in t[1]))
    return walk(lhs), walk(rhs)


def generalize(edits: list):
    """One rule (kind, lhs, rhs, level) from edits of the same kind and level, or None if they cannot share one."""
    kinds = {(e.kind, e.level) for e in edits}
    if len(kinds) != 1:
        return None
    kind, level = kinds.pop()
    if kind == "string":
        olds = {e.lhs[1][0] for e in edits}
        news = {e.rhs[1] for e in edits}
        if len(olds) != 1 or len(news) != 1:
            return None
        lefts = [e.lhs[1][1] for e in edits]
        rights = [e.lhs[1][2] for e in edits]
        left = lefts[0]
        while left and not all(x.endswith(left) for x in lefts):
            left = left[1:]
        right = rights[0]
        while right and not all(x.startswith(right) for x in rights):
            right = right[:-1]
        return ("string", ("=", (olds.pop(), left, right)), ("=", news.pop()), level)
    if len(edits) == 1:
        lhs, rhs = _abstract_carried(edits[0].lhs, edits[0].rhs)
    else:
        table: dict = {}
        pair = _au([("pair", (("l", e.lhs), ("r", e.rhs))) for e in edits], table)
        if is_var(pair):
            return None
        d = dict(pair[1])
        lhs, rhs = d["l"], d["r"]
    lhs, rhs = _renumber(lhs, rhs)
    return (kind, lhs, rhs, level)


def executable(rule) -> bool:
    kind, lhs, rhs, _ = rule
    if kind == "string":
        return bool(lhs[1][0] or lhs[1][1] or lhs[1][2])  # an insertion needs some context to anchor on
    if is_var(lhs) or (lhs[0] == "[]" and all(is_var(x) for x in lhs[1])):
        return False
    return variables(rhs) <= variables(lhs)


# --------------------------------------------------------------------------------------------- matching
def match(pattern, term, binding: dict) -> bool:
    if is_var(pattern):
        k = pattern[1]
        if k in binding:
            return binding[k] == term
        binding[k] = term
        return True
    if pattern[0] != term[0]:
        return False
    if pattern[0] == "=":
        return pattern[1] == term[1] and type(pattern[1]) is type(term[1])
    if pattern[0] == "[]":
        if len(pattern[1]) != len(term[1]):
            return False
        return all(match(p, t, binding) for p, t in zip(pattern[1], term[1]))
    pf, tf = pattern[1], dict(term[1])
    return all(f in tf and match(v, tf[f], binding) for f, v in pf)


def instantiate(t, binding: dict):
    if is_var(t):
        return binding[t[1]]
    if t[0] == "=":
        return t
    if t[0] == "[]":
        return ("[]", tuple(instantiate(c, binding) for c in t[1]))
    return (t[0], tuple((f, instantiate(v, binding)) for f, v in t[1]))


# --------------------------------------------------------------------------------------------- procedures
_NEEDS_PARENS = (ast.BoolOp, ast.BinOp, ast.UnaryOp, ast.Compare, ast.IfExp, ast.Lambda, ast.NamedExpr, ast.Await,
                 ast.Yield, ast.YieldFrom)


def _offsets(src: bytes) -> list:
    starts, pos = [0], 0
    for ln in src.splitlines(keepends=True):
        pos += len(ln)
        starts.append(pos)
    return starts


@functools.lru_cache(maxsize=4)
def _parsed(source: str):
    """DEV31 (performance; same results): one parse of a module, shared by every procedure (each re-parsed and re-walked
    the whole module, minutes per suspect on youtube-dl's 3,643-line utils.py). Nothing mutates the tree."""
    tree = ast.parse(source)
    nodes = tuple(ast.walk(tree))
    src = source.encode("utf-8")
    parents = {id(c): n for n in nodes for c in ast.iter_child_nodes(n)}
    try:
        whole = ast.unparse(tree)
    except ValueError:  # then no candidate normalizes: chunks are not used (_chunk)
        whole = None
    return tree, nodes, src, _offsets(src), source.splitlines(keepends=True), parents, {None: whole}


def _chunk_body(text: str) -> list:
    """The statements of whole source lines parsed alone; indented lines are parsed inside `if 1:`."""
    return ast.parse("if 1:\n" + text).body[0].body if text[:1] in " \t" else ast.parse(text).body


def _chunk(source: str, node):
    """(first line, last line, statement, its normalized text): the innermost statement holding `node` whose lines hold
    nothing else, found by parsing those lines alone; the whole module when there is none. DEV31 (performance; same
    results): a rewrite inside it then parses to the intended program iff its chunk parses to the intended statement
    (the rest of the file tokenizes unchanged), and two rewrites give the same normalized program iff their chunk keys
    (_keyed) are equal. Each statement is tried once."""
    tree, _, src, starts, _, parents, memo = _parsed(source)
    s = node
    while memo[None] is not None and s is not tree:
        s = parents[id(s)]
        if isinstance(s, ast.stmt):
            if id(s) not in memo:
                lo = min([s.lineno] + [d.lineno for d in getattr(s, "decorator_list", [])])
                try:
                    body = _chunk_body(src[starts[lo - 1]:starts[s.end_lineno]].decode())
                    memo[id(s)] = (lo, s.end_lineno, s, ast.unparse(s)) if len(body) == 1 and ast.dump(body[0]) == ast.dump(s) else None
                except (SyntaxError, ValueError):
                    memo[id(s)] = None
            if memo[id(s)]:
                return memo[id(s)]
    return 1, len(starts) - 1, tree, memo[None]  # byte lines: str.splitlines also splits at form feeds


def _keyed(piece: str, chunk, intended=None):
    """(parsed as intended, de-duplication key) for a rewrite whose changed chunk text is `piece`: the key is None when the
    rewrite cannot be normalized, `noop` when it normalizes to the unchanged program."""
    lo, _, stmt, original = chunk
    try:
        got = ast.parse(piece) if isinstance(stmt, ast.Module) else _chunk_body(piece)
        got = got if isinstance(stmt, ast.Module) else (got[0] if len(got) == 1 else None)
    except SyntaxError:
        return False, None
    if got is None or (intended is not None and ast.dump(got) != intended):
        return False, None
    try:
        norm = ast.unparse(got)
    except ValueError:
        return True, None
    return True, ("noop" if norm == original else (lo, norm))


@functools.lru_cache(maxsize=8)
def _in_span(source: str, lo: int, hi: int):
    """In ast.walk order: the expressions a procedure may rewrite within lines lo..hi, the string constants among them
    that are not docstrings, the statement blocks holding any such statement, and the `inside` test itself."""
    _, nodes, *_ = _parsed(source)
    # DEV18 bug fix (found by the DEV18 self-check on boltons human_readable_list): only the nodes INSIDE an f-string
    # are excluded; the f-string node itself has a reliable position and may be rewritten as a whole
    in_fstring = {id(x) for n in nodes if isinstance(n, ast.JoinedStr) for x in ast.walk(n) if x is not n}
    docstrings = {id(n.body[0].value) for n in nodes
                  if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)) and n.body
                  and isinstance(n.body[0], ast.Expr) and isinstance(getattr(n.body[0], "value", None), ast.Constant)}

    def inside(n):  # within the function's lines, and not part of an f-string (its positions are not reliable)
        return hasattr(n, "lineno") and lo <= n.lineno and n.end_lineno <= hi and id(n) not in in_fstring
    exprs = tuple(n for n in nodes if isinstance(n, ast.expr) and inside(n))
    strings = tuple(n for n in exprs if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings)
    blocks = tuple((n, f, b) for n in nodes for f in ("body", "orelse", "finalbody") for b in [getattr(n, f, None)]
                   if isinstance(b, list) and b and isinstance(b[0], ast.stmt) and any(inside(x) for x in b))
    return exprs, strings, blocks, inside


@dataclass
class Procedure:
    """An executable, learned rewrite. `apply` never changes text outside the matched region."""
    kind: str
    lhs: tuple
    rhs: tuple
    level: int = 0

    @property
    def id(self) -> str:
        return "p" + term_key((self.kind, self.lhs, self.rhs, self.level))

    def describe(self) -> str:
        if self.kind == "string":
            old, left, right = self.lhs[1]
            return f"string: {left!r}+{old!r}+{right!r} -> {self.rhs[1]!r}"

        def show(t):
            try:
                node = from_term(_show_vars(t))
                if isinstance(node, list):
                    return "; ".join(ast.unparse(x) for x in node)
                return ast.unparse(node)
            except Exception:
                return t[0]
        return f"{self.kind}: {show(self.lhs)} -> {show(self.rhs)}"[:160]

    def to_dict(self) -> dict:
        return {"kind": self.kind, "lhs": term_to_json(self.lhs), "rhs": term_to_json(self.rhs), "level": self.level}

    @classmethod
    def from_dict(cls, d) -> "Procedure":
        return cls(d["kind"], term_from_json(d["lhs"]), term_from_json(d["rhs"]), d["level"])

    def apply(self, source: str, span: tuple) -> list:
        """Rewritten programs, one per match inside lines span=(first, last). [] if nothing matches."""
        return [prog for prog, _ in self.apply_detailed(source, span)]

    def apply_detailed(self, source: str, span: tuple, fill=None, max_results: int | None = None) -> list:
        """[(program, info)]. DEV18: `fill(binding, node, tree)` may return [(rhs_term, info), ...] to instantiate the
        replacement per match (open procedures whose content holes are filled from the problem); default: the rule's
        own replacement with the match's binding.
        DEV18 A2 (performance; same results): candidates are validated as they are built, and with `max_results` the
        search stops at that many valid ones, which are exactly the first `max_results` of the full list."""
        try:
            return self._apply_detailed(source, span, fill, _Collector(max_results))
        except _Enough as e:
            return e.results

    def _apply_detailed(self, source, span, fill, out) -> list:
        try:
            tree, _, src, starts, lines, *_ = _parsed(source)
        except SyntaxError:
            return []
        exprs, strings, blocks, inside = _in_span(source, *span)

        def rhs_terms(binding, node):
            if fill is None:
                return [(instantiate(self.rhs, binding), {})]
            return fill(binding, node, tree)

        if self.kind == "string":
            old, left, right = self.lhs[1]
            needle = left + old + right
            for n in strings:
                if needle in n.value:
                    k = n.value.index(needle) + len(left)
                    new_val = n.value[:k] + self.rhs[1] + n.value[k + len(old):]
                    a, b = starts[n.lineno - 1] + n.col_offset, starts[n.end_lineno - 1] + n.end_col_offset
                    text = src[a:b].decode()
                    if text[:1] in "'\"" or text[:2].lower() in ("r'", 'r"'):
                        rep = repr(new_val) if not text[:1].lower() == "r" else None
                        if rep is None:  # keep a raw literal raw when the result is still representable that way
                            q = text[1]
                            rep = ("r" + q + new_val + q) if q not in new_val and not new_val.endswith("\\") else repr(new_val)
                        chunk = _chunk(source, n)
                        _, key = _keyed((src[starts[chunk[0] - 1]:a] + rep.encode() + src[b:starts[chunk[1]]]).decode(), chunk)
                        if key is not None:
                            out.append(((src[:a] + rep.encode() + src[b:]).decode(), {}), key)
            return out.results
        if self.kind == "expr":
            for n in exprs:
                binding: dict = {}
                if not match(self.lhs, to_term(n), binding):
                    continue
                chunk = _chunk(source, n)
                ca, cb = starts[chunk[0] - 1], starts[chunk[1]]
                for rhs_term, info in rhs_terms(binding, n):
                    try:
                        new = from_term(rhs_term)
                        intended = _substituted_dump(chunk[2], n, new)
                        plain = ast.unparse(new)
                    except Exception:  # a filled value that does not make a valid tree (e.g. a non-identifier name)
                        continue
                    a, b = starts[n.lineno - 1] + n.col_offset, starts[n.end_lineno - 1] + n.end_col_offset
                    # DEV17 bug fix (more_itertools run_length.decode): a node's text span is not always a valid place
                    # for any expression (a generator expression that is a call's only argument borrows the call's
                    # parentheses). Every rewrite is checked against the intended tree; parenthesized as a fallback.
                    for text in ([f"({plain})", plain] if isinstance(new, _NEEDS_PARENS) else [plain, f"({plain})"]):
                        ok, key = _keyed((src[ca:a] + text.encode() + src[b:cb]).decode(), chunk, intended)
                        if ok:
                            if key is not None:
                                out.append(((src[:a] + text.encode() + src[b:]).decode(), info), key)
                            break
            return out.results
        # statement windows
        width = len(self.lhs[1])
        for n, fname, block in blocks:
            for i in range(len(block) - width + 1):
                window = block[i:i + width]
                if not all(inside(s) for s in window):
                    continue
                binding = {}
                if not match(self.lhs, ("[]", tuple(to_term(s) for s in window)), binding):
                    continue
                first, last = window[0], window[-1]
                indent = lines[first.lineno - 1][:first.col_offset]
                # DEV17 bug fix (semver Version.parse): a decorated definition's text starts at its first decorator
                start_line = min([first.lineno] + [d.lineno for d in getattr(first, "decorator_list", [])])
                if lines[first.lineno - 1][:first.col_offset].strip():
                    continue
                for rhs_term, info in rhs_terms(binding, window):
                    try:
                        new_stmts = from_term(rhs_term)
                        mod = ast.Module(body=new_stmts, type_ignores=[])
                        ast.fix_missing_locations(mod)
                        body = ast.unparse(mod) + "\n"
                    except Exception:
                        continue
                    # DEV17 bug fix (found by the self-reproduction diagnostic on semver `match`): an `elif` branch is
                    # an If node inside its parent's orelse whose source starts with `elif`; writing it back as `if`
                    # would move it out of the chain and change the program
                    if fname == "orelse" and isinstance(n, ast.If) and lines[first.lineno - 1][first.col_offset:].startswith("elif"):
                        if len(new_stmts) != 1 or not isinstance(new_stmts[0], ast.If):
                            continue
                        body = "el" + body
                    text = _indent_code(body, indent)
                    out.append(("".join(lines[:start_line - 1]) + text + "".join(lines[last.end_lineno:]), info))
        return out.results

    @staticmethod
    def _valid(cands: list, seen: set) -> list:  # the rule _Collector applies incrementally
        res = []
        for c, info in cands:
            try:
                norm = ast.unparse(ast.parse(c))
            except (SyntaxError, ValueError):
                continue
            if norm not in seen:
                seen.add(norm)
                res.append((c, info))
        return res


class _Enough(Exception):
    def __init__(self, results):
        self.results = results


class _Collector:
    """Validates and de-duplicates candidates as they are appended (exactly `Procedure._valid`, in order); raises
    `_Enough` once `limit` valid candidates are held, so no further candidate is built."""

    def __init__(self, limit=None):
        self.limit, self.results, self.seen = limit, [], set()

    def append(self, item, norm=None):
        """`norm`: the item's de-duplication key when the caller has validated it (DEV31, chunk keys)."""
        if self.limit is not None and len(self.results) >= self.limit:
            raise _Enough(self.results)
        c, info = item
        if norm is None:
            try:
                norm = ast.unparse(ast.parse(c))
            except (SyntaxError, ValueError):
                return
        if norm not in self.seen:
            self.seen.add(norm)
            self.results.append((c, info))
            if self.limit is not None and len(self.results) >= self.limit:
                raise _Enough(self.results)


_PRIMITIVE_FIELDS = {"id", "attr", "arg", "name", "module", "asname", "value_str"}


def _substituted_dump(tree, target, new) -> str:
    """ast.dump of `tree` with the node object `target` replaced by `new` (the program a rewrite must produce)."""
    import copy

    class Sub(ast.NodeTransformer):
        def visit(self, node):
            if node is target:
                return copy.deepcopy(new)
            return self.generic_visit(node)
    return ast.dump(Sub().visit(copy.deepcopy(tree, {id(target): target})))


def _indent_code(text: str, indent: str) -> str:
    """Indent every line of generated code EXCEPT lines that begin inside a multi-line string literal (their leading
    whitespace is string content). DEV17 bug fix, found on toolz `interpose`: indenting a rewritten docstring's lines
    changed the docstring."""
    import io
    import tokenize
    inside = set()
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.STRING and tok.end[0] > tok.start[0]:
                inside.update(range(tok.start[0] + 1, tok.end[0] + 1))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass
    return "".join(ln if (i in inside or not ln.strip()) else indent + ln
                   for i, ln in enumerate(text.splitlines(keepends=True), 1))


def _show_vars(t, primitive: bool = False):
    """Variables rendered for describe(): V0, V1... as names (or as plain strings where the field is a primitive)."""
    if is_var(t):
        return ("=", f"V{t[1]}") if primitive else ("Name", (("id", ("=", f"V{t[1]}")), ("ctx", ("Load", ()))))
    if t[0] == "=":
        return t
    if t[0] == "[]":
        return ("[]", tuple(_show_vars(c) for c in t[1]))
    return (t[0], tuple((f, _show_vars(v, f in _PRIMITIVE_FIELDS or (t[0] == "Constant" and f == "value"))) for f, v in t[1]))


def induce(examples: list) -> list:
    """Candidate procedures from examples [(before_fn_src, after_fn_src, example_id)], with the ids that support
    each. Every example contributes a single-instance rule per context level; examples whose edits share a shape
    (same kind/level and same rule skeleton after generalization) also yield a joint, more general rule."""
    per_example = []
    for before, after, eid in examples:
        for e in extract_edits(before, after):
            per_example.append((eid, e))
    rules: dict = {}
    # single-instance rules
    for eid, e in per_example:
        r = generalize([e])
        if r and executable(r):
            rules.setdefault(r, set()).add(eid)
    # joint rules: group edits whose single-instance rules have the same skeleton (same changed structure)
    groups: dict = {}
    for eid, e in per_example:
        r = generalize([e])
        if r is None:
            continue
        key = (r[0], r[3], _skeleton(r[1]), _skeleton(r[2])) if r[0] != "string" else ("string", r[1][1][0], r[2][1])
        groups.setdefault(key, []).append((eid, e))
    for items in groups.values():
        ids = {eid for eid, _ in items}
        if len(ids) < 2:
            continue
        r = generalize([e for _, e in items])
        if r and executable(r):
            rules.setdefault(r, set()).update(ids)
    return [(Procedure(*r), sorted(ids)) for r, ids in rules.items()]


def _skeleton(t, depth=0):
    """Shape of a term with every primitive leaf erased (2 levels of node heads, enough to group like with like)."""
    if is_var(t) or t[0] == "=":
        return "_"
    if depth >= 3:
        return t[0]
    if t[0] == "[]":
        return "[" + ",".join(_skeleton(c, depth + 1) for c in t[1]) + "]"
    return t[0] + "(" + ",".join(_skeleton(v, depth + 1) for _, v in t[1]) + ")"
