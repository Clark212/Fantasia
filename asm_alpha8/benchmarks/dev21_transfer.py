"""DEV21 Part A: does sharing the family budget round-robin remove interference between learned families (DEV4's T3b
failure) on target structures and donor sets never used before? Pre-registered in benchmarks/preregistration/dev21_study.md.

DEV4's protocol (asm/learning/structtransfer.py), generalized: each attempt uses a fresh ProcedureCortex, installs donors
through the public propose + held-out validation lifecycle, gives the target 3 fit examples, calls induce once
(use_families=True, budget 512), then 8 validation examples; success = the active procedure answers every held-out interior
query correctly. Every attempt runs twice, with family_sharing 'listing' (the default) and 'round_robin' (paired).
Arms: none, one_relevant, relevant, unrelated, relevant_shuffled, mixed (relevant + unrelated: 3 families) and mixed4
(+ a fourth family, stress), the two mixed arms with the relevant donors' names sorting first and last.
Usage: python benchmarks/dev21_transfer.py <out.jsonl> [--development]   (--development: DEV4's structure, seed and donors)
"""
import json
import math
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from asm.coding.integrity import ChainedWriter, code_hash, environment_provenance, file_sha256  # noqa: E402
from asm.learning import structtransfer as T  # noqa: E402
from asm.procedure_cortex import ProcedureCortex  # noqa: E402

PREREG = ROOT / "benchmarks" / "preregistration" / "dev21_study.md"
SEED = 20261123
FIT_SEEDS = 3
IN_RANGE, OUT_OF_RANGE = T.IN_RANGE, T.OUT_OF_RANGE
MODES = ("listing", "round_robin")
STRUCTURES = {  # name -> c -> (expression, function); 'square' is DEV4's (development only)
    "square": lambda c: (("add", ("mul", "x", "x"), c), lambda x, c=c: x * x + c),
    "cube": lambda c: (("add", ("mul", ("mul", "x", "x"), "x"), c), lambda x, c=c: x * x * x + c),
    "shift": lambda c: (("mul", ("add", "x", c), "x"), lambda x, c=c: (x + c) * x),
    "flip": lambda c: (("sub", c, ("mul", "x", "x")), lambda x, c=c: c - x * x),
}
HELD_OUT = ("cube", "shift", "flip")
UNRELATED = (("aff_4x_p2", ("add", ("mul", 4, "x"), 2), lambda x: 4 * x + 2),       # a two-parameter family
             ("aff_m2x_p5", ("add", ("mul", -2, "x"), 5), lambda x: -2 * x + 5),
             ("min_x_2", ("min", "x", 2), lambda x: min(x, 2)),                      # a one-parameter family
             ("min_x_7", ("min", "x", 7), lambda x: min(x, 7)))
FOURTH = (("sub_x_3", ("sub", "x", 3), lambda x: x - 3),                             # mixed4's fourth family
          ("sub_x_6", ("sub", "x", 6), lambda x: x - 6))
ARMS = (("none", "last"), ("one_relevant", "last"), ("relevant", "last"), ("unrelated", "last"),
        ("relevant_shuffled", "last"), ("mixed", "last"), ("mixed", "first"), ("mixed4", "last"), ("mixed4", "first"))
GATE = {"no_interference_max_drop": 0.10, "t1_min_gap": 0.50, "relevant_max_drop_vs_listing": 0.05,
        "unrelated_max_gain_over_none": 0.05, "shuffled_max_success": 0.05, "max_wrong_per_query": 0.02,
        "unrelated_max_cost_ratio": 1.10, "control_min_interference": 0.10}


def donors(structure, arm, order, c, fit_seed, seed, unrelated=UNRELATED, fourth=FOURTH):
    """Donor list (name, expression, function). Relevant donors never use the target constant; their names sort before
    ('first': 'a0_...') or after ('last': 'z_...') every unrelated donor, which decides the families' listing order."""
    c1, c2 = T.donor_constants(c, fit_seed, seed)
    tag = "a0" if order == "first" else "z"
    relevant = []
    for k in (c1, c2):
        expr, fn = STRUCTURES[structure](k)
        relevant.append((f"{tag}_rel_{structure}_{'m' if k < 0 else 'p'}{abs(k)}", expr, fn))
    return {"none": [], "one_relevant": relevant[:1], "relevant": relevant, "relevant_shuffled": relevant,
            "unrelated": list(unrelated), "mixed": relevant + list(unrelated),
            "mixed4": relevant + list(unrelated) + list(fourth)}[arm]


def attempt(structure, arm, order, c, fit_seed, seed, mode, unrelated=UNRELATED):
    rng = random.Random(f"{seed}:attempt:{structure}:{c}:{fit_seed}")
    fit = sorted(rng.sample(range(10), 3))
    truth = STRUCTURES[structure](c)[1]
    queries = [x for x in range(10) if x not in fit and fit[0] <= x]
    ds = donors(structure, arm, order, c, fit_seed, seed, unrelated)
    cortex = ProcedureCortex(":memory:", trust_provider=T.TRUST, family_sharing=mode)
    try:
        active = T._install(cortex, ds)
        fit_labels = [truth(x) for x in fit]
        val_labels = [truth(x) for x in T.VALIDATION_XS]
        if arm == "relevant_shuffled":
            fit_labels = T.derange(fit_labels, random.Random(f"{seed}:shuffle:{structure}:{c}:{fit_seed}"))
            val_labels = T.derange(val_labels, random.Random(f"{seed}:shuffle-val:{structure}:{c}:{fit_seed}"))
        for x, y in zip(fit, fit_labels):
            cortex.observe("target", {"x": x}, y, evidence_id=f"t-fit-{x}", source_id="oracle")
        r = cortex.induce("target", use_families=True)
        answered = wrong = 0
        if r.get("status") == "proposed":
            for x, y in zip(T.VALIDATION_XS, val_labels):
                cortex.observe("target", {"x": x}, y, evidence_id=f"t-val-{x}", source_id="oracle")
            for q in queries:
                p = cortex.predict("target", {"x": q})
                if p.get("status") == "predicted":
                    answered += 1
                    wrong += p["value"] != truth(q)
        return {"structure": structure, "arm": arm, "order": order, "c": c, "fit_seed": fit_seed, "mode": mode,
                "fit_xs": fit, "donors": [d[0] for d in ds], "active_donors": active, "status": r.get("status"),
                "origin": r.get("origin"), "candidates": int(r.get("candidate_count", 0)),
                "evaluator_calls": int(r.get("evaluator_calls", 0)), "queries": len(queries), "answered": answered,
                "wrong": wrong, "success": bool(r.get("status") == "proposed" and answered == len(queries) and wrong == 0)}
    finally:
        cortex.close()


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    centre, half = (p + z * z / (2 * n)) / d, z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(max(0.0, centre - half), 3), round(min(1.0, centre + half), 3))


def mcnemar_one_sided(b, c):
    """Exact one-sided p that round_robin-only successes (b) exceed listing-only successes (c) by chance."""
    n = b + c
    return 1.0 if n == 0 else sum(math.comb(n, k) for k in range(b, n + 1)) / 2 ** n


def summarize(recs, structures):
    S = {}
    for mode in MODES:
        for arm, order in ARMS:
            for group, consts in (("in_range", IN_RANGE), ("out_of_range", OUT_OF_RANGE)):
                rs = [r for r in recs if r["mode"] == mode and r["arm"] == arm and r["order"] == order
                      and r["c"] in consts and r["structure"] in structures]
                if not rs:
                    continue
                k, q = sum(r["success"] for r in rs), sum(r["queries"] for r in rs)
                S[f"{mode}|{arm}|{order}|{group}"] = {
                    "n": len(rs), "success": k, "success_rate": round(k / len(rs), 4), "wilson95": wilson(k, len(rs)),
                    "mean_evaluator_calls": round(sum(r["evaluator_calls"] for r in rs) / len(rs), 2),
                    "family_origin_rate": round(sum(str(r["origin"]).startswith("family:") for r in rs) / len(rs), 4),
                    "wrong": sum(r["wrong"] for r in rs), "wrong_per_query": (sum(r["wrong"] for r in rs) / q) if q else 0.0}
    return S


def gate(recs, structures):
    S = summarize(recs, structures)
    rate = lambda m, a, o="last": S[f"{m}|{a}|{o}|in_range"]["success_rate"]  # noqa: E731
    cost = lambda m, a: S[f"{m}|{a}|last|in_range"]["mean_evaluator_calls"]  # noqa: E731
    g, rr = GATE, "round_robin"
    checks = {
        "V3_control_shows_interference": rate("listing", "relevant") - rate("listing", "mixed", "last") >= g["control_min_interference"],
        "C1_no_interference_relevant_last": rate(rr, "relevant") - rate(rr, "mixed", "last") <= g["no_interference_max_drop"],
        "C1_no_interference_relevant_first": rate(rr, "relevant") - rate(rr, "mixed", "first") <= g["no_interference_max_drop"],
        "C2_transfer_gain": rate(rr, "relevant") - rate(rr, "none") >= g["t1_min_gap"],
        "C2_relevant_not_worse_than_listing": rate("listing", "relevant") - rate(rr, "relevant") <= g["relevant_max_drop_vs_listing"],
        "C3_no_false_transfer_unrelated": rate(rr, "unrelated") - rate(rr, "none") <= g["unrelated_max_gain_over_none"],
        "C3_shuffled_does_not_succeed": rate(rr, "relevant_shuffled") <= g["shuffled_max_success"],
        "C4_safe_every_arm_and_mode": max(v["wrong_per_query"] for v in S.values()) <= g["max_wrong_per_query"],
        "C5_unrelated_cost_ratio": cost(rr, "unrelated") / cost(rr, "none") <= g["unrelated_max_cost_ratio"],
    }
    pairs = {}  # paired mixed attempts, relevant last: round_robin-only vs listing-only successes
    for r in recs:
        if r["arm"] == "mixed" and r["order"] == "last" and r["c"] in IN_RANGE and r["structure"] in structures:
            pairs.setdefault((r["structure"], r["c"], r["fit_seed"]), {})[r["mode"]] = r["success"]
    b = sum(1 for v in pairs.values() if v.get("round_robin") and not v.get("listing"))
    c = sum(1 for v in pairs.values() if v.get("listing") and not v.get("round_robin"))
    verdict = ("inconclusive (the control shows no interference)" if not checks["V3_control_shows_interference"]
               else "passed" if all(v for k, v in checks.items()) else "not passed")
    return {"G21-A": verdict, "checks": checks, "paired_mixed_relevant_last": {"round_robin_only": b, "listing_only": c,
            "exact_one_sided_p": mcnemar_one_sided(b, c)}, "summary": S}


def main():
    out = Path(sys.argv[1])
    dev = "--development" in sys.argv
    structures = ("square",) if dev else HELD_OUT
    seed = 20261102 if dev else SEED
    unrelated = T.UNRELATED_DONORS if dev else UNRELATED
    w = ChainedWriter(out, {"run": "dev21_transfer" + (" development (DEV4 structure, seed, donors)" if dev else ""),
                            "provenance": environment_provenance(), "asm_coding_sha256": code_hash(),
                            "asm_procedure_cortex_sha256": file_sha256(ROOT / "asm" / "procedure_cortex.py"),
                            "seed": seed, "fit_seeds": FIT_SEEDS, "structures": structures, "gate": GATE,
                            "preregistration_sha256": file_sha256(PREREG) if PREREG.exists() else None})
    t0, recs = time.time(), []
    for structure in structures:
        for arm, order in ARMS:
            if dev and arm == "mixed4":
                continue  # DEV4 had no fourth family
            for c in IN_RANGE + OUT_OF_RANGE:
                for s in range(FIT_SEEDS):
                    for mode in MODES:
                        rec = attempt(structure, arm, order, c, s, seed, mode, unrelated)
                        recs.append(rec)
                        w.append({"part": "attempt", **rec})
    if dev:
        S = summarize(recs, structures)
        result = {"summary": S}
    else:
        result = gate(recs, structures)
        result["per_structure"] = {s: gate(recs, (s,))["checks"] for s in structures}
    result["seconds"] = round(time.time() - t0, 1)
    w.append({"part": "result", **result})
    show = {k: v for k, v in result.items() if k != "summary"}
    print(json.dumps(show, indent=1))
    print(json.dumps({k: (v["success_rate"], v["wilson95"], v["mean_evaluator_calls"], v["wrong"])
                      for k, v in result["summary"].items() if k.endswith("in_range")}, indent=0))


if __name__ == "__main__":
    main()
