"""DEV24: does family transfer across input names scale to three-input targets (six input mappings per family), and what
do wrong labels do to it? Pre-registered in benchmarks/preregistration/dev24_study.md.

Part A (G24-A): DEV23's protocol on (x, y, z). Relevant donors use inputs (u, v, w) in each of the six role orders
(order k: the cortex's k-th mapping is the right one); unrelated donors use (p, q, r). Every attempt runs with
family_mapping 'exact' (control: no renaming) and 'rename' (the default since 2026-11-23). There is no separate
regression target: with three fit points, the search without families solves no three-input target in development (the
affine solve refuses underdetermined fits; x + y + z + c was unresolved in 47 of 48 attempts).
Part B (G24-B): the relevant arm in role order 0, with each label of the target (3 fit + 8 validation), of the relevant
donors (3 + 8 each) or of both wrong with probability NOISE, by a nonzero offset; one corruption pattern per attempt for
the target and one for the donors, shared by the arms; the same paired modes.
Usage: python benchmarks/dev24_transfer.py <out.jsonl> [--development]
"""
import itertools
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
import dev21_transfer as D21  # noqa: E402
import dev23_transfer as D23  # noqa: E402
from asm.coding.integrity import ChainedWriter, code_hash, environment_provenance, file_sha256  # noqa: E402
from asm.learning import structtransfer as T  # noqa: E402
from asm.procedure_cortex import ProcedureCortex  # noqa: E402
from asm.procedure_program import Program, substitute  # noqa: E402

PREREG = ROOT / "benchmarks" / "preregistration" / "dev24_study.md"
MODES = ("exact", "rename")
TARGET, DONOR = ("x", "y", "z"), ("u", "v", "w")
ROLES = tuple(itertools.permutations(range(3)))  # role order k: DONOR[i] plays TARGET[ROLES[k][i]]
RELEVANT_ARMS = tuple(f"relevant_r{k}" for k in range(6))
TRANSFER_ARMS = ("none", "unrelated", *RELEVANT_ARMS, "relevant_shuffled", "mixed_r0", "mixed_r5", "exact_names")
NOISE_ARMS = ("noise_target", "noise_donors", "noise_both")
NOISE, OFFSETS = 0.10, (-3, -2, -1, 1, 2, 3)
DONOR_FIT = ((0, 1, 2), (1, 2, 0), (2, 0, 1))
VALIDATION = ((10, 13, 16), (11, 10, 14), (12, 16, 11), (13, 11, 17), (14, 17, 12), (15, 12, 10), (16, 15, 13), (17, 14, 15))
# Mixed arms: 1 relevant + 2 unrelated families, 6 mappings each = 18 sources sharing at most 256 proposals round robin,
# so each source reaches 256 // 18 = 14 parameter values (-8..5); constants 6, 7, 8 are out of the budget's reach.
MIXED_REACH = tuple(c for c in D21.IN_RANGE if c + 8 < 256 // 18)
DEV = {  # development structures (run before the pre-registration)
    "dev_mul_add": lambda c: (("add", ("mul", "x", ("add", "y", c)), "z"), lambda x, y, z, c=c: x * (y + c) + z),
    "dev_sq_sub": lambda c: (("add", ("sub", ("mul", ("mul", "x", "x"), "y"), "z"), c), lambda x, y, z, c=c: x * x * y - z + c),
}
DEV_UNRELATED = (("u_aff_2p_p1", ("add", ("add", ("add", ("mul", 2, "p"), "q"), "r"), 1), lambda p, q, r: 2 * p + q + r + 1),
                 ("u_aff_3p_m4", ("add", ("add", ("add", ("mul", 3, "p"), "q"), "r"), -4), lambda p, q, r: 3 * p + q + r - 4),
                 ("u_max_q1", ("add", ("max", "p", ("add", "q", 1)), "r"), lambda p, q, r: max(p, q + 1) + r),
                 ("u_max_q5", ("add", ("max", "p", ("add", "q", 5)), "r"), lambda p, q, r: max(p, q + 5) + r))
HELD_OUT = {  # never run before the pre-registration
    "shift_y_minus_z": lambda c: (("sub", ("mul", ("add", "x", c), "y"), "z"), lambda x, y, z, c=c: (x + c) * y - z),
    "xyy_z": lambda c: (("add", ("add", ("mul", "x", ("mul", "y", "y")), "z"), c), lambda x, y, z, c=c: x * y * y + z + c),
    "diff_times_shift": lambda c: (("mul", ("sub", "x", "z"), ("add", "y", c)), lambda x, y, z, c=c: (x - z) * (y + c)),
}
UNRELATED = (("u_aff_4p_mq", ("add", ("add", ("add", ("mul", 4, "p"), ("mul", -1, "q")), ("mul", 2, "r")), 3),
              lambda p, q, r: 4 * p - q + 2 * r + 3),
             ("u_aff_4p_2q", ("add", ("add", ("add", ("mul", 4, "p"), ("mul", 2, "q")), ("mul", 2, "r")), -5),
              lambda p, q, r: 4 * p + 2 * q + 2 * r - 5),
             ("u_max_pm2", ("add", ("max", ("sub", "p", 2), "q"), "r"), lambda p, q, r: max(p - 2, q) + r),
             ("u_max_pm6", ("add", ("max", ("sub", "p", 6), "q"), "r"), lambda p, q, r: max(p - 6, q) + r))
SEED = 20261126
GATE = {"min_gain_vs_control": 0.30, "max_paired_p": 0.01, "max_role_penalty": 0.10, "t1_min_gap": 0.50,
        "no_interference_max_drop": 0.10, "unrelated_max_gain_over_none": 0.05, "shuffled_max_success": 0.05,
        "max_wrong_per_query": 0.02, "regression_max_drop": 0.05, "unrelated_max_cost_ratio": 1.10,
        "noise_max_wrong_rise": 0.005, "noise_max_shortfall": 0.05}


def corrupt(labels, rng):
    """Each label wrong with probability NOISE, by a nonzero offset; returns (labels, number made wrong)."""
    out = [v + rng.choice(OFFSETS) if rng.random() < NOISE else v for v in labels]
    return out, sum(a != b for a, b in zip(out, labels))


def role_donor(structures, structure, k, order):
    """A donor of `structure` with constant k over (u, v, w), in which DONOR[i] plays TARGET[ROLES[order][i]]."""
    expr, f = structures[structure](k)
    plays = {TARGET[ROLES[order][i]]: DONOR[i] for i in range(3)}
    return substitute(expr, plays), lambda *uvw: f(*(uvw[DONOR.index(plays[t])] for t in TARGET))


def install(cortex, donors, rng=None):
    """Each donor (name, expression, function of its sorted inputs) through propose + validation; with rng, its labels go
    through corrupt(), and a donor whose labels contradict its program is rejected or suspended as the cortex decides.
    Returns (active donors, wrong labels)."""
    wrong = 0
    for name, expr, fn in donors:
        names = sorted(D23.inputs_of(expr))
        fit, val = [fn(*p) for p in DONOR_FIT], [fn(*p) for p in VALIDATION]
        own = 0
        if rng:
            (fit, a), (val, b) = corrupt(fit, rng), corrupt(val, rng)
            own = a + b
        wrong += own
        for i, (p, y) in enumerate(zip(DONOR_FIT, fit)):
            cortex.observe(name, dict(zip(names, p)), y, evidence_id=f"{name}-fit-{i}", source_id="oracle")
        if cortex.propose(name, Program(dict.fromkeys(names, "int"), expr), provenance="external").get("status") != "proposed":
            if not own:
                raise RuntimeError(f"donor {name} with clean labels was not proposed")
            continue
        for i, (p, y) in enumerate(zip(VALIDATION, val)):
            cortex.observe(name, dict(zip(names, p)), y, evidence_id=f"{name}-val-{i}", source_id="oracle")
    return sum(v["state"] == "active" for name, _, _ in donors for v in cortex.versions(name)), wrong


def queries_for(fit, rng, n=6):
    """n query points from the fit's lowest coordinates up to 9, not fit points; if fewer exist, up to 17 (still inside the
    evidence range) minus the validation points (DEV22's amendment A1, in three dimensions)."""
    lo = [min(p[i] for p in fit) for i in range(3)]
    for top, skip in ((10, set(fit)), (18, set(fit) | set(VALIDATION))):
        pool = sorted(set(itertools.product(*(range(a, top) for a in lo))) - skip)
        if len(pool) >= n:
            return rng.sample(pool, n)
    raise ValueError("no query region")


def donors_for(structures, structure, arm, c, fit_seed, seed, unrelated):
    ks = T.donor_constants(c, fit_seed, seed)
    name = lambda k: f"z_rel_{structure}_{'m' if k < 0 else 'p'}{abs(k)}"  # noqa: E731  (after the unrelated donors)
    role = lambda order: [(name(k), *role_donor(structures, structure, k, order)) for k in ks]  # noqa: E731
    if arm[:-1] in ("relevant_r", "mixed_r"):
        return role(int(arm[-1])) + (list(unrelated) if arm.startswith("mixed") else [])
    return {"none": [], "unrelated": list(unrelated), "relevant_shuffled": role(0),
            "exact_names": [(name(k), *structures[structure](k)) for k in ks], **{a: role(0) for a in NOISE_ARMS}}[arm]


def attempt(structures, structure, arm, c, fit_seed, seed, mode, unrelated):
    rng = random.Random(f"{seed}:attempt:{structure}:{c}:{fit_seed}")
    fit = sorted(rng.sample(list(itertools.product(range(10), repeat=3)), 3))
    queries, truth = queries_for(fit, rng), structures[structure](c)[1]
    noisy = lambda part: (random.Random(f"{seed}:noise-{part}:{structure}:{c}:{fit_seed}")  # noqa: E731
                          if arm in (f"noise_{part}", "noise_both") else None)
    cortex = ProcedureCortex(":memory:", trust_provider=T.TRUST, family_scope="any_int", family_mapping=mode)
    try:
        active, wrong_donor = install(cortex, donors_for(structures, structure, arm, c, fit_seed, seed, unrelated), noisy("donors"))
        fit_y, val_y, wrong_target = [truth(*p) for p in fit], [truth(*p) for p in VALIDATION], 0
        if arm == "relevant_shuffled":
            fit_y = D21.shuffled(fit_y, random.Random(f"{seed}:shuffle:{structure}:{c}:{fit_seed}"))
            val_y = D21.shuffled(val_y, random.Random(f"{seed}:shuffle-val:{structure}:{c}:{fit_seed}"))
        if (r := noisy("target")):
            (fit_y, a), (val_y, b) = corrupt(fit_y, r), corrupt(val_y, r)
            wrong_target = a + b
        for i, (p, v) in enumerate(zip(fit, fit_y)):
            cortex.observe("target", dict(zip(TARGET, p)), v, evidence_id=f"t-fit-{i}", source_id="oracle")
        res = cortex.induce("target", use_families=True)
        answered = wrong = 0
        if res.get("status") == "proposed":
            for i, (p, v) in enumerate(zip(VALIDATION, val_y)):
                cortex.observe("target", dict(zip(TARGET, p)), v, evidence_id=f"t-val-{i}", source_id="oracle")
            for q in queries:
                pred = cortex.predict("target", dict(zip(TARGET, q)))
                if pred.get("status") == "predicted":
                    answered += 1
                    wrong += pred["value"] != truth(*q)
        return {"structure": structure, "arm": arm, "c": c, "fit_seed": fit_seed, "mode": mode, "fit": fit,
                "active_donors": active, "wrong_target_labels": wrong_target, "wrong_donor_labels": wrong_donor,
                "status": res.get("status"), "origin": res.get("origin"), "candidates": int(res.get("candidate_count", 0)),
                "evaluator_calls": int(res.get("evaluator_calls", 0)), "queries": len(queries), "answered": answered,
                "wrong": wrong, "success": res.get("status") == "proposed" and answered == len(queries) and wrong == 0}
    finally:
        cortex.close()


def cell(recs, mode, arms, structures, constants=D21.IN_RANGE):
    rs = [r for r in recs if r["mode"] == mode and r["arm"] in arms and r["structure"] in structures and r["c"] in constants]
    k, q = sum(r["success"] for r in rs), sum(r["queries"] for r in rs)
    return {"n": len(rs), "success_rate": round(k / len(rs), 4) if rs else 0.0, "wilson95": D21.wilson(k, len(rs)),
            "mean_evaluator_calls": round(sum(r["evaluator_calls"] for r in rs) / len(rs), 1) if rs else 0.0,
            "wrong": sum(r["wrong"] for r in rs), "wrong_per_query": sum(r["wrong"] for r in rs) / q if q else 0.0}


def predicted_noise(recs, transfer):
    """Part B's model, per attempt: no success if a target label is wrong; the arm without donors' outcome if only donor
    labels are wrong (two active donors are needed for a family); otherwise the noise-free outcome (role order 0)."""
    key = lambda r: (r["structure"], r["c"], r["fit_seed"], r["mode"])  # noqa: E731
    clean = {(key(r), r["arm"]): r["success"] for r in recs if r["arm"] in ("none", "relevant_r0")}
    out = {}
    for r in recs:
        if r["arm"] in NOISE_ARMS and r["structure"] in transfer and r["c"] in D21.IN_RANGE:
            arm = None if r["wrong_target_labels"] else "none" if r["wrong_donor_labels"] else "relevant_r0"
            out.setdefault((r["mode"], r["arm"]), []).append(clean[(key(r), arm)] if arm else False)
    return {k: round(sum(v) / len(v), 4) for k, v in out.items()}


def gate(recs, transfer):
    """Cells "mode|arm" (in-range constants; the checks use these) and "mode|arm|out_of_range" (reported; C6 uses all)."""
    S = {}
    for group, constants in (("", D21.IN_RANGE), ("|out_of_range", D21.OUT_OF_RANGE)):
        for m in MODES:
            S.update({f"{m}|{a}{group}": cell(recs, m, (a,), transfer, constants) for a in TRANSFER_ARMS + NOISE_ARMS})
            S[f"{m}|relevant{group}"] = cell(recs, m, RELEVANT_ARMS, transfer, constants)
    reach = {f"{m}|{a}|reach": cell(recs, m, (a,), transfer, MIXED_REACH) for m in MODES for a in ("relevant_r0", "relevant_r5", "mixed_r0", "mixed_r5")}
    rate = lambda key: {**S, **reach}[key]["success_rate"]  # noqa: E731
    pairs = {}
    for r in recs:
        if r["arm"] in RELEVANT_ARMS and r["structure"] in transfer and r["c"] in D21.IN_RANGE:
            pairs.setdefault((r["structure"], r["arm"], r["c"], r["fit_seed"]), {})[r["mode"]] = r["success"]
    b = sum(1 for v in pairs.values() if v["rename"] and not v["exact"])
    c = sum(1 for v in pairs.values() if v["exact"] and not v["rename"])
    pred, g = predicted_noise(recs, transfer), GATE
    part_a = [k for k in S if not any(n in k for n in NOISE_ARMS)]
    checks_a = {
        "C1_gain_over_control": rate("rename|relevant") - rate("exact|relevant") >= g["min_gain_vs_control"]
                                and D21.mcnemar_one_sided(b, c) < g["max_paired_p"],
        "C2_no_role_order_penalty": max(rate("rename|relevant_r0") - rate(f"rename|{a}") for a in RELEVANT_ARMS) <= g["max_role_penalty"],
        "C3_transfer_gain": rate("rename|relevant") - rate("rename|none") >= g["t1_min_gap"],
        "C4_no_interference_within_reach": all(rate(f"rename|relevant_r{o}|reach") - rate(f"rename|mixed_r{o}|reach")
                                               <= g["no_interference_max_drop"] for o in (0, 5)),
        "C5_no_false_transfer": rate("rename|unrelated") - rate("rename|none") <= g["unrelated_max_gain_over_none"]
                                and rate("rename|relevant_shuffled") <= g["shuffled_max_success"],
        "C6_safe": max(S[k]["wrong_per_query"] for k in part_a) <= g["max_wrong_per_query"],
        "C7_no_regression": all(rate(f"exact|{a}") - rate(f"rename|{a}") <= g["regression_max_drop"]
                                for a in ("exact_names", "unrelated")),
        "C8_unrelated_cost": S["rename|unrelated"]["mean_evaluator_calls"] / S["exact|unrelated"]["mean_evaluator_calls"]
                             <= g["unrelated_max_cost_ratio"],
    }
    checks_b = {
        "B1_safe_under_noise": all(S[f"{m}|{a}{gr}"]["wrong_per_query"] <= min(g["max_wrong_per_query"],
                                   S[f"{m}|relevant_r0{gr}"]["wrong_per_query"] + g["noise_max_wrong_rise"])
                                   for m in MODES for a in NOISE_ARMS for gr in ("", "|out_of_range")),
        "B2_success_at_least_predicted": all(rate(f"{m}|{a}") >= pred[(m, a)] - g["noise_max_shortfall"] for m in MODES for a in NOISE_ARMS),
    }
    return {"G24-A": "passed" if all(checks_a.values()) else "not passed", "checks_a": checks_a,
            "G24-B": "passed" if all(checks_b.values()) else "not passed", "checks_b": checks_b,
            "paired_relevant": {"rename_only": b, "exact_only": c, "exact_one_sided_p": D21.mcnemar_one_sided(b, c)},
            "noise_predicted": {f"{m}|{a}": v for (m, a), v in pred.items()},
            "per_structure": {s: {m: cell(recs, m, RELEVANT_ARMS, (s,))["success_rate"] for m in MODES} for s in transfer},
            "reach": reach, "summary": S}


def main():
    out, dev = Path(sys.argv[1]), "--development" in sys.argv
    transfer, unrelated, seed = (DEV, DEV_UNRELATED, 20261123) if dev else (HELD_OUT, UNRELATED, SEED)
    w = ChainedWriter(out, {"run": "dev24_transfer" + (" development" if dev else ""), "provenance": environment_provenance(),
                            "asm_coding_sha256": code_hash(), "harness_sha256": file_sha256(Path(__file__)),
                            "asm_procedure_cortex_sha256": file_sha256(ROOT / "asm" / "procedure_cortex.py"), "seed": seed,
                            "gate": GATE, "noise": NOISE, "preregistration_sha256": file_sha256(PREREG) if PREREG.exists() else None})
    t0, recs = time.time(), []
    for structure in transfer:
        for arm in TRANSFER_ARMS + NOISE_ARMS:
            for c in D21.IN_RANGE + D21.OUT_OF_RANGE:
                for s in range(D21.FIT_SEEDS):
                    for mode in MODES:
                        rec = attempt(transfer, structure, arm, c, s, seed, mode, unrelated)
                        recs.append(rec)
                        w.append({"part": "attempt", **rec})
    result = gate(recs, transfer)
    w.append({"part": "result", **result, "seconds": round(time.time() - t0, 1)})
    print(json.dumps({k: v for k, v in result.items() if k not in ("summary", "reach")}, indent=1))
    for k, v in {**result["summary"], **result["reach"]}.items():
        if "out_of_range" not in k:
            print(f"{k:34s} {v['success_rate']:.3f} {v['wilson95']} calls {v['mean_evaluator_calls']:7.1f} wrong {v['wrong']} n {v['n']}")


if __name__ == "__main__":
    main()
