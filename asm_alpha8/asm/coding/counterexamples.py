"""DEV12 counterexample search: do candidate patches that all pass the tests actually behave the same?

Method (no spec or oracle is assumed):
1. The tracing plugin records the literal arguments with which the tests call each repository function.
2. Those recorded argument tuples are perturbed one argument at a time (type-preserving: numbers +-1/0/negation,
   strings and sequences shortened/extended/emptied, dict keys dropped, booleans flipped).
3. The ORIGINAL (buggy) function and each candidate are executed on the same inputs inside the DEV10/DEV8.1
   sandbox worker and their outputs, exceptions and argument mutations are compared.
Outputs: each patch's behavioural footprint relative to the original, and concrete inputs on which candidates that
all pass the tests disagree (ready to be turned into a new test once someone says which answer is intended).

Honest scope: only module-level functions whose test calls had literal-reprable arguments can be compared; methods,
object-valued arguments and nondeterministic functions are reported as unavailable. Agreement on perturbed inputs
is evidence of equivalence, never proof.
"""
from __future__ import annotations

import ast
import json
import tempfile
import time
from pathlib import Path

from .patches import PatchProposal, apply_proposal
from .sandbox import copy_repo
from .semantics import SemanticAnalyzer, dec

MAX_INPUTS = 150


def perturb_values(v, depth: int = 0) -> list:
    """Type-preserving variants of one argument value (never equal to v, deterministic order)."""
    out: list = []
    if isinstance(v, bool):
        out = [not v]
    elif isinstance(v, int):
        out = [v + 1, v - 1, 0, -v, v * 2]
    elif isinstance(v, float):
        out = [v + 1.0, v - 1.0, 0.0, -v]
    elif isinstance(v, str):
        out = ["", v + "x", v[:-1], v.upper(), v.lower(), " " + v + " "]
    elif isinstance(v, (list, tuple)):
        t = type(v)
        out = [t(), t(v[:-1]), t(v[1:]), t(v) + t(v[-1:]), t(v[::-1])]
        if v and depth < 1:
            out += [t([w] + list(v[1:])) for w in perturb_values(v[0], depth + 1)[:3]]
    elif isinstance(v, dict):
        keys = list(v)[:2]
        out = [{}] + [{k: x for k, x in v.items() if k != drop} for drop in keys]
    seen, uniq = [], []
    for x in out:
        if x != v and repr(x) not in seen:
            seen.append(repr(x))
            uniq.append(x)
    return uniq


def perturb_inputs(recorded: list, limit: int = MAX_INPUTS) -> list:
    """recorded: reprs of argument tuples seen in the tests. Returns arg tuples (originals first, then variants)."""
    base = []
    for r in recorded:
        try:
            t = ast.literal_eval(r)
        except (ValueError, SyntaxError):
            continue
        if isinstance(t, tuple) and t not in base:
            base.append(t)
    inputs = base[:limit]  # the limit caps the TOTAL, recorded originals included
    seen = {repr(t) for t in inputs}
    if len(inputs) >= limit:
        return inputs
    for t in base:
        for i in range(len(t)):
            for var in perturb_values(t[i]):
                cand = t[:i] + (var,) + t[i + 1:]
                if repr(cand) not in seen:
                    seen.add(repr(cand))
                    inputs.append(cand)
                    if len(inputs) >= limit:
                        return inputs
    return inputs


def _canon(rec: dict) -> tuple:
    return (rec["exc"], json.dumps(rec["out"], sort_keys=True), json.dumps(rec["after"], sort_keys=True))


def _show(rec: dict) -> str:
    if rec["exc"]:
        return f"raises {rec['exc']}"
    r = repr(dec(rec["out"]))
    return r if len(r) <= 60 else r[:57] + "..."


def run_versions(analyzer: SemanticAnalyzer, base: Path, module: str, local_qualname: str, versions: dict,
                 inputs: list, diags: list) -> dict:
    """versions: name -> PatchProposal | None (None = the code as it is). Returns name -> {input index: record}."""
    out: dict = {}
    for name, prop in versions.items():
        with tempfile.TemporaryDirectory(prefix="asm_cx_") as td:
            repo = Path(td) / "repo"
            copy_repo(base, repo)
            if prop is not None:
                apply_proposal(repo, prop, backup=False)
            job = {module: [{"qualname": local_qualname, "id": "cx", "batteries": [
                {"cat": "custom", "inputs": [repr(a) for a in inputs]}]}]}
            raw, _ = analyzer._exec_jobs(job, repo, diags, time.monotonic() + 40)
            rec = raw.get((module, "cx"))
            out[name] = {r["i"]: r for r in rec["results"]} if rec else None
    return out


def analyze_candidates(base: Path, qname: str, module: str, path: str, accepted: tuple, alternatives: list,
                       recorded_calls: dict, is_method: bool = False) -> dict:
    """accepted: (name, PatchProposal); alternatives: [(name, PatchProposal)] that ALSO pass the tests."""
    local = qname[len(module) + 1:]
    if is_method or "." in local:
        return {"available": False, "reason": "methods and nested functions are not compared"}
    recorded = recorded_calls.get(f"{path}:{local}", [])
    if not recorded:
        return {"available": False, "reason": "no literal-argument calls to this function were recorded during the tests"}
    inputs = perturb_inputs(recorded)
    diags: list = []
    versions = {"original": None, accepted[0]: accepted[1], **{n: p for n, p in alternatives}}
    outs = run_versions(SemanticAnalyzer(per_call_timeout=1.0, per_module_timeout=30), base, module, local, versions,
                        inputs, diags)
    if any(v is None for v in outs.values()):
        return {"available": False, "reason": "the function could not be executed in the sandbox", "diagnostics": diags[:3]}

    def differing(a: str, b: str) -> list:
        ra, rb = outs[a], outs[b]
        return [i for i in sorted(set(ra) & set(rb)) if _canon(ra[i]) != _canon(rb[i])]
    comparable = [i for i in sorted(set.intersection(*[set(v) for v in outs.values()]))]
    noisy = {i for v in outs.values() for i in comparable if not v[i]["det"]}
    comparable = [i for i in comparable if i not in noisy]
    if not comparable:
        return {"available": False, "reason": "the function was nondeterministic or timed out on every input"}
    cmp_set = set(comparable)
    footprint = {n: round(len([i for i in differing("original", n) if i in cmp_set]) / len(comparable), 3)
                 for n in versions if n != "original"}
    distinguishing = []
    for n, _ in alternatives:
        for i in [i for i in differing(accepted[0], n) if i in cmp_set][:3]:
            distinguishing.append({"input": repr(inputs[i]), "alternative": n,
                                   "accepted_output": _show(outs[accepted[0]][i]), "alternative_output": _show(outs[n][i]),
                                   "original_output": _show(outs["original"][i])})
    return {"available": True, "reason": None, "inputs_tested": len(comparable), "footprint": footprint,
            "distinguishing": distinguishing[:6],
            "alternatives_agree_everywhere": bool(alternatives) and not distinguishing}
