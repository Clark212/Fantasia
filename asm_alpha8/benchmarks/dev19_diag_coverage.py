"""DEV19 EXPLORATORY diagnostic (not pre-registered): why did 12.6x more knowledge not add reproduced fixes?

For each fresh fix, at each knowledge level (shape library learned exactly as dev19_evaluate learns it):
  C  shape transfer   does any library shape reproduce the fix when handed the fix's own content (no caps)?
                      (dev18_selfcheck.check_c) -> the fraction of fresh fixes whose SHAPE is known
At LALL (saved knowledge of the first run, which the A2 fix cannot change: learning does not use candidates_for):
  P17 position        position of the fix in the unlimited P17 list, for the fixes P17 reproduces at all
Usage: python benchmarks/dev19_diag_coverage.py <history> <dev18_fresh> <dev19_train> <dev19_fresh> <knowledge_dev19.json> <out.jsonl>
"""
import collections
import json
import signal
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
import dev18_evaluate as E  # noqa: E402
import dev18_selfcheck as SC  # noqa: E402
from asm.coding.integrity import code_hash, read_records  # noqa: E402
from asm.coding.knowledge import KnowledgeBase  # noqa: E402
from asm.coding.shapes import ShapeLibrary  # noqa: E402

BUDGET_S = 180


def learn(lib, records, tag):  # exactly dev19_evaluate.learn, shapes only
    by_repo = collections.defaultdict(list)
    for r in records:
        by_repo[r["repo"]].append((r["before"], r["after"], r["id"]))
    for repo, ex in by_repo.items():
        lib.learn(ex, f"{tag}:{repo}")


def main():
    hist, f18, t19, f19, kbp, out = sys.argv[1:7]
    fresh = read_records(Path(f19))[1]
    signal.signal(signal.SIGALRM, SC._alarm)
    f = open(out, "w")
    f.write(json.dumps({"code": code_hash(), "budget_s": BUDGET_S}) + "\n")
    lib = ShapeLibrary()
    own = {p["id"]: SC.own_shapes(p["before"], p["after"]) for p in fresh}
    f.write(json.dumps({"own_status": dict(collections.Counter(s for _, s in own.values()))}) + "\n")
    for level, path, tag in (("L91", hist, "history"), ("L563", f18, "dev18"), ("LALL", t19, "dev19train")):
        learn(lib, read_records(Path(path))[1], tag)
        known = 0
        for p in fresh:
            shapes, status = own[p["id"]]
            row = {"level": level, "id": p["id"], "status": status}
            if shapes:
                t0 = time.time()
                signal.alarm(BUDGET_S)
                try:
                    hits = SC.check_c(lib, shapes, p["before"], E.norm(p["after"]))
                    row["C_hits"] = len(hits)
                    row["C_best"] = max((h["support"] for h in hits), default=None)
                    row["C_active"] = sum(h["status"] == "active" for h in hits)
                except SC.Timeout:
                    row["timeout"] = True
                finally:
                    signal.alarm(0)
                row["s"] = round(time.time() - t0, 1)
            known += bool(row.get("C_hits"))
            f.write(json.dumps(row) + "\n")
            f.flush()
        f.write(json.dumps({"level": level, "shapes": lib.summary(), "shape_known": known}) + "\n")
        print(level, "shape known:", known, "/", len(fresh), flush=True)
    kb = KnowledgeBase.load(kbp)
    for p in fresh:
        progs = E.p17_programs(kb, p["before"])
        pos = E.first_hit(progs, E.norm(p["after"]))
        if pos is not None:
            f.write(json.dumps({"p17_position": pos, "id": p["id"], "p17_programs": len(progs)}) + "\n")
            print("P17", p["id"], pos, len(progs), flush=True)
    f.write(json.dumps({"done": True}) + "\n")


if __name__ == "__main__":
    main()
