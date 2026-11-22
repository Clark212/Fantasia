"""DEV20: learned edit STEPS that combine.

DEV19 found that whole-fix shapes rarely recur (680 of 730 learned shapes were seen once) and that 12.6x more data barely
raised coverage. A real fix is often several small changes: as ONE shape it is specific and seen once, but each change on
its own is generic and recurs in other projects. DEV20 learns every minimal change of a fix as a STEP:

  extraction    `extract_steps`: every minimal difference between the before/after function, lifted to its nearest
                expression or statement node; a run of statements inserted, deleted or replaced is one statement step.
                The SAME change at several places (a consistent rename) is one step with `sites` > 1. Docstring changes
                are not learned (they do not change behaviour).
  abstraction   as DEV18 shapes (`shapes._abstract`: carried values become variables, introduced values typed holes, at
                most 2 per step), plus: the CONTEXT the step sits in (parent node type and field), and a name the fix
                introduced as the exception of a `raise` is an exception hole (DEV19: `ValueError`-like names were
                never offered, because the name operator does not list exceptions).
  candidates    SINGLE: one step at one place (ranked as DEV18 shapes, a place whose context the step was seen in
                first); MULTI-SITE: the same filled step at every place with the same match (rename every occurrence);
                PAIR: two steps learned together in at least 2 fixes, at two places of the function (closer places
                first). Ranking keys are computed first and programs are built lazily in rank order, so a limited search builds about `limit`
                programs, not every candidate.
No language model is involved; the tests and the contract still decide acceptance in the workflow.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import itertools
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from . import content as C
from . import shapes as SH
from .induction import (_EXPR_HEADS, _NEEDS_PARENS, _STMT_HEADS, Edit, Procedure, _offsets, _string_edit, from_term,
                        is_var, match, term_from_json, term_key, term_to_json, to_term)

PER_MATCH = SH.PER_MATCH        # fillings per match (as DEV18)
PER_STEP = SH.PER_SHAPE         # single-site candidates per step (as DEV18 per shape)
LIMIT = SH.LIMIT
PAIR_FILLINGS = 3               # best fillings per site combined in a pair (places anywhere in the function, the
                                # closer first: same statement, then one statement inside the other, then elsewhere)
PAIR_MIN_SUPPORT = 2            # a pair is used once it was learned from 2 different fixes
QUOTA = {"single": 50, "multi": 15, "pair": 15}   # share of the budget per candidate kind; unused share is passed on
EXCEPTION_SITES = ("any", "raise")  # DEV21 (experimental, opt-in): where an expression step with an exception hole may
                                    # apply. "any" (default, unchanged); "raise": only the exception of a `raise` (or the
                                    # callee of that exception), the role the hole was learned in (DEV20: such a step
                                    # applied everywhere filled most of the single share).
SHARING = ("key", "round_robin")  # DEV21 (experimental, opt-in): order within a kind. "key" (default, unchanged): every
                                  # candidate by its ranking key, so one generic step can fill most of a share (DEV20).
                                  # "round_robin": each step proposes its next candidate before any step proposes another.
EXCEPTION_HOLES = True          # a name introduced as a raised exception is an `exc` hole (False: DEV18 typing, ablation)


# ----------------------------------------------------------------------------------------------------- extraction
@dataclass
class ConcreteStep:
    kind: str           # expr | stmts
    lhs: tuple          # expr: node term; stmts: ("[]", statements)
    rhs: tuple
    ctx: str            # "Parent.field" of the step's place
    gctx: str           # the parent's own place ("Grandparent.field")
    sites: int = 1      # identical changes at several places


def _mdiffs(a, b, path=()):
    """Every minimal differing place between two terms: [(path, a_sub, b_sub, 'node' | 'list')]."""
    if a == b:
        return []
    if a[0] != b[0] or a[0] in ("=", "?"):
        return [(path, a, b, "node")]
    if a[0] == "[]":
        if len(a[1]) != len(b[1]):
            return [(path, a, b, "list")]
        out = []
        for i, (x, y) in enumerate(zip(a[1], b[1])):
            out += _mdiffs(x, y, path + (i,))
        return out
    if [f for f, _ in a[1]] != [f for f, _ in b[1]]:
        return [(path, a, b, "node")]
    fa, fb = dict(a[1]), dict(b[1])
    out = []
    for f in fa:
        if fa[f] != fb[f]:
            out += _mdiffs(fa[f], fb[f], path + (f,))
    return out


def _get(t, path):
    for k in path:
        t = t[1][k] if t[0] == "[]" else dict(t[1])[k]
    return t


def _place(t, path) -> tuple:
    """("Parent.field", "Grandparent.field") of the node at `path` (lists skipped)."""
    out = []
    p = tuple(path)
    while p and len(out) < 2:
        fld = p[-2] if isinstance(p[-1], int) and len(p) >= 2 else p[-1]
        p = p[:-2] if isinstance(p[-1], int) and len(p) >= 2 else p[:-1]
        out.append(f"{_get(t, p)[0]}.{fld}")
    while len(out) < 2:
        out.append("")
    return out[0], out[1]


def _stmt_list(x) -> bool:
    return x[0] == "[]" and all(i[0] in _STMT_HEADS for i in x[1])


def _str_const(t) -> bool:
    return t[0] == "Constant" and isinstance(dict(t[1])["value"][1], str)


def _is_docstring_change(kind, lhs, rhs, ctx) -> bool:
    """A changed docstring (or other bare string statement): no behaviour, nothing to learn."""
    if kind == "expr":
        return ctx == "Expr.value" and _str_const(lhs) and _str_const(rhs)
    def doc(s):
        return s[0] == "Expr" and _str_const(dict(s[1])["value"])
    return len(lhs[1]) == 1 and len(rhs[1]) == 1 and doc(lhs[1][0]) and doc(rhs[1][0])


def extract_steps(before: str, after: str) -> list:
    """The minimal steps turning `before` into `after` (each the source of one function); [] if a side does not parse."""
    try:
        ta, tb = to_term(ast.parse(before)), to_term(ast.parse(after))
    except SyntaxError:
        return []
    found = []          # (path, kind, lhs, rhs)
    for path, a, b, kind in _mdiffs(ta, tb):
        if kind == "list" and _stmt_list(a) and _stmt_list(b):
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
                else:   # an empty block filled: the enclosing statement is the step
                    kind = "node"
            if ra:
                found.append((path, "stmts", ("[]", tuple(ra)), ("[]", tuple(rb))))
                continue
        p = path
        while p and _get(ta, p)[0] not in _EXPR_HEADS | _STMT_HEADS:
            p = p[:-1]
        if not p:
            continue
        na, nb = _get(ta, p), _get(tb, p)
        if na[0] in _EXPR_HEADS and nb[0] in _EXPR_HEADS:
            found.append((p, "expr", na, nb))
        else:
            while p and not (_get(ta, p)[0] in _STMT_HEADS and _get(tb, p)[0] in _STMT_HEADS):
                p = p[:-1]
            if p:
                found.append((p, "stmts", ("[]", (_get(ta, p),)), ("[]", (_get(tb, p),))))
    # a step inside another step's region is part of it
    paths = {f[0] for f in found}
    found = [f for f in found if not any(q != f[0] and f[0][:len(q)] == q for q in paths)]
    out, index = [], {}
    for p, kind, lhs, rhs in found:
        ctx, gctx = _place(ta, p) if kind == "expr" else (_place(ta, p + (0,))[0] if _get(ta, p)[0] == "[]" else
                                                          _place(ta, p)[0], "")
        if _is_docstring_change(kind, lhs, rhs, ctx):
            continue
        key = (kind, term_key(lhs), term_key(rhs))
        if key in index:
            out[index[key]].sites += 1
            continue
        index[key] = len(out)
        out.append(ConcreteStep(kind, lhs, rhs, ctx, gctx))
    return out


# ---------------------------------------------------------------------------------------------------- abstraction
def _hole_at(t):
    """The hole id when `t` is a name hole (Name(id=<hole>)) or a call of one, else None."""
    if t[0] == "Call":
        t = dict(t[1])["func"]
    if t[0] == "Name":
        v = dict(t[1])["id"]
        if is_var(v) and isinstance(v[1], str):
            return v[1]
    return None


def _raise_holes(t, acc):
    if is_var(t) or t[0] == "=":
        return acc
    if t[0] == "Raise":
        h = _hole_at(dict(t[1])["exc"]) if dict(t[1])["exc"][0] != "=" else None
        if h:
            acc.add(h)
    for _, c in (enumerate(t[1]) if t[0] == "[]" else t[1]):
        _raise_holes(c, acc)
    return acc


def abstract_step(cs: ConcreteStep):
    """(lhs, rhs, holes, var_types) or None (more than 2 introduced values, or a pattern that would match anything)."""
    ab = SH._abstract(Edit(cs.kind, cs.lhs, cs.rhs, 0))
    if ab is None:
        return None
    lhs, rhs, holes, var_types = ab
    holes = dict(holes)
    exc = _raise_holes(rhs, set())
    if cs.kind == "expr" and (cs.ctx == "Raise.exc" or (cs.ctx == "Call.func" and cs.gctx == "Raise.exc")):
        h = _hole_at(rhs) if cs.ctx == "Raise.exc" else (_hole_at(rhs) if rhs[0] == "Name" else None)
        if h:
            exc.add(h)
    for h in exc if EXCEPTION_HOLES else ():
        if holes.get(h) == "name":
            holes[h] = "exc"
    return lhs, rhs, holes, var_types


class Step:
    def __init__(self, kind, lhs, rhs, holes, var_types=None):
        self.kind, self.lhs, self.rhs, self.holes = kind, lhs, rhs, dict(holes)
        self.var_types = {int(k): v for k, v in (var_types or {}).items()}
        self.support: list = []
        self.sources: list = []
        self.contexts: dict = {}
        self.multi = 0
        self.status = "candidate"

    @property
    def id(self) -> str:
        return "t" + term_key((self.kind, self.lhs, self.rhs, sorted(self.holes.items()), sorted(self.var_types.items())))

    def describe(self) -> str:
        p = Procedure(self.kind, self.lhs, SH._holes_as_vars(self.rhs), 0).describe()
        return p + "  holes=" + ",".join(f"{k}:{v}" for k, v in sorted(self.holes.items()))

    def to_dict(self) -> dict:
        return {"kind": self.kind, "lhs": term_to_json(self.lhs), "rhs": term_to_json(self.rhs), "holes": self.holes,
                "var_types": {str(k): v for k, v in sorted(self.var_types.items())}, "support": self.support,
                "sources": self.sources, "contexts": dict(sorted(self.contexts.items())), "multi": self.multi,
                "status": self.status}

    @classmethod
    def from_dict(cls, d) -> "Step":
        s = cls(d["kind"], term_from_json(d["lhs"]), term_from_json(d["rhs"]), d["holes"], d["var_types"])
        s.support, s.sources, s.contexts = list(d["support"]), list(d["sources"]), dict(d["contexts"])
        s.multi, s.status = d["multi"], d["status"]
        return s


# ------------------------------------------------------------------------------------------------- applying: text
def _sub_dump(tree, subs: dict) -> str:
    """ast.dump of `tree` with node objects replaced ({id(node): new})."""
    class Sub(ast.NodeTransformer):
        def visit(self, node):
            if id(node) in subs:
                return copy.deepcopy(subs[id(node)])
            return self.generic_visit(node)
    memo = {id(n): n for n in ast.walk(tree) if id(n) in subs}
    return ast.dump(Sub().visit(copy.deepcopy(tree, memo)))


class _Text:
    """One parsed function: byte offsets for splicing replacements into its exact text."""

    def __init__(self, source: str, tree):
        self.source, self.tree = source, tree
        self.src = source.encode("utf-8")
        self.starts = _offsets(self.src)

    def span(self, n):
        return self.starts[n.lineno - 1] + n.col_offset, self.starts[n.end_lineno - 1] + n.end_col_offset

    def build(self, edits: list):
        """Program with each (node, replacement term) replaced, or None if the text cannot express exactly that tree
        (e.g. a filled value that is not a valid identifier)."""
        try:
            edits = [(n, from_term(t)) for n, t in edits]
        except Exception:
            return None
        spans = sorted(((*self.span(n), n, new) for n, new in edits), key=lambda x: x[0])
        if any(spans[k][1] > spans[k + 1][0] for k in range(len(spans) - 1)):
            return None  # overlapping places
        try:
            intended = _sub_dump(self.tree, {id(n): new for n, new in edits})
            texts = []
            for a, b, n, new in spans:
                plain = ast.unparse(new)
                texts.append([f"({plain})", plain] if isinstance(new, _NEEDS_PARENS) else [plain, f"({plain})"])
        except Exception:
            return None
        for choice in itertools.islice(itertools.product(*texts), 8):
            out, last = [], 0
            for (a, b, _, _), t in zip(spans, choice):
                out.append(self.src[last:a])
                out.append(t.encode())
                last = b
            out.append(self.src[last:])
            cand = b"".join(out).decode()
            try:
                if ast.dump(ast.parse(cand)) == intended:
                    return cand
            except SyntaxError:
                continue
        return None


def _round_robin(proposals: list) -> list:
    """Proposals (sorted by key) reordered so that every source (step, or pair of steps) gives its next proposal
    before any source gives another; sources take turns in the order of their best proposal."""
    groups: dict = {}
    for p in proposals:
        groups.setdefault(p[2]["step"], []).append(p)
    queues = list(groups.values())
    return [q[r] for r in range(max((len(q) for q in queues), default=0)) for q in queues if r < len(q)]


def _sites(tree, span):
    """[(node, "Parent.field", statement)] for the expression nodes inside the function's lines; not inside f-strings
    (their positions are not reliable) and not docstrings or other bare string statements (steps do not learn changes to
    those, so rewriting them only spends the budget)."""
    lo, hi = span
    in_fstring = {id(x) for n in ast.walk(tree) if isinstance(n, ast.JoinedStr) for x in ast.walk(n) if x is not n}
    bare = {id(n.value) for n in ast.walk(tree) if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
            and isinstance(n.value.value, str)}
    in_fstring |= bare
    out = []

    def walk(node, stmt):
        for fld, val in ast.iter_fields(node):
            for child in (val if isinstance(val, list) else [val]):
                if not isinstance(child, ast.AST):
                    continue
                st = child if isinstance(child, ast.stmt) else stmt
                if isinstance(child, ast.expr) and hasattr(child, "lineno") and lo <= child.lineno \
                        and child.end_lineno <= hi and id(child) not in in_fstring:
                    out.append((child, f"{type(node).__name__}.{fld}", st))
                walk(child, st)
    walk(tree, None)
    return out


# --------------------------------------------------------------------------------------------------------- library
class StepLibrary:
    def __init__(self):
        self.steps: dict = {}
        self.pairs: dict = {}           # "id_a|id_b" (sorted) -> [example ids]
        self.vocab = C.StringVocabulary()
        self.examples_seen: set = set()

    # ------------------------------------------------------------------ learning
    def learn(self, examples: list, source: str) -> list:
        """examples: [(before_fn, after_fn, example_id)]; returns the ids of new steps."""
        new = []
        for before, after, eid in examples:
            if eid in self.examples_seen:
                continue
            self.examples_seen.add(eid)
            here = []
            for cs in extract_steps(before, after):
                if cs.kind == "expr" and cs.lhs[0] == "Constant" and cs.rhs[0] == "Constant":
                    va, vb = dict(cs.lhs[1])["value"][1], dict(cs.rhs[1])["value"][1]
                    if isinstance(va, str) and isinstance(vb, str):
                        se = _string_edit(va, vb)
                        if se:
                            self.vocab.add(se[0], se[1], se[2], se[3])
                ab = abstract_step(cs)
                if ab is None:
                    continue
                st = Step(cs.kind, *ab)
                cur = self.steps.get(st.id)
                if cur is None:
                    self.steps[st.id] = cur = st
                    new.append(st.id)
                if eid not in cur.support:
                    cur.support.append(eid)
                if source not in cur.sources:
                    cur.sources.append(source)
                cur.contexts[cs.ctx] = cur.contexts.get(cs.ctx, 0) + 1
                cur.multi += int(cs.sites >= 2)
                if cur.status == "candidate" and len(cur.support) >= 2:
                    cur.status = "active"
                here.append(cur.id)
            for a, b in itertools.combinations(here, 2):
                key = "|".join(sorted((a, b)))
                lst = self.pairs.setdefault(key, [])
                if eid not in lst:
                    lst.append(eid)
        return new

    # ------------------------------------------------------------------ applying
    def _fillings(self, st, binding, ctx, scope):
        """[(values, ops, rank)] for the step's holes at one match (at most PER_MATCH)."""
        for var, tname in st.var_types.items():  # matched values must have the learned types
            b = binding.get(var)
            if b is not None and b[0] == "=" and type(b[1]).__name__ != tname:
                return []
        if not st.holes:
            return [({}, ["structural"], 0)]
        options = [[(cid, v, op) for v, op in SH.ShapeLibrary._fillers(self, t, binding, ctx, scope)]
                   for cid, t in sorted(st.holes.items())]
        if any(not o for o in options):
            return []
        return [({cid: v for cid, v, _ in combo}, [op for _, _, op in combo], j)
                for j, combo in enumerate(itertools.islice(itertools.product(*options), PER_MATCH))]

    def proposals(self, source: str, span: tuple, ctx: C.ProblemContext, exception_sites: str = "any") -> tuple:
        """(text, {kind: [(key, edits, info)]}) for every candidate, unbuilt: `edits` is [(node, new_node)]."""
        if exception_sites not in EXCEPTION_SITES:
            raise ValueError(f"invalid exception_sites {exception_sites!r}")
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return None, {}
        text = _Text(source, tree)
        lines = source.splitlines(keepends=True)
        scope = C.scope_names(SH.C_strip("".join(lines[span[0] - 1: span[1]])))
        sites = _sites(tree, span)
        terms = [to_term(n) for n, _, _ in sites]
        live = sorted((s for s in self.steps.values() if s.status in ("active", "candidate")),
                      key=lambda s: (s.status != "active", -len(s.support), s.id))
        rank_of = {s.id: r for r, s in enumerate(live)}
        props = {"single": [], "multi": [], "pair": []}
        best = {}  # step id -> [(site index, values, ops, j, new_node)] for pairs
        raise_ids = set()
        if exception_sites == "raise":
            for r in ast.walk(tree):
                if isinstance(r, ast.Raise) and r.exc is not None:
                    raise_ids.add(id(r.exc))
                    if isinstance(r.exc, ast.Call):
                        raise_ids.add(id(r.exc.func))
        for rank, st in enumerate(live):
            if st.kind == "expr":
                only_raise = exception_sites == "raise" and "exc" in st.holes.values()
                groups = defaultdict(list)
                for i, t in enumerate(terms):
                    if only_raise and id(sites[i][0]) not in raise_ids:
                        continue
                    b: dict = {}
                    if match(st.lhs, t, b):
                        groups[json.dumps(term_to_json(tuple(sorted(b.items()))), default=repr)].append((i, b))
                filled = []  # per match group: its fillings, built
                for items in groups.values():
                    built = []
                    for values, ops, j in self._fillings(st, items[0][1], ctx, scope):
                        try:
                            built.append((ops, j, SH._subst(SH._fill_term(st.rhs, values), items[0][1])))
                        except Exception:
                            continue
                    if built:
                        filled.append((items, built))
                n_single = n_multi = 0
                # every place gets its best fillings before any place gets weaker ones (the cap keeps the best)
                for jj in range(max((len(b) for _, b in filled), default=0)):
                    for items, built in filled:
                        if jj >= len(built):
                            continue
                        ops, j, new = built[jj]
                        opr = max(SH.OP_RANK.get(o, 6) for o in ops)
                        for i, _ in items:
                            if n_single >= PER_STEP:
                                break
                            seen_ctx = 0 if sites[i][1] in st.contexts else 1
                            props["single"].append(((opr, j, seen_ctx, rank, n_single), [(sites[i][0], new)],
                                                    {"step": st.id, "ops": ops, "kind": "single"}))
                            n_single += 1
                            if j < PAIR_FILLINGS:
                                best.setdefault(st.id, []).append((i, ops, j, new))
                        if len(items) >= 2 and n_multi < PER_STEP:
                            props["multi"].append(((opr, j, -min(st.multi, 9), rank, n_multi),
                                                   [(sites[i][0], new) for i, _ in items],
                                                   {"step": st.id, "ops": ops, "kind": "multi", "sites": len(items)}))
                            n_multi += 1
            else:
                def fill(binding, node, tree_, st=st):
                    return [(SH._subst(SH._fill_term(st.rhs, values), binding), {"ops": ops, "rank": j})
                            for values, ops, j in self._fillings(st, binding, ctx, scope)]
                got = Procedure("stmts", st.lhs, st.rhs, 0).apply_detailed(source, span, fill, max_results=PER_STEP)
                for k, (prog, info) in enumerate(got):
                    opr = max(SH.OP_RANK.get(o, 6) for o in info.get("ops", ["structural"]))
                    props["single"].append(((opr, info.get("rank", 0), 0, rank, k), prog,
                                            {"step": st.id, "ops": info.get("ops"), "kind": "single"}))
        # pairs learned from at least PAIR_MIN_SUPPORT fixes, at two places of the function (DEV20 development: of
        # 60 two-change expression fixes, 24 change one statement, 14 a statement and one inside it, 22 two statements)
        inner, below = {}, {}

        def stmts_in(st):
            if id(st) not in inner:
                inner[id(st)] = {id(x) for x in ast.walk(st) if isinstance(x, ast.stmt)}
            return inner[id(st)]

        def nodes_in(n):
            if id(n) not in below:
                below[id(n)] = {id(x) for x in ast.walk(n)}
            return below[id(n)]
        for key, eids in self.pairs.items():
            if len(eids) < PAIR_MIN_SUPPORT:
                continue
            a, b = key.split("|")
            if a not in best or b not in best:
                continue
            prank = min(rank_of.get(a, 10 ** 6), rank_of.get(b, 10 ** 6))
            for (i, oa, ja, na), (k, ob, jb, nb) in itertools.product(best[a], best[b]):
                if i == k or (a == b and i > k):
                    continue
                n1, n2 = sites[i][0], sites[k][0]
                if id(n2) in nodes_in(n1) or id(n1) in nodes_in(n2):
                    continue  # one place inside the other
                s1, s2 = sites[i][2], sites[k][2]
                near = 0 if s1 is s2 else (1 if s1 is not None and s2 is not None and
                                           (id(s2) in stmts_in(s1) or id(s1) in stmts_in(s2)) else 2)
                opr = max(SH.OP_RANK.get(o, 6) for o in oa + ob)
                props["pair"].append(((near, opr, ja + jb, -len(eids), prank), [(n1, na), (n2, nb)],
                                      {"step": f"{a}+{b}", "ops": oa + ob, "kind": "pair"}))
        for k in props:
            props[k].sort(key=lambda x: x[0])
        return text, props

    def candidates_for(self, source: str, path: str, span: tuple, ctx: C.ProblemContext, limit: int = LIMIT,
                       as_candidates: bool = True, quota: dict | None = None, sharing: str = "key",
                       exception_sites: str = "any") -> list:
        """At most `limit` ranked candidates: each kind's best up to its share of the budget (QUOTA, scaled to
        `limit`), then whatever share a kind could not use goes to the others in rank order. `sharing` orders the
        candidates within a kind (SHARING); `exception_sites` limits where exception holes apply (EXCEPTION_SITES)."""
        if sharing not in SHARING:
            raise ValueError(f"invalid sharing {sharing!r}")
        if limit <= 0:
            return []
        text, props = self.proposals(source, span, ctx, exception_sites)
        if text is None:
            return []
        if sharing == "round_robin":
            props = {k: _round_robin(v) for k, v in props.items()}
        quota = quota or QUOTA
        total = sum(quota.values())
        share = {k: (limit * v) // total for k, v in quota.items()}
        share["single"] += limit - sum(share.values())
        out, seen = [], set()
        pos = {k: 0 for k in props}

        def take(kind, n):
            got = 0
            lst = props.get(kind, [])
            while got < n and pos[kind] < len(lst) and len(out) < limit:
                key, edits, info = lst[pos[kind]]
                pos[kind] += 1
                prog = edits if isinstance(edits, str) else text.build(edits)
                if prog is None:
                    continue
                try:
                    norm = ast.unparse(ast.parse(prog))
                except (SyntaxError, ValueError):
                    continue
                if norm in seen:
                    continue
                seen.add(norm)
                out.append((prog, info))
                got += 1
            return got
        for kind in ("single", "multi", "pair"):
            take(kind, share.get(kind, 0))
        for kind in ("single", "multi", "pair"):  # unused shares, in rank order of the kinds
            take(kind, limit - len(out))
        if not as_candidates:
            return out
        from .research import Candidate
        cands = []
        for prog, info in out:
            c = Candidate(path, prog, f"learned: step {info['step']} ({info['kind']}) via {'+'.join(info['ops'] or [])}")
            c.meta = {"kind": "learned_step", "family": "learned", "line": span[0], "line_score": 0.0, "line_rank": 99,
                      "original": info["step"], "option": info["kind"], "step": info["step"]}
            cands.append(c)
        return cands

    # ------------------------------------------------------------------ persistence
    def summary(self) -> dict:
        by: dict = {}
        for s in self.steps.values():
            by[s.status] = by.get(s.status, 0) + 1
        return {"steps": len(self.steps), "by_status": dict(sorted(by.items())), "examples": len(self.examples_seen),
                "pairs": len(self.pairs), "pairs_usable": sum(len(v) >= PAIR_MIN_SUPPORT for v in self.pairs.values()),
                "multi_site_steps": sum(s.multi > 0 for s in self.steps.values()), "string_edits": len(self.vocab.edits)}

    def body(self) -> dict:
        return {"steps": [self.steps[k].to_dict() for k in sorted(self.steps)],
                "pairs": {k: self.pairs[k] for k in sorted(self.pairs)}, "vocab": self.vocab.to_dict(),
                "examples_seen": sorted(self.examples_seen)}

    def save(self, path) -> str:
        body = json.loads(json.dumps(self.body()))  # sealed exactly as `load` will see it
        canon = json.dumps(body, sort_keys=True, separators=(",", ":"))
        seal = hashlib.sha256(canon.encode()).hexdigest()
        Path(path).write_text(json.dumps({"body": body, "sha256": seal}, sort_keys=True, separators=(",", ":")) + "\n")
        return seal

    @classmethod
    def load(cls, path) -> "StepLibrary":
        d = json.loads(Path(path).read_text())
        if hashlib.sha256(json.dumps(d["body"], sort_keys=True, separators=(",", ":")).encode()).hexdigest() != d.get("sha256"):
            raise ValueError("step library failed its integrity check (edited or corrupted); refusing to load")
        lib = cls()
        for s in d["body"]["steps"]:
            st = Step.from_dict(s)
            lib.steps[st.id] = st
        lib.pairs = {k: list(v) for k, v in d["body"]["pairs"].items()}
        lib.vocab = C.StringVocabulary.from_dict(d["body"]["vocab"])
        lib.examples_seen = set(d["body"]["examples_seen"])
        return lib
