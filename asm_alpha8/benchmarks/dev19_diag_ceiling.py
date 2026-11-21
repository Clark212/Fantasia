"""DEV19 EXPLORATORY diagnostic, part 2 (not pre-registered). For the fresh fixes whose shape the LALL library knows
(dev19_diag_coverage.py, part C), with the LALL shape library of run 1 (learning does not use candidates_for, so A2 cannot change it):
  B  content coverage   are the fix's needed values among the real content operators' fillers at the fix location?
                        (dev18_selfcheck.check_b, LALL vocabulary)
  D  S18 ceiling        the real S18 with the budget caps lifted: is the fix produced at all, and at which position?
Usage: python benchmarks/dev19_diag_ceiling.py <dev19_fresh> <shapes_dev19.json> <coverage.jsonl> <out.jsonl>
"""
import json
import signal
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
import dev18_selfcheck as SC  # noqa: E402
from asm.coding import content as C  # noqa: E402
from asm.coding.integrity import code_hash, read_records  # noqa: E402
from asm.coding.shapes import ShapeLibrary  # noqa: E402

BUDGET_S = 300


def main():
    f19, shp, diag, out = sys.argv[1:5]
    known = {r["id"] for r in map(json.loads, open(diag)) if r.get("level") == "LALL" and r.get("C_hits")}
    lib = ShapeLibrary.load(shp)
    signal.signal(signal.SIGALRM, SC._alarm)
    with open(out, "w") as f:
        f.write(json.dumps({"code": code_hash(), "library": lib.summary(), "known": len(known), "budget_s": BUDGET_S}) + "\n")
        for p in read_records(Path(f19))[1]:
            if p["id"] not in known:
                continue
            before, target = p["before"], SC.norm(p["after"])
            ctx = C.ProblemContext.from_dict(p["context"])
            shapes, _ = SC.own_shapes(before, p["after"])
            row = {"id": p["id"]}
            t0 = time.time()
            signal.alarm(BUDGET_S)
            try:
                cover, own_pos = SC.check_b(shapes, before, target, ctx, lib.vocab)
                row["B_cover"], row["B_own_within_k"] = cover, own_pos
            except SC.Timeout:
                row["B_timeout"] = True
            finally:
                signal.alarm(0)
            signal.alarm(BUDGET_S)
            try:
                row["D_position"], row["D_candidates"], row["D_ops"] = SC.check_d(lib, before, target, ctx)
            except SC.Timeout:
                row["D_timeout"] = True
            finally:
                signal.alarm(0)
            row["s"] = round(time.time() - t0, 1)
            f.write(json.dumps(row) + "\n")
            f.flush()
            print(json.dumps({k: row.get(k) for k in ("id", "B_own_within_k", "D_position", "D_candidates", "s")}), flush=True)
        f.write(json.dumps({"done": True}) + "\n")


if __name__ == "__main__":
    main()
