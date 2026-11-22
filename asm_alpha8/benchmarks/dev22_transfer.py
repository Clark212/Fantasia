"""DEV22: do learned families transfer structure to integer targets with two inputs (ProcedureCortex(family_scope=
'any_int'))? Pre-registered in benchmarks/preregistration/dev22_study.md; DEV21's protocol (dev21_transfer.py) on (x, y).

Each attempt: a fresh cortex; donors through propose + held-out validation; the target gets 3 fit examples, one induce
(budget 512), 8 validation examples; success = every held-out query answered correctly. Every attempt runs with
family_scope 'one_input' (control: today's behaviour) and 'any_int' (candidate), paired.
Usage: python benchmarks/dev22_transfer.py <out.jsonl> [--development]
"""
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
import dev21_transfer as D21  # noqa: E402
from asm.coding.integrity import ChainedWriter, code_hash, environment_provenance, file_sha256  # noqa: E402
from asm.learning import structtransfer as T  # noqa: E402
from asm.procedure_cortex import ProcedureCortex  # noqa: E402
from asm.procedure_program import Program  # noqa: E402

PREREG = ROOT / "benchmarks" / "preregistration" / "dev22_study.md"
SCHEMA = {"x": "int", "y": "int"}
MODES = ("one_input", "any_int")
DONOR_FIT = ((0, 1), (1, 2), (2, 0))
VALIDATION = ((10, 13), (11, 10), (12, 16), (13, 11), (14, 17), (15, 12), (16, 15), (17, 14))
TRANSFER_ARMS = ("none", "one_relevant", "relevant", "unrelated", "relevant_shuffled", "mixed")
REGRESSION_ARMS = ("none", "unrelated")   # a target today's search solves, with unrelated families present
STRUCTURES = {  # name -> c -> (expression, function); development (run before the pre-registration)
    "dev_mulxy": lambda c: (("add", ("mul", "x", "y"), c), lambda x, y, c=c: x * y + c),
    "dev_shiftmul": lambda c: (("mul", ("add", "x", c), "y"), lambda x, y, c=c: (x + c) * y),
    "dev_affine": lambda c: (("add", ("sub", ("mul", 2, "x"), ("mul", 3, "y")), c), lambda x, y, c=c: 2 * x - 3 * y + c),
}
HELD_OUT = {  # never run before the pre-registration
    "xmul_ysub": lambda c: (("mul", "x", ("sub", "y", c)), lambda x, y, c=c: x * (y - c)),
    "maxplus": lambda c: (("add", ("max", "x", "y"), c), lambda x, y, c=c: max(x, y) + c),
    "sqmix": lambda c: (("add", ("mul", "x", "x"), ("mul", c, "y")), lambda x, y, c=c: x * x + c * y),
}
REGRESSION = {"aff_hold": lambda c: (("add", ("add", ("mul", -1, "x"), ("mul", 4, "y")), c), lambda x, y, c=c: -x + 4 * y + c)}
UNRELATED_HELD_OUT = (("aff_2x_3y_p1", ("add", ("add", ("mul", 2, "x"), ("mul", 3, "y")), 1), lambda x, y: 2 * x + 3 * y + 1),
                      ("aff_5x_3y_m2", ("add", ("add", ("mul", 5, "x"), ("mul", 3, "y")), -2), lambda x, y: 5 * x + 3 * y - 2),
                      ("min_xy_p2", ("add", ("min", "x", "y"), 2), lambda x, y: min(x, y) + 2),
                      ("min_xy_p6", ("add", ("min", "x", "y"), 6), lambda x, y: min(x, y) + 6))
SEED = 20261124
GATE = {"min_gain_vs_control": 0.30, "max_paired_p": 0.01, "t1_min_gap": 0.50, "no_interference_max_drop": 0.10,
        "unrelated_max_gain_over_none": 0.05, "shuffled_max_success": 0.05, "max_wrong_per_query": 0.02,
        "regression_max_drop": 0.05, "unrelated_max_cost_ratio": 1.10}
UNRELATED = (("aff_2x_y_p1", ("add", ("add", ("mul", 2, "x"), "y"), 1), lambda x, y: 2 * x + y + 1),
             ("aff_3x_y_m4", ("add", ("add", ("mul", 3, "x"), "y"), -4), lambda x, y: 3 * x + y - 4),
             ("max_x_y1", ("max", "x", ("add", "y", 1)), lambda x, y: max(x, y + 1)),
             ("max_x_y5", ("max", "x", ("add", "y", 5)), lambda x, y: max(x, y + 5)))


def install(cortex, donors):
    for name, expr, fn in donors:
        for i, (x, y) in enumerate(DONOR_FIT):
            cortex.observe(name, {"x": x, "y": y}, fn(x, y), evidence_id=f"{name}-fit-{i}", source_id="oracle")
        if cortex.propose(name, Program(SCHEMA, expr), provenance="external").get("status") != "proposed":
            raise RuntimeError(f"donor {name} was not proposed")
        for i, (x, y) in enumerate(VALIDATION):
            cortex.observe(name, {"x": x, "y": y}, fn(x, y), evidence_id=f"{name}-val-{i}", source_id="oracle")
    return sum(v["state"] == "active" for name, _, _ in donors for v in cortex.versions(name))


def attempt(structures, structure, arm, c, fit_seed, seed, mode, unrelated=UNRELATED):
    rng = random.Random(f"{seed}:attempt:{structure}:{c}:{fit_seed}")
    fit = sorted(rng.sample([(x, y) for x in range(10) for y in range(10)], 3))
    lo = (min(x for x, _ in fit), min(y for _, y in fit))
    queries = rng.sample(sorted({(x, y) for x in range(lo[0], 10) for y in range(lo[1], 10)} - set(fit)), 6)
    truth = structures[structure](c)[1]
    c1, c2 = T.donor_constants(c, fit_seed, seed)
    relevant = [(f"z_rel_{structure}_{'m' if k < 0 else 'p'}{abs(k)}", *structures[structure](k)) for k in (c1, c2)]
    donors = {"none": [], "one_relevant": relevant[:1], "relevant": relevant, "relevant_shuffled": relevant,
              "unrelated": list(unrelated), "mixed": relevant + list(unrelated)}[arm]
    cortex = ProcedureCortex(":memory:", trust_provider=T.TRUST, family_scope=mode)
    try:
        active = install(cortex, donors)
        fit_y, val_y = [truth(x, y) for x, y in fit], [truth(x, y) for x, y in VALIDATION]
        if arm == "relevant_shuffled":
            fit_y = D21.shuffled(fit_y, random.Random(f"{seed}:shuffle:{structure}:{c}:{fit_seed}"))
            val_y = D21.shuffled(val_y, random.Random(f"{seed}:shuffle-val:{structure}:{c}:{fit_seed}"))
        for i, ((x, y), v) in enumerate(zip(fit, fit_y)):
            cortex.observe("target", {"x": x, "y": y}, v, evidence_id=f"t-fit-{i}", source_id="oracle")
        r = cortex.induce("target", use_families=True)
        answered = wrong = 0
        if r.get("status") == "proposed":
            for i, ((x, y), v) in enumerate(zip(VALIDATION, val_y)):
                cortex.observe("target", {"x": x, "y": y}, v, evidence_id=f"t-val-{i}", source_id="oracle")
            for x, y in queries:
                p = cortex.predict("target", {"x": x, "y": y})
                if p.get("status") == "predicted":
                    answered += 1
                    wrong += p["value"] != truth(x, y)
        return {"structure": structure, "arm": arm, "c": c, "fit_seed": fit_seed, "mode": mode, "fit": fit,
                "donors": [d[0] for d in donors], "active_donors": active, "status": r.get("status"),
                "origin": r.get("origin"), "candidates": int(r.get("candidate_count", 0)),
                "evaluator_calls": int(r.get("evaluator_calls", 0)), "queries": len(queries), "answered": answered,
                "wrong": wrong, "success": r.get("status") == "proposed" and answered == len(queries) and wrong == 0}
    finally:
        cortex.close()


def summarize(recs):
    S = {}
    for mode in MODES:
        for arm in TRANSFER_ARMS:
            for group, consts in (("in_range", D21.IN_RANGE), ("out_of_range", D21.OUT_OF_RANGE)):
                rs = [r for r in recs if r["mode"] == mode and r["arm"] == arm and r["c"] in consts]
                if rs:
                    k, q = sum(r["success"] for r in rs), sum(r["queries"] for r in rs)
                    S[f"{mode}|{arm}|{group}"] = {
                        "n": len(rs), "success_rate": round(k / len(rs), 4), "wilson95": D21.wilson(k, len(rs)),
                        "mean_evaluator_calls": round(sum(r["evaluator_calls"] for r in rs) / len(rs), 2),
                        "family_origin_rate": round(sum(str(r["origin"]).startswith("family:") for r in rs) / len(rs), 4),
                        "wrong": sum(r["wrong"] for r in rs), "wrong_per_query": sum(r["wrong"] for r in rs) / q if q else 0.0}
    return S


def gate(recs):
    T_, R_ = [r for r in recs if r["structure"] in HELD_OUT], [r for r in recs if r["structure"] in REGRESSION]
    S, g = summarize(T_), GATE
    rate = lambda m, a: S[f"{m}|{a}|in_range"]["success_rate"]  # noqa: E731
    cost = lambda m, a: S[f"{m}|{a}|in_range"]["mean_evaluator_calls"]  # noqa: E731
    pairs = {}
    for r in T_:
        if r["arm"] == "relevant" and r["c"] in D21.IN_RANGE:
            pairs.setdefault((r["structure"], r["c"], r["fit_seed"]), {})[r["mode"]] = r["success"]
    b = sum(1 for v in pairs.values() if v["any_int"] and not v["one_input"])
    c = sum(1 for v in pairs.values() if v["one_input"] and not v["any_int"])
    reg = {m: [r for r in R_ if r["mode"] == m and r["arm"] == "unrelated" and r["c"] in D21.IN_RANGE] for m in MODES}
    reg_rate = {m: sum(r["success"] for r in v) / len(v) for m, v in reg.items()}
    checks = {
        "C1_gain_over_control": rate("any_int", "relevant") - rate("one_input", "relevant") >= g["min_gain_vs_control"]
                                and D21.mcnemar_one_sided(b, c) < g["max_paired_p"],
        "C2_transfer_gain": rate("any_int", "relevant") - rate("any_int", "none") >= g["t1_min_gap"],
        "C3_no_interference": rate("any_int", "relevant") - rate("any_int", "mixed") <= g["no_interference_max_drop"],
        "C4_no_false_transfer": rate("any_int", "unrelated") - rate("any_int", "none") <= g["unrelated_max_gain_over_none"]
                                and rate("any_int", "relevant_shuffled") <= g["shuffled_max_success"],
        "C5_safe": max([v["wrong_per_query"] for v in S.values()]
                       + [sum(r["wrong"] for r in R_) / max(1, sum(r["queries"] for r in R_))]) <= g["max_wrong_per_query"],
        "C6_no_regression": reg_rate["one_input"] - reg_rate["any_int"] <= g["regression_max_drop"],
        "C7_unrelated_cost": cost("any_int", "unrelated") / cost("one_input", "unrelated") <= g["unrelated_max_cost_ratio"],
    }
    return {"G22-A": "passed" if all(checks.values()) else "not passed", "checks": checks,
            "paired_relevant": {"any_int_only": b, "one_input_only": c, "exact_one_sided_p": D21.mcnemar_one_sided(b, c)},
            "regression": {m: {"n": len(v), "success": reg_rate[m],
                               "mean_evaluator_calls": round(sum(r["evaluator_calls"] for r in v) / len(v), 1)} for m, v in reg.items()},
            "summary": S}


def main():
    out, dev = Path(sys.argv[1]), "--development" in sys.argv
    if dev:
        plan, seed, unrelated = [(s, TRANSFER_ARMS) for s in STRUCTURES], 20261122, UNRELATED
    else:
        plan = [(s, TRANSFER_ARMS) for s in HELD_OUT] + [(s, REGRESSION_ARMS) for s in REGRESSION]
        seed, unrelated = SEED, UNRELATED_HELD_OUT
    structures = {**STRUCTURES, **HELD_OUT, **REGRESSION}
    w = ChainedWriter(out, {"run": "dev22_transfer" + (" development" if dev else ""), "provenance": environment_provenance(),
                            "asm_coding_sha256": code_hash(), "harness_sha256": file_sha256(Path(__file__)),
                            "asm_procedure_cortex_sha256": file_sha256(ROOT / "asm" / "procedure_cortex.py"), "seed": seed,
                            "gate": None if dev else GATE,
                            "preregistration_sha256": file_sha256(PREREG) if PREREG.exists() else None})
    t0, recs = time.time(), []
    for structure, arms in plan:
        for arm in arms:
            for c in D21.IN_RANGE + D21.OUT_OF_RANGE:
                for s in range(D21.FIT_SEEDS):
                    for mode in MODES:
                        rec = attempt(structures, structure, arm, c, s, seed, mode, unrelated)
                        recs.append(rec)
                        w.append({"part": "attempt", **rec})
    result = {"summary": summarize(recs)} if dev else gate(recs)
    if not dev:
        result["per_structure"] = {s: {m: summarize([r for r in recs if r["structure"] == s])[f"{m}|relevant|in_range"]["success_rate"]
                                       for m in MODES} for s in HELD_OUT}
    w.append({"part": "result", **result, "seconds": round(time.time() - t0, 1)})
    print(json.dumps({k: v for k, v in result.items() if k != "summary"}, indent=1))
    for k, v in result["summary"].items():
        if k.endswith("in_range"):
            print(f"{k:38s} {v['success_rate']:.3f} {v['wilson95']} calls {v['mean_evaluator_calls']:7.1f} fam {v['family_origin_rate']:.2f} wrong {v['wrong']}")


if __name__ == "__main__":
    main()
