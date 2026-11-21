"""DEV18 open procedures: learned fix SHAPES whose content is filled in from the problem.

DEV17's procedures kept the concrete content of the fixes they were learned from, so they applied almost nowhere else.
Here each learned edit is abstracted one step further, into a shape:
  - every identifier and constant on the pattern side becomes a variable (matched against any value);
  - on the replacement side, a value that was carried over reuses the pattern's variable, and a value the fix INTRODUCED
    becomes a typed CONTENT HOLE: string, number, name, attribute, exception, or boolean/None.
Shapes are grouped across examples; how often a shape occurs is its support (a data-driven prior). String edits also
feed a character-level `StringVocabulary`.

`ShapeLibrary.candidates_for` applies shapes to a function and fills each hole from `content.ProblemContext`: the failing
tests' literals, the module's own constants and names, learned string edits. Candidates are ranked by where their content
came from (problem-derived first), then by shape support; ASM's tests still decide acceptance.

Lifecycle (as DEV17): a shape with support >= 2 is ACTIVE, otherwise CANDIDATE; `record_outcome` adds field evidence and a
shape with 20 field fires and no success is RETIRED. The library is saved sealed (SHA-256).
"""
from __future__ import annotations

import ast
import hashlib
import itertools
import json
from pathlib import Path

from . import content as C
from .induction import Procedure, extract_edits, is_var, term_from_json, term_key, term_to_json

MAX_HOLES = 2
PER_MATCH = 24
PER_SHAPE = 40
LIMIT = 80
RETIRE_MIN_FIRES = 20
CONTENT_FIELDS = {("Constant", "value"), ("Name", "id"), ("Attribute", "attr"), ("keyword", "arg"), ("arg", "arg")}
OP_RANK = {"extend": 0, "test": 1, "problem": 1, "structural": 2, "vocab": 2, "scope": 3, "module": 4, "neighbour": 4,
           "builtin": 5, "small": 6, "literal": 6}


def _is_content_value(v) -> bool:
    return isinstance(v, (str, int, float)) and not isinstance(v, bool)


def _abstract(edit):
    """(lhs, rhs, holes, var_types) or None. holes: {cid: type}; types: str, num, name, attr, exc.
    var_types: {var: python type name of the value it replaced}, checked at match time (a shape learned from a string
    change must not fire on a number)."""
    var_of: dict = {}
    var_types: dict = {}

    def walk_l(t, head=None, fld=None):
        if t[0] == "=":
            if (head, fld) in CONTENT_FIELDS and _is_content_value(t[1]):
                key = repr(t[1])
                if key not in var_of:
                    var_of[key] = ("?", len(var_of))
                    var_types[len(var_of) - 1] = type(t[1]).__name__
                return var_of[key]
            return t
        if t[0] == "[]":
            return ("[]", tuple(walk_l(c, head, fld) for c in t[1]))
        return (t[0], tuple((f, walk_l(v, t[0], f)) for f, v in t[1]))
    holes: dict = {}

    def walk_r(t, head=None, fld=None, in_exc=False):
        if t[0] == "=":
            if (head, fld) in CONTENT_FIELDS and _is_content_value(t[1]):
                key = repr(t[1])
                if key in var_of:
                    return var_of[key]
                cid = f"c{len(holes)}"
                if in_exc and head == "Name":
                    holes[cid] = "exc"
                elif head == "Constant":
                    holes[cid] = "str" if isinstance(t[1], str) else "num"
                elif head == "Attribute":
                    holes[cid] = "attr"
                else:
                    holes[cid] = "name"
                return ("?", cid)
            if head == "Constant" and fld == "value" and (t[1] is None or isinstance(t[1], bool)):
                return t  # True/False/None stay as written
            return t
        if t[0] == "[]":
            return ("[]", tuple(walk_r(c, head, fld, in_exc) for c in t[1]))
        return (t[0], tuple((f, walk_r(v, t[0], f, in_exc or (t[0] == "ExceptHandler" and f == "type"))) for f, v in t[1]))
    lhs = walk_l(edit.lhs)
    rhs = walk_r(edit.rhs)
    if len(holes) > MAX_HOLES or is_var(lhs) or (lhs[0] == "[]" and all(is_var(x) for x in lhs[1])):
        return None
    if lhs == rhs:
        return None
    return lhs, rhs, holes, var_types


class Shape:
    def __init__(self, kind, lhs, rhs, holes, level, var_types=None):
        self.kind, self.lhs, self.rhs, self.holes, self.level = kind, lhs, rhs, dict(holes), level
        self.var_types = {int(k): v for k, v in (var_types or {}).items()}
        self.support: list = []
        self.sources: list = []
        self.field = {"fires": 0, "hits": 0, "problems": []}
        self.status = "candidate"

    @property
    def id(self) -> str:
        return "s" + term_key((self.kind, self.lhs, self.rhs, sorted(self.holes.items()), self.level,
                               sorted(self.var_types.items())))

    def describe(self) -> str:
        p = Procedure(self.kind, self.lhs, _holes_as_vars(self.rhs), self.level).describe()
        return p + "  holes=" + ",".join(f"{k}:{v}" for k, v in sorted(self.holes.items()))

    def to_dict(self) -> dict:
        # DEV18 bug fix (found by the DEV18 self-check): var_types is keyed by int; JSON turns the keys into strings,
        # whose sorted order differs from the ints' once there are 11 or more ("10" < "2"), so a library with such a
        # shape failed its own seal when loaded. Keys are written as strings; terms through term_to_json.
        return {"kind": self.kind, "lhs": term_to_json(self.lhs), "rhs": term_to_json(self.rhs), "holes": self.holes,
                "level": self.level, "var_types": {str(k): v for k, v in sorted(self.var_types.items())},
                "support": self.support, "sources": self.sources, "field": self.field, "status": self.status}

    @classmethod
    def from_dict(cls, d) -> "Shape":
        s = cls(d["kind"], term_from_json(d["lhs"]), term_from_json(d["rhs"]), d["holes"], d["level"], d.get("var_types"))
        s.support, s.sources, s.field, s.status = list(d["support"]), list(d["sources"]), dict(d["field"]), d["status"]
        return s


def _holes_as_vars(t):
    if is_var(t) and isinstance(t[1], str):
        return ("?", 900 + int(t[1][1:]))
    if t[0] == "=" or is_var(t):
        return t
    if t[0] == "[]":
        return ("[]", tuple(_holes_as_vars(c) for c in t[1]))
    return (t[0], tuple((f, _holes_as_vars(v)) for f, v in t[1]))


def _fill_term(t, values: dict):
    if is_var(t) and isinstance(t[1], str):
        return ("=", values[t[1]])
    if t[0] == "=" or is_var(t):
        return t
    if t[0] == "[]":
        return ("[]", tuple(_fill_term(c, values) for c in t[1]))
    return (t[0], tuple((f, _fill_term(v, values)) for f, v in t[1]))


def _subst(t, binding):
    if is_var(t) and not isinstance(t[1], str):
        return binding[t[1]]
    if t[0] == "=" or is_var(t):
        return t
    if t[0] == "[]":
        return ("[]", tuple(_subst(c, binding) for c in t[1]))
    return (t[0], tuple((f, _subst(v, binding)) for f, v in t[1]))


class ShapeLibrary:
    def __init__(self):
        self.shapes: dict = {}
        self.vocab = C.StringVocabulary()
        self.examples_seen: set = set()

    # ------------------------------------------------------------------ learning
    def learn(self, examples: list, source: str) -> list:
        """examples: [(before_fn, after_fn, example_id)]; returns ids of new shapes."""
        new = []
        for before, after, eid in examples:
            if eid in self.examples_seen:
                continue
            self.examples_seen.add(eid)
            seen_here = set()
            for e in extract_edits(before, after):
                if e.kind == "string":
                    old, left, right = e.lhs[1]
                    self.vocab.add(old, e.rhs[1], left, right)
                    continue
                ab = _abstract(e)
                if ab is None:
                    continue
                sh = Shape(e.kind, ab[0], ab[1], ab[2], e.level, ab[3])
                if sh.id in seen_here:
                    continue
                seen_here.add(sh.id)
                cur = self.shapes.get(sh.id)
                if cur is None:
                    self.shapes[sh.id] = cur = sh
                    new.append(sh.id)
                cur.support.append(eid)
                if source not in cur.sources:
                    cur.sources.append(source)
                if cur.status == "candidate" and len(set(cur.support)) >= 2:
                    cur.status = "active"
        return new

    # ------------------------------------------------------------------ applying
    def _fillers(self, htype, binding, ctx, scope):
        olds_str = [v[1] for v in binding.values() if v[0] == "=" and isinstance(v[1], str)]
        olds_num = [v[1] for v in binding.values() if v[0] == "=" and _is_content_value(v[1]) and not isinstance(v[1], str)]
        if htype == "str":
            out, seen = [], set()
            for old in olds_str or [""]:
                for val, op in C.string_fillers(old, ctx, self.vocab):
                    if val not in seen:
                        seen.add(val)
                        out.append((val, op))
            if not olds_str:
                out += [(s, "test") for s in ctx.test_strings[:6]]
            return out[:12]
        if htype == "num":
            return C.number_fillers(olds_num[0] if olds_num else 0, ctx)
        if htype == "exc":
            return C.exception_fillers(None, ctx)
        if htype == "attr":
            return C.attr_fillers(olds_str[0] if olds_str else None, ctx)
        return C.name_fillers(olds_str[0] if olds_str else None, scope, ctx)

    def candidates_for(self, source: str, path: str, span: tuple, ctx: C.ProblemContext, limit: int = LIMIT,
                       as_candidates: bool = True) -> list:
        """Ranked repair candidates (research.Candidate, or (program, info) when as_candidates=False)."""
        lines = source.splitlines(keepends=True)
        fn_src = "".join(lines[span[0] - 1: span[1]])
        scope = C.scope_names(C_strip(fn_src))
        live = [s for s in self.shapes.values() if s.status in ("active", "candidate")]
        live.sort(key=lambda s: (s.status != "active", -len(set(s.support)), s.level, s.id))
        pool = []
        for rank, sh in enumerate(live):
            def fill(binding, node, tree, sh=sh):
                for var, tname in sh.var_types.items():  # the matched values must have the learned types
                    b = binding.get(var)
                    if b is not None and b[0] == "=" and type(b[1]).__name__ != tname:
                        return []
                if not sh.holes:
                    return [(_subst(sh.rhs, binding), {"shape": sh.id, "ops": ["structural"], "rank": 0})]
                options = [[(cid, v, op) for v, op in self._fillers(t, binding, ctx, scope)] for cid, t in sorted(sh.holes.items())]
                if any(not o for o in options):
                    return []
                out = []
                for j, combo in enumerate(itertools.islice(itertools.product(*options), PER_MATCH)):
                    vals = {cid: v for cid, v, _ in combo}
                    out.append((_subst(_fill_term(sh.rhs, vals), binding),
                                {"shape": sh.id, "ops": [op for _, _, op in combo], "rank": j}))
                return out
            got = Procedure(sh.kind, sh.lhs, sh.rhs, sh.level).apply_detailed(source, span, fill, max_results=PER_SHAPE)
            for k, (prog, info) in enumerate(got):
                op_rank = max(OP_RANK.get(o, 6) for o in info.get("ops", ["structural"]))
                # where the content came from, then how good this filler is for ITS match, then shape support, then
                # position: every match gets its best fillers tried before any match's weaker ones
                pool.append(((op_rank, info.get("rank", 0), rank, k), prog, info))
        pool.sort(key=lambda x: x[0])
        out, seen = [], set()
        for _, prog, info in pool:
            try:
                n = ast.unparse(ast.parse(prog))
            except SyntaxError:
                continue
            if n in seen:
                continue
            seen.add(n)
            out.append((prog, info))
            if len(out) >= limit:
                break
        if not as_candidates:
            return out
        from .research import Candidate
        cands = []
        for prog, info in out:
            c = Candidate(path, prog, f"learned: shape {info['shape']} via {'+'.join(info['ops'])}")
            c.meta = {"kind": "learned_shape", "family": "learned", "line": span[0], "line_score": 0.0, "line_rank": 99,
                      "original": info["shape"], "option": "+".join(info["ops"]), "shape": info["shape"]}
            cands.append(c)
        return cands

    # ------------------------------------------------------------------ evidence
    def record_outcome(self, shape_id: str, success: bool, problem_id: str) -> None:
        sh = self.shapes[shape_id]
        sh.field["fires"] += 1
        sh.field["hits"] += int(success)
        sh.field["problems"].append([problem_id, bool(success)])
        if success and sh.status == "candidate":
            sh.status = "active"
        if sh.field["fires"] >= RETIRE_MIN_FIRES and sh.field["hits"] == 0:
            sh.status = "retired"

    def summary(self) -> dict:
        by: dict = {}
        for s in self.shapes.values():
            by[s.status] = by.get(s.status, 0) + 1
        return {"shapes": len(self.shapes), "by_status": dict(sorted(by.items())), "examples": len(self.examples_seen),
                "string_edits": len(self.vocab.edits)}

    def body(self) -> dict:
        return {"shapes": [self.shapes[k].to_dict() for k in sorted(self.shapes)], "vocab": self.vocab.to_dict(),
                "examples_seen": sorted(self.examples_seen)}

    def save(self, path) -> str:
        body = json.loads(json.dumps(self.body()))  # sealed exactly as `load` will see it
        canon = json.dumps(body, sort_keys=True, separators=(",", ":"))
        seal = hashlib.sha256(canon.encode()).hexdigest()
        Path(path).write_text(json.dumps({"body": body, "sha256": seal}, sort_keys=True, separators=(",", ":")) + "\n")
        return seal

    @classmethod
    def load(cls, path) -> "ShapeLibrary":
        d = json.loads(Path(path).read_text())
        if hashlib.sha256(json.dumps(d["body"], sort_keys=True, separators=(",", ":")).encode()).hexdigest() != d.get("sha256"):
            raise ValueError("shape library failed its integrity check (edited or corrupted); refusing to load")
        lib = cls()
        for s in d["body"]["shapes"]:
            sh = Shape.from_dict(s)
            lib.shapes[sh.id] = sh
        lib.vocab = C.StringVocabulary.from_dict(d["body"]["vocab"])
        lib.examples_seen = set(d["body"]["examples_seen"])
        return lib


def C_strip(fn_src: str) -> str:
    """The function's text without its own indentation, so it parses on its own."""
    lines = fn_src.splitlines(keepends=True)
    first = next((l for l in lines if l.strip()), "")
    ind = first[: len(first) - len(first.lstrip())]
    return "".join(l[len(ind):] if l.startswith(ind) else l for l in lines)
