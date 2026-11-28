"""DEV20 DEVELOPMENT (exploratory; development data only): leave-one-project-out coverage of the 1,254 DEV17-DEV19
fixes by learned steps (asm.coding.steps) and by whole-fix shapes (asm.coding.shapes).
Usage: python benchmarks/dev20_dev_coverage.py
"""
import collections, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import asm.coding.shapes as SH
from asm.coding.induction import extract_edits, term_key
from asm.coding.integrity import read_records
from asm.coding.steps import Step, abstract_step, extract_steps
R = Path(__file__).resolve().parents[1] / "benchmarks" / "results"
recs = []
for f in ("dev17/history.jsonl", "dev18/fresh.jsonl", "dev19/train.jsonl", "dev19/fresh.jsonl"):
    recs += read_records(R / f)[1]
rows = []
for r in recs:
    st = extract_steps(r["before"], r["after"])
    ids = []
    for cs in st:
        ab = abstract_step(cs)
        ids.append(None if ab is None else Step(cs.kind, *ab).id)
    shapes = []
    for e in extract_edits(r["before"], r["after"]):
        if e.kind != "string":
            ab = SH._abstract(e)
            if ab is not None:
                shapes.append(SH.Shape(e.kind, ab[0], ab[1], ab[2], e.level, ab[3]).id)
    rows.append((r, ids, shapes, st))
sp, hp = collections.defaultdict(set), collections.defaultdict(set)
for r, ids, shapes, st in rows:
    for i in ids:
        if i: sp[i].add(r["repo"])
    for s in shapes: hp[s].add(r["repo"])
def cov_steps(r, ids): return bool(ids) and None not in ids and all(sp[i] - {r["repo"]} for i in ids)
def cov_shape(r, shapes): return any(hp[s] - {r["repo"]} for s in shapes)
multi_diff = [(r, ids, shapes) for r, ids, shapes, st in rows if len(st) >= 2]
multi_site = [(r, ids, shapes) for r, ids, shapes, st in rows if len(st) == 1 and st[0].sites >= 2]
print(json.dumps({"fixes": len(rows), "projects": len({r["repo"] for r, *_ in rows}),
  "steps_covered": sum(cov_steps(r, i) for r, i, s, _ in rows), "shapes_covered": sum(cov_shape(r, s) for r, i, s, _ in rows),
  "several_different_changes": len(multi_diff), "different_changes_steps_covered": sum(cov_steps(r, i) for r, i, s in multi_diff),
  "different_changes_shapes_covered": sum(cov_shape(r, s) for r, i, s in multi_diff),
  "same_change_at_several_places": len(multi_site), "same_change_steps_covered": sum(cov_steps(r, i) for r, i, s in multi_site),
  "of_these_shapes_covered_multisite": sum(cov_shape(r, s) for r, i, s in multi_site),
  "no_steps": sum(1 for r, i, s, st in rows if not st), "a_step_over_2_values": sum(1 for r, i, s, st in rows if None in i)}, indent=1))
