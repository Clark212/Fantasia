"""DEV35: causal repair by intervention (no learned patterns, no language model).

While the bug's tests run, ASM intervenes on the suspect function one site at a time and observes the outcome:
  - each condition (if/while/conditional test, comparison, and/or operand) is flipped, in every run or only while a
    failing test runs;
  - each integer constant is moved by one;
  - each load of a local variable is replaced by another local's value of the same type.
An intervention is a CAUSE when the failing tests pass under it and every test that passed still passes. Each cause
becomes source edits:
  - a flipped condition: `not (c)`, the complementary comparison, and/or swapped;
  - a condition that must differ between failing and passing runs: a guard `c and not p` / `c or p`, where p is an
    atom over the locals (`x is None`, `not x`, `x == k`, `isinstance(x, T)`, `len(x) == 0`) that the recorded values
    separate;
  - a moved constant, a swapped variable.
The tests then judge each edit as for any other candidate (RepairWorkflow); this module only proposes them.
Instrumentation and tests run in a throwaway copy through SafeTestRunner; the plugin re-runs test items in one process
(pytest's runtestprotocol), so hundreds of interventions cost one process start.
"""
from __future__ import annotations

import ast
import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .sandbox import copy_repo

MAX_INTERVENTIONS = 400
PROBE = "asm_iv__"  # a builtin the plugin defines; no leading "__", so class bodies do not mangle it
COMPLEMENT = {ast.Eq: "!=", ast.NotEq: "==", ast.Lt: ">=", ast.GtE: "<", ast.Gt: "<=", ast.LtE: ">", ast.Is: "is not",
              ast.IsNot: "is", ast.In: "not in", ast.NotIn: "in"}

PLUGIN = r'''
import builtins, json, os, sys
STATE = {"spec": None, "test": None, "failing": (), "rec": None}
PER_TEST = 5.0  # seconds a test may take under an intervention
SIMPLE = (type(None), bool, int, float, str)


def _snap(frame):
    out = {}
    for k, v in list(frame.f_locals.items())[:30]:
        if k.startswith("__"):
            continue
        info = {"type": type(v).__name__, "truthy": None, "len": None, "value": None}
        try:
            info["truthy"] = bool(v)
        except Exception:
            pass
        try:
            info["len"] = len(v)
        except Exception:
            pass
        if isinstance(v, SIMPLE) and not (isinstance(v, str) and len(v) > 60):
            info["value"] = v
        out[k] = info
    return out


def iv(sid, v):
    st, sp = STATE, STATE["spec"]
    if st["rec"] is not None:
        rows = st["rec"].setdefault(str(sid), [])
        if len(rows) < 60:
            rows.append({"test": st["test"], "value": v if isinstance(v, SIMPLE) else None, "type": type(v).__name__,
                         "locals": _snap(sys._getframe(1))})
    if sp is not None and sp["sid"] == sid:
        kind = sp["kind"]
        if kind == "flip" or (kind == "flip_failing" and st["test"] in st["failing"]):
            return not v
        if kind == "add" and isinstance(v, int) and not isinstance(v, bool):
            return v + sp["delta"]
        if kind == "swap":
            return sys._getframe(1).f_locals.get(sp["name"], v)
    return v


builtins.asm_iv__ = iv


def pytest_runtestloop(session):
    from _pytest.runner import runtestprotocol
    spec = json.loads(open(os.environ["ASM_CAUSAL_SPEC"]).read())
    items = {i.nodeid: i for i in session.items}
    STATE["failing"] = tuple(spec["failing"])

    import signal

    def alarm(signum, frame):
        raise TimeoutError("intervention made the test hang")

    signal.signal(signal.SIGALRM, alarm)

    def run(tests):
        res = {}
        for t in tests:
            if t not in items:
                res[t] = "missing"
                continue
            STATE["test"] = t
            signal.setitimer(signal.ITIMER_REAL, PER_TEST)  # a flipped loop condition must not hang the whole run
            try:
                reports = runtestprotocol(items[t], nextitem=None, log=False)
                res[t] = "passed" if all(r.passed or r.skipped for r in reports) else "failed"
            except TimeoutError:
                res[t] = "failed"
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)
            if res[t] != "passed" and STATE["spec"] is not None:
                break  # one failing test refutes the intervention
        STATE["test"] = None
        return res

    out = {"record": {}, "baseline": {}, "causes": [], "tried": 0}
    STATE["rec"] = out["record"]
    out["baseline"] = run(spec["failing"] + spec["passing"])
    STATE["rec"] = None
    keep = [t for t in spec["passing"] if out["baseline"].get(t) == "passed"]
    for sp in spec["interventions"]:
        STATE["spec"] = sp
        out["tried"] += 1
        if all(v == "passed" for v in run(spec["failing"]).values()) and all(v == "passed" for v in run(keep).values()):
            out["causes"].append(sp)
    STATE["spec"] = None
    with open(os.environ["ASM_CAUSAL_OUT"], "w") as fh:
        json.dump(out, fh, default=str)
    return True
'''


@dataclass
class Site:
    sid: int
    kind: str  # cond | int | name
    node: ast.AST = field(repr=False)


def _locals_of(fn) -> set:
    names = {a.arg for a in fn.args.args + fn.args.kwonlyargs + fn.args.posonlyargs}
    names |= {a.arg for a in (fn.args.vararg, fn.args.kwarg) if a}
    names |= {n.id for n in ast.walk(fn) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
    return names


def sites(tree: ast.Module, span: tuple) -> tuple[ast.AST, list]:
    """The function whose def is in `span` (its first line) and its intervention sites, in source order."""
    fn = next((n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
               and n.lineno <= span[0] <= n.end_lineno and n.lineno >= span[0] - 1), None)
    if fn is None:
        fn = next((n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                   and n.lineno <= span[0] and n.end_lineno >= span[1]), None)
    if fn is None:
        return None, []
    local, out, conds = _locals_of(fn), [], set()
    for n in ast.walk(fn):
        if isinstance(n, (ast.If, ast.While, ast.IfExp)):
            conds.add(id(n.test))
        elif isinstance(n, ast.BoolOp):
            conds.update(id(v) for v in n.values)
    for n in ast.walk(fn):
        if n is fn or not hasattr(n, "lineno"):
            continue
        if id(n) in conds or isinstance(n, ast.Compare):
            out.append(Site(len(out), "cond", n))
        elif isinstance(n, ast.Constant) and type(n.value) is int:
            out.append(Site(len(out), "int", n))
        elif isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id in local:
            out.append(Site(len(out), "name", n))
    out.sort(key=lambda s: (s.node.lineno, s.node.col_offset))
    for i, s in enumerate(out):
        s.sid = i
    return fn, out


class _Wrap(ast.NodeTransformer):
    def __init__(self, ids: dict):
        self.ids = ids

    def generic_visit(self, node):
        super().generic_visit(node)
        sid = self.ids.get(id(node))
        if sid is None:
            return node
        return ast.copy_location(ast.Call(ast.Name(PROBE, ast.Load()), [ast.Constant(sid), node], []), node)


def instrument(source: str, span: tuple) -> tuple[str | None, list]:
    tree = ast.parse(source)
    fn, ss = sites(tree, span)
    if fn is None or not ss:
        return None, []
    ids = {id(s.node): s.sid for s in ss}
    _Wrap(ids).visit(fn)
    ast.fix_missing_locations(tree)
    return ast.unparse(tree), ss


def _splice(source: str, node: ast.AST, text: str) -> str:
    """Replace `node`'s source text (ast offsets count UTF-8 bytes) with `text`."""
    lines = source.splitlines(keepends=True)
    pos = lambda ln, col: sum(len(x) for x in lines[: ln - 1]) + len(lines[ln - 1].encode()[:col].decode(errors="ignore"))  # noqa: E731
    return source[: pos(node.lineno, node.col_offset)] + text + source[pos(node.end_lineno, node.end_col_offset):]


def _seg(source: str, node) -> str:
    return ast.get_source_segment(source, node) or ast.unparse(node)


def interventions(ss: list, record: dict) -> list:
    out = []
    for s in ss:
        rows = record.get(str(s.sid), [])
        if not rows:
            continue  # never executed by the tests: no evidence either way
        if s.kind == "cond":
            out += [{"sid": s.sid, "kind": "flip"}, {"sid": s.sid, "kind": "flip_failing"}]
        elif s.kind == "int":
            out += [{"sid": s.sid, "kind": "add", "delta": d} for d in (1, -1)]
        else:
            t = rows[0]["type"]
            others = sorted({k for r in rows for k, v in r["locals"].items() if v["type"] == t and k != s.node.id})
            out += [{"sid": s.sid, "kind": "swap", "name": k} for k in others]
    return out[:MAX_INTERVENTIONS]


def _atoms(fail: list, passing: list) -> list:
    """Predicates over the locals true at every failing-run execution and false at every passing-run one."""
    names = set.intersection(*[set(r["locals"]) for r in fail + passing]) if fail and passing else set()
    out = []
    for k in sorted(names):
        f, p = [r["locals"][k] for r in fail], [r["locals"][k] for r in passing]
        tests = [(f"{k} is None", lambda i: i["type"] == "NoneType"), (f"not {k}", lambda i: i["truthy"] is False)]
        tests += [(f"isinstance({k}, {t})", lambda i, t=t: i["type"] == t) for t in sorted({i["type"] for i in f})
                  if t in ("str", "int", "float", "list", "dict", "tuple", "bytes", "bool", "set")]
        tests += [(f"len({k}) == 0", lambda i: i["len"] == 0)]
        vals = {repr(i["value"]) for i in f if i["value"] is not None}
        if len(vals) == 1:
            v = next(iter(vals))
            tests += [(f"{k} == {v}", lambda i, v=v: i["value"] is not None and repr(i["value"]) == v)]
        for text, pred in tests:
            if all(pred(i) for i in f) and not any(pred(i) for i in p):
                out.append(text)
            elif not any(pred(i) for i in f) and all(pred(i) for i in p):
                out.append(f"not ({text})")
    return out[:10]


def edits(source: str, ss: list, causes: list, record: dict, failing: list) -> list:
    """(new module source, description) for every cause."""
    by, out = {s.sid: s for s in ss}, []
    for c in causes:
        s = by[c["sid"]]
        n, seg = s.node, _seg(source, s.node)
        if c["kind"] == "flip":
            out.append((_splice(source, n, f"not ({seg})"), f"causal: flip `{seg}`"))
            if isinstance(n, ast.Compare) and len(n.ops) == 1 and type(n.ops[0]) in COMPLEMENT:
                text = f"{_seg(source, n.left)} {COMPLEMENT[type(n.ops[0])]} {_seg(source, n.comparators[0])}"
                out.append((_splice(source, n, text), f"causal: `{seg}` -> `{text}`"))
        elif c["kind"] == "flip_failing":
            rows = record.get(str(s.sid), [])
            fail = [r for r in rows if r["test"] in failing]
            passing = [r for r in rows if r["test"] not in failing]
            seen = {r["value"] for r in fail}
            if len(seen) != 1 or not isinstance(next(iter(seen)), bool):
                continue
            join = "and not" if next(iter(seen)) else "or"
            for p in _atoms(fail, passing):
                text = f"(({seg}) {join} ({p}))"
                out.append((_splice(source, n, text), f"causal: guard `{seg}` with `{p}`"))
        elif c["kind"] == "add":
            out.append((_splice(source, n, str(n.value + c["delta"])), f"causal: {n.value} -> {n.value + c['delta']}"))
        elif c["kind"] == "swap":
            out.append((_splice(source, n, c["name"]), f"causal: `{n.id}` -> `{c['name']}`"))
    seen, uniq = set(), []
    for src, why in out:
        try:
            ast.parse(src)
        except SyntaxError:
            continue
        if src != source and src not in seen:
            seen.add(src)
            uniq.append((src, why))
    return uniq


def investigate(runner, root: Path, path: str, span: tuple, failing: list, passing: list, timeout: float = 120.0,
                files: list | None = None) -> dict:
    """Record, then intervene, on the function at `span` of `path` while the given tests run. Returns
    {"edits": [(source, why)], "causes": [...], "tried": n, "sites": n, "note": str}. `files`: the test files to run (pytest
    node ids can be relative to another directory than the repository's, so they are not always paths)."""
    source = (root / path).read_text(encoding="utf-8")
    try:
        inst, ss = instrument(source, span)
    except (SyntaxError, ValueError, RecursionError) as exc:
        return {"edits": [], "causes": [], "tried": 0, "sites": 0, "note": f"not instrumented: {type(exc).__name__}"}
    if inst is None:
        return {"edits": [], "causes": [], "tried": 0, "sites": 0, "note": "no intervention sites"}
    with tempfile.TemporaryDirectory(prefix="asm_dev35_") as td:
        td = Path(td)
        repo, plugin = td / "repo", td / "plugin"
        copy_repo(root, repo)
        plugin.mkdir()
        (plugin / "asm_causal_plugin.py").write_text(PLUGIN)
        (repo / path).write_text(inst, encoding="utf-8")

        def run(ivs):
            (td / "spec.json").write_text(json.dumps({"failing": failing, "passing": passing, "interventions": ivs}))
            out = td / "out.json"
            if out.exists():
                out.unlink()
            try:
                r = runner.run_pytest(repo, files or sorted({t.split("::", 1)[0] for t in failing + passing}), timeout=timeout,
                                      extra_args=["-p", "asm_causal_plugin", "-p", "no:randomly"],
                                      env_extra={"PYTHONPATH": str(plugin), "ASM_CAUSAL_SPEC": str(td / "spec.json"),
                                                 "ASM_CAUSAL_OUT": str(out)})
            except (FileNotFoundError, ValueError) as exc:
                return {"error": "targets", "tail": str(exc)}
            return json.loads(out.read_text()) if out.exists() else {"error": r.classification, "tail": (r.stdout + r.stderr)[-400:]}

        first = run([])
        if "error" in first:
            return {"edits": [], "causes": [], "tried": 0, "sites": len(ss), "note": f"record run: {first['error']}: {first['tail']}"}
        if any(first["baseline"].get(t) != "failed" for t in failing):
            return {"edits": [], "causes": [], "tried": 0, "sites": len(ss), "note": "a failing test passes when instrumented"}
        ivs = interventions(ss, first["record"])
        second = run(ivs) if ivs else {"causes": [], "tried": 0}
        if "error" in second:
            return {"edits": [], "causes": [], "tried": 0, "sites": len(ss), "note": f"intervention run: {second['error']}"}
    return {"edits": edits(source, ss, second["causes"], first["record"], failing), "causes": second["causes"],
            "tried": second["tried"], "sites": len(ss), "note": ""}
