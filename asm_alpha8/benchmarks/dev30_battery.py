"""DEV30: an M4-candidate battery. Does the whole structure-transfer stack, every opt-in mechanism of DEV25-DEV28 together,
transfer learned structure under every condition DEV21-DEV28 tested one at a time, on fresh two- and three-input
structures, without false transfer or wrong answers? Pre-registered in benchmarks/preregistration/dev30_study.md.

Configurations, paired on every attempt:
  defaults  today's ProcedureCortex (round_robin, any_int, rename; enumerate, first, window, strict)
  stack     + family_parameters='solve', family_ambiguity='ask', family_memory='index', contradiction_policy='tolerant'
Conditions (relevant donors over (u, v[, w]) in a role order drawn per attempt from all n! orders):
  relevant   the basic transfer                        far        constants beyond -8..8 (|c| = 9..12, 20, 50)
  ambiguous  fit points from {0,1,2}^n                 memory     60 background procedures named to sort first
  restart    memory, then the cortex closed and reopened noisy  each label of the target and donors wrong at 0.05
  combined   memory + noisy + far constants            none / unrelated / shuffled  the false-transfer controls
Every target and donor gets 5 fit labels and 10 validation labels; the oracle answers at most 2 questions.
Usage: python benchmarks/dev30_battery.py <out.jsonl> [--development]
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
import dev27_transfer as D27  # noqa: E402
from asm.coding.integrity import ChainedWriter, code_hash, environment_provenance, file_sha256  # noqa: E402
from asm.learning import structtransfer as T  # noqa: E402
from asm.procedure_cortex import ProcedureCortex  # noqa: E402
from asm.procedure_program import Program, substitute  # noqa: E402

PREREG = ROOT / "benchmarks" / "preregistration" / "dev30_study.md"
CONFIGS = {"defaults": {}, "stack": {"family_parameters": "solve", "family_ambiguity": "ask", "family_memory": "index",
                                     "contradiction_policy": "tolerant"}}
TRANSFER = ("relevant", "far", "ambiguous", "memory", "restart", "noisy", "combined")
CONTROLS = ("none", "unrelated", "shuffled")
ARMS = TRANSFER + CONTROLS
FAR = (-50, -20, -12, -11, -10, -9, 9, 10, 11, 12, 20, 50)
NOISE, QUERIES, MEMORY = 0.05, 2, 60
TARGET, DONOR = ("x", "y", "z"), ("u", "v", "w")
DONOR_FIT = ((0, 1, 2), (1, 2, 0), (2, 0, 1), (3, 1, 2), (1, 3, 4))
VALIDATION = ((10, 13, 16), (11, 10, 14), (12, 16, 11), (13, 11, 17), (14, 17, 12), (15, 12, 10), (16, 15, 13), (17, 14, 15),
              (11, 16, 10), (16, 11, 17))
OFFSETS = (-3, -2, -1, 1, 2, 3)
S = lambda e, f: (lambda c: (e(c), f(c)))  # noqa: E731
DEV = {  # development structures, from earlier development data
    "dev2_mul_shift": lambda c: (("add", ("mul", "x", ("add", "y", c)), "y"), lambda x, y, c=c: x * (y + c) + y),
    "dev3_mul_add": lambda c: (("add", ("mul", "x", ("add", "y", c)), "z"), lambda x, y, z, c=c: x * (y + c) + z),
    "dev3_sq_sub": lambda c: (("add", ("sub", ("mul", ("mul", "x", "x"), "y"), "z"), c), lambda x, y, z, c=c: x * x * y - z + c),
}
HELD_OUT = {  # never run before the pre-registration
    "xyy_minus_cx": lambda c: (("sub", ("mul", "x", ("mul", "y", "y")), ("mul", c, "x")), lambda x, y, c=c: x * y * y - c * x),
    "y_shift_x_plus_y": lambda c: (("add", ("mul", ("sub", "y", c), "x"), "y"), lambda x, y, c=c: (y - c) * x + y),
    "xx_plus_y_shift": lambda c: (("add", ("mul", "x", "x"), ("mul", "y", ("add", "x", c))), lambda x, y, c=c: x * x + y * (x + c)),
    "x_times_sum_shift": lambda c: (("mul", "x", ("add", ("add", "y", "z"), c)), lambda x, y, z, c=c: x * (y + z + c)),
    "yy_minus_x_shift": lambda c: (("sub", ("mul", "y", "y"), ("mul", "x", ("add", "z", c))), lambda x, y, z, c=c: y * y - x * (z + c)),
    "z_minus_c_times_xy": lambda c: (("mul", ("sub", "z", c), ("add", "x", ("mul", 2, "y"))), lambda x, y, z, c=c: (z - c) * (x + 2 * y)),
}
DEV_UNRELATED = {2: (("u_aff_2p_q", ("add", ("add", ("mul", 2, "p"), "q"), 1)), ("u_aff_2p_3q", ("add", ("add", ("mul", 2, "p"), ("mul", 3, "q")), -4)),
                     ("u_max_p_q2", ("max", "p", ("add", "q", 2))), ("u_max_p_q6", ("max", "p", ("add", "q", 6)))),
                 3: (("u_aff_p2q_r", ("add", ("add", ("add", "p", ("mul", 2, "q")), "r"), 3)), ("u_aff_p2q_m2r", ("add", ("add", ("add", "p", ("mul", 2, "q")), ("mul", -2, "r")), -1)),
                     ("u_max_q1_r", ("add", ("max", "p", ("add", "q", 1)), "r")), ("u_max_q5_r", ("add", ("max", "p", ("add", "q", 5)), "r")))}
UNRELATED = {2: (("u_aff_3p_2q", ("add", ("add", ("mul", 3, "p"), ("mul", 2, "q")), -2)), ("u_aff_3p_m1q", ("add", ("add", ("mul", 3, "p"), ("mul", -1, "q")), 5)),
                 ("u_min_p_q3", ("min", "p", ("add", "q", 3))), ("u_min_p_q7", ("min", "p", ("add", "q", 7)))),
             3: (("u_aff_2p_q_3r", ("add", ("add", ("add", ("mul", 2, "p"), "q"), ("mul", 3, "r")), -1)), ("u_aff_2p_q_m1r", ("add", ("add", ("add", ("mul", 2, "p"), "q"), ("mul", -1, "r")), 4)),
                 ("u_min_q2_r", ("sub", ("min", "p", ("add", "q", 2)), "r")), ("u_min_q6_r", ("sub", ("min", "p", ("add", "q", 6)), "r")))}  # held out
SEED, MEMORY_SEED, DEV_SEED, DEV_MEMORY_SEED = 20261201, 91, 30001, 1
GATE = {"min_success": 0.90, "min_success_noisy": 0.40, "min_gain": 0.30, "max_paired_p": 0.01, "max_control_success": 0.05,
        "max_wrong_per_query": 0.02, "max_wrong_rise": 0.005, "max_cost_ratio": 1.5}


def arity(structure, structures):
    return structures[structure](1)[1].__code__.co_argcount - 1  # the lambda's own arguments, without c


def corrupt(labels, rng, p):
    return [v + rng.choice(OFFSETS) if p and rng.random() < p else v for v in labels]


def queries_for(fit, n, rng, k=6):
    lo = [min(p[i] for p in fit) for i in range(n)]
    validation = {v[:n] for v in VALIDATION}
    for top, skip in ((10, set(fit)), (18, set(fit) | validation)):
        pool = sorted(set(itertools.product(*(range(a, top) for a in lo))) - skip)
        if len(pool) >= k:
            return rng.sample(pool, k)
    raise ValueError("no query region")


def install(cortex, donors, rng=None, p=0.0):
    """Each donor (name, expression, function of its sorted inputs) through propose (5 fit labels) and 10 validation labels."""
    for name, expr, fn in donors:
        names = sorted(D27.D24.D23.inputs_of(expr))
        fit, val = corrupt([fn(*q[:len(names)]) for q in DONOR_FIT], rng, p), corrupt([fn(*q[:len(names)]) for q in VALIDATION], rng, p)
        for i, (q, y) in enumerate(zip(DONOR_FIT, fit)):
            cortex.observe(name, dict(zip(names, q)), y, evidence_id=f"{name}-fit-{i}", source_id="oracle")
        if cortex.propose(name, Program(dict.fromkeys(names, "int"), expr), provenance="external").get("status") == "proposed":
            for i, (q, y) in enumerate(zip(VALIDATION, val)):
                cortex.observe(name, dict(zip(names, q)), y, evidence_id=f"{name}-val-{i}", source_id="oracle")
    return sum(v["state"] == "active" for name, _, _ in donors for v in cortex.versions(name))


def relevant_donors(structures, structure, c, fit_seed, seed, order):
    """Two donors of the structure (constants from donor_constants) over DONOR[:n], DONOR[i] playing TARGET[order[i]]."""
    n = arity(structure, structures)
    out = []
    for k in T.donor_constants(c if c in D21.IN_RANGE else 1, fit_seed, seed):
        expr, f = structures[structure](k)
        plays = {TARGET[order[i]]: DONOR[i] for i in range(n)}
        fn = lambda *args, f=f, plays=plays: f(*(args[DONOR.index(plays[t])] for t in TARGET[:n]))  # noqa: E731
        out.append((f"z_rel_{structure}_{'m' if k < 0 else 'p'}{abs(k)}", substitute(expr, plays), fn))
    return out


def unrelated_donors(unrelated, n):
    return [(name, expr, lambda *a, e=expr, names=tuple(sorted(D27.D24.D23.inputs_of(expr))): Program(dict.fromkeys(names, "int"), e).run(dict(zip(names, a))))
            for name, expr in unrelated[n]]


def attempt(structures, structure, arm, c, fit_seed, seed, config, memory_file, workdir, unrelated):
    n = arity(structure, structures)
    rng = random.Random(f"{seed}:attempt:{structure}:{arm}:{c}:{fit_seed}")
    order = rng.choice(list(itertools.permutations(range(n))))
    grid = range(3) if arm == "ambiguous" else range(10)
    fit = sorted(rng.sample(list(itertools.product(grid, repeat=n)), 5))
    queries, truth = queries_for(fit, n, rng), structures[structure](c)[1]
    p = NOISE if arm in ("noisy", "combined") else 0.0
    noise = random.Random(f"{seed}:noise:{structure}:{arm}:{c}:{fit_seed}") if p else None
    path = Path(workdir) / "attempt.db"
    for leftover in (Path(f"{path}-wal"), Path(f"{path}-shm"), path):
        leftover.unlink(missing_ok=True)
    if arm in ("memory", "restart", "combined"):
        shutil.copyfile(memory_file, path)
    options = dict(trust_provider=T.TRUST, family_scope="any_int", family_mapping="rename", **CONFIGS[config])
    cortex = ProcedureCortex(path, **options)
    try:
        donors = ([] if arm in ("none", "unrelated") else relevant_donors(structures, structure, c, fit_seed, seed, order))
        active = install(cortex, unrelated_donors(unrelated, n) if arm == "unrelated" else []) + install(cortex, donors, noise, p)
        if arm == "restart":
            cortex.families()
            cortex.close()
            cortex = ProcedureCortex(path, **options)
        fit_y, val_y = [truth(*q) for q in fit], [truth(*q[:n]) for q in VALIDATION]
        if arm == "shuffled":
            fit_y = D21.shuffled(fit_y, random.Random(f"{seed}:shuffle:{structure}:{c}:{fit_seed}"))
            val_y = D21.shuffled(val_y, random.Random(f"{seed}:shuffle-val:{structure}:{c}:{fit_seed}"))
        fit_y, val_y = corrupt(fit_y, noise, p), corrupt(val_y, noise, p)
        for i, (q, v) in enumerate(zip(fit, fit_y)):
            cortex.observe("target", dict(zip(TARGET, q)), v, evidence_id=f"t-fit-{i}", source_id="oracle")
        res, asked, calls = cortex.induce("target", use_families=True), 0, 0
        while True:
            calls += int(res.get("evaluator_calls", 0))
            if res.get("status") != "needs_information" or asked == QUERIES:
                break
            q = res["information_query"]["input"]
            cortex.observe("target", dict(q), truth(*(q[k] for k in TARGET[:n])), evidence_id=f"t-ask-{asked}", source_id="oracle")
            asked += 1
            res = cortex.induce("target", use_families=True)
        answered = wrong = 0
        if res.get("status") == "proposed":
            for i, (q, v) in enumerate(zip(VALIDATION, val_y)):
                cortex.observe("target", dict(zip(TARGET, q[:n])), v, evidence_id=f"t-val-{i}", source_id="oracle")
            for q in queries:
                pred = cortex.predict("target", dict(zip(TARGET, q)))
                if pred.get("status") == "predicted":
                    answered += 1
                    wrong += pred["value"] != truth(*q)
        return {"structure": structure, "arity": n, "arm": arm, "c": c, "fit_seed": fit_seed, "config": config, "order": list(order),
                "fit": fit, "active_donors": active, "asked": asked, "status": res.get("status"), "origin": res.get("origin"),
                "evaluator_calls": calls, "queries": len(queries), "answered": answered, "wrong": wrong,
                "success": res.get("status") == "proposed" and answered == len(queries) and wrong == 0}
    finally:
        cortex.close()


def memory_template(workdir, seed):
    path = Path(workdir) / "memory.db"
    cortex = ProcedureCortex(path, trust_provider=T.TRUST, family_memory="index")
    D27.install_memory(cortex, D27.memory(MEMORY, seed))
    cortex.families()
    cortex.close()
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    return path


def constants(arm):
    return FAR if arm in ("far", "combined") else D21.IN_RANGE


def cell(recs, config, arms):
    rs = [r for r in recs if r["config"] == config and r["arm"] in arms]
    k, q = sum(r["success"] for r in rs), sum(r["queries"] for r in rs)
    return {"n": len(rs), "success_rate": round(k / len(rs), 4) if rs else 0.0, "wilson95": D21.wilson(k, len(rs)),
            "mean_evaluator_calls": round(sum(r["evaluator_calls"] for r in rs) / len(rs), 1) if rs else 0.0,
            "mean_asked": round(sum(r["asked"] for r in rs) / len(rs), 3) if rs else 0.0,
            "wrong": sum(r["wrong"] for r in rs), "wrong_per_query": sum(r["wrong"] for r in rs) / q if q else 0.0}


def gate(recs):
    S = {f"{cf}|{a}": cell(recs, cf, (a,)) for cf in CONFIGS for a in ARMS}
    S.update({f"{cf}|transfer": cell(recs, cf, TRANSFER) for cf in CONFIGS})
    rate = lambda key: S[key]["success_rate"]  # noqa: E731
    pairs = {}
    for r in recs:
        if r["arm"] in TRANSFER:
            pairs.setdefault((r["structure"], r["arm"], r["c"], r["fit_seed"]), {})[r["config"]] = r["success"]
    b = sum(1 for v in pairs.values() if v["stack"] and not v["defaults"])
    c = sum(1 for v in pairs.values() if v["defaults"] and not v["stack"])
    g = GATE
    checks = {
        "B1_transfer_everywhere": all(rate(f"stack|{a}") >= g["min_success"] for a in TRANSFER if a not in ("noisy", "combined"))
                                  and all(rate(f"stack|{a}") >= g["min_success_noisy"] for a in ("noisy", "combined")),
        "B2_gain_over_defaults": rate("stack|transfer") - rate("defaults|transfer") >= g["min_gain"] and D21.mcnemar_one_sided(b, c) < g["max_paired_p"],
        "B3_no_false_transfer": all(rate(f"{cf}|{a}") <= g["max_control_success"] for cf in CONFIGS for a in CONTROLS),
        "B4_safe": max(v["wrong_per_query"] for v in S.values()) <= g["max_wrong_per_query"]
                   and all(S[f"stack|{a}"]["wrong_per_query"] - S[f"defaults|{a}"]["wrong_per_query"] <= g["max_wrong_rise"] for a in ARMS),
        "B5_cost": S["stack|relevant"]["mean_evaluator_calls"] / S["defaults|relevant"]["mean_evaluator_calls"] <= g["max_cost_ratio"],
    }
    return {"G30-A": "passed" if all(checks.values()) else "not passed", "checks": checks,
            "paired_transfer": {"stack_only": b, "defaults_only": c, "exact_one_sided_p": D21.mcnemar_one_sided(b, c)},
            "by_arity": {f"{cf}|arity{n}": cell([r for r in recs if r["arity"] == n], cf, TRANSFER)["success_rate"] for cf in CONFIGS for n in (2, 3)},
            "summary": S}


def main():
    out, dev = Path(sys.argv[1]), "--development" in sys.argv
    structures, seed, memory_seed, unrelated = (DEV, DEV_SEED, DEV_MEMORY_SEED, DEV_UNRELATED) if dev else (HELD_OUT, SEED, MEMORY_SEED, UNRELATED)
    w = ChainedWriter(out, {"run": "dev30_battery" + (" development" if dev else ""), "provenance": environment_provenance(),
                            "asm_coding_sha256": code_hash(), "harness_sha256": file_sha256(Path(__file__)),
                            "asm_procedure_cortex_sha256": file_sha256(ROOT / "asm" / "procedure_cortex.py"), "seed": seed,
                            "memory_seed": memory_seed, "configs": CONFIGS, "gate": GATE,
                            "preregistration_sha256": file_sha256(PREREG) if PREREG.exists() else None})
    t0, recs = time.time(), []
    with tempfile.TemporaryDirectory() as workdir:
        memory_file = memory_template(workdir, memory_seed)
        for structure in structures:
            for arm in ARMS:
                for c in constants(arm):
                    for s in range(D21.FIT_SEEDS):
                        for config in CONFIGS:
                            rec = attempt(structures, structure, arm, c, s, seed, config, memory_file, workdir, unrelated)
                            recs.append(rec)
                            w.append({"part": "attempt", **rec})
    result = gate(recs)
    w.append({"part": "result", **result, "seconds": round(time.time() - t0, 1)})
    print(json.dumps({k: v for k, v in result.items() if k != "summary"}, indent=1))
    for k, v in result["summary"].items():
        print(f"{k:22s} {v['success_rate']:.3f} {v['wilson95']} calls {v['mean_evaluator_calls']:7.1f} asked {v['mean_asked']:.3f} wrong {v['wrong']} n {v['n']}")


if __name__ == "__main__":
    main()
