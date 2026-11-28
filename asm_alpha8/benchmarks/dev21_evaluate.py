"""DEV21 Part B, as pre-registered in benchmarks/preregistration/dev21_study.md: do DEV21's two mechanisms for learned
edit steps reproduce fresh developer fixes that DEV20's ordering misses? round_robin: each step proposes its next
candidate before any step proposes another (StepLibrary.candidates_for(sharing='round_robin'), Part A's rule applied to
steps); guard: an exception hole applies only at the exception of a `raise` (exception_sites='raise'); both.

Knowledge: all 1,737 real fixes of DEV17-DEV20, learned in per-project batches by P17 (KnowledgeBase), S18 (ShapeLibrary)
and S20 (StepLibrary). Per fresh problem (K = 80), as DEV20: B (any position), P17 (any position), S18 (within K); and
S20 four times, paired: control (DEV20 as run), round_robin, guard, both.
G21-B (round_robin vs control) and G21-C (guard vs control): b = fixes only the arm reproduces, c = fixes only the control
reproduces; each passes iff b - c >= 3 and its exact one-sided sign test survives Holm's correction over the two at 0.05.
"both" is descriptive.
Usage: python benchmarks/dev21_evaluate.py <out_dir> <dev21_fresh.jsonl> <knowledge.jsonl> ... [--workers=N]
"""
import collections
import json
import math
import multiprocessing
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
import dev18_evaluate as E  # noqa: E402
import asm.coding.steps as ST  # noqa: E402
from asm.coding.content import ProblemContext  # noqa: E402
from asm.coding.integrity import ChainedWriter, code_hash, environment_provenance, file_sha256, read_records  # noqa: E402
from asm.coding.knowledge import KnowledgeBase  # noqa: E402
from asm.coding.shapes import ShapeLibrary  # noqa: E402

K = E.K
PREREG = ROOT / "benchmarks" / "preregistration" / "dev21_study.md"
ARMS = {"control": {}, "round_robin": {"sharing": "round_robin"}, "guard": {"exception_sites": "raise"},
        "both": {"sharing": "round_robin", "exception_sites": "raise"}}
GATES = {"G21-B": "round_robin", "G21-C": "guard"}
MIN_NET, ALPHA = 3, 0.05
_G: dict = {}


def sign_test_p(b, c):
    """Exact one-sided p of at least b successes for the guard among b + c discordant fixes, under equal chances."""
    n = b + c
    return 1.0 if n == 0 else sum(math.comb(n, k) for k in range(b, n + 1)) / 2 ** n


def holm(pvalues: dict, alpha: float = ALPHA) -> dict:
    """{name: rejected} by Holm's step-down procedure (the smallest p against alpha/m, the next against alpha/(m-1), ...;
    stop at the first that fails)."""
    out, still = {}, True
    for i, name in enumerate(sorted(pvalues, key=lambda n: (pvalues[n], n))):
        still = still and pvalues[name] <= alpha / (len(pvalues) - i)
        out[name] = still
    return out


def gate_verdicts(rows: list) -> dict:
    """G21-B and G21-C from paired rows ({arm: reproduced})."""
    stats = {}
    for gate, arm in GATES.items():
        b = [r["id"] for r in rows if r[arm] and not r["control"]]
        c = [r["id"] for r in rows if r["control"] and not r[arm]]
        stats[gate] = {"arm": arm, "arm_only": b, "control_only": c, "net": len(b) - len(c), "p": sign_test_p(len(b), len(c))}
    rejected = holm({g: v["p"] for g, v in stats.items()})
    for g, v in stats.items():
        v["holm_rejects_null"] = rejected[g]
        v["verdict"] = "passed" if v["net"] >= MIN_NET and rejected[g] else "not passed"
    return stats


def learn_all(paths):
    kb, lib, steps = KnowledgeBase(), ShapeLibrary(), ST.StepLibrary()
    for p in paths:
        by = collections.defaultdict(list)
        for r in read_records(p)[1]:
            by[r["repo"]].append((r["before"], r["after"], r["id"]))
        tag = p.parent.name + "/" + p.stem
        for repo, ex in by.items():  # one batch per project, as DEV19 and DEV20
            kb.learn(ex, f"{tag}:{repo}")
            lib.learn(ex, f"{tag}:{repo}")
            steps.learn(ex, f"{tag}:{repo}")
    return kb, lib, steps


def score(p):
    kb, lib, steps = _G["kb"], _G["lib"], _G["steps"]
    t0 = time.time()
    before, target = p["before"], E.norm(p["after"])
    span, ctx = (1, before.count("\n") + 1), ProblemContext.from_dict(p["context"])
    b = E.builtin_position(before, p["after"])
    p17 = E.first_hit(E.p17_programs(kb, before), target)
    s18 = E.first_hit([x for x, _ in E.s18_programs(lib, before, ctx, K)], target)
    row = {"id": p["id"], "repo": p["repo"], "builtin_any": b is not None, "builtin_within_k": b is not None and b < K,
           "p17_any": p17 is not None, "p17_within_k": p17 is not None and p17 < K, "s18": s18 is not None}
    known = row["builtin_any"] or row["p17_any"] or row["s18"]
    for arm, opts in ARMS.items():
        got = steps.candidates_for(before, "m.py", span, ctx, limit=K, as_candidates=False, **opts)
        hit = E.first_hit([x for x, _ in got], target)
        row[arm] = hit is not None
        row[arm + "_position"] = hit
        row[arm + "_kind"] = got[hit][1]["kind"] if hit is not None else None
        row[arm + "_new"] = hit is not None and not known
    row["seconds"] = round(time.time() - t0, 1)
    return row


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    workers = int(next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--workers=")), "4"))
    out, fresh_path, know = Path(args[0]), Path(args[1]), [Path(a) for a in args[2:]]
    out.mkdir(parents=True, exist_ok=True)
    w = ChainedWriter(out / "dev21_eval.jsonl", {"run": "dev21_evaluate", "provenance": environment_provenance(),
                                                 "asm_coding_sha256": code_hash(), "K": K, "arms": ARMS,
                                                 "inputs": {f"{p.parent.name}/{p.name}": file_sha256(p) for p in [fresh_path, *know]},
                                                 "preregistration_sha256": file_sha256(PREREG)})
    t0 = time.time()
    kb, lib, steps = learn_all(know)
    _G.update(kb=kb, lib=lib, steps=steps)
    steps.save(out / "steps_dev21.json")
    w.append({"part": "learned", "procedures": kb.summary(), "shapes": lib.summary(), "steps": steps.summary(),
              "seconds": round(time.time() - t0)})
    print(json.dumps({"learned": steps.summary(), "seconds": round(time.time() - t0)}), flush=True)
    rows = []
    with multiprocessing.get_context("fork").Pool(workers) as pool:
        for row in pool.imap(score, read_records(fresh_path)[1], chunksize=1):
            rows.append(row)
            w.append({"part": "fresh", **row})
            print(json.dumps({k: row[k] for k in ("id", *ARMS, "seconds")}), flush=True)
    summ = {"problems": len(rows), "builtin_any": sum(r["builtin_any"] for r in rows),
            "builtin_within_k": sum(r["builtin_within_k"] for r in rows), "p17_any": sum(r["p17_any"] for r in rows),
            "p17_within_k": sum(r["p17_within_k"] for r in rows), "s18": sum(r["s18"] for r in rows),
            **{arm: sum(r[arm] for r in rows) for arm in ARMS}, **{arm + "_new": sum(r[arm + "_new"] for r in rows) for arm in ARMS},
            "gates": gate_verdicts(rows), "seconds": round(time.time() - t0)}
    w.append({"part": "summary", **summ})
    print(json.dumps(summ, indent=1), flush=True)


if __name__ == "__main__":
    main()
