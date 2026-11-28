"""DEV28: does tolerating one contradicting label (ProcedureCortex(contradiction_policy='tolerant'), opt-in, approved by the
owner for testing) keep transfer working under wrong labels, without wrong answers? Pre-registered in
benchmarks/preregistration/dev28_study.md.

DEV24's three-input protocol with more evidence, since one wrong label cannot be tolerated among three: targets and donors
get 5 fit and 10 validation labels. Noise arms (role order 0): each label of the target and of the relevant donors is wrong
with probability 0.05 or 0.10 (DEV24's offsets ±1..3), one corruption pattern per attempt shared by both modes. Every
attempt runs with contradiction_policy 'strict' (control: the default) and 'tolerant', both with family_parameters='solve'.
Usage: python benchmarks/dev28_transfer.py <out.jsonl> [--development]
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
import dev24_transfer as D24  # noqa: E402
from asm.coding.integrity import ChainedWriter, code_hash, environment_provenance, file_sha256  # noqa: E402
from asm.learning import structtransfer as T  # noqa: E402
from asm.procedure_cortex import ProcedureCortex  # noqa: E402
from asm.procedure_program import Program  # noqa: E402

PREREG = ROOT / "benchmarks" / "preregistration" / "dev28_study.md"
MODES = ("strict", "tolerant")
CLEAN = ("none", "unrelated", "relevant_shuffled", "relevant_r0", "relevant_r5", "mixed_r0")
NOISY = {"noise05_r0": 0.05, "noise10_r0": 0.10, "noise10_mixed_r0": 0.10}
ARMS = CLEAN + tuple(NOISY)
CONSTANTS = D21.IN_RANGE + D21.OUT_OF_RANGE
FIT_POINTS, DONOR_FIT = 5, D24.DONOR_FIT + ((3, 1, 2), (1, 3, 4))
VALIDATION = D24.VALIDATION + ((11, 16, 10), (16, 11, 17))
DEV = {k: D24.DEV[k] for k in ("dev_mul_add", "dev_sq_sub")}
HELD_OUT = {  # never run before the pre-registration
    "y_shift_x_minus_z": lambda c: (("sub", ("mul", "y", ("add", "x", c)), "z"), lambda x, y, z, c=c: y * (x + c) - z),
    "zz_plus_xy_shift": lambda c: (("add", ("mul", "z", "z"), ("mul", "x", ("sub", "y", c))), lambda x, y, z, c=c: z * z + x * (y - c)),
    "x_minus_y_times_z_shift": lambda c: (("mul", ("sub", "x", "y"), ("add", "z", c)), lambda x, y, z, c=c: (x - y) * (z + c)),
}
UNRELATED = (("u_aff_p2q_r3", ("add", ("add", ("add", "p", ("mul", 2, "q")), ("mul", 3, "r")), 2), lambda p, q, r: p + 2 * q + 3 * r + 2),
             ("u_aff_p2q_rm1", ("add", ("add", ("add", "p", ("mul", 2, "q")), ("mul", -1, "r")), -3), lambda p, q, r: p + 2 * q - r - 3),
             ("u_max_q2", ("sub", ("max", "p", ("add", "q", 2)), "r"), lambda p, q, r: max(p, q + 2) - r),
             ("u_max_q6", ("sub", ("max", "p", ("add", "q", 6)), "r"), lambda p, q, r: max(p, q + 6) - r))
SEED, DEV_SEED = 20261130, 28001
GATE = {"min_noise_gain": 0.15, "max_paired_p": 0.01, "max_clean_loss": 0.02, "unrelated_max_gain_over_none": 0.05,
        "shuffled_max_success": 0.05, "max_wrong_per_query": 0.02, "max_wrong_rise": 0.005, "max_cost_ratio": 3.0}


def corrupt(labels, rng, p):
    out = [v + rng.choice(D24.OFFSETS) if rng.random() < p else v for v in labels]
    return out, sum(a != b for a, b in zip(out, labels))


def install(cortex, donors, rng=None, p=0.0):
    """Each donor through propose (5 fit labels) and 10 validation labels; with rng, labels corrupted at rate p."""
    wrong = 0
    for name, expr, fn in donors:
        names = sorted(D24.D23.inputs_of(expr))
        fit, val = [fn(*q) for q in DONOR_FIT], [fn(*q) for q in VALIDATION]
        if rng:
            (fit, a), (val, b) = corrupt(fit, rng, p), corrupt(val, rng, p)
            wrong += a + b
        for i, (q, y) in enumerate(zip(DONOR_FIT, fit)):
            cortex.observe(name, dict(zip(names, q)), y, evidence_id=f"{name}-fit-{i}", source_id="oracle")
        if cortex.propose(name, Program(dict.fromkeys(names, "int"), expr), provenance="external").get("status") == "proposed":
            for i, (q, y) in enumerate(zip(VALIDATION, val)):
                cortex.observe(name, dict(zip(names, q)), y, evidence_id=f"{name}-val-{i}", source_id="oracle")
    return sum(v["state"] == "active" for name, _, _ in donors for v in cortex.versions(name)), wrong


def attempt(structures, structure, arm, c, fit_seed, seed, mode, unrelated):
    rng = random.Random(f"{seed}:attempt:{structure}:{c}:{fit_seed}")
    fit = sorted(rng.sample(list(itertools.product(range(10), repeat=3)), FIT_POINTS))
    queries, truth = D24.queries_for(fit, rng), structures[structure](c)[1]
    p = NOISY.get(arm, 0.0)
    noise = random.Random(f"{seed}:noise:{structure}:{c}:{fit_seed}:{arm}") if p else None
    base = "mixed_r0" if arm == "noise10_mixed_r0" else "relevant_r0" if arm in NOISY else arm
    relevant = [d for d in D24.donors_for(structures, structure, base, c, fit_seed, seed, unrelated) if d[0].startswith("z_rel_")]
    others = [d for d in D24.donors_for(structures, structure, base, c, fit_seed, seed, unrelated) if not d[0].startswith("z_rel_")]
    cortex = ProcedureCortex(":memory:", trust_provider=T.TRUST, family_scope="any_int", family_mapping="rename",
                             family_parameters="solve", contradiction_policy=mode)
    try:
        active_other, _ = install(cortex, others)
        active, wrong_donor = install(cortex, relevant, noise, p)
        fit_y, val_y = [truth(*q) for q in fit], [truth(*q) for q in VALIDATION]
        if arm == "relevant_shuffled":
            fit_y = D21.shuffled(fit_y, random.Random(f"{seed}:shuffle:{structure}:{c}:{fit_seed}"))
            val_y = D21.shuffled(val_y, random.Random(f"{seed}:shuffle-val:{structure}:{c}:{fit_seed}"))
        wrong_target = 0
        if noise:
            (fit_y, a), (val_y, b) = corrupt(fit_y, noise, p), corrupt(val_y, noise, p)
            wrong_target = a + b
        for i, (q, v) in enumerate(zip(fit, fit_y)):
            cortex.observe("target", dict(zip(D24.TARGET, q)), v, evidence_id=f"t-fit-{i}", source_id="oracle")
        res = cortex.induce("target", use_families=True)
        answered = wrong = 0
        if res.get("status") == "proposed":
            for i, (q, v) in enumerate(zip(VALIDATION, val_y)):
                cortex.observe("target", dict(zip(D24.TARGET, q)), v, evidence_id=f"t-val-{i}", source_id="oracle")
            for q in queries:
                pred = cortex.predict("target", dict(zip(D24.TARGET, q)))
                if pred.get("status") == "predicted":
                    answered += 1
                    wrong += pred["value"] != truth(*q)
        return {"structure": structure, "arm": arm, "c": c, "fit_seed": fit_seed, "mode": mode, "fit": fit,
                "active_donors": active + active_other, "wrong_target_labels": wrong_target, "wrong_donor_labels": wrong_donor,
                "status": res.get("status"), "origin": res.get("origin"), "candidates": int(res.get("candidate_count", 0)),
                "evaluator_calls": int(res.get("evaluator_calls", 0)), "queries": len(queries), "answered": answered,
                "wrong": wrong, "success": res.get("status") == "proposed" and answered == len(queries) and wrong == 0}
    finally:
        cortex.close()


def cell(recs, mode, arms, structures, constants=CONSTANTS):
    rs = [r for r in recs if r["mode"] == mode and r["arm"] in arms and r["structure"] in structures and r["c"] in constants]
    k, q = sum(r["success"] for r in rs), sum(r["queries"] for r in rs)
    return {"n": len(rs), "success_rate": round(k / len(rs), 4) if rs else 0.0, "wilson95": D21.wilson(k, len(rs)),
            "mean_evaluator_calls": round(sum(r["evaluator_calls"] for r in rs) / len(rs), 1) if rs else 0.0,
            "wrong": sum(r["wrong"] for r in rs), "wrong_per_query": sum(r["wrong"] for r in rs) / q if q else 0.0}


def gate(recs, transfer):
    S = {f"{m}|{a}": cell(recs, m, (a,), transfer) for m in MODES for a in ARMS}
    S.update({f"{m}|{name}": cell(recs, m, arms, transfer) for m in MODES for name, arms in
              (("noisy", tuple(NOISY)), ("clean_relevant", ("relevant_r0", "relevant_r5", "mixed_r0")))})
    rate = lambda key: S[key]["success_rate"]  # noqa: E731
    pairs = {}
    for r in recs:
        if r["arm"] in NOISY and r["structure"] in transfer:
            pairs.setdefault((r["structure"], r["arm"], r["c"], r["fit_seed"]), {})[r["mode"]] = r["success"]
    b = sum(1 for v in pairs.values() if v["tolerant"] and not v["strict"])
    c = sum(1 for v in pairs.values() if v["strict"] and not v["tolerant"])
    g = GATE
    checks = {
        "C1_noise_gain": rate("tolerant|noisy") - rate("strict|noisy") >= g["min_noise_gain"] and D21.mcnemar_one_sided(b, c) < g["max_paired_p"],
        "C2_no_clean_loss": rate("strict|clean_relevant") - rate("tolerant|clean_relevant") <= g["max_clean_loss"],
        "C3_no_false_transfer": rate("tolerant|unrelated") - rate("tolerant|none") <= g["unrelated_max_gain_over_none"]
                                and rate("tolerant|relevant_shuffled") <= g["shuffled_max_success"],
        "C4_safe": max(v["wrong_per_query"] for v in S.values()) <= g["max_wrong_per_query"]
                   and all(S[f"tolerant|{a}"]["wrong_per_query"] - S[f"strict|{a}"]["wrong_per_query"] <= g["max_wrong_rise"] for a in ARMS),
        "C5_cost": S["tolerant|clean_relevant"]["mean_evaluator_calls"] / S["strict|clean_relevant"]["mean_evaluator_calls"] <= g["max_cost_ratio"],
    }
    return {"G28-A": "passed" if all(checks.values()) else "not passed", "checks": checks,
            "paired_noisy": {"tolerant_only": b, "strict_only": c, "exact_one_sided_p": D21.mcnemar_one_sided(b, c)},
            "per_structure": {s: {m: cell(recs, m, tuple(NOISY), (s,))["success_rate"] for m in MODES} for s in transfer},
            "summary": S}


def main():
    out, dev = Path(sys.argv[1]), "--development" in sys.argv
    transfer, unrelated, seed = (DEV, D24.DEV_UNRELATED, DEV_SEED) if dev else (HELD_OUT, UNRELATED, SEED)
    w = ChainedWriter(out, {"run": "dev28_transfer" + (" development" if dev else ""), "provenance": environment_provenance(),
                            "asm_coding_sha256": code_hash(), "harness_sha256": file_sha256(Path(__file__)),
                            "asm_procedure_cortex_sha256": file_sha256(ROOT / "asm" / "procedure_cortex.py"), "seed": seed,
                            "gate": GATE, "noise": NOISY, "preregistration_sha256": file_sha256(PREREG) if PREREG.exists() else None})
    t0, recs = time.time(), []
    for structure in transfer:
        for arm in ARMS:
            for c in CONSTANTS:
                for s in range(D21.FIT_SEEDS):
                    for mode in MODES:
                        rec = attempt(transfer, structure, arm, c, s, seed, mode, unrelated)
                        recs.append(rec)
                        w.append({"part": "attempt", **rec})
    result = gate(recs, transfer)
    w.append({"part": "result", **result, "seconds": round(time.time() - t0, 1)})
    print(json.dumps({k: v for k, v in result.items() if k != "summary"}, indent=1))
    for k, v in result["summary"].items():
        print(f"{k:28s} {v['success_rate']:.3f} {v['wilson95']} calls {v['mean_evaluator_calls']:7.1f} wrong {v['wrong']} n {v['n']}")


if __name__ == "__main__":
    main()
