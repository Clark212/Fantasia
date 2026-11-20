"""DEV13 generalized behavioural verification.

Question answered: does a proposed patch change program behaviour only where the failing tests demand it?

Extends DEV12's counterexample search from literal-argument functions to:
- OBJECT-valued arguments: the tracing plugin pickles the real argument tuples (receiver objects included) the tests
  pass to each function; the replay worker unpickles them in the sandbox, so methods and functions that take objects
  are replayed on realistic inputs. Perturbation edits literal arguments and literal attributes of recorded objects.
- METHODS: the receiver object is part of the recorded arguments.
- NESTED functions: a closure cannot be replayed without its enclosing call, so the OUTERMOST enclosing function or
  method is replayed; its behaviour includes the nested function's effect.
- STATE and SIDE EFFECTS: compared per input between the original and each candidate: return value, final state of every
  argument and of returned objects, printed output, files created, and module-level globals.
- NONDETERMINISM: randomness, wall-clock time, `time.sleep` and `os.urandom` are made deterministic in the worker, so
  functions that use them become comparable; inputs that still differ between two identical runs are excluded and counted.

Key signal (aimed at "overfitting" patches): a patch whose output changes on inputs that PASSING tests already used.
The buggy program passed those tests, so a correct fix has no reason to change what they exercise; the tests accepted
the change without checking it. Reported as `changed_on_passing_recorded`. It is a warning, not a verdict.

Honest scope: agreement on recorded and perturbed inputs is evidence, never proof. Unpicklable arguments (open files,
locks, generators, lambdas), classmethods, *args/**kwargs signatures and classes local to test modules are not replayable.
Replay unpickles data that came from this repository's own tests inside the same sandbox that already executes its code.
`datetime.now()`, `time.time_ns()` and other C-level clocks are not controlled.
"""
from __future__ import annotations

import ast
import json
import tempfile
from pathlib import Path

from .counterexamples import perturb_values
from .generation import find_function_node, generate_sets, mine_constants
from .patches import apply_proposal
from .sandbox import copy_repo, run_python_worker

MAX_INPUTS = 120

_WORKER2 = r'''
import sys, os, json, importlib, io, copy, signal, contextlib, ast, types, time, pickle, base64, hashlib, random, shutil
job = json.load(open(sys.argv[1])); out_path = sys.argv[2]
sys.dont_write_bytecode = True
if job.get("root"): sys.path.insert(0, job["root"])
os.chdir(job["cwd"]); sys.setrecursionlimit(800)
res = open(out_path, "a", buffering=1)
def emit(o): res.write(json.dumps(o) + "\n"); res.flush()
_real_mono = time.monotonic
_clock = [1700000000.0]
def _tick(*a):
    _clock[0] += 0.001
    return _clock[0]
time.time = _tick; time.monotonic = _tick; time.perf_counter = _tick; time.process_time = _tick; time.sleep = lambda s: None
_ur = [random.Random(99)]
os.urandom = lambda n: bytes(_ur[0].getrandbits(8) for _ in range(n))
def reset_env():
    random.seed(1234); _clock[0] = 1700000000.0; _ur[0] = random.Random(99)
_SKIP = (types.FunctionType, types.MethodType, types.BuiltinFunctionType, types.ModuleType, type)
def enc(v, d=0, seen=None):
    seen = seen if seen is not None else frozenset()
    if v is None: return {"t": "none"}
    if isinstance(v, bool): return {"t": "bool", "v": v}
    if isinstance(v, int): return {"t": "int", "v": v if abs(v) < 2**53 else str(v)}
    if isinstance(v, float): return {"t": "float", "v": repr(v)}
    if isinstance(v, str): return {"t": "str", "v": v[:2000]}
    if isinstance(v, bytes): return {"t": "bytes", "v": v[:200].hex()}
    if isinstance(v, ast.AST): return {"t": "ast", "v": ast.dump(v)[:1500]}
    if isinstance(v, _SKIP): return {"t": "callable", "v": getattr(v, "__qualname__", type(v).__name__)}
    if id(v) in seen or d > 4: return {"t": "ref", "v": type(v).__qualname__}
    seen = seen | {id(v)}
    if isinstance(v, (list, tuple)): return {"t": type(v).__name__, "v": [enc(x, d + 1, seen) for x in v[:60]]}
    if isinstance(v, dict): return {"t": "dict", "v": [[enc(k, d + 1, seen), enc(x, d + 1, seen)] for k, x in list(v.items())[:60]]}
    if isinstance(v, (set, frozenset)): return {"t": "set", "v": sorted((enc(x, d + 1, seen) for x in list(v)[:60]), key=json.dumps)}
    state = {}
    try: items = list(vars(v).items())
    except TypeError: items = []
    slots = getattr(type(v), "__slots__", ())
    for sl in (slots if not isinstance(slots, str) else (slots,)):
        if hasattr(v, sl): items.append((sl, getattr(v, sl)))
    for k, x in items[:40]:
        if k.startswith("__") or isinstance(x, _SKIP): continue
        state[k] = enc(x, d + 1, seen)
    return {"t": "obj", "cls": type(v).__qualname__, "state": state}
class _TO(BaseException): pass
def _alarm(s, f): raise _TO()
signal.signal(signal.SIGALRM, _alarm)
def call(fn, args, tmo):
    signal.setitimer(signal.ITIMER_REAL, tmo)
    try: return ("ok", fn(*args), None)
    except _TO: return ("exc", None, "Timeout")
    except BaseException as e: return ("exc", None, type(e).__name__)
    finally: signal.setitimer(signal.ITIMER_REAL, 0)
def files_state():
    out = {}
    for dp, dn, fns in os.walk("."):
        for f in fns[:40]:
            p = os.path.join(dp, f)
            try: out[p] = hashlib.sha1(open(p, "rb").read()).hexdigest()[:12]
            except OSError: out[p] = "?"
    return out
def clean_cwd():
    for e in os.listdir("."):
        try: shutil.rmtree(e) if os.path.isdir(e) and not os.path.islink(e) else os.remove(e)
        except OSError: pass
def gvals(mod):
    return {k: v for k, v in list(vars(mod).items())[:200] if not k.startswith("__") and not isinstance(v, _SKIP)}
def apply_sets(args, sets):
    args = list(args)
    for idx, attr, lit in sets:
        val = ast.literal_eval(lit)
        if attr is None: args[idx] = val
        else: setattr(args[idx], attr, val)
    return tuple(args)
def one_run(fn, spec, mod, tmo):
    reset_env()
    args = pickle.loads(base64.b64decode(spec["blob"]))
    if spec.get("donor"):
        donor = pickle.loads(base64.b64decode(spec["donor"]))
        args = list(args)
        for k in spec.get("take", []): args[k] = donor[k]
        args = tuple(args)
    args = apply_sets(args, spec.get("set", []))
    saved = {}
    for k, v in gvals(mod).items():
        try: saved[k] = copy.deepcopy(v)
        except Exception: pass
    gb = {k: json.dumps(enc(v, 2)) for k, v in gvals(mod).items()}
    before_files = files_state()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
        r = call(fn, args, tmo)
    out = enc(r[1]) if r[0] == "ok" else None
    after = [enc(a) for a in args]
    files_after = files_state()
    new_files = {p: h for p, h in files_after.items() if before_files.get(p) != h}
    clean_cwd()
    ga = {k: json.dumps(enc(v, 2)) for k, v in gvals(mod).items()}
    gdiff = {k: ga[k] for k in ga if gb.get(k) != ga[k]}
    for k in list(gdiff):
        if k in saved: setattr(mod, k, saved[k])
        else:
            try: delattr(mod, k)
            except AttributeError: pass
    text = buf.getvalue()
    return {"exc": r[2], "out": out, "after": after, "stdout": hashlib.sha1(text.encode()).hexdigest()[:12] + ":" + str(len(text)),
            "files": new_files, "globals": gdiff}
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
        key = {"module": m["module"], "qualname": f["qualname"], "id": f["id"]}
        try:
            fn = mod
            for part in f["qualname"].split("."): fn = getattr(fn, part)
        except BaseException as e:
            emit(dict(key, error="lookup: " + type(e).__name__)); continue
        results, t0, timeouts = [], _real_mono(), 0
        for i, spec in enumerate(f["inputs"]):
            if timeouts >= 5 or _real_mono() - t0 > job["function_budget"]: break
            try:
                r1 = one_run(fn, spec, mod, tmo); r2 = one_run(fn, spec, mod, tmo)
            except BaseException as e:
                results.append({"i": i, "skip": type(e).__name__ + ": " + str(e)[:80]}); continue
            if r1["exc"] == "Timeout": timeouts += 1
            r1["i"] = i; r2["i"] = i
            r1["det"] = json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True)
            results.append(r1)
        emit(dict(key, results=results))
emit({"done": True})
'''


# ----------------------------------------------------------------- targets and inputs
def verification_target(qname: str, funcs: dict):
    """Resolve what to replay for a patched function: itself, or its outermost enclosing function/method."""
    f = funcs.get(qname)
    via = False
    while f is not None and f.kind == "nested":
        f, via = funcs.get(f.qname.rsplit(".", 1)[0]), True
    return (f, via)


def _tuple_desc(parts: list) -> str:
    return "(" + ", ".join(parts) + ("," if len(parts) == 1 else "") + ")"


def _show_arg(view: dict, sets: list, idx: int) -> str:
    if view["k"] == "lit":
        base = view["r"]
        for i, attr, lit in sets:
            if i == idx and attr is None:
                base = lit
        return base
    if view["k"] == "obj":
        attrs = dict(view["attrs"])
        for i, attr, lit in sets:
            if i == idx and attr is not None:
                attrs[attr] = lit
        return f"{view['cls']}{{{', '.join(f'{k}={v}' for k, v in list(attrs.items())[:5])}}}"
    return f"<{view.get('cls', '?')}>"


def build_inputs(records: list, outcomes: dict, limit: int = MAX_INPUTS, generate: dict | None = None) -> list:
    """Recorded argument tuples first (with the outcomes of the tests that used them), then literal perturbations, then
    (if `generate` = {"mined", "budget", "seed"}) inputs beyond the test suite, tagged origin="generated"."""
    by_hash: dict = {}
    for r in records:
        e = by_hash.setdefault(r["h"], {"blob": r["pickle"], "view": r["view"], "tests": []})
        e["tests"].append(outcomes.get(r["test"], "unknown"))
    inputs = []
    for e in by_hash.values():
        inputs.append({"blob": e["blob"], "set": [], "origin": "recorded", "outcomes": sorted(set(e["tests"])),
                       "desc": _tuple_desc([_show_arg(v, [], i) for i, v in enumerate(e["view"])]), "view": e["view"]})
    for b in list(inputs):
        added = 0
        for idx, v in enumerate(b["view"]):
            targets = []
            if v["k"] == "lit":
                try:
                    targets.append((None, ast.literal_eval(v["r"])))
                except (ValueError, SyntaxError):
                    pass
            elif v["k"] == "obj":
                for attr, r in v["attrs"].items():
                    try:
                        targets.append((attr, ast.literal_eval(r)))
                    except (ValueError, SyntaxError):
                        pass
            for attr, val in targets:
                for var in perturb_values(val):
                    if len(inputs) >= limit or added >= 14:
                        break
                    sets = [[idx, attr, repr(var)]]
                    inputs.append({"blob": b["blob"], "set": sets, "origin": "perturbed", "outcomes": [],
                                   "desc": _tuple_desc([_show_arg(w, sets, j) for j, w in enumerate(b["view"])]),
                                   "view": b["view"]})
                    added += 1
    inputs = inputs[:limit]
    if generate and generate.get("budget", 0) > 0:
        bases = [i for i in inputs if i["origin"] == "recorded"]
        seen = {(i["blob"], repr(i["set"])) for i in inputs}
        # inputs made only of literals are identified by their displayed argument tuple: a crossover or generated value
        # that reproduces an input already present would spend budget on a call that is already replayed
        all_lit = lambda view: all(v["k"] == "lit" for v in view)  # noqa: E731
        seen_desc = {i["desc"] for i in inputs if all_lit(i["view"])}
        generated = []
        # CROSSOVER: argument k of recorded call B placed into recorded call A. Every value is one the tests really
        # produced (objects included), only the combination is new; reaches object-heavy code literal generation cannot.
        crosses = []
        for a in bases:
            for b in bases:
                if a is b or len(a["view"]) != len(b["view"]):
                    continue
                for k in range(len(a["view"])):
                    if a["view"][k] != b["view"][k]:
                        crosses.append((a, b, k))
        import random as _random
        _random.Random(generate.get("seed", 0)).shuffle(crosses)
        for a, b, k in crosses[: int(generate["budget"] * generate.get("crossover_share", 0.4))]:
            key = (a["blob"], b["blob"], k)
            if key in seen:
                continue
            seen.add(key)
            view = list(a["view"])
            view[k] = b["view"][k]
            desc = _tuple_desc([_show_arg(w, [], j) for j, w in enumerate(view)])
            if all_lit(view):
                if desc in seen_desc:
                    continue
                seen_desc.add(desc)
            generated.append({"blob": a["blob"], "donor": b["blob"], "take": [k], "set": [], "origin": "generated",
                              "generator": "crossover", "outcomes": [], "view": view,
                              "desc": _tuple_desc([_show_arg(w, [], j) for j, w in enumerate(view)])})
        per_base = max(4, (generate["budget"] - len(generated)) // max(1, len(bases)))
        for k, b in enumerate(bases):
            for sets in generate_sets(b["view"], generate["mined"], per_base, generate.get("seed", 0) + k):
                key = (b["blob"], repr(sets))
                if key in seen:
                    continue
                seen.add(key)
                desc = _tuple_desc([_show_arg(w, sets, j) for j, w in enumerate(b["view"])])
                if all_lit(b["view"]):
                    if desc in seen_desc:
                        continue
                    seen_desc.add(desc)
                generated.append({"blob": b["blob"], "set": sets, "origin": "generated", "generator": "literal", "outcomes": [],
                                  "desc": desc, "view": b["view"]})
        # interleave bases so a small budget still covers every recorded call
        inputs += generated[: generate["budget"]]
    return inputs


# ----------------------------------------------------------------------- execution
def run_versions(base: Path, module: str, local_qualname: str, versions: dict, inputs: list, diags: list) -> dict:
    """versions: name -> PatchProposal | None (None = the code as it is). Returns name -> {input index: record} | None."""
    out: dict = {}
    for name, prop in versions.items():
        with tempfile.TemporaryDirectory(prefix="asm_ver_") as td:
            td = Path(td)
            repo, cwd = td / "repo", td / "cwd"
            cwd.mkdir()
            copy_repo(base, repo)
            if prop is not None:
                apply_proposal(repo, prop, backup=False)
            job = {"root": str(repo), "cwd": str(cwd), "call_timeout": 1.0, "import_timeout": 10.0, "function_budget": 20.0,
                   "modules": [{"module": module, "functions": [{"qualname": local_qualname, "id": "v", "inputs": [
                       {"blob": i["blob"], "set": i["set"], "donor": i.get("donor"), "take": i.get("take", [])} for i in inputs]}]}]}
            jp, op = td / "job.json", td / "out.jsonl"
            jp.write_text(json.dumps(job))
            op.write_text("")
            run = run_python_worker(_WORKER2, [str(jp), str(op)], cwd, timeout=60, memory_mb=1024)
            if run["timed_out"]:
                diags.append({"code": "verification_timeout", "version": name})
            rec = None
            for line in op.read_text().splitlines():
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if "import_error" in r:
                    diags.append({"code": "verification_import_error", "version": name, "message": r["import_error"]})
                elif "error" in r:
                    diags.append({"code": "verification_lookup_error", "version": name, "message": r["error"]})
                elif "results" in r:
                    rec = r
            out[name] = {r["i"]: r for r in rec["results"]} if rec else None
    return out


_COMPONENTS = ("exc", "out", "after", "stdout", "files", "globals")


def _canon(r: dict) -> str:
    return json.dumps({k: r[k] for k in _COMPONENTS}, sort_keys=True)


def _components(a: dict, b: dict) -> list:
    return [k for k in _COMPONENTS if json.dumps(a[k], sort_keys=True) != json.dumps(b[k], sort_keys=True)]


def render(e) -> str:
    """Human-readable form of a worker-encoded value."""
    if e is None:
        return "None"
    t = e["t"]
    if t == "none":
        return "None"
    if t in {"bool", "int", "float"}:
        return str(e["v"])
    if t == "str":
        return repr(e["v"])
    if t == "bytes":
        return f"bytes.fromhex({e['v']!r})"
    if t in {"list", "tuple", "set"}:
        inner = ", ".join(render(x) for x in e["v"][:8]) + (", ..." if len(e["v"]) > 8 else "")
        return {"list": f"[{inner}]", "tuple": f"({inner}{',' if len(e['v']) == 1 else ''})", "set": "{" + inner + "}"}[t]
    if t == "dict":
        return "{" + ", ".join(f"{render(k)}: {render(v)}" for k, v in e["v"][:6]) + (", ..." if len(e["v"]) > 6 else "") + "}"
    if t == "obj":
        return f"{e['cls']}(" + ", ".join(f"{k}={render(v)}" for k, v in list(e["state"].items())[:6]) + ")"
    if t == "ast":
        return "<ast " + e["v"][:40] + "...>"
    return f"<{e.get('v', t)}>"


def _short(r: dict) -> str:
    if r["exc"]:
        return f"raises {r['exc']}"
    s = render(r["out"])
    return s if len(s) <= 90 else s[:87] + "..."


def generation_plan(base: Path, target, budget: int, seed: int) -> dict | None:
    """Constants mined from the target function's own source, plus the generation budget and seed."""
    if budget <= 0:
        return None
    try:
        node = find_function_node((Path(base) / target.path).read_text(encoding="utf-8"), target.line)
    except OSError:
        node = None
    return {"mined": mine_constants(node) if node is not None else {"nums": [], "strs": []}, "budget": budget, "seed": seed}


def verify_patch(base: Path, qname: str, accepted: tuple, alternatives: list, spectrum, funcs: dict,
                 gen_budget: int = 100, gen_seed: int = 0) -> dict:
    """accepted: (name, PatchProposal); alternatives: [(name, PatchProposal)] that also pass the tests.
    gen_budget: number of inputs generated beyond the test suite (0 = DEV13 behaviour)."""
    target, via = verification_target(qname, funcs)
    if target is None:
        return {"available": False, "reason": "the enclosing function could not be resolved"}
    local = target.qname[len(target.module) + 1:]
    info = {"qname": target.qname, "kind": target.kind, "via_enclosing": via}
    records = spectrum.records.get(f"{target.path}:{local}", [])
    if not records:
        return {"available": False, "target": info,
                "reason": f"no replayable calls to {local} were recorded during the tests "
                          "(arguments may be unpicklable, or the tests do not call it)"}
    inputs = build_inputs(records, spectrum.outcomes, generate=generation_plan(base, target, gen_budget, gen_seed))
    diags: list = []
    versions = {"original": None, accepted[0]: accepted[1], **{n: p for n, p in alternatives}}
    outs = run_versions(base, target.module, local, versions, inputs, diags)
    if any(v is None for v in outs.values()):
        return {"available": False, "reason": "the function could not be replayed in the sandbox", "diagnostics": diags[:3],
                "target": info}
    common = set.intersection(*[set(v) for v in outs.values()])
    usable = [i for i in sorted(common) if all("skip" not in outs[n][i] for n in outs)]
    nondet = {i for i in usable if not all(outs[n][i]["det"] for n in outs)}
    comparable = [i for i in usable if i not in nondet]
    if len(comparable) < 3:
        return {"available": False, "reason": f"only {len(comparable)} input(s) could be compared deterministically",
                "target": info, "excluded_nondeterministic": len(nondet), "inputs_total": len(inputs)}
    name0 = accepted[0]
    footprint, passing, failing, comps, by_origin = {}, {}, {}, {}, {}
    for n in versions:
        if n == "original":
            continue
        d = [i for i in comparable if _canon(outs["original"][i]) != _canon(outs[n][i])]
        footprint[n] = round(len(d) / len(comparable), 3)
        passing[n] = [inputs[i]["desc"] for i in d if inputs[i]["origin"] == "recorded" and "passed" in inputs[i]["outcomes"]]
        failing[n] = [inputs[i]["desc"] for i in d if inputs[i]["origin"] == "recorded" and "passed" not in inputs[i]["outcomes"]]
        c: dict = {}
        for i in d:
            for comp in _components(outs["original"][i], outs[n][i]):
                c[comp] = c.get(comp, 0) + 1
        comps[n] = c
        o: dict = {}
        for i in d:
            o[inputs[i]["origin"]] = o.get(inputs[i]["origin"], 0) + 1
        by_origin[n] = o
    distinguishing = []
    for n, _ in alternatives:
        for i in [i for i in comparable if _canon(outs[name0][i]) != _canon(outs[n][i])][:3]:
            distinguishing.append({"input": inputs[i]["desc"], "alternative": n, "accepted_output": _short(outs[name0][i]),
                                   "alternative_output": _short(outs[n][i]), "original_output": _short(outs["original"][i]),
                                   "differs_in": _components(outs[name0][i], outs[n][i]), "origin": inputs[i]["origin"]})
    return {"available": True, "reason": None, "target": info, "inputs_total": len(inputs), "inputs_tested": len(comparable),
            "inputs_recorded": sum(1 for i in comparable if inputs[i]["origin"] == "recorded"),
            "inputs_by_origin": {o: sum(1 for i in comparable if inputs[i]["origin"] == o) for o in ("recorded", "perturbed", "generated")},
            "changed_by_origin": by_origin,
            "excluded_nondeterministic": len(nondet), "footprint": footprint,
            "changed_on_passing_recorded": passing, "changed_on_failing_recorded": failing, "changed_components": comps,
            "distinguishing": distinguishing[:6],
            "alternatives_agree_everywhere": bool(alternatives) and not distinguishing}
