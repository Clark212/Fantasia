"""DEV19 A2 check (exploratory): replay a learning cycle on the FIXED code and count, per problem, whether the fix is
found within the K = 80 budget, and separately whether only the 81st program (the one the limit-0 defect added when P17
alone filled K) would have found it. The knowledge trajectory is the same either way (every revealed fix is learned).

Usage: python benchmarks/dev19_cycle_check.py dev18 <history.jsonl> <dev18_fresh.jsonl> <out.jsonl>
  (DEV18 run 3's cycle: the history learned one record at a time, as dev18_evaluate.main does. The DEV19 cycle needs no
  replay: its two runs are compared directly.)
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
import dev18_evaluate as E  # noqa: E402
from asm.coding.content import ProblemContext  # noqa: E402
from asm.coding.integrity import code_hash, read_records  # noqa: E402
from asm.coding.knowledge import KnowledgeBase  # noqa: E402
from asm.coding.shapes import ShapeLibrary  # noqa: E402

K = E.K


def cycle(kb, lib, fresh, out):
    online = only_81st = 0
    with open(out, "w") as f:
        f.write(json.dumps({"code": code_hash(), "K": K, "start": time.time()}) + "\n")
        for p in sorted(fresh, key=lambda r: (r["date"], r["id"])):
            ctx = ProblemContext.from_dict(p["context"])
            target = E.norm(p["after"])
            progs = E.p17_programs(kb, p["before"], K)
            n_p17 = len(progs)
            progs += [x for x, _ in E.s18_programs(lib, p["before"], ctx, max(0, K - len(progs)))]
            hit = E.first_hit(progs, target)
            extra = None
            if hit is None and n_p17 >= K:  # what the defect added: S18's first candidate
                first = [x for x, _ in E.s18_programs(lib, p["before"], ctx, 1)]
                extra = bool(first) and E.norm(first[0]) == target
            online += hit is not None
            only_81st += bool(extra)
            f.write(json.dumps({"id": p["id"], "p17": n_p17, "total": len(progs), "hit": hit, "only_81st": extra,
                                "t": round(time.time())}) + "\n")
            f.flush()
            ex = [(p["before"], p["after"], p["id"])]
            kb.learn(ex, f"revealed:{p['repo']}")
            lib.learn(ex, f"revealed:{p['repo']}")
        res = {"online_within_80": online, "only_81st": only_81st, "online_with_defect": online + only_81st}
        f.write(json.dumps(res) + "\n")
    print(json.dumps(res), flush=True)


def main():
    mode = sys.argv[1]
    kb, lib = KnowledgeBase(), ShapeLibrary()
    if mode == "dev18":
        hist, f18, out = sys.argv[2:5]
        for r in read_records(Path(hist))[1]:  # exactly as dev18_evaluate.main
            ex = [(r["before"], r["after"], r["id"])]
            kb.learn(ex, f"history:{r['repo']}")
            lib.learn(ex, f"history:{r['repo']}")
        print(json.dumps({"learned": kb.summary(), "shapes": lib.summary()}), flush=True)
        cycle(kb, lib, read_records(Path(f18))[1], out)
    else:
        raise SystemExit("only dev18 is needed: the DEV19 cycle is checked by comparing its two runs")


if __name__ == "__main__":
    main()
