"""DEV9 deep Python code understanding (static; never imports or executes project code).

Builds, per repository: control-flow graphs, reaching-definition data flow,
a resolved call graph, class hierarchies with attribute flow, and a module
dependency graph with cycle detection.

Honest scope: syntactic/structural analysis of Python only. Dynamic dispatch,
monkey-patching, getattr/eval, decorators that rewrite functions and untyped
receivers are NOT resolved; they are reported as unresolved with a reason so
callers can see how much of the graph is certain. This is understanding of
structure and data movement, not of intent (that is DEV10).
"""
from __future__ import annotations

import ast
import builtins
import hashlib
import os
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .analyzer import DEFAULT_EXCLUDES
from .research import tree_fingerprint

BUILTINS = frozenset(dir(builtins))
_FUNC = (ast.FunctionDef, ast.AsyncFunctionDef)
_SCOPES = _FUNC + (ast.ClassDef,)
_DYNAMIC = {"locals", "vars", "eval", "exec"}
_REPORT_DEAD = {"assign", "augassign", "annassign", "walrus", "except"}


# ----------------------------------------------------------------- data model
@dataclass
class FunctionInfo:
    qname: str
    module: str
    name: str
    kind: str  # function | method | nested
    class_qname: str | None
    path: str
    line: int
    end_line: int
    params: list[str]
    decorators: list[str]
    is_async: bool
    complexity: int
    cfg_nodes: int = 0
    cfg_edges: int = 0
    returns: int = 0
    raises: int = 0
    unreachable_lines: list[int] = field(default_factory=list)
    maybe_unbound: list[dict] = field(default_factory=list)
    dead_stores: list[dict] = field(default_factory=list)
    dynamic_scope: bool = False
    dataflow: str = "ok"  # ok | skipped_too_large


@dataclass
class ClassInfo:
    qname: str
    name: str
    module: str
    path: str
    line: int
    bases: list[str]
    resolved_bases: list[str]
    external_bases: list[str]
    methods: dict
    attribute_flow: dict
    read_never_written: list[str]


@dataclass
class ModuleInfo:
    path: str
    module: str
    sha256: str
    lines: int
    imports: list[dict]
    functions: list[str]
    classes: list[str]
    parse_error: str | None = None


@dataclass
class CallEdge:
    caller: str
    callee: str | None
    line: int
    kind: str  # direct | method | constructor | module_member | inferred_receiver | super
    reason: str | None = None  # why unresolved


# ------------------------------------------------------------- name collection
def _free_names(node) -> set[str]:
    loads, stores, declared = set(), set(), set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name):
            (stores if isinstance(sub.ctx, ast.Store) else loads).add(sub.id)
        elif isinstance(sub, ast.arg):
            stores.add(sub.arg)
        elif isinstance(sub, _SCOPES) and sub is not node:
            stores.add(sub.name)
        elif isinstance(sub, ast.ExceptHandler) and sub.name:
            stores.add(sub.name)
        elif isinstance(sub, (ast.Import, ast.ImportFrom)):
            for a in sub.names:
                stores.add((a.asname or a.name).split(".")[0])
        elif isinstance(sub, (ast.Global, ast.Nonlocal)):
            declared.update(sub.names)
    return (loads - stores) | declared


class _DU(ast.NodeVisitor):
    """Defs/uses of one statement header; nested scopes contribute free names only."""
    def __init__(self, kind="assign"):
        self.defs: list[tuple[str, str]] = []
        self.uses: set[str] = set()
        self.free: set[str] = set()
        self.kind = kind

    def visit_Name(self, n):
        if isinstance(n.ctx, ast.Store):
            self.defs.append((n.id, self.kind))
        else:
            self.uses.add(n.id)

    def visit_NamedExpr(self, n):
        self.visit(n.value)
        self.defs.append((n.target.id, "walrus"))

    def _scope(self, n):
        for d in getattr(n, "decorator_list", []):
            self.visit(d)
        args = getattr(n, "args", None)
        if isinstance(args, ast.arguments):
            for d in list(args.defaults) + [d for d in args.kw_defaults if d is not None]:
                self.visit(d)
        for b in getattr(n, "bases", []):
            self.visit(b)
        for k in getattr(n, "keywords", []):
            self.visit(k.value)
        self.free |= _free_names(n)

    visit_Lambda = visit_FunctionDef = visit_AsyncFunctionDef = visit_ClassDef = _scope

    def _comp(self, n):
        self.free |= _free_names(n)

    visit_ListComp = visit_SetComp = visit_DictComp = visit_GeneratorExp = _comp

    def visit_Call(self, n):
        if isinstance(n.func, ast.Name) and n.func.id in _DYNAMIC:
            self.uses.add("<dynamic>")
        self.generic_visit(n)


def _du(*nodes, kind="assign"):
    v = _DU(kind)
    for n in nodes:
        if n is not None:
            v.visit(n)
    return v


def _truthy_const(test) -> bool:
    return isinstance(test, ast.Constant) and bool(test.value) is True


# ------------------------------------------------------------------------ CFG
class _CFG:
    def __init__(self, fn):
        self.nodes: list[dict] = []
        self.succ: list[set[int]] = []
        self.loops: list[tuple[list[int], int]] = []
        self.try_stack: list[list[int]] = []
        self.declared: set[str] = set()
        self.returns = self.raises = 0
        self.entry = self._new("entry", fn.lineno)
        self.exit = self._new("exit", getattr(fn, "end_lineno", fn.lineno))
        a = fn.args
        params = [x.arg for x in a.posonlyargs + a.args + a.kwonlyargs]
        params += [x.arg for x in (a.vararg, a.kwarg) if x]
        self.params = params
        self.nodes[self.entry]["defs"] = [(p, "param") for p in params]
        # decorators/defaults are evaluated outside; body only here
        exits = self._seq(fn.body, [self.entry])
        for e in exits:
            self.succ[e].add(self.exit)

    def _new(self, kind, line, defs=(), uses=(), free=()):
        i = len(self.nodes)
        self.nodes.append({"kind": kind, "line": line, "defs": list(defs),
                           "uses": set(uses), "free": set(free)})
        self.succ.append(set())
        for lst in getattr(self, "try_stack", []):
            lst.append(i)
        return i

    def _link(self, preds, n):
        for p in preds:
            self.succ[p].add(n)

    def _seq(self, stmts, preds):
        cur = list(preds)
        for s in stmts:
            cur = self._stmt(s, cur)
        return cur

    def _simple(self, s, preds, kind="assign", **extra):
        d = _du(s, kind=kind)
        n = self._new("stmt", s.lineno, d.defs, d.uses, d.free)
        self._link(preds, n)
        return n

    def _stmt(self, s, preds):
        if isinstance(s, ast.If):
            d = _du(s.test)
            b = self._new("branch", s.lineno, d.defs, d.uses, d.free)
            self._link(preds, b)
            return self._seq(s.body, [b]) + (self._seq(s.orelse, [b]) if s.orelse else [b])
        if isinstance(s, (ast.While,)):
            d = _du(s.test)
            h = self._new("branch", s.lineno, d.defs, d.uses, d.free)
            self._link(preds, h)
            breaks: list[int] = []
            self.loops.append((breaks, h))
            body_exits = self._seq(s.body, [h])
            self._link(body_exits, h)
            self.loops.pop()
            if _truthy_const(s.test):
                else_exits: list[int] = []
            else:
                else_exits = self._seq(s.orelse, [h]) if s.orelse else [h]
            return else_exits + breaks
        if isinstance(s, (ast.For, ast.AsyncFor)):
            d = _du(s.target, kind="for")
            di = _du(s.iter)
            h = self._new("branch", s.lineno, d.defs, d.uses | di.uses, d.free | di.free)
            self._link(preds, h)
            breaks = []
            self.loops.append((breaks, h))
            body_exits = self._seq(s.body, [h])
            self._link(body_exits, h)
            self.loops.pop()
            else_exits = self._seq(s.orelse, [h]) if s.orelse else [h]
            return else_exits + breaks
        if isinstance(s, (ast.Try,)) or (hasattr(ast, "TryStar") and isinstance(s, ast.TryStar)):
            return self._try(s, preds)
        if isinstance(s, (ast.With, ast.AsyncWith)):
            defs, uses, free = [], set(), set()
            for it in s.items:
                a = _du(it.context_expr)
                b = _du(it.optional_vars, kind="with")
                defs += b.defs
                uses |= a.uses | b.uses
                free |= a.free | b.free
            n = self._new("stmt", s.lineno, defs, uses, free)
            self._link(preds, n)
            return self._seq(s.body, [n])
        if hasattr(ast, "Match") and isinstance(s, ast.Match):
            return self._match(s, preds)
        if isinstance(s, ast.Return):
            n = self._simple(s, preds)
            self.succ[n].add(self.exit)
            self.returns += 1
            return []
        if isinstance(s, ast.Raise):
            n = self._simple(s, preds)
            self.succ[n].add(self.exit)
            self.raises += 1
            return []
        if isinstance(s, ast.Break):
            n = self._new("stmt", s.lineno)
            self._link(preds, n)
            if self.loops:
                self.loops[-1][0].append(n)
            return []
        if isinstance(s, ast.Continue):
            n = self._new("stmt", s.lineno)
            self._link(preds, n)
            if self.loops:
                self.succ[n].add(self.loops[-1][1])
            return []
        if isinstance(s, _SCOPES):
            d = _du(s)
            n = self._new("stmt", s.lineno, [(s.name, "def")], d.uses, d.free)
            self._link(preds, n)
            return [n]
        if isinstance(s, (ast.Global, ast.Nonlocal)):
            self.declared |= set(s.names)
            n = self._new("stmt", s.lineno)
            self._link(preds, n)
            return [n]
        if isinstance(s, ast.Import):
            n = self._new("stmt", s.lineno, [((a.asname or a.name).split(".")[0], "import") for a in s.names])
        elif isinstance(s, ast.ImportFrom):
            n = self._new("stmt", s.lineno, [(a.asname or a.name, "import") for a in s.names if a.name != "*"])
        elif isinstance(s, ast.AugAssign):
            d = _du(s.target, kind="augassign"), _du(s.value)
            uses = d[0].uses | d[1].uses | ({s.target.id} if isinstance(s.target, ast.Name) else set())
            n = self._new("stmt", s.lineno, d[0].defs, uses, d[0].free | d[1].free)
        elif isinstance(s, ast.AnnAssign):
            d = _du(s.target, kind="annassign")
            dv = _du(s.value)
            defs = d.defs if s.value is not None else []
            n = self._new("stmt", s.lineno, defs, d.uses | dv.uses, d.free | dv.free)
        elif isinstance(s, ast.Assign):
            kind = "unpack" if any(isinstance(t, (ast.Tuple, ast.List)) for t in s.targets) else "assign"
            n = self._simple(s, preds, kind)
            return [n]
        else:
            n = self._simple(s, preds)
            return [n]
        self._link(preds, n)
        return [n]

    def _try(self, s, preds):
        t = self._new("join", s.lineno)
        self._link(preds, t)
        self.try_stack.append([])
        body_exits = self._seq(s.body, [t])
        body_nodes = self.try_stack.pop()
        sources = [t] + body_nodes
        handler_exits: list[int] = []
        for h in s.handlers:
            d = _du(h.type)
            hn = self._new("branch", h.lineno, [(h.name, "except")] if h.name else [], d.uses, d.free)
            for src in sources:
                self.succ[src].add(hn)
            handler_exits += self._seq(h.body, [hn])
        else_exits = self._seq(s.orelse, body_exits) if s.orelse else body_exits
        normal = else_exits + handler_exits
        if not s.finalbody:
            return normal
        entry = self._new("join", s.finalbody[0].lineno)
        self._link(normal, entry)
        exits = self._seq(s.finalbody, [entry])
        # exceptional path: finally runs, then the exception propagates (no fall-through)
        exc = self._new("join", s.finalbody[0].lineno)
        for src in sources:
            self.succ[src].add(exc)
        for e in self._seq(s.finalbody, [exc]):
            self.succ[e].add(self.exit)
        return exits

    def _match(self, s, preds):
        d = _du(s.subject)
        m = self._new("branch", s.lineno, d.defs, d.uses, d.free)
        self._link(preds, m)
        exits: list[int] = []
        irrefutable = False
        for c in s.cases:
            defs, vals = [], []
            for p in ast.walk(c.pattern):
                nm = getattr(p, "name", None) if isinstance(p, (ast.MatchAs, ast.MatchStar)) else None
                if nm:
                    defs.append((nm, "match"))
                if isinstance(p, ast.MatchMapping) and p.rest:
                    defs.append((p.rest, "match"))
                if isinstance(p, ast.MatchValue):
                    vals.append(p.value)
            g = _du(c.guard, *vals)
            cn = self._new("branch", c.pattern.lineno, defs, g.uses, g.free)
            self.succ[m].add(cn)
            exits += self._seq(c.body, [cn])
            if isinstance(c.pattern, ast.MatchAs) and c.pattern.pattern is None and c.guard is None:
                irrefutable = True
        if not irrefutable:
            exits.append(m)
        return exits

    # ------------------------------------------------------------- analysis
    def reachable(self) -> set[int]:
        seen, q = {self.entry}, deque([self.entry])
        while q:
            n = q.popleft()
            for m in self.succ[n]:
                if m not in seen:
                    seen.add(m)
                    q.append(m)
        return seen

    def dataflow(self, reach: set[int]):
        nodes, succ = self.nodes, self.succ
        local = {n for nd in nodes for n, _ in nd["defs"]} - self.declared
        defs_all: list[tuple[int, str, str, int]] = []  # node, name, kind, line
        gen: list[set[int]] = [set() for _ in nodes]
        for i, nd in enumerate(nodes):
            for name, kind in nd["defs"]:
                if name in local:
                    defs_all.append((i, name, kind, nd["line"]))
                    gen[i].add(len(defs_all) - 1)
        unbound: dict[str, int] = {}
        for name in sorted(local - set(self.params)):
            defs_all.append((self.entry, name, "unbound", nodes[self.entry]["line"]))
            unbound[name] = len(defs_all) - 1
        names_at = [{defs_all[d][1] for d in g} for g in gen]
        preds: dict[int, list[int]] = defaultdict(list)
        for i in reach:
            for j in succ[i]:
                if j in reach:
                    preds[j].append(i)
        IN = [set() for _ in nodes]
        OUT = [set() for _ in nodes]
        work = deque(sorted(reach))
        queued = set(work)
        while work:
            i = work.popleft()
            queued.discard(i)
            if i == self.entry:
                IN[i] = set()
                new_out = set(gen[i]) | set(unbound.values())
            else:
                IN[i] = set().union(*(OUT[p] for p in preds[i])) if preds[i] else set()
                new_out = {d for d in IN[i] if defs_all[d][1] not in names_at[i]} | gen[i]
            if new_out != OUT[i]:
                OUT[i] = new_out
                for j in succ[i]:
                    if j in reach and j not in queued:
                        work.append(j)
                        queued.add(j)
        return local, defs_all, IN


def _complexity(fn) -> int:
    total = 1
    stack = list(ast.iter_child_nodes(fn))
    while stack:
        n = stack.pop()
        if isinstance(n, _SCOPES):
            continue
        if isinstance(n, (ast.If, ast.IfExp, ast.Assert, ast.ExceptHandler)):
            total += 1
        elif isinstance(n, (ast.For, ast.AsyncFor, ast.While)):
            total += 1 + bool(n.orelse)
        elif isinstance(n, ast.Try) or (hasattr(ast, "TryStar") and isinstance(n, ast.TryStar)):
            total += bool(n.orelse)
        elif isinstance(n, ast.BoolOp):
            total += len(n.values) - 1
        elif isinstance(n, ast.comprehension):
            total += 1 + len(n.ifs)
        elif hasattr(ast, "match_case") and isinstance(n, ast.match_case):
            total += 1
        stack.extend(ast.iter_child_nodes(n))
    return total


def analyze_function(fn, max_nodes=3000) -> dict:
    cfg = _CFG(fn)
    reach = cfg.reachable()
    out = {"cfg_nodes": len(cfg.nodes), "cfg_edges": sum(len(s) for s in cfg.succ),
           "returns": cfg.returns, "raises": cfg.raises, "maybe_unbound": [], "dead_stores": [],
           "dynamic_scope": any("<dynamic>" in nd["uses"] for nd in cfg.nodes), "dataflow": "ok",
           "unreachable_lines": sorted(
               {nd["line"] for i, nd in enumerate(cfg.nodes) if i not in reach and nd["kind"] in {"stmt", "branch"}}
               - {nd["line"] for i, nd in enumerate(cfg.nodes) if i in reach}),
           "use_def": []}
    if len(cfg.nodes) > max_nodes:
        out["dataflow"] = "skipped_too_large"
        return out
    local, defs_all, IN = cfg.dataflow(reach)
    closure = set()
    for nd in cfg.nodes:
        closure |= nd["free"]
    used: set[int] = set()
    seen_unbound: set[tuple[str, int]] = set()
    for i in sorted(reach):
        nd = cfg.nodes[i]
        for name in sorted(nd["uses"]):
            if name not in local:
                continue
            reaching = [d for d in IN[i] if defs_all[d][1] == name]
            used.update(reaching)
            real = sorted({defs_all[d][3] for d in reaching if defs_all[d][2] != "unbound"})
            out["use_def"].append({"name": name, "line": nd["line"], "defs": real})
            if any(defs_all[d][2] == "unbound" for d in reaching) and (name, nd["line"]) not in seen_unbound:
                seen_unbound.add((name, nd["line"]))
                out["maybe_unbound"].append({"name": name, "line": nd["line"],
                                             "definitely": not real})
    if not out["dynamic_scope"]:
        seen = set()
        for d, (node, name, kind, line) in enumerate(defs_all):
            if (kind in _REPORT_DEAD and node in reach and d not in used and name not in closure
                    and not name.startswith("_") and (name, line) not in seen):
                seen.add((name, line))
                out["dead_stores"].append({"name": name, "line": line})
    out["maybe_unbound"].sort(key=lambda x: (x["line"], x["name"]))
    out["dead_stores"].sort(key=lambda x: (x["line"], x["name"]))
    return out


def _runtime_imports(tree) -> set[int]:
    out: set[int] = set()

    def visit(stmts):
        for st in stmts:
            if isinstance(st, _FUNC):
                continue
            if isinstance(st, (ast.Import, ast.ImportFrom)):
                out.add(id(st))
            elif isinstance(st, ast.If):
                t = st.test
                guard = (isinstance(t, ast.Name) and t.id == "TYPE_CHECKING") or \
                        (isinstance(t, ast.Attribute) and t.attr == "TYPE_CHECKING")
                if not guard:
                    visit(st.body)
                visit(st.orelse)
            else:
                for fld in ("body", "orelse", "finalbody"):
                    visit(getattr(st, fld, []) or [])
                for h in getattr(st, "handlers", []) or []:
                    visit(h.body)
    visit(tree.body)
    return out


# ------------------------------------------------------------ repository level
@dataclass
class UnderstandingReport:
    root: str
    fingerprint: str
    modules: list[ModuleInfo]
    classes: list[ClassInfo]
    functions: list[FunctionInfo]
    call_edges: list[CallEdge]
    module_edges: list[tuple[str, str]]
    module_cycles: list[list[str]]  # import-time cycles (can break imports)
    lazy_module_cycles: list[list[str]]  # cycles only via function-level / TYPE_CHECKING imports
    recursion_groups: list[list[str]]
    diagnostics: list[dict]
    stats: dict
    _flows: dict = field(default_factory=dict, repr=False)

    def to_dict(self) -> dict:
        d = {k: v for k, v in asdict(self).items() if k != "_flows"}
        return d

    def summary(self) -> dict:
        return dict(self.stats, fingerprint=self.fingerprint, module_cycles=len(self.module_cycles),
                    lazy_module_cycles=len(self.lazy_module_cycles),
                    recursion_groups=len(self.recursion_groups), diagnostics=len(self.diagnostics))

    # ---- queries
    def _fn(self, qname):
        for f in self.functions:
            if f.qname == qname:
                return f
        raise KeyError(qname)

    def callees(self, qname: str, transitive=False) -> list[str]:
        return self._walk({c.caller: [] for c in self.call_edges}, qname, transitive, forward=True)

    def callers(self, qname: str, transitive=False) -> list[str]:
        return self._walk(None, qname, transitive, forward=False)

    def _walk(self, _unused, start, transitive, forward):
        adj = defaultdict(set)
        for c in self.call_edges:
            if c.callee is not None:
                if forward:
                    adj[c.caller].add(c.callee)
                else:
                    adj[c.callee].add(c.caller)
        seen, q = set(), deque([start])
        while q:
            n = q.popleft()
            for m in sorted(adj[n]):
                if m not in seen and m != start:
                    seen.add(m)
                    if transitive:
                        q.append(m)
        return sorted(seen)

    def impacted_modules(self, path_or_module: str) -> list[str]:
        """Modules that (transitively) import the given module: the blast radius of editing it."""
        by_path = {m.path: m.module for m in self.modules}
        target = by_path.get(path_or_module, path_or_module)
        rev = defaultdict(set)
        for a, b in self.module_edges:
            rev[b].add(a)
        seen, q = set(), deque([target])
        while q:
            n = q.popleft()
            for m in sorted(rev[n]):
                if m not in seen and m != target:
                    seen.add(m)
                    q.append(m)
        return sorted(seen)

    def use_def(self, qname: str) -> list[dict]:
        return list(self._flows.get(qname, []))

    def unreferenced_functions(self) -> list[str]:
        """CANDIDATES only: no static caller found. Public API, callbacks, dunder and dynamic use are not seen."""
        called = {c.callee for c in self.call_edges if c.callee}
        out = []
        for f in self.functions:
            if f.kind == "nested" or f.qname in called or (f.name.startswith("__") and f.name.endswith("__")):
                continue
            if any(d.split(".")[-1] in {"property", "setter", "abstractmethod", "fixture"} for d in f.decorators):
                continue
            out.append(f.qname)
        return sorted(out)


class CodeUnderstanding:
    def __init__(self, max_files=2000, max_file_bytes=1_000_000, max_cfg_nodes=3000):
        self.max_files = max_files
        self.max_file_bytes = max_file_bytes
        self.max_cfg_nodes = max_cfg_nodes

    # ---------------------------------------------------------- discovery
    def _discover(self, base: Path, diags):
        found = []
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(d for d in dirnames if d not in DEFAULT_EXCLUDES
                                 and not os.path.islink(os.path.join(dirpath, d)))
            for fn in sorted(filenames):
                p = Path(dirpath) / fn
                if not fn.endswith(".py") or p.is_symlink():
                    continue
                rel = p.relative_to(base).as_posix()
                if p.stat().st_size > self.max_file_bytes:
                    diags.append({"code": "file_too_large", "path": rel})
                    continue
                found.append(rel)
        if len(found) > self.max_files:
            diags.append({"code": "file_limit", "message": f"{len(found)} files; analyzing first {self.max_files}"})
            found = found[: self.max_files]
        return found

    @staticmethod
    def _module_name(rel: str) -> str:
        parts = rel[:-3].split("/")
        if parts and parts[0] == "src" and len(parts) > 1:
            parts = parts[1:]
        if parts[-1] == "__init__":
            parts = parts[:-1]
        return ".".join(parts) or "__init__"

    # --------------------------------------------------------------- main
    def analyze(self, root: str | Path) -> UnderstandingReport:
        base = Path(root).resolve(strict=True)
        if not base.is_dir():
            raise NotADirectoryError(str(base))
        diags: list[dict] = []
        files = self._discover(base, diags)
        trees: dict[str, tuple[ast.Module, str, int]] = {}
        modules: dict[str, ModuleInfo] = {}
        for rel in files:
            raw = (base / rel).read_bytes()
            mname = self._module_name(rel)
            info = ModuleInfo(rel, mname, hashlib.sha256(raw).hexdigest(), raw.count(b"\n") + 1, [], [], [])
            try:
                tree = ast.parse(raw.decode("utf-8"), filename=rel)
                trees[mname] = (tree, rel, 0)
            except (SyntaxError, UnicodeDecodeError, ValueError, RecursionError) as exc:
                info.parse_error = f"{type(exc).__name__}: {str(exc)[:200]}"
                diags.append({"code": "parse_error", "path": rel, "message": info.parse_error})
            modules[mname] = info
        is_pkg = {m.module for m in modules.values() if m.path.endswith("__init__.py")}

        # ---- pass 1: declarations, imports
        functions: dict[str, FunctionInfo] = {}
        fnodes: dict[str, ast.AST] = {}
        classes: dict[str, dict] = {}
        aliases: dict[str, dict] = {m: {} for m in modules}
        module_edges: set[tuple[str, str]] = set()
        runtime_edges: set[tuple[str, str]] = set()

        def resolve_relative(mname, level, mod):
            pkg = mname if mname in is_pkg else ".".join(mname.split(".")[:-1])
            parts = pkg.split(".") if pkg else []
            if level > 1:
                parts = parts[: len(parts) - (level - 1)]
            return ".".join(parts + ([mod] if mod else []))

        for mname, (tree, rel, _) in sorted(trees.items()):
            minfo = modules[mname]
            runtime_nodes = _runtime_imports(tree)
            for node in ast.walk(tree):
                targets: set[str] = set()
                if isinstance(node, ast.Import):
                    for a in node.names:
                        resolved = a.name if a.name in modules else None
                        top = a.name.split(".")[0]
                        if a.asname:
                            aliases[mname][a.asname] = ("module", a.name)
                        else:
                            aliases[mname][top] = ("module", top)
                        minfo.imports.append({"target": a.name, "line": node.lineno, "resolved": resolved,
                                              "import_time": id(node) in runtime_nodes})
                        for cand in {a.name}:
                            if cand in modules:
                                targets.add(cand)
                elif isinstance(node, ast.ImportFrom):
                    target = resolve_relative(mname, node.level, node.module) if node.level else (node.module or "")
                    minfo.imports.append({"target": ("." * node.level) + (node.module or ""),
                                          "line": node.lineno, "resolved": target if target in modules else None,
                                          "import_time": id(node) in runtime_nodes})
                    needs_target = False
                    for a in node.names:
                        if a.name == "*":
                            needs_target = True
                            continue
                        full = f"{target}.{a.name}" if target else a.name
                        if full in modules:
                            aliases[mname][a.asname or a.name] = ("module", full)
                            targets.add(full)
                        else:
                            aliases[mname][a.asname or a.name] = ("symbol", target, a.name)
                            needs_target = True
                    if needs_target and target in modules:
                        targets.add(target)
                targets.discard(mname)
                for t in targets:
                    module_edges.add((mname, t))
                    if id(node) in runtime_nodes:
                        runtime_edges.add((mname, t))

        def collect(mname, rel, body, prefix, class_q, kind):
            for node in body:
                if isinstance(node, _FUNC):
                    q = f"{prefix}.{node.name}"
                    a = node.args
                    params = [x.arg for x in a.posonlyargs + a.args + a.kwonlyargs]
                    params += [x.arg for x in (a.vararg, a.kwarg) if x]
                    decos = []
                    for d in node.decorator_list:
                        try:
                            decos.append(ast.unparse(d))
                        except Exception:
                            decos.append("?")
                    fi = FunctionInfo(q, mname, node.name, kind, class_q, rel, node.lineno,
                                      getattr(node, "end_lineno", node.lineno), params, decos,
                                      isinstance(node, ast.AsyncFunctionDef), _complexity(node))
                    functions[q] = fi
                    fnodes[q] = node
                    modules[mname].functions.append(q)
                    collect(mname, rel, node.body, q, None, "nested")
                    # nested classes inside functions are not indexed
                elif isinstance(node, ast.ClassDef) and kind != "nested":
                    q = f"{prefix}.{node.name}"
                    classes[q] = {"node": node, "module": mname, "path": rel}
                    modules[mname].classes.append(q)
                    collect(mname, rel, node.body, q, q, "method")

        for mname, (tree, rel, _) in sorted(trees.items()):
            collect(mname, rel, tree.body, mname, None, "function")
            for node in ast.walk(tree):  # nested defs under if/try at module level
                pass

        # ---- member lookup helpers
        def lookup_member(mod: str, name: str, depth=0):
            q = f"{mod}.{name}"
            if q in functions or q in classes:
                return q
            if depth < 5 and mod in aliases and name in aliases[mod]:
                al = aliases[mod][name]
                if al[0] == "symbol":
                    return lookup_member(al[1], al[2], depth + 1)
                if al[0] == "module" and al[1] in modules:
                    return ("module", al[1])
            return None

        def resolve_class_name(mname, expr) -> str | None:
            parts = []
            e = expr
            while isinstance(e, ast.Attribute):
                parts.append(e.attr)
                e = e.value
            if not isinstance(e, ast.Name):
                return None
            parts = [e.id] + parts[::-1]
            first = parts[0]
            if f"{mname}.{first}" in classes and len(parts) == 1:
                return f"{mname}.{first}"
            al = aliases[mname].get(first)
            if al is None:
                return None
            if al[0] == "symbol":
                r = lookup_member(al[1], al[2])
                return r if isinstance(r, str) and r in classes and len(parts) == 1 else None
            mod = al[1]
            rest = parts[1:]
            while rest:
                if f"{mod}.{rest[0]}" in modules:
                    mod = f"{mod}.{rest[0]}"
                    rest = rest[1:]
                else:
                    break
            if len(rest) == 1:
                r = lookup_member(mod, rest[0])
                return r if isinstance(r, str) and r in classes else None
            return None

        # ---- classes
        class_infos: dict[str, ClassInfo] = {}
        for cq, c in sorted(classes.items()):
            node, mname = c["node"], c["module"]
            raw_bases, resolved, external = [], [], []
            for b in node.bases:
                try:
                    raw_bases.append(ast.unparse(b))
                except Exception:
                    raw_bases.append("?")
                r = resolve_class_name(mname, b)
                (resolved if r else external).append(r or raw_bases[-1])
            methods = {fn.name: f"{cq}.{fn.name}" for fn in node.body if isinstance(fn, _FUNC)}
            class_infos[cq] = ClassInfo(cq, node.name, mname, c["path"], node.lineno, raw_bases,
                                        resolved, external, methods, {}, [])

        def mro(cq, seen=None):
            seen = seen if seen is not None else set()
            if cq in seen or cq not in class_infos:
                return []
            seen.add(cq)
            out = [cq]
            for b in class_infos[cq].resolved_bases:
                out += mro(b, seen)
            return out

        def find_method(cq, name):
            for k in mro(cq):
                m = class_infos[k].methods.get(name)
                if m:
                    return m
            return None

        # ---- attribute flow
        for cq, ci in class_infos.items():
            node = classes[cq]["node"]
            flow = defaultdict(lambda: {"writers": set(), "readers": set()})
            for st in node.body:
                if isinstance(st, ast.Assign):
                    for t in st.targets:
                        for n in ast.walk(t):
                            if isinstance(n, ast.Name):
                                flow[n.id]["writers"].add("<class body>")
                elif isinstance(st, ast.AnnAssign) and st.value is not None and isinstance(st.target, ast.Name):
                    flow[st.target.id]["writers"].add("<class body>")
            for fn in node.body:
                if not isinstance(fn, _FUNC) or not fn.args.args:
                    continue
                if any(ast.unparse(d) == "staticmethod" for d in fn.decorator_list):
                    continue
                recv = fn.args.args[0].arg
                for n in ast.walk(fn):
                    if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == recv:
                        role = "writers" if isinstance(n.ctx, (ast.Store, ast.Del)) else "readers"
                        flow[n.attr][role].add(fn.name)
            ci.attribute_flow = {a: {"writers": sorted(v["writers"]), "readers": sorted(v["readers"])}
                                 for a, v in sorted(flow.items())}
            chain = mro(cq)
            inherits_external = any(class_infos[k].external_bases for k in chain)
            if not inherits_external:
                all_methods = {m for k in chain for m in class_infos[k].methods}
                written = set()
                for k in chain:
                    pass
                for k in chain:
                    for a, v in class_infos[k].attribute_flow.items() if k != cq else ci.attribute_flow.items():
                        if v["writers"]:
                            written.add(a)
                ci.read_never_written = sorted(a for a, v in ci.attribute_flow.items()
                                               if v["readers"] and a not in written and a not in all_methods)

        # ---- calls
        edges: list[CallEdge] = []
        flows: dict = {}

        def scope_chain(q):
            parts = q.split(".")
            return [".".join(parts[:i]) for i in range(len(parts), 0, -1)]

        def local_types(fn_node, mname) -> dict[str, str]:
            counts, ctor = defaultdict(int), {}
            for n in ast.walk(fn_node):
                if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
                    counts[n.id] += 1
                if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) \
                        and isinstance(n.value, ast.Call):
                    c = resolve_class_name(mname, n.value.func)
                    if c:
                        ctor[n.targets[0].id] = c
            return {k: v for k, v in ctor.items() if counts[k] == 1}

        def ctor_target(cq):
            return find_method(cq, "__init__") or cq

        def resolve_call(call, mname, fq, class_q, recv_name, ltypes, local_names=frozenset()):
            f = call.func
            if isinstance(f, ast.Name):
                n = f.id
                for sc in scope_chain(fq) if fq else []:
                    cand = f"{sc}.{n}"
                    if sc in functions and cand in functions:
                        return cand, "direct", None
                if n in local_names:
                    return None, "direct", "local_callable"
                m = lookup_member(mname, n)
                if isinstance(m, str):
                    return (ctor_target(m), "constructor", None) if m in classes else (m, "direct", None)
                if n in aliases[mname] and aliases[mname][n][0] == "symbol":
                    return None, "direct", "external"
                if n in BUILTINS:
                    return None, "direct", "builtin"
                return None, "direct", "unknown_name"
            if isinstance(f, ast.Attribute):
                # super().m()
                if isinstance(f.value, ast.Call) and isinstance(f.value.func, ast.Name) \
                        and f.value.func.id == "super" and class_q:
                    for b in class_infos[class_q].resolved_bases:
                        m = find_method(b, f.attr)
                        if m:
                            return m, "super", None
                    return None, "super", "attribute_not_found_in_class_hierarchy"
                parts, e = [], f
                while isinstance(e, ast.Attribute):
                    parts.append(e.attr)
                    e = e.value
                if not isinstance(e, ast.Name):
                    return None, "method", "dynamic_receiver"
                parts = parts[::-1]
                head = e.id
                if head == recv_name and class_q and len(parts) == 1:
                    m = find_method(class_q, parts[0])
                    if m:
                        return m, "method", None
                    ext = any(class_infos[k].external_bases for k in mro(class_q))
                    return None, "method", "external_base" if ext else "attribute_not_found_in_class_hierarchy"
                if head in ltypes and len(parts) == 1:
                    m = find_method(ltypes[head], parts[0])
                    if m:
                        return m, "inferred_receiver", None
                if f"{mname}.{head}" in classes and len(parts) == 1:
                    m = find_method(f"{mname}.{head}", parts[0])
                    if m:
                        return m, "method", None
                al = aliases[mname].get(head)
                if al is None:
                    return None, "method", "builtin" if head in BUILTINS else "dynamic_receiver"
                if al[0] == "symbol":
                    r = lookup_member(al[1], al[2])
                    if isinstance(r, str) and r in classes and len(parts) == 1:
                        m = find_method(r, parts[0])
                        if m:
                            return m, "method", None
                    if isinstance(r, tuple) and r[0] == "module":
                        al = ("module", r[1])
                    else:
                        return None, "method", "external" if r is None else "dynamic_receiver"
                mod, rest = al[1], parts
                while rest and f"{mod}.{rest[0]}" in modules:
                    mod = f"{mod}.{rest[0]}"
                    rest = rest[1:]
                if mod not in modules:
                    return None, "module_member", "external"
                if len(rest) == 1:
                    r = lookup_member(mod, rest[0])
                    if isinstance(r, str):
                        return (ctor_target(r), "constructor", None) if r in classes else (r, "module_member", None)
                    return None, "module_member", "member_not_found"
                if len(rest) == 2:
                    r = lookup_member(mod, rest[0])
                    if isinstance(r, str) and r in classes:
                        m = find_method(r, rest[1])
                        if m:
                            return m, "method", None
                return None, "module_member", "dynamic_receiver"
            return None, "direct", "dynamic_receiver"

        def calls_in(body_nodes):
            stack = list(body_nodes)
            while stack:
                n = stack.pop()
                if isinstance(n, _SCOPES):
                    continue
                if isinstance(n, ast.Call):
                    yield n
                stack.extend(ast.iter_child_nodes(n))

        for q, fi in sorted(functions.items()):
            node = fnodes[q]
            recv = None
            if fi.class_qname and node.args.args and not any(
                    ast.unparse(d) == "staticmethod" for d in node.decorator_list):
                recv = node.args.args[0].arg
            lt = local_types(node, fi.module)
            lnames = {x.arg for x in ast.walk(node.args) if isinstance(x, ast.arg)}
            lnames |= {x.id for x in ast.walk(node) if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Store)}
            for call in sorted(calls_in(node.body), key=lambda c: (c.lineno, c.col_offset)):
                callee, kind, why = resolve_call(call, fi.module, q, fi.class_qname, recv, lt, lnames)
                edges.append(CallEdge(q, callee, call.lineno, kind, why))
            res = analyze_function(node, self.max_cfg_nodes)
            flows[q] = res.pop("use_def")
            for k, v in res.items():
                setattr(fi, k, v)
        for mname, (tree, rel, _) in sorted(trees.items()):
            top = [n for n in tree.body if not isinstance(n, _SCOPES)]
            for call in sorted(calls_in(top), key=lambda c: (c.lineno, c.col_offset)):
                callee, kind, why = resolve_call(call, mname, None, None, None, {})
                edges.append(CallEdge(f"{mname}.<module>", callee, call.lineno, kind, why))

        # ---- graph analysis
        mod_adj = defaultdict(set)
        for a, b in module_edges:
            mod_adj[a].add(b)
        rt_adj = defaultdict(set)
        for a, b in runtime_edges:
            rt_adj[a].add(b)
        cycles = [sorted(c) for c in _scc(sorted(modules), rt_adj) if len(c) > 1]
        all_cycles = [sorted(c) for c in _scc(sorted(modules), mod_adj) if len(c) > 1]
        lazy_cycles = [c for c in all_cycles if not any(set(c) <= set(rc) for rc in cycles)]
        call_adj = defaultdict(set)
        for e in edges:
            if e.callee:
                call_adj[e.caller].add(e.callee)
        recursion = [sorted(c) for c in _scc(sorted(functions), call_adj)
                     if len(c) > 1 or (len(c) == 1 and c[0] in call_adj[c[0]])]

        total = len(edges)
        resolved = sum(1 for e in edges if e.callee)
        external = sum(1 for e in edges if e.reason in {"builtin", "external"})
        reasons = defaultdict(int)
        for e in edges:
            if e.reason:
                reasons[e.reason] += 1
        in_repo = total - external
        stats = {"modules": len(modules), "parsed_modules": len(trees), "functions": len(functions),
                 "classes": len(classes), "call_sites": total, "resolved_calls": resolved,
                 "external_or_builtin_calls": external,
                 "repo_call_resolution_rate": round(resolved / in_repo, 4) if in_repo else None,
                 "unresolved_reasons": dict(sorted(reasons.items())),
                 "module_edges": len(module_edges)}
        report = UnderstandingReport(
            str(base), tree_fingerprint(base), [modules[m] for m in sorted(modules)],
            [class_infos[c] for c in sorted(class_infos)], [functions[f] for f in sorted(functions)],
            sorted(edges, key=lambda e: (e.caller, e.line, e.callee or "")), sorted(module_edges),
            cycles, lazy_cycles, recursion, diags, stats)
        report._flows = flows
        return report


def _scc(nodes, adj):
    """Iterative Tarjan strongly connected components."""
    index, low, on, stack, out, counter = {}, {}, set(), [], [], [0]
    for root in nodes:
        if root in index:
            continue
        work = [(root, iter(sorted(adj.get(root, ()))))]
        index[root] = low[root] = counter[0]; counter[0] += 1
        stack.append(root); on.add(root)
        while work:
            v, it = work[-1]
            advanced = False
            for w in it:
                if w not in index:
                    index[w] = low[w] = counter[0]; counter[0] += 1
                    stack.append(w); on.add(w)
                    work.append((w, iter(sorted(adj.get(w, ())))))
                    advanced = True
                    break
                if w in on:
                    low[v] = min(low[v], index[w])
            if advanced:
                continue
            work.pop()
            if work:
                low[work[-1][0]] = min(low[work[-1][0]], low[v])
            if low[v] == index[v]:
                comp = []
                while True:
                    w = stack.pop(); on.discard(w); comp.append(w)
                    if w == v:
                        break
                out.append(comp)
    return out
