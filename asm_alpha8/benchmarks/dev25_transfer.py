"""DEV25: does solving a family's parameters from the fit examples (ProcedureCortex(family_parameters='solve')) remove the
two limits of enumerating them, namely the budget's reach when many sources compete (DEV24) and the -8..8 range?
Pre-registered in benchmarks/preregistration/dev25_study.md.

DEV24's three-input protocol (dev24_transfer.py): relevant donors over (u, v, w) in role order 0 or 5, unrelated donors
over (p, q, r); constants in range (-8..8), out of range (|c| = 9..12) and far (|c| = 20, 50). Every attempt runs with
family_parameters 'enumerate' (control: today's default) and 'solve' (candidate), both with family_scope='any_int' and
family_mapping='rename'. One structure per run is not affine in its parameter, to check the fallback to enumeration.
Usage: python benchmarks/dev25_transfer.py <out.jsonl> [--development]
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
import dev24_transfer as D24  # noqa: E402
from asm.coding.integrity import ChainedWriter, code_hash, environment_provenance, file_sha256  # noqa: E402
from asm.learning import structtransfer as T  # noqa: E402
from asm.procedure_cortex import ProcedureCortex  # noqa: E402

PREREG = ROOT / "benchmarks" / "preregistration" / "dev25_study.md"
MODES = ("enumerate", "solve")
ARMS = ("none", "unrelated", "relevant_r0", "relevant_r5", "relevant_shuffled", "mixed_r0", "mixed_r5")
NONAFFINE_ARMS = ("none", "relevant_r0", "mixed_r0")
FAR = (-50, -20, 20, 50)
CONSTANTS = D21.IN_RANGE + D21.OUT_OF_RANGE + FAR
BEYOND_REACH = tuple(c for c in D21.IN_RANGE if c not in D24.MIXED_REACH)  # 6, 7, 8 (DEV24's budget arithmetic)
DEV = {k: D24.DEV[k] for k in ("dev_mul_add", "dev_sq_sub")}
DEV_NONAFFINE = {"dev_shift_sq": lambda c: (("add", ("mul", ("sub", "x", c), ("sub", "y", c)), "z"),
                                            lambda x, y, z, c=c: (x - c) * (y - c) + z)}
HELD_OUT = {  # never run before the pre-registration
    "x_plus_y_shift": lambda c: (("add", "x", ("mul", "y", ("add", "z", c))), lambda x, y, z, c=c: x + y * (z + c)),
    "x_y_minus_zz": lambda c: (("sub", ("mul", "x", ("sub", "y", c)), ("mul", "z", "z")), lambda x, y, z, c=c: x * (y - c) - z * z),
    "sum_shift_times_z": lambda c: (("sub", ("mul", ("add", ("add", "x", "y"), c), "z"), "x"), lambda x, y, z, c=c: (x + y + c) * z - x),
}
NONAFFINE = {"shift_sq_minus_z": lambda c: (("sub", ("mul", ("add", "x", c), ("add", "y", c)), "z"),
                                            lambda x, y, z, c=c: (x + c) * (y + c) - z)}
UNRELATED = (("u_aff_3p_m2q", ("add", ("add", ("add", ("mul", 3, "p"), ("mul", -2, "q")), "r"), 4), lambda p, q, r: 3 * p - 2 * q + r + 4),
             ("u_aff_3p_q", ("add", ("add", ("add", ("mul", 3, "p"), ("mul", 1, "q")), "r"), -2), lambda p, q, r: 3 * p + q + r - 2),
             ("u_max_qm3", ("sub", ("max", "p", ("sub", "q", 3)), "r"), lambda p, q, r: max(p, q - 3) - r),
             ("u_max_qm7", ("sub", ("max", "p", ("sub", "q", 7)), "r"), lambda p, q, r: max(p, q - 7) - r))
SEED = 20261127
GATE = {"min_reach_gain": 0.50, "min_range_gain": 0.50, "max_paired_p": 0.01, "max_loss": 0.05,
        "unrelated_max_gain_over_none": 0.05, "shuffled_max_success": 0.05, "max_wrong_per_query": 0.02, "max_cost_ratio": 1.10}


def attempt(structures, structure, arm, c, fit_seed, seed, mode, unrelated):
    """DEV24's attempt (dev24_transfer.attempt), with family_parameters=mode."""
    rng = random.Random(f"{seed}:attempt:{structure}:{c}:{fit_seed}")
    fit = sorted(rng.sample([(x, y, z) for x in range(10) for y in range(10) for z in range(10)], 3))
    queries, truth = D24.queries_for(fit, rng), structures[structure](c)[1]
    cortex = ProcedureCortex(":memory:", trust_provider=T.TRUST, family_scope="any_int", family_mapping="rename", family_parameters=mode)
    try:
        active, _ = D24.install(cortex, D24.donors_for(structures, structure, arm, c, fit_seed, seed, unrelated))
        fit_y, val_y = [truth(*p) for p in fit], [truth(*p) for p in D24.VALIDATION]
        if arm == "relevant_shuffled":
            fit_y = D21.shuffled(fit_y, random.Random(f"{seed}:shuffle:{structure}:{c}:{fit_seed}"))
            val_y = D21.shuffled(val_y, random.Random(f"{seed}:shuffle-val:{structure}:{c}:{fit_seed}"))
        for i, (p, v) in enumerate(zip(fit, fit_y)):
            cortex.observe("target", dict(zip(D24.TARGET, p)), v, evidence_id=f"t-fit-{i}", source_id="oracle")
        res = cortex.induce("target", use_families=True)
        answered = wrong = 0
        if res.get("status") == "proposed":
            for i, (p, v) in enumerate(zip(D24.VALIDATION, val_y)):
                cortex.observe("target", dict(zip(D24.TARGET, p)), v, evidence_id=f"t-val-{i}", source_id="oracle")
            for q in queries:
                pred = cortex.predict("target", dict(zip(D24.TARGET, q)))
                if pred.get("status") == "predicted":
                    answered += 1
                    wrong += pred["value"] != truth(*q)
        return {"structure": structure, "arm": arm, "c": c, "fit_seed": fit_seed, "mode": mode, "fit": fit,
                "active_donors": active, "status": res.get("status"), "origin": res.get("origin"),
                "candidates": int(res.get("candidate_count", 0)), "evaluator_calls": int(res.get("evaluator_calls", 0)),
                "queries": len(queries), "answered": answered, "wrong": wrong,
                "success": res.get("status") == "proposed" and answered == len(queries) and wrong == 0}
    finally:
        cortex.close()


def cell(recs, mode, arms, structures, constants):
    rs = [r for r in recs if r["mode"] == mode and r["arm"] in arms and r["structure"] in structures and r["c"] in constants]
    k, q = sum(r["success"] for r in rs), sum(r["queries"] for r in rs)
    return {"n": len(rs), "success_rate": round(k / len(rs), 4) if rs else 0.0, "wilson95": D21.wilson(k, len(rs)),
            "mean_evaluator_calls": round(sum(r["evaluator_calls"] for r in rs) / len(rs), 1) if rs else 0.0,
            "wrong": sum(r["wrong"] for r in rs), "wrong_per_query": sum(r["wrong"] for r in rs) / q if q else 0.0}


def paired(recs, arms, structures, constants):
    """(solve only, enumerate only, exact one-sided p) over the attempts of these arms, structures and constants."""
    pairs = {}
    for r in recs:
        if r["arm"] in arms and r["structure"] in structures and r["c"] in constants:
            pairs.setdefault((r["structure"], r["arm"], r["c"], r["fit_seed"]), {})[r["mode"]] = r["success"]
    b = sum(1 for v in pairs.values() if v["solve"] and not v["enumerate"])
    c = sum(1 for v in pairs.values() if v["enumerate"] and not v["solve"])
    return b, c, D21.mcnemar_one_sided(b, c)


def gate(recs, transfer, nonaffine):
    groups = {"in_range": D21.IN_RANGE, "within_reach": D24.MIXED_REACH, "beyond_reach": BEYOND_REACH,
              "out_of_range": D21.OUT_OF_RANGE, "far": FAR, "beyond_grid": D21.OUT_OF_RANGE + FAR}
    S = {f"{m}|{a}|{g}": cell(recs, m, (a,), transfer, cs) for m in MODES for a in ARMS for g, cs in groups.items()}
    S.update({f"{m}|relevant|{g}": cell(recs, m, ("relevant_r0", "relevant_r5"), transfer, cs) for m in MODES for g, cs in groups.items()})
    S.update({f"{m}|mixed|{g}": cell(recs, m, ("mixed_r0", "mixed_r5"), transfer, cs) for m in MODES for g, cs in groups.items()})
    S.update({f"{m}|nonaffine_{a}|{g}": cell(recs, m, (a,), nonaffine, cs) for m in MODES for a in NONAFFINE_ARMS
              for g, cs in groups.items()})
    rate = lambda m, key: S[f"{m}|{key}"]["success_rate"]  # noqa: E731
    gain = lambda key: rate("solve", key) - rate("enumerate", key)  # noqa: E731
    reach = paired(recs, ("mixed_r0", "mixed_r5"), transfer, BEYOND_REACH)
    grid = paired(recs, ("relevant_r0", "relevant_r5"), transfer, D21.OUT_OF_RANGE + FAR)
    cost = lambda key: S[f"solve|{key}"]["mean_evaluator_calls"] / S[f"enumerate|{key}"]["mean_evaluator_calls"]  # noqa: E731
    g = GATE
    checks = {
        "C1_reach": gain("mixed|beyond_reach") >= g["min_reach_gain"] and reach[2] < g["max_paired_p"],
        "C2_range": gain("relevant|beyond_grid") >= g["min_range_gain"] and grid[2] < g["max_paired_p"],
        "C3_no_loss": all(-gain(k) <= g["max_loss"] for k in ("relevant|in_range", "mixed|within_reach")),
        "C4_fallback": -gain("nonaffine_relevant_r0|in_range") <= g["max_loss"] and -gain("nonaffine_mixed_r0|within_reach") <= g["max_loss"],
        "C5_no_false_transfer": rate("solve", "unrelated|in_range") - rate("solve", "none|in_range") <= g["unrelated_max_gain_over_none"]
                                and rate("solve", "relevant_shuffled|in_range") <= g["shuffled_max_success"],
        "C6_safe": max(v["wrong_per_query"] for v in S.values()) <= g["max_wrong_per_query"],
        "C7_cost": cost("relevant|in_range") <= g["max_cost_ratio"] and cost("unrelated|in_range") <= g["max_cost_ratio"],
    }
    return {"G25-A": "passed" if all(checks.values()) else "not passed", "checks": checks,
            "paired_beyond_reach": dict(zip(("solve_only", "enumerate_only", "exact_one_sided_p"), reach)),
            "paired_beyond_grid": dict(zip(("solve_only", "enumerate_only", "exact_one_sided_p"), grid)),
            "per_structure": {s: {m: cell(recs, m, ("relevant_r0", "relevant_r5"), (s,), CONSTANTS)["success_rate"] for m in MODES}
                              for s in transfer}, "summary": S}


def main():
    out, dev = Path(sys.argv[1]), "--development" in sys.argv
    transfer, nonaffine, unrelated, seed = ((DEV, DEV_NONAFFINE, D24.DEV_UNRELATED, 20261124) if dev
                                            else (HELD_OUT, NONAFFINE, UNRELATED, SEED))
    structures = {**transfer, **nonaffine}
    w = ChainedWriter(out, {"run": "dev25_transfer" + (" development" if dev else ""), "provenance": environment_provenance(),
                            "asm_coding_sha256": code_hash(), "harness_sha256": file_sha256(Path(__file__)),
                            "asm_procedure_cortex_sha256": file_sha256(ROOT / "asm" / "procedure_cortex.py"), "seed": seed,
                            "gate": GATE, "preregistration_sha256": file_sha256(PREREG) if PREREG.exists() else None})
    t0, recs = time.time(), []
    for structure, arms in [(s, ARMS) for s in transfer] + [(s, NONAFFINE_ARMS) for s in nonaffine]:
        for arm in arms:
            for c in CONSTANTS:
                for s in range(D21.FIT_SEEDS):
                    for mode in MODES:
                        rec = attempt(structures, structure, arm, c, s, seed, mode, unrelated)
                        recs.append(rec)
                        w.append({"part": "attempt", **rec})
    result = gate(recs, transfer, nonaffine)
    w.append({"part": "result", **result, "seconds": round(time.time() - t0, 1)})
    print(json.dumps({k: v for k, v in result.items() if k != "summary"}, indent=1))
    for k, v in result["summary"].items():
        print(f"{k:44s} {v['success_rate']:.3f} {v['wilson95']} calls {v['mean_evaluator_calls']:7.1f} wrong {v['wrong']} n {v['n']}")


if __name__ == "__main__":
    main()
