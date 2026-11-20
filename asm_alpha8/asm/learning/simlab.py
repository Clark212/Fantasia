"""DEV3: controlled hidden-rule simulation lab with controls, calibration and pre-registered criteria.

Experimental; NOT wired into ASM beliefs, memory or action selection.

What it measures: WITHIN-TASK learning from experience. A fresh learner is built per task, sees k
noise-free examples of a hidden rule, and is scored on held-out inputs of that same task. It does NOT
measure cross-task transfer (that is DEV4) and carries no state between tasks.

Honest framing of the setup:
- Each environment family declares a finite hypothesis class and samples the hidden rule uniformly from
  it. ``RuleSearchLearner`` is given that class, i.e. it has the correct inductive bias by construction.
  It exists to validate the HARNESS (reference learner that must pass; controls that must fail), not as a
  claim about ASM.
- Scored queries are held-out inputs whose answer is determined by the training pool under the declared
  class, so a perfect learner can reach 100% and ambiguity is not counted against anyone.
- Shots cycle through a shuffled copy of the training pool (every pool input is seen once before any repeats);
  scored queries are never in the pool.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import math
import random
from collections import Counter
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from .experience import Experience

FAMILIES = ("boolean_4", "xor_4", "affine_mod")
PRIMES = (29, 31, 37, 41)
ABSTAIN = None


# ---------------------------------------------------------------- environments
def _bit_inputs(n: int) -> tuple:
    return tuple(itertools.product((False, True), repeat=n))


def hypothesis_params(family: str, public: Mapping[str, Any]) -> list[dict[str, Any]]:
    if family == "boolean_4":
        n = public["n"]
        return [{"i": i, "j": j, "si": si, "sj": sj, "op": op}
                for i, j in itertools.combinations(range(n), 2)
                for si in (False, True) for sj in (False, True) for op in ("and", "or")]
    if family == "xor_4":
        n = public["n"]
        return [{"subset": list(s), "c": c}
                for size in range(1, n + 1) for s in itertools.combinations(range(n), size) for c in (0, 1)]
    if family == "affine_mod":
        m = public["m"]
        return [{"a": a, "b": b} for a in range(1, m) for b in range(m)]
    raise ValueError(f"unknown family {family!r}")


def evaluate_rule(family: str, public: Mapping[str, Any], params: Mapping[str, Any], x: Any) -> Any:
    if family == "boolean_4":
        li = x[params["i"]] if params["si"] else not x[params["i"]]
        lj = x[params["j"]] if params["sj"] else not x[params["j"]]
        return (li and lj) if params["op"] == "and" else (li or lj)
    if family == "xor_4":
        return bool((sum(1 for i in params["subset"] if x[i]) + params["c"]) % 2)
    if family == "affine_mod":
        return (params["a"] * x + params["b"]) % public["m"]
    raise ValueError(f"unknown family {family!r}")


@dataclass(frozen=True)
class Task:
    task_id: str
    family: str
    public: Mapping[str, Any]          # what a learner is allowed to know
    truth: Mapping[str, Any]           # hidden rule parameters (never given to learners)
    pool: tuple                        # inputs shots may be drawn from
    queries: tuple                     # held-out, determined-by-pool inputs that are scored

    def label(self, x: Any) -> Any:
        return evaluate_rule(self.family, self.public, self.truth, x)


def make_task(family: str, index: int, seed: int) -> Task:
    rng = random.Random(f"{seed}:{family}:{index}")
    for _attempt in range(200):
        public = {"n": 4} if family != "affine_mod" else {"m": rng.choice(PRIMES)}
        universe = _bit_inputs(public["n"]) if family != "affine_mod" else tuple(range(public["m"]))
        hyps = hypothesis_params(family, public)
        truth = hyps[rng.randrange(len(hyps))]
        held = rng.sample(range(len(universe)), 4 if family != "affine_mod" else max(8, public["m"] // 3))
        pool = tuple(u for i, u in enumerate(universe) if i not in set(held))
        pool_labels = [evaluate_rule(family, public, truth, x) for x in pool]
        consistent = [h for h in hyps if all(evaluate_rule(family, public, h, x) == y for x, y in zip(pool, pool_labels))]
        queries = tuple(universe[i] for i in sorted(held)
                        if len({evaluate_rule(family, public, h, universe[i]) for h in consistent}) == 1)
        if len(queries) >= 2:
            return Task(f"{family}-{index:04d}", family, public, truth, pool, queries)
    raise RuntimeError(f"could not build a determined task for {family}/{index}")


def make_suite(family: str, count: int, seed: int) -> list[Task]:
    return [make_task(family, i, seed) for i in range(count)]


def draw_shots(task: Task, kmax: int, seed: int) -> list[tuple[Any, Any]]:
    """Nested shot sequence: the first k entries are the shots for budget k.

    The pool is shuffled once and cycled, so k >= len(pool) has seen every pool input at least once."""
    rng = random.Random(f"{seed}:shots:{task.task_id}")
    order = list(task.pool)
    rng.shuffle(order)
    return [(x, task.label(x)) for x in (order[i % len(order)] for i in range(kmax))]


def task_experiences(task: Task) -> list[Experience]:
    """Ground-truth labelled records for every pool and query input (for persistence in an ExperienceLog)."""
    out = []
    for kind, inputs in (("pool", task.pool), ("query", task.queries)):
        for idx, x in enumerate(inputs):
            out.append(Experience(f"{task.task_id}:{kind}:{idx}", "simulation", task.family, task.task_id,
                                  {"input": list(x) if isinstance(x, tuple) else x}, None,
                                  {"output": task.label(x)}, "labeled", 1.0, {"role": kind}))
    return out


# ---------------------------------------------------------------- learners
class Learner:
    name = "learner"
    errors = 0

    def fit(self, ctx: Mapping[str, Any], shots: Sequence[tuple[Any, Any]]) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def predict(self, x: Any) -> tuple[Any, float]:  # (answer or None to abstain, confidence in [0, 1])
        raise NotImplementedError


class MemorizerLearner(Learner):
    """No-generalisation baseline; also a leakage canary (it can only score if a query was seen as a shot)."""
    name = "memorizer"

    def fit(self, ctx, shots):
        self.table = {x: y for x, y in shots}

    def predict(self, x):
        return (self.table[x], 1.0) if x in self.table else (ABSTAIN, 0.0)


class MajorityLearner(Learner):
    """Chance floor: always answers the most common observed outcome."""
    name = "majority"

    def fit(self, ctx, shots):
        counts = Counter(y for _, y in shots)
        self.answer, self.conf = (None, 0.0)
        if counts:
            value, n = sorted(counts.items(), key=lambda kv: (-kv[1], repr(kv[0])))[0]
            self.answer, self.conf = value, n / len(shots)

    def predict(self, x):
        return (self.answer, self.conf) if self.answer is not None else (ABSTAIN, 0.0)


class RuleSearchLearner(Learner):
    """Reference learner with the correct hypothesis class. modes: abstain | vote | guess."""

    def __init__(self, mode: str = "abstain") -> None:
        if mode not in ("abstain", "vote", "guess"):
            raise ValueError("mode must be abstain, vote or guess")
        self.mode = mode
        self.name = f"rulesearch_{mode}"

    def fit(self, ctx, shots):
        self.family, self.public = ctx["family"], ctx["public"]
        self.consistent = [h for h in hypothesis_params(self.family, self.public)
                           if all(evaluate_rule(self.family, self.public, h, x) == y for x, y in shots)]
        counts = Counter(y for _, y in shots)
        self.fallback = sorted(counts.items(), key=lambda kv: (-kv[1], repr(kv[0])))[0][0] if counts else None

    def predict(self, x):
        if not self.consistent:
            return (self.fallback, 1.0) if self.mode == "guess" and self.fallback is not None else (ABSTAIN, 0.0)
        votes = Counter(evaluate_rule(self.family, self.public, h, x) for h in self.consistent)
        value, n = sorted(votes.items(), key=lambda kv: (-kv[1], repr(kv[0])))[0]
        if self.mode == "abstain":
            return (value, 1.0) if len(votes) == 1 else (ABSTAIN, 0.0)
        if self.mode == "vote":
            return value, n / len(self.consistent)
        return value, 1.0                                       # guess: always answers, always "certain"


class ShuffledControl(Learner):
    """Trains the wrapped learner on outcomes shuffled within the task: learning should collapse."""

    def __init__(self, inner: Learner) -> None:
        self.inner = inner
        self.name = f"shuffled_{inner.name}"

    def fit(self, ctx, shots):
        rng = random.Random(f"shuffle:{ctx['task_id']}:{len(shots)}")
        ys = [y for _, y in shots]
        rng.shuffle(ys)
        self.inner.fit(ctx, [(x, y) for (x, _), y in zip(shots, ys)])

    def predict(self, x):
        return self.inner.predict(x)

    @property
    def errors(self):  # type: ignore[override]
        return self.inner.errors


class ASMProcedureLearner(Learner):
    """ASM's existing ProcedureCortex used as a black-box learner (online observe + auto-induce)."""
    name = "asm_procedure_cortex"

    def __init__(self, **cortex_kwargs: Any) -> None:
        self.cortex_kwargs = cortex_kwargs      # forwarded to ProcedureCortex (e.g. extrapolation_guard="abstain")
        self.errors = 0
        self.error_samples: list[str] = []

    @staticmethod
    def _values(family: str, x: Any) -> dict[str, Any]:
        return {"x": x} if family == "affine_mod" else {f"f{i}": bool(v) for i, v in enumerate(x)}

    def fit(self, ctx, shots):
        from ..procedure_cortex import ProcedureCortex
        self.family, self.mech = ctx["family"], f"m_{ctx['task_id']}".replace("-", "_")
        self.cortex = ProcedureCortex(":memory:", trust_provider=lambda source: {"reliability": 1.0, "version": 1}, **self.cortex_kwargs)
        for i, (x, y) in enumerate(shots):
            try:
                self.cortex.observe(self.mech, self._values(self.family, x), y, evidence_id=f"e{i}",
                                    source_id="sim", root_id=f"r{i}", auto_induce=True)
            except Exception as exc:  # recorded and reported, never silently dropped
                self.errors += 1
                if len(self.error_samples) < 5:
                    self.error_samples.append(f"{type(exc).__name__}: {str(exc)[:80]}")

    def predict(self, x):
        try:
            out = self.cortex.predict(self.mech, self._values(self.family, x))
        except Exception as exc:
            self.errors += 1
            if len(self.error_samples) < 5:
                self.error_samples.append(f"{type(exc).__name__}: {str(exc)[:80]}")
            return ABSTAIN, 0.0
        if out.get("status") != "predicted":
            return ABSTAIN, 0.0
        return out["value"], float(out["confidence"])


# ---------------------------------------------------------------- metrics
def calibration_metrics(records: Sequence[tuple[bool, float]], bins: int = 10) -> dict[str, float]:
    """records: (correct, confidence) for ANSWERED queries only."""
    if not records:
        return {"ece": 0.0, "brier": 0.0, "mean_confidence": 0.0}
    n = len(records)
    brier = sum((conf - (1.0 if ok else 0.0)) ** 2 for ok, conf in records) / n
    ece = 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        members = [(ok, c) for ok, c in records if (lo <= c < hi) or (b == bins - 1 and c == 1.0)]
        if members:
            acc = sum(1 for ok, _ in members if ok) / len(members)
            conf = sum(c for _, c in members) / len(members)
            ece += len(members) / n * abs(acc - conf)
    return {"ece": ece, "brier": brier, "mean_confidence": sum(c for _, c in records) / n}


def score_task(learner: Learner, task: Task, shots: Sequence[tuple[Any, Any]], queries: Sequence[Any]) -> list[tuple[bool, bool, float]]:
    """Fit on shots, answer queries. Returns (answered, correct, confidence) per query."""
    learner.fit({"family": task.family, "public": dict(task.public), "task_id": task.task_id}, list(shots))
    rows = []
    for x in queries:
        answer, conf = learner.predict(x)
        if answer is ABSTAIN:
            rows.append((False, False, 0.0))
        else:
            rows.append((True, answer == task.label(x), float(conf)))
    return rows


def summarize(rows: Sequence[tuple[bool, bool, float]]) -> dict[str, float]:
    n = len(rows)
    answered = sum(1 for a, _, _ in rows if a)
    correct = sum(1 for _, ok, _ in rows if ok)
    cal = calibration_metrics([(ok, c) for a, ok, c in rows if a])
    return {"n": n, "answered": answered, "correct": correct,
            "coverage": answered / n if n else 0.0,
            "precision": correct / answered if answered else 0.0,
            "correct_rate": correct / n if n else 0.0,
            "wrong_rate": (answered - correct) / n if n else 0.0, **cal}


def paired_bootstrap(a: Sequence[float], b: Sequence[float], *, seed: int = 0, resamples: int = 2000) -> dict[str, float]:
    """95% percentile interval for mean(a - b) resampling tasks (a and b are per-task values, same order)."""
    if len(a) != len(b) or not a:
        raise ValueError("need equal-length, non-empty per-task values")
    diffs = [x - y for x, y in zip(a, b)]
    rng = random.Random(seed)
    means = sorted(sum(rng.choice(diffs) for _ in diffs) / len(diffs) for _ in range(resamples))
    return {"mean": sum(diffs) / len(diffs), "lo": means[int(0.025 * resamples)], "hi": means[int(0.975 * resamples) - 1]}


# ---------------------------------------------------------------- benchmark
def run_benchmark(factories: Mapping[str, Callable[[], Learner]], *, seed: int, tasks_per_family: int,
                  ks: Sequence[int], families: Sequence[str] = FAMILIES, log: Any = None) -> dict[str, Any]:
    """A FRESH learner is built per task and per k: nothing can leak between tasks or budgets."""
    ks = sorted(ks)
    results: dict[str, Any] = {"seed": seed, "tasks_per_family": tasks_per_family, "ks": ks, "cells": {}, "errors": {},
                               "queries_per_family": {}}
    for family in families:
        suite = make_suite(family, tasks_per_family, seed)
        if log is not None:
            log.append_many(r for t in suite for r in task_experiences(t))
        results["queries_per_family"][family] = sum(len(t.queries) for t in suite)
        shots_by_task = {t.task_id: draw_shots(t, ks[-1], seed) for t in suite}
        for t in suite:
            if set(t.queries) & set(t.pool):
                raise AssertionError(f"{t.task_id}: query inside training pool")
            if any(x not in set(t.pool) for x, _ in shots_by_task[t.task_id]):
                raise AssertionError(f"{t.task_id}: shot outside training pool")
        for name, factory in factories.items():
            for k in ks:
                rows_all, per_task = [], []
                for t in suite:
                    learner = factory()
                    rows = score_task(learner, t, shots_by_task[t.task_id][:k], t.queries)
                    rows_all.extend(rows)
                    per_task.append(sum(1 for _, ok, _ in rows if ok) / len(rows))
                    if getattr(learner, "errors", 0):
                        results["errors"].setdefault(name, {"count": 0, "samples": []})
                        results["errors"][name]["count"] += learner.errors
                        results["errors"][name]["samples"] = (results["errors"][name]["samples"]
                                                                + list(getattr(learner, "error_samples", [])))[:5]
                cell = summarize(rows_all)
                cell["per_task_correct_rate"] = per_task
                results["cells"].setdefault(name, {}).setdefault(family, {})[str(k)] = cell
    if log is not None:
        results["suite_log_head_hash"] = log.head_hash
        results["suite_log_entries"] = len(log)
    return results


# ---------------------------------------------------------------- pre-registration
def prereg_hash(prereg: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(prereg, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _cell(results, learner, family, k):
    return results["cells"][learner][family][str(k)]


def evaluate_preregistration(results: Mapping[str, Any], prereg: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Apply the pre-registered criteria to benchmark results. Returns one verdict per criterion."""
    ks, kmax = results["ks"], results["ks"][-1]
    fams = [f for f in prereg["families"] if f in results["queries_per_family"]]
    verdicts = []

    def add(cid, passed, observed, rule, group):
        verdicts.append({"id": cid, "group": group, "passed": bool(passed), "observed": observed, "rule": rule})

    h = prereg["harness_validity"]
    rs = h["H1_rulesearch_safe"]
    worst = max(_cell(results, rs["learner"], f, k)["wrong_rate"] for f in fams for k in ks)
    add("H1", worst <= rs["max_wrong_rate"], {"max_wrong_rate": worst}, f"wrong_rate <= {rs['max_wrong_rate']} for all families and k", "harness")
    c = h["H2_rulesearch_learns"]
    obs = {f: _cell(results, c["learner"], f, kmax)["correct_rate"] for f in fams}
    add("H2", all(v >= c["min_correct_rate_at_kmax"] for v in obs.values()), obs, f"correct_rate at kmax >= {c['min_correct_rate_at_kmax']}", "harness")
    c = h["H3_memorizer_canary"]
    worst = max(_cell(results, c["learner"], f, k)["correct_rate"] for f in fams for k in ks)
    add("H3", worst <= c["max_correct_rate"], {"max_correct_rate": worst}, "memorizer scores nothing on held-out queries (leakage canary)", "harness")
    c = h["H4_shuffled_control_collapses"]
    obs = {f: _cell(results, c["learner"], f, kmax)["correct_rate"] for f in fams}
    add("H4", all(v <= c["max_correct_rate_at_kmax"] for v in obs.values()), obs, f"shuffled-label control correct_rate at kmax <= {c['max_correct_rate_at_kmax']}", "harness")
    c = h["H5_calibration_metric_discriminates"]
    obs = {f: _cell(results, c["overconfident"], f, c["at_k"])["ece"] - _cell(results, c["honest"], f, c["at_k"])["ece"]
           for f in c["families"] if f in fams}
    add("H5", bool(obs) and all(v >= c["min_ece_gap"] for v in obs.values()), obs, f"ECE(overconfident) - ECE(honest) >= {c['min_ece_gap']} at k={c['at_k']}", "harness")
    c = h["H6_majority_floor_is_beaten"]
    obs = {f: _cell(results, c["learner"], f, kmax)["correct_rate"] - _cell(results, "majority", f, kmax)["correct_rate"] for f in fams}
    add("H6", all(v >= c["min_gap_over_majority"] for v in obs.values()), obs, f"rulesearch - majority correct_rate at kmax >= {c['min_gap_over_majority']}", "harness")

    a = prereg["asm_claims"]
    learner = a["learner"]
    if learner in results["cells"]:
        cl = a["A1_never_confidently_wrong"]
        obs = {f: max(_cell(results, learner, f, k)["wrong_rate"] for k in ks) for f in fams}
        add("A1", all(v <= cl["max_wrong_rate"] for v in obs.values()), obs, f"wrong_rate <= {cl['max_wrong_rate']} at every k", "asm")
        cl = a["A2_learns_with_enough_data"]
        obs = {f: _cell(results, learner, f, kmax)["correct_rate"] for f in fams}
        add("A2", all(v >= cl["min_correct_rate_at_kmax"] for v in obs.values()), obs, f"correct_rate at kmax >= {cl['min_correct_rate_at_kmax']}", "asm")
        cl = a["A3_beats_majority_control"]
        obs = {}
        for f in fams:
            ci = paired_bootstrap(_cell(results, learner, f, kmax)["per_task_correct_rate"],
                                  _cell(results, "majority", f, kmax)["per_task_correct_rate"], seed=prereg["seed"])
            obs[f] = {k: round(v, 4) for k, v in ci.items()}
        add("A3", all(v["lo"] > cl["min_ci_lower_bound"] for v in obs.values()), obs, "95% CI lower bound of (asm - majority) correct_rate at kmax > 0", "asm")
    return verdicts
