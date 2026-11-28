"""DEV19 evaluation, as pre-registered in benchmarks/preregistration/dev19_study.md: does more training data close the
gap DEV18 found (too few learned shapes)? The system is DEV18's (with amendment A2), unchanged; only the knowledge grows.

Knowledge levels (each learned from real fixes only, in batches per project):
  L91    the 91 DEV17 history fixes (DEV18's knowledge)
  L563   + the 472 DEV18 fresh fixes (inspected during DEV18, so now training data)
  LALL   + the fixes mined from the 10 DEV19 training projects
Each level is scored on the DEV19 fresh problems with dev18_evaluate.score (B, P17, S18, D18 within K = 80).
Learning cycle (descriptive): from LALL, the fresh problems in date order; attempt with D18, then learn the fix.
Usage: python benchmarks/dev19_evaluate.py <history.jsonl> <dev18_fresh.jsonl> <dev19_train.jsonl> <dev19_fresh.jsonl> <out_dir>
"""
import collections
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
import dev18_evaluate as E  # noqa: E402
from asm.coding.content import ProblemContext  # noqa: E402
from asm.coding.integrity import ChainedWriter, code_hash, environment_provenance, file_sha256, read_records  # noqa: E402
from asm.coding.knowledge import KnowledgeBase  # noqa: E402
from asm.coding.shapes import ShapeLibrary  # noqa: E402

K = E.K
PREREG = ROOT / "benchmarks" / "preregistration" / "dev19_study.md"


def learn(kb, lib, records, tag):
    by_repo = collections.defaultdict(list)
    for r in records:
        by_repo[r["repo"]].append((r["before"], r["after"], r["id"]))
    for repo, ex in by_repo.items():  # one induction per project batch: same knowledge, far less re-induction
        kb.learn(ex, f"{tag}:{repo}")
        lib.learn(ex, f"{tag}:{repo}")


def main():
    hist, f18, t19, f19, out = map(Path, sys.argv[1:6])
    out.mkdir(parents=True, exist_ok=True)
    w = ChainedWriter(out / "dev19_eval.jsonl", {"run": "dev19_evaluate", "provenance": environment_provenance(),
                                                 "asm_coding_sha256": code_hash(), "K": K,
                                                 "inputs": {p.name: file_sha256(p) for p in (hist, f18, t19, f19)},
                                                 "preregistration_sha256": file_sha256(PREREG)})
    fresh = read_records(f19)[1]
    kb, lib = KnowledgeBase(), ShapeLibrary()
    summaries = {}
    for level, recs, tag in (("L91", read_records(hist)[1], "history"), ("L563", read_records(f18)[1], "dev18"),
                             ("LALL", read_records(t19)[1], "dev19train")):
        learn(kb, lib, recs, tag)
        w.append({"part": "learned", "level": level, "procedures": kb.summary(), "shapes": lib.summary()})
        rows = []
        for p in fresh:
            row = {"level": level, "id": p["id"], **E.score(p, kb, lib, ProblemContext.from_dict(p["context"]))}
            rows.append(row)
            w.append({"part": "fresh", **row})
        new = [r["id"] for r in rows if r["d18"] and not r["builtin_any"] and not r["p17_any"]]
        summaries[level] = {"problems": len(rows), "builtin_any": sum(r["builtin_any"] for r in rows),
                            "p17_any": sum(r["p17_any"] for r in rows), "p17_within_k": sum(r["p17_within_k"] for r in rows),
                            "s18": sum(r["s18"] for r in rows), "d18": sum(r["d18"] for r in rows), "new_by_d19": new}
        print(json.dumps({level: {k: (len(v) if isinstance(v, list) else v) for k, v in summaries[level].items()}}), flush=True)
    n_new = len(summaries["LALL"]["new_by_d19"])
    summaries["G19-1"] = "passed" if n_new >= 10 and n_new >= 0.02 * len(fresh) else "not passed"
    kb.save(out / "knowledge_dev19.json")
    lib.save(out / "shapes_dev19.json")
    kb2, lib2 = copy.deepcopy(kb), copy.deepcopy(lib)
    online = 0
    for p in sorted(fresh, key=lambda r: (r["date"], r["id"])):
        progs = E.p17_programs(kb2, p["before"], K)
        progs += [x for x, _ in E.s18_programs(lib2, p["before"], ProblemContext.from_dict(p["context"]), max(0, K - len(progs)))]
        online += E.first_hit(progs, E.norm(p["after"])) is not None
        kb2.learn([(p["before"], p["after"], p["id"])], f"revealed:{p['repo']}")
        lib2.learn([(p["before"], p["after"], p["id"])], f"revealed:{p['repo']}")
    summaries["cycle"] = {"online_reproduced": online, "static_reproduced": summaries["LALL"]["d18"]}
    w.append({"part": "summary", **summaries})
    print(json.dumps({k: v for k, v in summaries.items() if k in ("G19-1", "cycle")}))


if __name__ == "__main__":
    main()
