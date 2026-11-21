"""DEV4 Part A: structural discovery map for ASM's ProcedureCortex (6 families, ground truth known, with controls).

Experimental; NOT wired into ASM beliefs, memory or action selection. Reuses the DEV3 lab primitives.

Each task draws a hidden rule uniformly from a declared grid. Scored queries are held-out INTERIOR inputs whose answer is
determined by the training pool under that grid, so a perfect learner can reach 100%. A fresh learner is built per task and per
budget k; shots cycle through a shuffled copy of the pool. Limitation: ASM can answer an ambiguous case with a
``needs_information`` query that this lab never answers, so ASM coverage here is a lower bound.
"""
from __future__ import annotations

import itertools
import random
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from .simlab import (ABSTAIN, Learner, Task, draw_shots, paired_bootstrap, prereg_hash, score_task, summarize)

FAMILIES = ("affine", "quad", "clamp", "threshold", "linear2", "product2")
SCHEMAS = {"affine": ("x",), "quad": ("x",), "clamp": ("x",), "threshold": ("x",), "linear2": ("x", "y"), "product2": ("x", "y")}
UNARY_UNIVERSE = tuple(range(16))
GRID_UNIVERSE = tuple((x, y) for x in range(6) for y in range(6))


def grid(family: str) -> list[dict[str, Any]]:
    if family == "affine":
        return [{"a": a, "b": b} for a in range(-6, 7) if a for b in range(-9, 10)]
    if family == "quad":
        return [{"a": a, "b": b} for a in (-3, -2, 2, 3) for b in range(-9, 10)]
    if family == "clamp":
        return [{"op": op, "c": c} for op in ("min", "max") for c in range(2, 13)]
    if family == "threshold":
        return [{"c": c, "p": p, "q": q} for c in range(4, 12) for p in range(-5, 6) for q in range(-5, 6) if p != q]
    if family == "linear2":
        return [{"a": a, "b": b} for a in (-3, -2, -1, 1, 2, 3) for b in (-3, -2, -1, 1, 2, 3)]
    if family == "product2":
        return [{"c": c} for c in range(-5, 6)]
    raise ValueError(f"unknown family {family!r}")


def evaluate(family: str, public: Mapping[str, Any], p: Mapping[str, Any], x: Any) -> int:
    if family == "affine":
        return p["a"] * x + p["b"]
    if family == "quad":
        return p["a"] * x * x + p["b"]
    if family == "clamp":
        return min(x, p["c"]) if p["op"] == "min" else max(x, p["c"])
    if family == "threshold":
        return p["p"] if x < p["c"] else p["q"]
    if family == "linear2":
        return p["a"] * x[0] + p["b"] * x[1]
    if family == "product2":
        return x[0] * x[1] + p["c"]
    raise ValueError(f"unknown family {family!r}")


@dataclass(frozen=True)
class StructTask(Task):
    def label(self, x: Any) -> int:
        return evaluate(self.family, self.public, self.truth, x)


def make_struct_task(family: str, index: int, seed: int) -> StructTask:
    rng = random.Random(f"{seed}:struct:{family}:{index}")
    hyps = grid(family)
    unary = len(SCHEMAS[family]) == 1
    universe = UNARY_UNIVERSE if unary else GRID_UNIVERSE
    interior = [u for u in universe if (1 <= u <= 14 if unary else 1 <= u[0] <= 4 and 1 <= u[1] <= 4)]
    n_held = 3 if unary else 6
    for _ in range(300):
        truth = hyps[rng.randrange(len(hyps))]
        held = rng.sample(interior, n_held)
        pool = tuple(u for u in universe if u not in set(held))
        labels = [evaluate(family, {}, truth, u) for u in pool]
        consistent = [h for h in hyps if all(evaluate(family, {}, h, u) == y for u, y in zip(pool, labels))]
        queries = tuple(u for u in sorted(held) if len({evaluate(family, {}, h, u) for h in consistent}) == 1)
        if len(queries) >= 2:
            return StructTask(f"{family}-{index:04d}", family, {"schema": list(SCHEMAS[family])}, truth, pool, queries)
    raise RuntimeError(f"could not build a determined task for {family}/{index}")


def make_struct_suite(family: str, count: int, seed: int) -> list[StructTask]:
    return [make_struct_task(family, i, seed) for i in range(count)]


class GridReferenceLearner(Learner):
    """Reference given the family grid; answers only when every consistent hypothesis agrees."""
    name = "grid_reference"

    def fit(self, ctx, shots):
        self.family = ctx["family"]
        self.consistent = [h for h in grid(self.family) if all(evaluate(self.family, {}, h, x) == y for x, y in shots)]

    def predict(self, x):
        values = {evaluate(self.family, {}, h, x) for h in self.consistent}
        return (next(iter(values)), 1.0) if len(values) == 1 else (ABSTAIN, 0.0)


class ASMStructLearner(Learner):
    """ASM's ProcedureCortex (default configuration unless kwargs say otherwise) as a black-box learner."""
    name = "asm_struct"

    def __init__(self, **cortex_kwargs: Any) -> None:
        self.cortex_kwargs = cortex_kwargs
        self.errors = 0
        self.error_samples: list[str] = []

    def _values(self, x: Any) -> dict[str, Any]:
        return {self.schema[0]: x} if len(self.schema) == 1 else dict(zip(self.schema, x))

    def _note(self, exc: Exception) -> None:
        self.errors += 1
        if len(self.error_samples) < 5:
            self.error_samples.append(f"{type(exc).__name__}: {str(exc)[:80]}")

    def fit(self, ctx, shots):
        from ..procedure_cortex import ProcedureCortex
        self.schema = tuple(ctx["public"]["schema"])
        self.mech = f"m_{ctx['task_id']}".replace("-", "_")
        self.cortex = ProcedureCortex(":memory:", trust_provider=lambda source: {"reliability": 1.0, "version": 1}, **self.cortex_kwargs)
        for i, (x, y) in enumerate(shots):
            try:
                self.cortex.observe(self.mech, self._values(x), y, evidence_id=f"e{i}", source_id="sim", root_id=f"r{i}", auto_induce=True)
            except Exception as exc:  # recorded and reported, never silently dropped
                self._note(exc)

    def predict(self, x):
        try:
            out = self.cortex.predict(self.mech, self._values(x))
        except Exception as exc:
            self._note(exc)
            return ABSTAIN, 0.0
        return (out["value"], float(out["confidence"])) if out.get("status") == "predicted" else (ABSTAIN, 0.0)


def run_struct_benchmark(factories: Mapping[str, Callable[[], Learner]], *, seed: int, tasks_per_family: int, ks: Sequence[int],
                         families: Sequence[str] = FAMILIES) -> dict[str, Any]:
    """A FRESH learner is built per task and per k; scored queries are never in the training pool (asserted)."""
    ks = sorted(ks)
    res: dict[str, Any] = {"seed": seed, "tasks_per_family": tasks_per_family, "ks": ks, "cells": {}, "errors": {}, "queries_per_family": {}}
    for family in families:
        suite = make_struct_suite(family, tasks_per_family, seed)
        res["queries_per_family"][family] = sum(len(t.queries) for t in suite)
        shots = {t.task_id: draw_shots(t, ks[-1], seed) for t in suite}
        for t in suite:
            if set(t.queries) & set(t.pool):
                raise AssertionError(f"{t.task_id}: query inside training pool")
        for name, factory in factories.items():
            for k in ks:
                rows_all, per_task = [], []
                for t in suite:
                    learner = factory()
                    rows = score_task(learner, t, shots[t.task_id][:k], t.queries)
                    rows_all.extend(rows)
                    per_task.append(sum(1 for _, ok, _ in rows if ok) / len(rows))
                    if getattr(learner, "errors", 0):
                        e = res["errors"].setdefault(name, {"count": 0, "samples": []})
                        e["count"] += learner.errors
                        e["samples"] = (e["samples"] + list(getattr(learner, "error_samples", [])))[:5]
                cell = summarize(rows_all)
                cell["per_task_correct_rate"] = per_task
                res["cells"].setdefault(name, {}).setdefault(family, {})[str(k)] = cell
    return res


def evaluate_part_a(results: Mapping[str, Any], prereg: Mapping[str, Any]) -> list[dict[str, Any]]:
    pa, ks, verdicts = prereg["part_a"], results["ks"], []
    kmax = ks[-1]
    fams = [f for f in pa["families"] if f in results["queries_per_family"]]
    cell = lambda name, fam, k: results["cells"][name][fam][str(k)]

    def add(cid, group, passed, observed, rule):
        verdicts.append({"id": cid, "group": group, "passed": bool(passed), "observed": observed, "rule": rule})

    v = pa["validity"]
    c = v["H1_reference_safe"]
    worst = max(cell(c["learner"], f, k)["wrong_rate"] for f in fams for k in ks)
    add("A-H1", "harness", worst <= c["max_wrong_rate"], {"max_wrong_rate": worst}, "grid reference never wrong at any k")
    c = v["H2_reference_learns"]
    obs = {f: cell(c["learner"], f, kmax)["correct_rate"] for f in fams}
    add("A-H2", "harness", all(x >= c["min_correct_rate_at_kmax"] for x in obs.values()), obs, f"grid reference correct_rate at kmax >= {c['min_correct_rate_at_kmax']}")
    c = v["H3_memorizer_canary"]
    worst = max(cell(c["learner"], f, k)["correct_rate"] for f in fams for k in ks)
    add("A-H3", "harness", worst <= c["max_correct_rate"], {"max_correct_rate": worst}, "memorizer scores nothing (leakage canary)")
    c = v["H4_shuffled_control_collapses"]
    obs = {f: cell(c["learner"], f, kmax)["correct_rate"] for f in fams}
    add("A-H4", "harness", all(x <= c["max_correct_rate_at_kmax"] for x in obs.values()), obs, f"shuffled-label reference correct_rate at kmax <= {c['max_correct_rate_at_kmax']}")
    c = v["H5_majority_floor_is_beaten"]
    obs = {f: cell(c["learner"], f, kmax)["correct_rate"] - cell("majority", f, kmax)["correct_rate"] for f in fams}
    add("A-H5", "harness", all(x >= c["min_gap_over_majority"] for x in obs.values()), obs, f"reference - majority correct_rate at kmax >= {c['min_gap_over_majority']}")

    a = pa["asm_claims"]
    if a["learner"] in results["cells"]:
        c = a["A1_never_wrong_on_determined_queries"]
        obs = {f: max(cell(a["learner"], f, k)["wrong_rate"] for k in ks) for f in fams}
        add("A1", "asm", all(x <= c["max_wrong_rate"] for x in obs.values()), obs, f"ASM wrong_rate <= {c['max_wrong_rate']} at every k, every family")
        c = a["A2_shuffled_labels_never_answered_wrongly"]
        obs = {f: max(cell(c["learner"], f, k)["wrong_rate"] for k in ks) for f in fams}
        add("A2", "asm", all(x <= c["max_wrong_rate"] for x in obs.values()), obs, f"ASM trained on shuffled labels: wrong_rate <= {c['max_wrong_rate']}")
        c = a["A3_coverage"]
        obs = {f: cell(a["learner"], f, kmax)["correct_rate"] for f in fams}
        n_ok = sum(1 for x in obs.values() if x >= c["min_correct_rate_at_kmax"])
        add("A3", "asm", n_ok >= c["min_families"], {"families_at_threshold": n_ok, **obs}, f">= {c['min_families']} families with correct_rate >= {c['min_correct_rate_at_kmax']} at k={kmax}")
    return verdicts
