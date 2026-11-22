"""DEV23: does a family learned over other input names transfer to a two-input target when ASM must guess which input
maps to which (ProcedureCortex(family_mapping='rename'))? Pre-registered in benchmarks/preregistration/dev23_study.md.

DEV22's protocol (dev22_transfer.py). Relevant donors use inputs (a, b) in one of two role orders: 'aligned' (a plays
x, b plays y: the positional guess is right) or 'swapped' (a plays y). Unrelated donors use (p, q). Every attempt runs
with family_mapping 'exact' (control: DEV22's families) and 'rename' (candidate), both with family_scope 'any_int'.
Usage: python benchmarks/dev23_transfer.py <out.jsonl> [--development]
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
import dev22_transfer as D22  # noqa: E402
from asm.coding.integrity import ChainedWriter, code_hash, environment_provenance, file_sha256  # noqa: E402
from asm.learning import structtransfer as T  # noqa: E402
from asm.procedure_cortex import ProcedureCortex  # noqa: E402
from asm.procedure_program import Program, substitute  # noqa: E402

PREREG = ROOT / "benchmarks" / "preregistration" / "dev23_study.md"
MODES = ("exact", "rename")
TRANSFER_ARMS = ("none", "one_relevant", "relevant_aligned", "relevant_swapped", "unrelated", "relevant_shuffled",
                 "mixed_aligned", "mixed_swapped", "exact_names")
REGRESSION_ARMS = ("none", "unrelated")
DEV = {  # development structures (run before the pre-registration)
    "dev_mul_shift": lambda c: (("add", ("mul", "x", ("add", "y", c)), "y"), lambda x, y, c=c: x * (y + c) + y),
    "dev_max_shift": lambda c: (("max", ("add", "x", c), ("mul", 2, "y")), lambda x, y, c=c: max(x + c, 2 * y)),
}
DEV_REGRESSION = {"dev_aff": lambda c: (("add", ("add", ("mul", 2, "x"), ("mul", 5, "y")), c), lambda x, y, c=c: 2 * x + 5 * y + c)}
DEV_UNRELATED = (("u_aff_2p_q_p1", ("add", ("add", ("mul", 2, "p"), "q"), 1), lambda p, q: 2 * p + q + 1),
                 ("u_aff_3p_q_m4", ("add", ("add", ("mul", 3, "p"), "q"), -4), lambda p, q: 3 * p + q - 4),
                 ("u_max_p_q1", ("max", "p", ("add", "q", 1)), lambda p, q: max(p, q + 1)),
                 ("u_max_p_q5", ("max", "p", ("add", "q", 5)), lambda p, q: max(p, q + 5)))
HELD_OUT = {  # never run before the pre-registration
    "x2y_plus": lambda c: (("add", ("mul", ("mul", "x", "x"), "y"), c), lambda x, y, c=c: x * x * y + c),
    "shift_ym1": lambda c: (("mul", ("add", "x", c), ("sub", "y", 1)), lambda x, y, c=c: (x + c) * (y - 1)),
    "x_minus_cyy": lambda c: (("sub", "x", ("mul", c, ("mul", "y", "y"))), lambda x, y, c=c: x - c * y * y),
}
REGRESSION = {"aff23": lambda c: (("add", ("sub", ("mul", 3, "x"), ("mul", 2, "y")), c), lambda x, y, c=c: 3 * x - 2 * y + c)}
UNRELATED = (("u_aff_4p_mq_p3", ("add", ("add", ("mul", 4, "p"), ("mul", -1, "q")), 3), lambda p, q: 4 * p - q + 3),
             ("u_aff_4p_2q_m5", ("add", ("add", ("mul", 4, "p"), ("mul", 2, "q")), -5), lambda p, q: 4 * p + 2 * q - 5),
             ("u_max_pm2_q", ("max", ("sub", "p", 2), "q"), lambda p, q: max(p - 2, q)),
             ("u_max_pm6_q", ("max", ("sub", "p", 6), "q"), lambda p, q: max(p - 6, q)))
SEED = 20261125
GATE = {"min_gain_vs_control": 0.30, "max_paired_p": 0.01, "max_role_penalty": 0.10, "t1_min_gap": 0.50,
        "no_interference_max_drop": 0.10, "unrelated_max_gain_over_none": 0.05, "shuffled_max_success": 0.05,
        "max_wrong_per_query": 0.02, "regression_max_drop": 0.05, "unrelated_max_cost_ratio": 1.10}


def renamed(structures, structure, k, names):
    """A donor of `structure` with constant k over inputs (a, b); names = (the input playing x, the one playing y)."""
    expr, f = structures[structure](k)
    fn = (lambda a, b: f(a, b)) if names == ("a", "b") else (lambda a, b: f(b, a))
    return substitute(expr, {"x": names[0], "y": names[1]}), fn


def inputs_of(tree):
    return set().union(*map(inputs_of, tree[1:])) if isinstance(tree, tuple) else {tree} if isinstance(tree, str) else set()


def install(cortex, donors):
    """Each donor (name, two-input expression, function of its sorted inputs) through propose + held-out validation."""
    for name, expr, fn in donors:
        n1, n2 = sorted(inputs_of(expr))
        point = lambda u, v: {n1: u, n2: v}  # noqa: E731
        for i, (u, v) in enumerate(D22.DONOR_FIT):
            cortex.observe(name, point(u, v), fn(u, v), evidence_id=f"{name}-fit-{i}", source_id="oracle")
        if cortex.propose(name, Program({n1: "int", n2: "int"}, expr), provenance="external").get("status") != "proposed":
            raise RuntimeError(f"donor {name} was not proposed")
        for i, (u, v) in enumerate(D22.VALIDATION):
            cortex.observe(name, point(u, v), fn(u, v), evidence_id=f"{name}-val-{i}", source_id="oracle")
    return sum(v["state"] == "active" for name, _, _ in donors for v in cortex.versions(name))


def donors_for(structures, structure, arm, c, fit_seed, seed, unrelated):
    ks = T.donor_constants(c, fit_seed, seed)
    tag = lambda k: f"{'m' if k < 0 else 'p'}{abs(k)}"  # noqa: E731
    name = lambda k: f"z_rel_{structure}_{tag(k)}"  # noqa: E731  (after the unrelated donors, as in DEV22)
    aligned = [(name(k), *renamed(structures, structure, k, ("a", "b"))) for k in ks]
    swapped = [(name(k), *renamed(structures, structure, k, ("b", "a"))) for k in ks]
    exact = [(name(k), *structures[structure](k)) for k in ks]
    return {"none": [], "one_relevant": aligned[:1], "relevant_aligned": aligned, "relevant_swapped": swapped,
            "unrelated": list(unrelated), "relevant_shuffled": aligned, "mixed_aligned": aligned + list(unrelated),
            "mixed_swapped": swapped + list(unrelated), "exact_names": exact}[arm]


def attempt(structures, structure, arm, c, fit_seed, seed, mode, unrelated):
    rng = random.Random(f"{seed}:attempt:{structure}:{c}:{fit_seed}")
    fit = sorted(rng.sample([(x, y) for x in range(10) for y in range(10)], 3))
    queries, truth = D22.queries_for(fit, rng), structures[structure](c)[1]
    donors = donors_for(structures, structure, arm, c, fit_seed, seed, unrelated)
    cortex = ProcedureCortex(":memory:", trust_provider=T.TRUST, family_scope="any_int", family_mapping=mode)
    try:
        active = install(cortex, donors)
        fit_y, val_y = [truth(x, y) for x, y in fit], [truth(x, y) for x, y in D22.VALIDATION]
        if arm == "relevant_shuffled":
            fit_y = D21.shuffled(fit_y, random.Random(f"{seed}:shuffle:{structure}:{c}:{fit_seed}"))
            val_y = D21.shuffled(val_y, random.Random(f"{seed}:shuffle-val:{structure}:{c}:{fit_seed}"))
        for i, ((x, y), v) in enumerate(zip(fit, fit_y)):
            cortex.observe("target", {"x": x, "y": y}, v, evidence_id=f"t-fit-{i}", source_id="oracle")
        r = cortex.induce("target", use_families=True)
        answered = wrong = 0
        if r.get("status") == "proposed":
            for i, ((x, y), v) in enumerate(zip(D22.VALIDATION, val_y)):
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


def cell(recs, mode, arms, structures, constants=D21.IN_RANGE):
    rs = [r for r in recs if r["mode"] == mode and r["arm"] in arms and r["structure"] in structures and r["c"] in constants]
    k, q = sum(r["success"] for r in rs), sum(r["queries"] for r in rs)
    return {"n": len(rs), "success_rate": round(k / len(rs), 4) if rs else 0.0, "wilson95": D21.wilson(k, len(rs)),
            "mean_evaluator_calls": round(sum(r["evaluator_calls"] for r in rs) / len(rs), 1) if rs else 0.0,
            "wrong": sum(r["wrong"] for r in rs), "wrong_per_query": sum(r["wrong"] for r in rs) / q if q else 0.0}


def gate(recs, transfer, regression):
    """Cells "mode|arm" (in-range constants; the checks use these) and "mode|arm|out_of_range" (reported; C6 uses all)."""
    S = {}
    for group, constants in (("", D21.IN_RANGE), ("|out_of_range", D21.OUT_OF_RANGE)):
        for m in MODES:
            S.update({f"{m}|{a}{group}": cell(recs, m, (a,), transfer, constants) for a in TRANSFER_ARMS})
            S[f"{m}|relevant{group}"] = cell(recs, m, ("relevant_aligned", "relevant_swapped"), transfer, constants)
            S.update({f"{m}|regression_{a}{group}": cell(recs, m, (a,), regression, constants) for a in REGRESSION_ARMS})
    rate = lambda key: S[key]["success_rate"]  # noqa: E731
    pairs = {}
    for r in recs:
        if r["arm"] in ("relevant_aligned", "relevant_swapped") and r["structure"] in transfer and r["c"] in D21.IN_RANGE:
            pairs.setdefault((r["structure"], r["arm"], r["c"], r["fit_seed"]), {})[r["mode"]] = r["success"]
    b = sum(1 for v in pairs.values() if v["rename"] and not v["exact"])
    c = sum(1 for v in pairs.values() if v["exact"] and not v["rename"])
    g = GATE
    checks = {
        "C1_gain_over_control": rate("rename|relevant") - rate("exact|relevant") >= g["min_gain_vs_control"]
                                and D21.mcnemar_one_sided(b, c) < g["max_paired_p"],
        "C2_no_role_order_penalty": rate("rename|relevant_aligned") - rate("rename|relevant_swapped") <= g["max_role_penalty"],
        "C3_transfer_gain": rate("rename|relevant") - rate("rename|none") >= g["t1_min_gap"],
        "C4_no_interference": all(rate(f"rename|relevant_{o}") - rate(f"rename|mixed_{o}") <= g["no_interference_max_drop"]
                                  for o in ("aligned", "swapped")),
        "C5_no_false_transfer": rate("rename|unrelated") - rate("rename|none") <= g["unrelated_max_gain_over_none"]
                                and rate("rename|relevant_shuffled") <= g["shuffled_max_success"],
        "C6_safe": max(v["wrong_per_query"] for v in S.values()) <= g["max_wrong_per_query"],
        "C7_no_regression": rate("exact|exact_names") - rate("rename|exact_names") <= g["regression_max_drop"]
                            and rate("exact|regression_unrelated") - rate("rename|regression_unrelated") <= g["regression_max_drop"],
        "C8_unrelated_cost": S["rename|unrelated"]["mean_evaluator_calls"] / S["exact|unrelated"]["mean_evaluator_calls"]
                             <= g["unrelated_max_cost_ratio"],
    }
    return {"G23-A": "passed" if all(checks.values()) else "not passed", "checks": checks,
            "paired_relevant": {"rename_only": b, "exact_only": c, "exact_one_sided_p": D21.mcnemar_one_sided(b, c)},
            "per_structure": {s: {m: cell(recs, m, ("relevant_aligned", "relevant_swapped"), (s,))["success_rate"] for m in MODES}
                              for s in transfer}, "summary": S}


def main():
    out, dev = Path(sys.argv[1]), "--development" in sys.argv
    transfer, regression, unrelated, seed = (DEV, DEV_REGRESSION, DEV_UNRELATED, 20261122) if dev else (HELD_OUT, REGRESSION, UNRELATED, SEED)
    structures = {**transfer, **regression}
    w = ChainedWriter(out, {"run": "dev23_transfer" + (" development" if dev else ""), "provenance": environment_provenance(),
                            "asm_coding_sha256": code_hash(), "harness_sha256": file_sha256(Path(__file__)),
                            "asm_procedure_cortex_sha256": file_sha256(ROOT / "asm" / "procedure_cortex.py"), "seed": seed,
                            "gate": GATE, "preregistration_sha256": file_sha256(PREREG) if PREREG.exists() else None})
    t0, recs = time.time(), []
    for structure, arms in [(s, TRANSFER_ARMS) for s in transfer] + [(s, REGRESSION_ARMS) for s in regression]:
        for arm in arms:
            for c in D21.IN_RANGE + D21.OUT_OF_RANGE:
                for s in range(D21.FIT_SEEDS):
                    for mode in MODES:
                        rec = attempt(structures, structure, arm, c, s, seed, mode, unrelated)
                        recs.append(rec)
                        w.append({"part": "attempt", **rec})
    result = gate(recs, transfer, regression)
    w.append({"part": "result", **result, "seconds": round(time.time() - t0, 1)})
    print(json.dumps({k: v for k, v in result.items() if k != "summary"}, indent=1))
    for k, v in result["summary"].items():
        print(f"{k:32s} {v['success_rate']:.3f} {v['wilson95']} calls {v['mean_evaluator_calls']:7.1f} wrong {v['wrong']} n {v['n']}")


if __name__ == "__main__":
    main()
