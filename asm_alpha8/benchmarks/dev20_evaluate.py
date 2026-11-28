"""DEV20 evaluation, as pre-registered in benchmarks/preregistration/dev20_study.md: do learned edit STEPS (single,
multi-site, paired; exception holes in raise positions) reproduce fresh developer fixes that the built-in operations,
DEV17 procedures and DEV18 shapes do not?

Knowledge: all 1,254 real fixes of DEV17-DEV19 (history, DEV18 fresh, DEV19 training, DEV19 fresh), learned in
per-project batches by every learned system: P17 (KnowledgeBase), S18 (ShapeLibrary), S20 (StepLibrary).
Per fresh problem (K = 80):
  B     built-in operations (DEV15), any position and within K
  P17   DEV17 procedures, any position and within K
  S18   DEV18 shapes with content from the problem, within K
  S20   DEV20 steps, within K; ablations: single steps only, and without exception holes
  D20   the workflow's order: P17 (<= 30), then S18 (<= 20), then S20 to K
G20-1: fixes reproduced by S20 within K that neither B (any), P17 (any) nor S18 (within K) reproduces.
Usage: python benchmarks/dev20_evaluate.py <out_dir> <dev20_fresh.jsonl> <knowledge.jsonl> ... [--workers=N]
"""
import collections
import json
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
PREREG = ROOT / "benchmarks" / "preregistration" / "dev20_study.md"
D20_SHARE = (30, 20)  # the workflow's shares for procedures and shapes when steps are present (faultloc)
_G: dict = {}         # learned systems, set before the workers fork


def learn_all(paths):
    kb, lib, steps = KnowledgeBase(), ShapeLibrary(), ST.StepLibrary()
    ST.EXCEPTION_HOLES = False
    noexc = ST.StepLibrary()
    ST.EXCEPTION_HOLES = True
    for p in paths:
        by = collections.defaultdict(list)
        for r in read_records(p)[1]:
            by[r["repo"]].append((r["before"], r["after"], r["id"]))
        tag = p.parent.name + "/" + p.stem
        for repo, ex in by.items():  # one batch per project, as DEV19
            kb.learn(ex, f"{tag}:{repo}")
            lib.learn(ex, f"{tag}:{repo}")
            steps.learn(ex, f"{tag}:{repo}")
            ST.EXCEPTION_HOLES = False
            noexc.learn(ex, f"{tag}:{repo}")
            ST.EXCEPTION_HOLES = True
    return kb, lib, steps, noexc


def score(p):
    kb, lib, steps, noexc = _G["kb"], _G["lib"], _G["steps"], _G["noexc"]
    t0 = time.time()
    before, target = p["before"], E.norm(p["after"])
    span = (1, before.count("\n") + 1)
    ctx = ProblemContext.from_dict(p["context"])
    b = E.builtin_position(before, p["after"])
    p17_all = E.p17_programs(kb, before)
    p17 = E.first_hit(p17_all, target)
    s18 = [x for x, _ in E.s18_programs(lib, before, ctx, K)]
    s18_hit = E.first_hit(s18, target)
    s20 = steps.candidates_for(before, "m.py", span, ctx, limit=K, as_candidates=False)
    s20_hit = E.first_hit([x for x, _ in s20], target)
    single = steps.candidates_for(before, "m.py", span, ctx, limit=K, as_candidates=False,
                                  quota={"single": 1, "multi": 0, "pair": 0})
    single = [x for x, info in single if info["kind"] == "single"]
    ne = [x for x, _ in noexc.candidates_for(before, "m.py", span, ctx, limit=K, as_candidates=False)]
    d20 = p17_all[:D20_SHARE[0]]
    d20 += s18[:max(0, min(D20_SHARE[1], K - len(d20)))]
    d20 += [x for x, _ in steps.candidates_for(before, "m.py", span, ctx, limit=max(0, K - len(d20)), as_candidates=False)]
    d20_hit = E.first_hit(d20, target)
    row = {"id": p["id"], "repo": p["repo"], "builtin_any": b is not None, "builtin_within_k": b is not None and b < K,
           "builtin_position": b, "p17_any": p17 is not None, "p17_within_k": p17 is not None and p17 < K, "p17_position": p17,
           "p17_programs": len(p17_all), "s18": s18_hit is not None, "s18_position": s18_hit,
           "s20": s20_hit is not None, "s20_position": s20_hit,
           "s20_kind": s20[s20_hit][1]["kind"] if s20_hit is not None else None,
           "s20_ops": s20[s20_hit][1]["ops"] if s20_hit is not None else None,
           "s20_step": s20[s20_hit][1]["step"] if s20_hit is not None else None,
           "s20_single_only": E.first_hit(single, target) is not None,
           "s20_without_exception_holes": E.first_hit(ne, target) is not None,
           "d20": d20_hit is not None, "d20_position": d20_hit, "s20_candidates": len(s20), "seconds": round(time.time() - t0, 1)}
    row["new_by_s20"] = row["s20"] and not row["builtin_any"] and not row["p17_any"] and not row["s18"]
    return row


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    workers = int(next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--workers=")), "4"))
    out, fresh_path, know = Path(args[0]), Path(args[1]), [Path(a) for a in args[2:]]
    out.mkdir(parents=True, exist_ok=True)
    w = ChainedWriter(out / "dev20_eval.jsonl", {"run": "dev20_evaluate", "provenance": environment_provenance(),
                                                 "asm_coding_sha256": code_hash(), "K": K, "d20_share": D20_SHARE,
                                                 "inputs": {f"{p.parent.name}/{p.name}": file_sha256(p) for p in [fresh_path, *know]},
                                                 "preregistration_sha256": file_sha256(PREREG)})
    t0 = time.time()
    kb, lib, steps, noexc = learn_all(know)
    _G.update(kb=kb, lib=lib, steps=steps, noexc=noexc)
    kb.save(out / "knowledge_dev20.json")
    lib.save(out / "shapes_dev20.json")
    steps.save(out / "steps_dev20.json")
    w.append({"part": "learned", "procedures": kb.summary(), "shapes": lib.summary(), "steps": steps.summary(),
              "steps_without_exception_holes": noexc.summary(), "seconds": round(time.time() - t0)})
    print(json.dumps({"learned": steps.summary(), "seconds": round(time.time() - t0)}), flush=True)
    fresh = read_records(fresh_path)[1]
    rows = []
    with multiprocessing.get_context("fork").Pool(workers) as pool:
        for row in pool.imap(score, fresh, chunksize=1):  # results in the fresh file's order
            rows.append(row)
            w.append({"part": "fresh", **row})
            print(json.dumps({k: row[k] for k in ("id", "s20", "s20_position", "new_by_s20", "seconds")}), flush=True)
    n = len(rows)
    new = [r["id"] for r in rows if r["new_by_s20"]]
    summ = {"problems": n, "builtin_any": sum(r["builtin_any"] for r in rows),
            "builtin_within_k": sum(r["builtin_within_k"] for r in rows), "p17_any": sum(r["p17_any"] for r in rows),
            "p17_within_k": sum(r["p17_within_k"] for r in rows), "s18": sum(r["s18"] for r in rows),
            "s20": sum(r["s20"] for r in rows), "d20": sum(r["d20"] for r in rows),
            "s20_by_kind": dict(collections.Counter(r["s20_kind"] for r in rows if r["s20"])),
            "s20_single_only": sum(r["s20_single_only"] for r in rows),
            "s20_without_exception_holes": sum(r["s20_without_exception_holes"] for r in rows),
            "new_by_s20": new, "new_by_kind": dict(collections.Counter(r["s20_kind"] for r in rows if r["new_by_s20"])),
            "G20-1": "passed" if len(new) >= 10 and len(new) >= 0.02 * n else "not passed",
            "seconds": round(time.time() - t0)}
    w.append({"part": "summary", **summ})
    print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in summ.items()}), flush=True)


if __name__ == "__main__":
    main()
