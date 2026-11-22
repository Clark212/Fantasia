"""DEV20: why S20 misses fixes (descriptive). Run on development data while developing DEV20, and on the fresh set as
the pre-registered descriptive analysis Q3 (benchmarks/preregistration/dev20_study.md).
The step library is learned from the knowledge files in order, in per-project batches. Every test fix is put in one class:
  - no steps / a step with > 2 new values / a step never learned / a composition DEV20 does not build;
  - ELIGIBLE: every step learned (active, or seen once) and a composition DEV20 builds (single; multi-site expression
    step; a pair of single expression steps learned together in >= 2 fixes).
For each eligible fix: reproduced within K = 80; else found with an unlimited budget (ranked beyond 80); else, for a
single expression step, whether each hole's own value (the developer's) is among the values the content operators offer
at that place (DEV18's operators, unchanged).
Usage: python benchmarks/dev20_gap.py <out.jsonl> <test.jsonl> <knowledge.jsonl> ...
"""
import ast
import collections
import json
import multiprocessing
import signal
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
import asm.coding.content as C  # noqa: E402
import asm.coding.shapes as SH  # noqa: E402
import asm.coding.steps as ST  # noqa: E402
import dev18_selfcheck as SC  # noqa: E402
from asm.coding.content import ProblemContext  # noqa: E402
from asm.coding.induction import match, to_term  # noqa: E402
from asm.coding.integrity import read_records  # noqa: E402

K = 80
BUDGET_S = 90
_G: dict = {}


class Timeout(BaseException):
    """A BaseException, so that ASM's own `except Exception` handlers (a text build that fails, a filled value that does
    not make a valid tree) cannot swallow it. dev18_selfcheck's Timeout is an Exception: an alarm that fired inside such a
    handler was swallowed, and the run went on without a limit (no result changed; it only took longer)."""


def _alarm(signum, frame):
    raise Timeout()


def tv(v):
    return type(v).__name__, v


def classify(lib, r):
    st = ST.extract_steps(r["before"], r["after"])
    ab = [ST.abstract_step(cs) for cs in st]
    ids = [None if a is None else ST.Step(cs.kind, *a).id for cs, a in zip(st, ab)]
    if not st:
        return "no steps", st, ab, ids
    if None in ids:
        return "a step with > 2 new values", st, ab, ids
    if not all(i in lib.steps for i in ids):
        return "a step never learned", st, ab, ids
    if len(st) == 1:
        if st[0].sites == 1:
            return "ELIGIBLE single", st, ab, ids
        return ("ELIGIBLE multi-site", st, ab, ids) if st[0].kind == "expr" else ("a statement step at several places", st, ab, ids)
    if len(st) == 2:
        if any(cs.kind == "stmts" for cs in st):
            return "a pair with a statement step", st, ab, ids
        if any(cs.sites > 1 for cs in st):
            return "a pair with a multi-site element", st, ab, ids
        if len(lib.pairs.get("|".join(sorted(ids)), [])) >= ST.PAIR_MIN_SUPPORT:
            return "ELIGIBLE pair", st, ab, ids
        return "a pair not learned together in 2 fixes", st, ab, ids
    return "3+ steps", st, ab, ids


def analyse(r):
    lib = _G["lib"]
    cls, st, ab, ids = classify(lib, r)
    row = {"id": r["id"], "class": cls}
    if not cls.startswith("ELIGIBLE"):
        return row
    row["status"] = "active" if all(lib.steps[i].status == "active" for i in ids) else "seen once"
    before = r["before"]
    span, ctx, target = (1, before.count("\n") + 1), ProblemContext.from_dict(r.get("context", {})), SC.norm(r["after"])
    signal.signal(signal.SIGALRM, _alarm)
    signal.alarm(BUDGET_S)
    try:
        got = lib.candidates_for(before, "m.py", span, ctx, limit=K, as_candidates=False)
        row["within_k"] = next((i for i, (c, _) in enumerate(got) if SC.norm(c) == target), None)
        if row["within_k"] is None:
            got = lib.candidates_for(before, "m.py", span, ctx, limit=10 ** 6, as_candidates=False)
            row["unlimited"] = next((i for i, (c, _) in enumerate(got) if SC.norm(c) == target), None)
            row["unlimited_candidates"] = len(got)
    except Timeout:
        row["timeout"] = True
    finally:
        signal.alarm(0)
    if cls == "ELIGIBLE single" and st[0].kind == "expr":
        cs, step = st[0], lib.steps[ids[0]]
        sites = ST._sites(ast.parse(before), span)
        at = [n for n, _, _ in sites if to_term(n) == cs.lhs]
        own: dict = {}
        SC.hole_values(cs.rhs, ab[0][1], own)
        if not at:
            row["content"] = "the place is not a site (inside an f-string or a bare string)"
        else:
            binding: dict = {}
            match(step.lhs, to_term(at[0]), binding)
            scope = C.scope_names(SH.C_strip(before))
            missing = []
            for cid, htype in sorted(step.holes.items()):
                offered = [tv(v) for v, _ in SH.ShapeLibrary._fillers(lib, htype, binding, ctx, scope)]
                if tv(own.get(cid)) not in offered:
                    missing.append({"type": htype, "value": repr(own.get(cid))[:80]})
            row["holes"] = dict(step.holes)
            row["content"] = "every value offered" if not missing else "a value not offered"
            row["missing"] = missing
    return row


def verdict(x):
    if x.get("within_k") is not None:
        return "reproduced within 80"
    if x.get("timeout"):
        return f"timeout ({BUDGET_S} s)"
    if x.get("unlimited") is not None:
        return "produced, ranked beyond 80"
    if "content" in x:
        return "not produced: " + x["content"]
    return "not produced (multi-site / pair: content not checked)"


def main():
    out, test, know = Path(sys.argv[1]), Path(sys.argv[2]), [Path(a) for a in sys.argv[3:]]
    lib = ST.StepLibrary()
    for f in know:
        by = collections.defaultdict(list)
        for r in read_records(f)[1]:
            by[r["repo"]].append((r["before"], r["after"], r["id"]))
        for repo, ex in by.items():  # per-project batches
            lib.learn(ex, repo)
    _G["lib"] = lib
    recs = read_records(test)[1]
    with multiprocessing.get_context("fork").Pool(4) as pool:
        rows = list(pool.imap(analyse, recs, chunksize=1))
    summary = {"test": f"{test.parent.name}/{test.name}", "knowledge": [f"{p.parent.name}/{p.name}" for p in know],
               "test_fixes": len(rows), "library": lib.summary(),
               "classes": dict(collections.Counter(x["class"] for x in rows).most_common()),
               "eligible_by_outcome": {" | ".join(k): v for k, v in collections.Counter(
                   (x["status"], x["class"][9:], verdict(x)) for x in rows if x["class"].startswith("ELIGIBLE")).most_common()},
               "holes_not_offered_by_type": dict(collections.Counter(m["type"] for x in rows for m in x.get("missing", []))),
               "unlimited_positions_beyond_80": sorted(x["unlimited"] for x in rows if x.get("unlimited") is not None)}
    with open(out, "w") as fh:
        for x in rows:
            fh.write(json.dumps(x) + "\n")
        fh.write(json.dumps({"summary": summary}) + "\n")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
