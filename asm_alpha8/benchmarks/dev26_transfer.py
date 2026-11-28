"""DEV26: when several solved family candidates fit the three fit points and disagree elsewhere, does asking for the label
of the input that separates them best (ProcedureCortex(family_ambiguity='ask')) recover the attempts that proposing the
first one loses, without losses, wrong answers, or many questions? Pre-registered in benchmarks/preregistration/dev26_study.md.

DEV25's three-input protocol with family_parameters='solve' in both modes: 'first' (control: the default) and 'ask'.
When induce returns needs_information, the oracle labels the queried input (a fourth fit example) and induce runs again,
at most QUERIES times. Each relevant and mixed arm also runs with degenerate fits: the three fit points are drawn from
{0,1,2}^3, where coincidences such as x = z at every point (DEV24's and DEV25's ambiguity failures) are common.
Usage: python benchmarks/dev26_transfer.py <out.jsonl> [--development]
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

PREREG = ROOT / "benchmarks" / "preregistration" / "dev26_study.md"
MODES = ("first", "ask")
QUERIES = 2
BASE = ("relevant_r0", "relevant_r5", "mixed_r0", "mixed_r5")
DEGENERATE = tuple(f"deg_{a}" for a in BASE)
ARMS = ("none", "unrelated", "relevant_shuffled") + BASE + DEGENERATE
CONSTANTS = D21.IN_RANGE + D21.OUT_OF_RANGE
DEV = {**{k: D24.DEV[k] for k in ("dev_mul_add", "dev_sq_sub")}, "diff_times_shift": D24.HELD_OUT["diff_times_shift"]}
HELD_OUT = {  # never run before the pre-registration
    "antisym_plus": lambda c: (("add", ("mul", ("sub", "y", "x"), "z"), c), lambda x, y, z, c=c: (y - x) * z + c),
    "x_shift_minus_yy": lambda c: (("sub", ("mul", "x", ("add", "z", c)), ("mul", "y", "y")), lambda x, y, z, c=c: x * (z + c) - y * y),
    "pair_times_y": lambda c: (("add", ("mul", ("add", "x", "z"), "y"), ("mul", c, "x")), lambda x, y, z, c=c: (x + z) * y + c * x),
}
UNRELATED = (("u_aff_2p3q_m1r", ("add", ("add", ("add", ("mul", 2, "p"), ("mul", 3, "q")), ("mul", -1, "r")), 1),
              lambda p, q, r: 2 * p + 3 * q - r + 1),
             ("u_aff_2p3q_2r", ("add", ("add", ("add", ("mul", 2, "p"), ("mul", 3, "q")), ("mul", 2, "r")), -6),
              lambda p, q, r: 2 * p + 3 * q + 2 * r - 6),
             ("u_max_p4", ("add", ("max", ("add", "p", 4), "q"), "r"), lambda p, q, r: max(p + 4, q) + r),
             ("u_max_p1", ("add", ("max", ("add", "p", 1), "q"), "r"), lambda p, q, r: max(p + 1, q) + r))
SEED = 20261128
GATE = {"min_recovery": 0.10, "max_paired_p": 0.01, "max_loss": 0.02, "unrelated_max_gain_over_none": 0.05,
        "shuffled_max_success": 0.05, "max_wrong_per_query": 0.02, "max_queries_standard": 0.10, "max_cost_ratio": 1.50,
        "max_order_gap": 0.03}


def attempt(structures, structure, arm, c, fit_seed, seed, mode, unrelated):
    """DEV25's attempt with family_ambiguity=mode, degenerate fits for deg_ arms, and the oracle answering queries."""
    rng = random.Random(f"{seed}:attempt:{structure}:{c}:{fit_seed}")
    grid = range(3) if arm.startswith("deg_") else range(10)
    fit = sorted(rng.sample(list(itertools.product(grid, repeat=3)), 3))
    queries, truth = D24.queries_for(fit, rng), structures[structure](c)[1]
    cortex = ProcedureCortex(":memory:", trust_provider=T.TRUST, family_scope="any_int", family_mapping="rename",
                             family_parameters="solve", family_ambiguity=mode)
    try:
        active, _ = D24.install(cortex, D24.donors_for(structures, structure, arm.removeprefix("deg_"), c, fit_seed, seed, unrelated))
        fit_y, val_y = [truth(*p) for p in fit], [truth(*p) for p in D24.VALIDATION]
        if arm == "relevant_shuffled":
            fit_y = D21.shuffled(fit_y, random.Random(f"{seed}:shuffle:{structure}:{c}:{fit_seed}"))
            val_y = D21.shuffled(val_y, random.Random(f"{seed}:shuffle-val:{structure}:{c}:{fit_seed}"))
        for i, (p, v) in enumerate(zip(fit, fit_y)):
            cortex.observe("target", dict(zip(D24.TARGET, p)), v, evidence_id=f"t-fit-{i}", source_id="oracle")
        res, asked, candidates, calls = cortex.induce("target", use_families=True), 0, 0, 0
        while True:
            candidates, calls = candidates + int(res.get("candidate_count", 0)), calls + int(res.get("evaluator_calls", 0))
            if res.get("status") != "needs_information" or asked == QUERIES:
                break
            q = res["information_query"]["input"]
            cortex.observe("target", dict(q), truth(*(q[k] for k in D24.TARGET)), evidence_id=f"t-ask-{asked}", source_id="oracle")
            asked += 1
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
                "active_donors": active, "asked": asked, "status": res.get("status"), "origin": res.get("origin"),
                "candidates": candidates, "evaluator_calls": calls, "queries": len(queries), "answered": answered,
                "wrong": wrong, "success": res.get("status") == "proposed" and answered == len(queries) and wrong == 0}
    finally:
        cortex.close()


def cell(recs, mode, arms, structures, constants=CONSTANTS):
    rs = [r for r in recs if r["mode"] == mode and r["arm"] in arms and r["structure"] in structures and r["c"] in constants]
    k, q = sum(r["success"] for r in rs), sum(r["queries"] for r in rs)
    return {"n": len(rs), "success_rate": round(k / len(rs), 4) if rs else 0.0, "wilson95": D21.wilson(k, len(rs)),
            "mean_evaluator_calls": round(sum(r["evaluator_calls"] for r in rs) / len(rs), 1) if rs else 0.0,
            "mean_asked": round(sum(r["asked"] for r in rs) / len(rs), 3) if rs else 0.0,
            "wrong": sum(r["wrong"] for r in rs), "wrong_per_query": sum(r["wrong"] for r in rs) / q if q else 0.0}


def gate(recs, transfer):
    S = {f"{m}|{a}": cell(recs, m, (a,), transfer) for m in MODES for a in ARMS}
    S.update({f"{m}|{name}": cell(recs, m, arms, transfer) for m in MODES for name, arms in (("standard", BASE), ("degenerate", DEGENERATE))})
    rate = lambda key: S[key]["success_rate"]  # noqa: E731
    pairs = {}
    for r in recs:
        if r["arm"] in DEGENERATE and r["structure"] in transfer:
            pairs.setdefault((r["structure"], r["arm"], r["c"], r["fit_seed"]), {})[r["mode"]] = r["success"]
    b = sum(1 for v in pairs.values() if v["ask"] and not v["first"])
    c = sum(1 for v in pairs.values() if v["first"] and not v["ask"])
    g = GATE
    checks = {
        "C1_recovery": rate("ask|degenerate") - rate("first|degenerate") >= g["min_recovery"] and D21.mcnemar_one_sided(b, c) < g["max_paired_p"],
        "C2_no_loss": rate("first|standard") - rate("ask|standard") <= g["max_loss"],
        "C3_no_false_transfer": rate("ask|unrelated") - rate("ask|none") <= g["unrelated_max_gain_over_none"]
                                and rate("ask|relevant_shuffled") <= g["shuffled_max_success"],
        "C4_safe": max(v["wrong_per_query"] for v in S.values()) <= g["max_wrong_per_query"]
                   and S["ask|standard"]["wrong"] + S["ask|degenerate"]["wrong"] <= S["first|standard"]["wrong"] + S["first|degenerate"]["wrong"],
        "C5_few_questions": S["ask|standard"]["mean_asked"] <= g["max_queries_standard"],
        "C6_cost": S["ask|standard"]["mean_evaluator_calls"] / S["first|standard"]["mean_evaluator_calls"] <= g["max_cost_ratio"],
        "C7_order_free": all(abs(rate(f"ask|{d}{k}_r0") - rate(f"ask|{d}{k}_r5")) <= g["max_order_gap"]
                             for d in ("", "deg_") for k in ("relevant", "mixed")),
    }
    return {"G26-A": "passed" if all(checks.values()) else "not passed", "checks": checks,
            "paired_degenerate": {"ask_only": b, "first_only": c, "exact_one_sided_p": D21.mcnemar_one_sided(b, c)},
            "per_structure": {s: {m: cell(recs, m, BASE + DEGENERATE, (s,))["success_rate"] for m in MODES} for s in transfer},
            "summary": S}


def main():
    out, dev = Path(sys.argv[1]), "--development" in sys.argv
    transfer, unrelated, seed = (DEV, D24.DEV_UNRELATED, 20261125) if dev else (HELD_OUT, UNRELATED, SEED)
    w = ChainedWriter(out, {"run": "dev26_transfer" + (" development" if dev else ""), "provenance": environment_provenance(),
                            "asm_coding_sha256": code_hash(), "harness_sha256": file_sha256(Path(__file__)),
                            "asm_procedure_cortex_sha256": file_sha256(ROOT / "asm" / "procedure_cortex.py"), "seed": seed,
                            "gate": GATE, "queries": QUERIES, "preregistration_sha256": file_sha256(PREREG) if PREREG.exists() else None})
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
        print(f"{k:28s} {v['success_rate']:.3f} {v['wilson95']} calls {v['mean_evaluator_calls']:7.1f} asked {v['mean_asked']:.3f} wrong {v['wrong']} n {v['n']}")


if __name__ == "__main__":
    main()
