"""DEV20 EXPLORATORY (after the pre-registered run; not pre-registered): why S20 with single steps only, and S20 without
exception holes, reproduce fixes S20 misses. For each such fix: its position in S20 and in the no-exception-hole library,
with the default shares and with single steps only, the first 80 candidates by kind, and how many of S20's single
candidates come from steps with an exception hole.
Usage: python benchmarks/dev20_explore_why.py"""
import ast, collections, json, sys
ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from pathlib import Path
import asm.coding.steps as ST
from asm.coding.content import ProblemContext
from asm.coding.integrity import read_records
R = ROOT / "benchmarks" / "results"
know = ["dev17/history.jsonl", "dev18/fresh.jsonl", "dev19/train.jsonl", "dev19/fresh.jsonl"]
steps = ST.StepLibrary.load(R / "dev20" / "steps_dev20.json")
ST.EXCEPTION_HOLES = False
noexc = ST.StepLibrary()
for f in know:
    by = collections.defaultdict(list)
    for r in read_records(R / f)[1]: by[r["repo"]].append((r["before"], r["after"], r["id"]))
    tag = Path(f).parent.name + "/" + Path(f).stem
    for repo, ex in by.items(): noexc.learn(ex, f"{tag}:{repo}")
ST.EXCEPTION_HOLES = True
def norm(s):
    try: return ast.unparse(ast.parse(s))
    except Exception: return None
fresh = {r["id"]: r for r in read_records(R / "dev20/fresh.jsonl")[1]}
ids = ["markdown@1aedcafa01ac:CodeHiliteExtension.extendMarkdown", "mistune@e17c751a1f09:DirectiveToc.__init__",
       "babel@f8cae8e2a163:ExtractMessages.finalize_options", "babel@47072d2c9639:PluralRule.__init__"]
for i in ids:
    p = fresh[i]; before = p["before"]; span = (1, before.count("\n") + 1); ctx = ProblemContext.from_dict(p["context"]); tgt = norm(p["after"])
    print("=" * 8, i)
    for name, lib in (("S20", steps), ("noexc", noexc)):
        for q, quota in (("default", None), ("single-only", {"single": 1, "multi": 0, "pair": 0})):
            c = lib.candidates_for(before, "m.py", span, ctx, limit=10 ** 6 if q == "single-only" else 80, as_candidates=False, quota=quota)
            singles = [x for x in c if x[1]["kind"] == "single"]
            pos = next((k for k, (x, _) in enumerate(c[:80] if q == "default" else c) if norm(x) == tgt), None)
            spos = next((k for k, (x, _) in enumerate(singles) if norm(x) == tgt), None)
            kinds = collections.Counter(x[1]["kind"] for x in c[:80])
            print(f"  {name:6s} {q:12s} hit within 80: {pos if (pos is not None and pos < 80) else None} | rank among singles: {spos} | first 80 by kind {dict(kinds)}")
    st = ST.extract_steps(before, p["after"])
    for cs in st:
        ab = ST.abstract_step(cs)
        sid = ST.Step(cs.kind, *ab).id if ab else None
        print("   step", cs.kind, cs.ctx, "holes", ab[2] if ab else None, "| in S20 lib:", sid in steps.steps, steps.steps[sid].status if sid in steps.steps else "")
    # which steps fill the first 50 single slots of S20 that noexc does not have?
    c = steps.candidates_for(before, "m.py", span, ctx, limit=80, as_candidates=False)
    exc_steps = collections.Counter(x[1]["step"] for x in c if x[1]["kind"] == "single" and "exc" in "".join(steps.steps[x[1]["step"]].holes.values()) ) if c else {}
    print("   S20 single candidates from steps with an exc hole:", sum(exc_steps.values()))
