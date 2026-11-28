"""DEV27: does family transfer survive a large memory (ProcedureCortex(family_memory='index')) and a restart? Today
families() reads only the first 32 active versions (by name) and keeps at most 16 families, so a relevant family can sit
outside its window. Pre-registered in benchmarks/preregistration/dev27_study.md.

DEV26's three-input protocol (family_parameters='solve', family_ambiguity='ask', the oracle answering at most 2 questions)
on a cortex file that already holds N background procedures (2 or 3 inputs, a few shapes with random constants, so some
form families), named to sort before the relevant donors. Arms: none, relevant_r0, relevant_r5, and restart_r0 (the
cortex is closed and reopened after the relevant donors are installed and the families read). Every attempt runs with
family_memory 'window' (control: the default) and 'index'.
Usage: python benchmarks/dev27_transfer.py <out.jsonl> [--development]
"""
import itertools
import json
import random
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
import dev21_transfer as D21  # noqa: E402
import dev24_transfer as D24  # noqa: E402
import dev26_transfer as D26  # noqa: E402
from asm.coding.integrity import ChainedWriter, code_hash, environment_provenance, file_sha256  # noqa: E402
from asm.learning import structtransfer as T  # noqa: E402
from asm.procedure_cortex import ProcedureCortex  # noqa: E402
from asm.procedure_program import Program  # noqa: E402

PREREG = ROOT / "benchmarks" / "preregistration" / "dev27_study.md"
MODES = ("window", "index")
SIZES = (0, 48, 120)  # with the target and two donors, at most 123 of the cortex's 128 mechanisms
ARMS = ("none", "relevant_r0", "relevant_r5", "restart_r0")
CONSTANTS = D21.IN_RANGE + D21.OUT_OF_RANGE
SHAPES = {3: {"aff": lambda r: ("add", ("add", ("mul", r.choice((1, 2, 3)), "a"), ("mul", "b", "c")), r.randint(-5, 5)),
              "shift": lambda r: ("sub", ("mul", ("add", "a", r.randint(-5, 5)), "b"), "c"),
              "maxk": lambda r: ("add", ("max", "a", "b"), ("mul", r.randint(-3, 3), "c"))},
          2: {"aff2": lambda r: ("add", ("add", ("mul", r.choice((1, 2, 3)), "a"), ("mul", r.choice((1, 2)), "b")), r.randint(-5, 5)),
              "maxk2": lambda r: ("max", "a", ("add", "b", r.randint(-5, 5)))}}
DEV = {k: D24.DEV[k] for k in ("dev_mul_add", "dev_sq_sub")}
HELD_OUT = {  # never run before the pre-registration
    "z_shift_y_plus_x": lambda c: (("add", ("mul", ("sub", "z", c), "y"), "x"), lambda x, y, z, c=c: (z - c) * y + x),
    "xy_minus_z_shift": lambda c: (("sub", ("mul", "x", "y"), ("mul", "z", ("sub", "z", c))), lambda x, y, z, c=c: x * y - z * (z - c)),
    "weighted_sum_times_z": lambda c: (("mul", ("add", ("add", "x", ("mul", 2, "y")), c), "z"), lambda x, y, z, c=c: (x + 2 * y + c) * z),
}
SEED, MEMORY_SEED, DEV_SEED, DEV_MEMORY_SEED = 20261129, 77, 27001, 1
GATE = {"min_scale_gain": 0.50, "max_paired_p": 0.01, "max_small_memory_gap": 0.02, "max_restart_loss": 0.02,
        "max_none_success": 0.05, "max_wrong_per_query": 0.02, "max_cost_vs_search": 0.50}


def memory(n, seed):
    """n background procedures b_000..: even ones over (a, b, c), odd ones over (a, b); shapes and constants at random."""
    r = random.Random(seed)
    return [(f"b_{i:03d}", SHAPES[k][r.choice(sorted(SHAPES[k]))](r)) for i, k in zip(range(n), itertools.cycle((3, 2)))]


def install_memory(cortex, procedures):
    for name, expr in procedures:
        names = sorted(D24.D23.inputs_of(expr))
        program = Program(dict.fromkeys(names, "int"), expr)
        for i, p in enumerate(D24.DONOR_FIT):
            v = dict(zip(names, p))
            cortex.observe(name, v, program.run(v), evidence_id=f"{name}-fit-{i}", source_id="oracle")
        if cortex.propose(name, program, provenance="external").get("status") != "proposed":
            raise RuntimeError(f"background {name} was not proposed")
        for i, p in enumerate(D24.VALIDATION):
            v = dict(zip(names, p))
            cortex.observe(name, v, program.run(v), evidence_id=f"{name}-val-{i}", source_id="oracle")


def templates(workdir, memory_seed):
    """One cortex file per memory size, families already indexed, checkpointed so a plain file copy is complete."""
    out = {}
    for n in SIZES:
        path = Path(workdir) / f"memory_{n}.db"
        cortex = ProcedureCortex(path, trust_provider=T.TRUST, family_memory="index")
        install_memory(cortex, memory(n, memory_seed))
        cortex.families()
        cortex.close()
        with sqlite3.connect(path) as db:
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        out[n] = path
    return out


def attempt(structures, structure, arm, n, c, fit_seed, seed, mode, template, workdir):
    rng = random.Random(f"{seed}:attempt:{structure}:{c}:{fit_seed}")
    fit = sorted(rng.sample(list(itertools.product(range(10), repeat=3)), 3))
    queries, truth = D24.queries_for(fit, rng), structures[structure](c)[1]
    path = Path(workdir) / "attempt.db"
    for leftover in (Path(f"{path}-wal"), Path(f"{path}-shm")):
        leftover.unlink(missing_ok=True)  # never let an earlier attempt's journal touch this copy
    shutil.copyfile(template, path)
    options = dict(trust_provider=T.TRUST, family_scope="any_int", family_mapping="rename", family_parameters="solve",
                   family_ambiguity="ask", family_memory=mode)
    cortex = ProcedureCortex(path, **options)
    try:
        donors = D24.donors_for(structures, structure, "relevant_r5" if arm == "relevant_r5" else "relevant_r0", c, fit_seed, seed, ())
        active, _ = D24.install(cortex, donors if arm != "none" else [])
        if arm == "restart_r0":
            cortex.families()
            cortex.close()
            cortex = ProcedureCortex(path, **options)
        for i, p in enumerate(fit):
            cortex.observe("target", dict(zip(D24.TARGET, p)), truth(*p), evidence_id=f"t-fit-{i}", source_id="oracle")
        res, asked, candidates, calls = cortex.induce("target", use_families=True), 0, 0, 0
        while True:
            candidates, calls = candidates + int(res.get("candidate_count", 0)), calls + int(res.get("evaluator_calls", 0))
            if res.get("status") != "needs_information" or asked == D26.QUERIES:
                break
            q = res["information_query"]["input"]
            cortex.observe("target", dict(q), truth(*(q[k] for k in D24.TARGET)), evidence_id=f"t-ask-{asked}", source_id="oracle")
            asked += 1
            res = cortex.induce("target", use_families=True)
        answered = wrong = 0
        if res.get("status") == "proposed":
            for i, p in enumerate(D24.VALIDATION):
                cortex.observe("target", dict(zip(D24.TARGET, p)), truth(*p), evidence_id=f"t-val-{i}", source_id="oracle")
            for q in queries:
                pred = cortex.predict("target", dict(zip(D24.TARGET, q)))
                if pred.get("status") == "predicted":
                    answered += 1
                    wrong += pred["value"] != truth(*q)
        fams = len(cortex.families())
        return {"structure": structure, "arm": arm, "memory": n, "c": c, "fit_seed": fit_seed, "mode": mode, "fit": fit,
                "active_donors": active, "families": fams, "asked": asked, "status": res.get("status"),
                "origin": res.get("origin"), "candidates": candidates, "evaluator_calls": calls, "queries": len(queries),
                "answered": answered, "wrong": wrong,
                "success": res.get("status") == "proposed" and answered == len(queries) and wrong == 0}
    finally:
        cortex.close()


def cell(recs, mode, arms, n, structures):
    rs = [r for r in recs if r["mode"] == mode and r["arm"] in arms and r["memory"] == n and r["structure"] in structures and r["c"] in D21.IN_RANGE]
    k, q = sum(r["success"] for r in rs), sum(r["queries"] for r in rs)
    return {"n": len(rs), "success_rate": round(k / len(rs), 4) if rs else 0.0, "wilson95": D21.wilson(k, len(rs)),
            "mean_evaluator_calls": round(sum(r["evaluator_calls"] for r in rs) / len(rs), 1) if rs else 0.0,
            "mean_families": round(sum(r["families"] for r in rs) / len(rs), 1) if rs else 0.0,
            "wrong": sum(r["wrong"] for r in rs), "wrong_per_query": sum(r["wrong"] for r in rs) / q if q else 0.0}


def gate(recs, transfer):
    relevant = ("relevant_r0", "relevant_r5")
    S = {f"{m}|{a}|{n}": cell(recs, m, (a,), n, transfer) for m in MODES for a in ARMS for n in SIZES}
    S.update({f"{m}|relevant|{n}": cell(recs, m, relevant, n, transfer) for m in MODES for n in SIZES})
    rate = lambda key: S[key]["success_rate"]  # noqa: E731
    paired = {}
    for n in SIZES:
        pairs = {}
        for r in recs:
            if r["arm"] in relevant and r["memory"] == n and r["structure"] in transfer and r["c"] in D21.IN_RANGE:
                pairs.setdefault((r["structure"], r["arm"], r["c"], r["fit_seed"]), {})[r["mode"]] = r["success"]
        b = sum(1 for v in pairs.values() if v["index"] and not v["window"])
        c = sum(1 for v in pairs.values() if v["window"] and not v["index"])
        paired[f"memory_{n}"] = {"index_only": b, "window_only": c, "exact_one_sided_p": D21.mcnemar_one_sided(b, c)}
    g = GATE
    checks = {
        "C1_scale": all(rate(f"index|relevant|{n}") - rate(f"window|relevant|{n}") >= g["min_scale_gain"]
                        and paired[f"memory_{n}"]["exact_one_sided_p"] < g["max_paired_p"] for n in SIZES if n >= 32),
        "C2_small_memory_unchanged": abs(rate("index|relevant|0") - rate("window|relevant|0")) <= g["max_small_memory_gap"],
        "C3_restart": all(rate(f"index|relevant_r0|{n}") - rate(f"index|restart_r0|{n}") <= g["max_restart_loss"] for n in SIZES),
        "C4_no_false_transfer": all(rate(f"{m}|none|{n}") <= g["max_none_success"] for m in MODES for n in SIZES),
        "C5_safe": max(v["wrong_per_query"] for v in S.values()) <= g["max_wrong_per_query"],
        "C6_cheaper_than_search": all(S[f"index|relevant|{n}"]["mean_evaluator_calls"] / S[f"index|none|{n}"]["mean_evaluator_calls"]
                                      <= g["max_cost_vs_search"] for n in SIZES),
    }
    return {"G27-A": "passed" if all(checks.values()) else "not passed", "checks": checks, "paired_relevant": paired,
            "per_structure": {s: {f"{m}|{n}": cell(recs, m, relevant, n, (s,))["success_rate"] for m in MODES for n in SIZES}
                              for s in transfer}, "summary": S}


def main():
    out, dev = Path(sys.argv[1]), "--development" in sys.argv
    transfer, seed, memory_seed = (DEV, DEV_SEED, DEV_MEMORY_SEED) if dev else (HELD_OUT, SEED, MEMORY_SEED)
    w = ChainedWriter(out, {"run": "dev27_transfer" + (" development" if dev else ""), "provenance": environment_provenance(),
                            "asm_coding_sha256": code_hash(), "harness_sha256": file_sha256(Path(__file__)),
                            "asm_procedure_cortex_sha256": file_sha256(ROOT / "asm" / "procedure_cortex.py"), "seed": seed,
                            "memory_seed": memory_seed, "sizes": SIZES, "gate": GATE,
                            "preregistration_sha256": file_sha256(PREREG) if PREREG.exists() else None})
    t0, recs = time.time(), []
    with tempfile.TemporaryDirectory() as workdir:
        bases = templates(workdir, memory_seed)
        for structure in transfer:
            for n in SIZES:
                for arm in ARMS:
                    for c in CONSTANTS:
                        for s in range(D21.FIT_SEEDS):
                            for mode in MODES:
                                rec = attempt(transfer, structure, arm, n, c, s, seed, mode, bases[n], workdir)
                                recs.append(rec)
                                w.append({"part": "attempt", **rec})
    result = gate(recs, transfer)
    w.append({"part": "result", **result, "seconds": round(time.time() - t0, 1)})
    print(json.dumps({k: v for k, v in result.items() if k != "summary"}, indent=1))
    for k, v in result["summary"].items():
        print(f"{k:26s} {v['success_rate']:.3f} {v['wilson95']} calls {v['mean_evaluator_calls']:7.1f} families {v['mean_families']:5.1f} wrong {v['wrong']} n {v['n']}")


if __name__ == "__main__":
    main()
