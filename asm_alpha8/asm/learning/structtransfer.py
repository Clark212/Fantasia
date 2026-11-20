"""DEV4 Part B: does ASM's families mechanism transfer structure between tasks? (target structure y = x*x + c)

Experimental; NOT wired into ASM beliefs, memory or action selection.

Each attempt uses a FRESH ProcedureCortex (default configuration). Donors are validated procedures installed through the public
``propose`` + held-out-validation lifecycle and never use the target constant. The target gets 3 fit examples, one induction call
(``use_families=True``, budget 512), then 8 validation examples; success means the active procedure answers every held-out
interior query correctly. Arms: none / one_relevant / relevant / unrelated / mixed / relevant_shuffled.
"""
from __future__ import annotations

import random
from typing import Any, Mapping, Sequence

from .simlab import prereg_hash

IN_RANGE = (-8, -7, -6, -5, -4, -3, -2, -1, 1, 2, 3, 4, 5, 6, 7, 8)
OUT_OF_RANGE = (-12, -11, -10, -9, 9, 10, 11, 12)
ARMS = ("none", "one_relevant", "relevant", "unrelated", "mixed", "relevant_shuffled")
TRUST = lambda source: {"reliability": 0.99, "version": 1}
DONOR_FIT_XS = (0, 1, 2)
VALIDATION_XS = tuple(range(10, 18))

# donor programs as (name, expression, python function)
def _square_donor(c: int):
    return (f"sq_{'m' if c < 0 else 'p'}{abs(c)}", ("add", ("mul", "x", "x"), c), lambda x, c=c: x * x + c)


UNRELATED_DONORS = (
    ("aff_2x_p1", ("add", ("mul", 2, "x"), 1), lambda x: 2 * x + 1),
    ("aff_3x_m4", ("add", ("mul", 3, "x"), -4), lambda x: 3 * x - 4),
    ("max_x_3", ("max", "x", 3), lambda x: max(x, 3)),
    ("max_x_6", ("max", "x", 6), lambda x: max(x, 6)),
)


def derange(values: Sequence[Any], rng: random.Random) -> list[Any]:
    """A permutation of ``values`` in which no position keeps its original value (a plain shuffle of 3 items is the identity 1 time in 6)."""
    values = list(values)
    if len(values) < 2 or len(set(values)) < 2:
        raise ValueError("need at least two distinct values to derange")
    for _ in range(10000):
        perm = values[:]
        rng.shuffle(perm)
        if all(a != b for a, b in zip(perm, values)):
            return perm
    raise RuntimeError("could not derange")


def donor_constants(target_c: int, fit_seed: int, seed: int) -> tuple[int, int]:
    rng = random.Random(f"{seed}:donors:{target_c}:{fit_seed}")
    choices = [c for c in IN_RANGE if c != target_c]
    return tuple(rng.sample(choices, 2))     # two distinct in-range constants, never the target's


def donors_for(arm: str, target_c: int, fit_seed: int, seed: int) -> list[tuple[str, Any, Any]]:
    c1, c2 = donor_constants(target_c, fit_seed, seed)
    relevant = [_square_donor(c1), _square_donor(c2)]
    if arm in ("none",):
        return []
    if arm == "one_relevant":
        return relevant[:1]
    if arm in ("relevant", "relevant_shuffled"):
        return relevant
    if arm == "unrelated":
        return list(UNRELATED_DONORS)
    if arm == "mixed":
        return relevant + list(UNRELATED_DONORS)
    raise ValueError(f"unknown arm {arm!r}")


def _install(cortex, donors) -> int:
    from ..procedure_program import Program
    active = 0
    for name, expr, fn in donors:
        for x in DONOR_FIT_XS:
            cortex.observe(name, {"x": x}, fn(x), evidence_id=f"{name}-fit-{x}", source_id="oracle")
        proposed = cortex.propose(name, Program({"x": "int"}, expr), provenance="external")
        if proposed.get("status") != "proposed":
            raise RuntimeError(f"donor {name} was not proposed: {proposed}")
        for x in VALIDATION_XS:
            cortex.observe(name, {"x": x}, fn(x), evidence_id=f"{name}-val-{x}", source_id="oracle")
        active += sum(1 for v in cortex.versions(name) if v["state"] == "active")
    return active


def run_attempt(arm: str, target_c: int, fit_seed: int, seed: int) -> dict[str, Any]:
    from ..procedure_cortex import ProcedureCortex
    rng = random.Random(f"{seed}:attempt:{target_c}:{fit_seed}")
    fit = sorted(rng.sample(range(10), 3))
    truth = lambda x: x * x + target_c
    queries = [x for x in range(10) if x not in fit and fit[0] <= x]
    donors = donors_for(arm, target_c, fit_seed, seed)
    cortex = ProcedureCortex(":memory:", trust_provider=TRUST)         # DEFAULT configuration
    try:
        active_donors = _install(cortex, donors)
        fit_labels = [truth(x) for x in fit]
        val_labels = [truth(x) for x in VALIDATION_XS]
        if arm == "relevant_shuffled":
            fit_labels = derange(fit_labels, random.Random(f"{seed}:shuffle:{target_c}:{fit_seed}"))
            val_labels = derange(val_labels, random.Random(f"{seed}:shuffle-val:{target_c}:{fit_seed}"))
        for x, y in zip(fit, fit_labels):
            cortex.observe("target", {"x": x}, y, evidence_id=f"t-fit-{x}", source_id="oracle")
        r = cortex.induce("target", use_families=True)
        rec: dict[str, Any] = {"arm": arm, "target_c": target_c, "fit_seed": fit_seed, "fit_xs": fit,
                               "donor_constants": [d[0] for d in donors], "active_donors": active_donors,
                               "status": r.get("status"), "origin": r.get("origin"),
                               "evaluator_calls": int(r.get("evaluator_calls", 0)), "candidates": int(r.get("candidate_count", 0))}
        answered = wrong = 0
        if r.get("status") == "proposed":
            for x, y in zip(VALIDATION_XS, val_labels):
                cortex.observe("target", {"x": x}, y, evidence_id=f"t-val-{x}", source_id="oracle")
            for q in queries:
                p = cortex.predict("target", {"x": q})
                if p.get("status") == "predicted":
                    answered += 1
                    wrong += p["value"] != truth(q)
        rec.update(queries=len(queries), answered=answered, wrong=wrong,
                   success=bool(r.get("status") == "proposed" and answered == len(queries) and wrong == 0))
        return rec
    finally:
        cortex.close()


def run_transfer(*, seed: int, fit_seeds: int, arms: Sequence[str] = ARMS, in_range: Sequence[int] = IN_RANGE,
                 out_of_range: Sequence[int] = OUT_OF_RANGE) -> dict[str, Any]:
    res: dict[str, Any] = {"seed": seed, "fit_seeds": fit_seeds, "attempts": [], "summary": {}}
    for group, constants in (("in_range", in_range), ("out_of_range", out_of_range)):
        for arm in arms:
            recs = [run_attempt(arm, c, s, seed) for c in constants for s in range(fit_seeds)]
            res["attempts"].extend({**r, "group": group} for r in recs)
            n = len(recs)
            queries = sum(r.get("queries", 0) for r in recs)
            res["summary"].setdefault(group, {})[arm] = {
                "n": n, "success_rate": sum(r["success"] for r in recs) / n,
                "mean_evaluator_calls": sum(r["evaluator_calls"] for r in recs) / n,
                "family_origin_rate": sum(1 for r in recs if str(r["origin"]).startswith("family:")) / n,
                "wrong_answers": sum(r["wrong"] for r in recs), "answered": sum(r["answered"] for r in recs),
                "wrong_per_query": (sum(r["wrong"] for r in recs) / queries) if queries else 0.0,
            }
    return res


def evaluate_part_b(results: Mapping[str, Any], prereg: Mapping[str, Any]) -> list[dict[str, Any]]:
    pb, S, verdicts = prereg["part_b"], results["summary"], []

    def add(cid, group, passed, observed, rule):
        verdicts.append({"id": cid, "group": group, "passed": bool(passed), "observed": observed, "rule": rule})

    rate = lambda grp, arm: S[grp][arm]["success_rate"]
    cost = lambda grp, arm: S[grp][arm]["mean_evaluator_calls"]
    c = pb["validity"]["V2_shuffled_labels_do_not_succeed"]
    add("B-V1", "harness", all(set(r["donor_constants"]).isdisjoint({f"sq_{'m' if a['target_c'] < 0 else 'p'}{abs(a['target_c'])}"})
                                for a in results["attempts"] for r in [a]),
        {"attempts_checked": len(results["attempts"])}, "no donor ever uses the target constant")
    add("B-V2", "harness", rate("in_range", c["arm"]) <= c["max_success"], {"success": rate("in_range", c["arm"])},
        f"{c['arm']} success <= {c['max_success']} (success cannot occur without signal)")
    t = pb["claims"]
    k = t["T1_capability_gain"]
    gap = rate("in_range", "relevant") - rate("in_range", "none")
    add("T1", "asm", gap >= k["min_success_gap_relevant_vs_none"], {"relevant": rate("in_range", "relevant"), "none": rate("in_range", "none"), "gap": gap},
        f"success(relevant) - success(none) >= {k['min_success_gap_relevant_vs_none']} (in-range targets)")
    k = t["T2_one_donor_is_not_enough"]
    gain = rate("in_range", "one_relevant") - rate("in_range", "none")
    add("T2", "asm", gain <= k["max_success_gain_over_none"], {"one_relevant": rate("in_range", "one_relevant"), "none": rate("in_range", "none"), "gain": gain},
        f"success(one_relevant) - success(none) <= {k['max_success_gain_over_none']}")
    k = t["T3_no_negative_transfer"]
    drop = rate("in_range", "none") - rate("in_range", k["arm"])
    ratio = cost("in_range", k["arm"]) / cost("in_range", "none") if cost("in_range", "none") else float("inf")
    add("T3", "asm", drop <= k["max_success_drop"] and ratio <= k["max_cost_ratio"], {"success_drop": drop, "cost_ratio": ratio},
        f"unrelated donors: success drop <= {k['max_success_drop']} and cost ratio <= {k['max_cost_ratio']}")
    k = t["T3b_no_interference"]
    drop = rate("in_range", "relevant") - rate("in_range", k["arm"])
    add("T3b", "asm", drop <= k["max_success_drop_vs_relevant"], {"success_drop": drop, "mixed": rate("in_range", "mixed")},
        f"mixed donors: success within {k['max_success_drop_vs_relevant']} of relevant")
    k = t["T4_safe"]
    worst = max(S[g][a]["wrong_per_query"] for g in S for a in S[g])
    add("T4", "asm", worst <= k["max_wrong_active_rate"], {"max_wrong_per_query": worst}, f"wrong answers per held-out query <= {k['max_wrong_active_rate']} in every arm")
    k = t["T5_parameter_range_limit"]
    add("T5", "asm", rate("out_of_range", "relevant") <= k["max_success_out_of_range"], {"success_out_of_range": rate("out_of_range", "relevant")},
        f"relevant donors cannot reach constants outside +-8: success <= {k['max_success_out_of_range']} (predicted range limit)")
    return verdicts
