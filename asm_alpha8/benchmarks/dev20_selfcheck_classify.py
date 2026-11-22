"""DEV20 DEVELOPMENT (exploratory; development data only): classify the self-check failures (`dev20_selfcheck.py`
output) into the design's stated limits, or UNEXPLAINED (a candidate bug, for a person to read).
For each fix the self-check did not reproduce (with each hole filled by the fix's own value), in this order:
  - a step inside an f-string (`_sites` leaves f-string interiors out: their positions are not reliable);
  - a pair with a statement step (pairs join expression steps only);
  - a multi-site step whose fix changed only some of the places with the same match (multi-site rewrites them all);
  - a pair with a multi-site element (a pair joins two single places);
  - a statement step at several places (multi-site applies to expression steps);
  - a whole `else`/`elif`/`finally` block deleted (DEV17's statement splice cannot remove its header line);
  - reproduced once the per-step caps are lifted (BUDGET_S per fix), or timed out doing so;
  - otherwise UNEXPLAINED.
Usage: python benchmarks/dev20_selfcheck_classify.py <selfcheck.jsonl> > classification.txt
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
import asm.coding.steps as ST  # noqa: E402
import dev18_selfcheck as SC  # noqa: E402
import dev20_selfcheck as D  # noqa: E402
from asm.coding.content import ProblemContext  # noqa: E402
from asm.coding.induction import match, term_to_json, to_term  # noqa: E402
from asm.coding.integrity import read_records  # noqa: E402

R = ROOT / "benchmarks" / "results"
BUDGET_S = 300
_G: dict = {}
FILES = ("dev17/history.jsonl", "dev18/fresh.jsonl", "dev19/train.jsonl", "dev19/fresh.jsonl")
OPTIONAL_BLOCKS = ("If.orelse", "For.orelse", "AsyncFor.orelse", "While.orelse", "Try.orelse", "Try.finalbody",
                   "TryStar.orelse", "TryStar.finalbody")


class Timeout(BaseException):
    """A BaseException, so that ASM's own `except Exception` handlers (a text build that fails, a filled value that does
    not make a valid tree) cannot swallow it. dev18_selfcheck's Timeout is an Exception: an alarm that fired inside such a
    handler was swallowed, and the run went on without a limit (no result changed; it only took longer)."""


def _alarm(signum, frame):
    raise Timeout()


def oracle_lib(before, after):
    """As the self-check: a library from this fix alone, every step and pair usable, holes filled with its own values."""
    steps = ST.extract_steps(before, after)
    abst = [ST.abstract_step(cs) for cs in steps]
    lib = ST.StepLibrary()
    lib.learn([(before, after, "x")], "self")
    for s in lib.steps.values():
        s.status = "active"
    for k in lib.pairs:
        lib.pairs[k] = lib.pairs[k] * ST.PAIR_MIN_SUPPORT
    oracle = collections.defaultdict(list)
    for cs, ab in zip(steps, abst):
        hv: dict = {}
        SC.hole_values(cs.rhs, ab[1], hv)
        sid = ST.Step(cs.kind, *ab).id
        if hv not in oracle[sid]:
            oracle[sid].append(hv)

    def fillings(st, binding, ctx, scope):
        for var, tname in st.var_types.items():
            b = binding.get(var)
            if b is not None and b[0] == "=" and type(b[1]).__name__ != tname:
                return []
        return [(hv, ["oracle"], j) for j, hv in enumerate(oracle.get(st.id, [{}]))]
    lib._fillings = fillings
    return steps, abst, lib


def partial(before, cs, ab):
    tree = ast.parse(before)
    groups = collections.Counter()
    for n, _, _ in ST._sites(tree, (1, before.count("\n") + 1)):
        b: dict = {}
        if match(ab[0], to_term(n), b):
            groups[json.dumps(term_to_json(tuple(sorted(b.items()))), default=repr)] += 1
    return bool(groups) and max(groups.values()) > cs.sites


def classify(f, r):
    before, after = r["before"], r["after"]
    steps, abst, lib = oracle_lib(before, after)
    kind = f["kind"]
    if any(cs.ctx.startswith(("JoinedStr", "FormattedValue")) or cs.gctx.startswith(("JoinedStr", "FormattedValue"))
           for cs in steps):
        return f"{kind}: inside an f-string"
    if kind == "pair" and any(cs.kind == "stmts" for cs in steps):
        return "pair: involves a statement step (pairs join expression steps only)"
    if kind == "multi" and steps[0].kind == "expr" and partial(before, steps[0], abst[0]):
        return "multi: the fix changed only some of the places with the same match"
    if kind == "pair" and any(cs.sites > 1 for cs in steps):
        return "pair: an element is a multi-site step (a pair joins two single places)"
    if kind == "multi" and steps[0].kind == "stmts":
        return "multi: a statement step at several places (multi-site applies to expression steps)"
    if any(cs.kind == "stmts" and cs.ctx in OPTIONAL_BLOCKS and not cs.rhs[1] for cs in steps):
        return f"{kind}: a whole else/elif/finally block deleted (the statement splice cannot remove its header)"
    saved = (ST.PER_STEP, ST.PER_MATCH, ST.PAIR_FILLINGS)
    ST.PER_STEP = ST.PER_MATCH = ST.PAIR_FILLINGS = 10 ** 6
    signal.signal(signal.SIGALRM, _alarm)
    signal.alarm(BUDGET_S)
    try:
        cands = lib.candidates_for(before, "m.py", (1, before.count("\n") + 1), ProblemContext(), limit=10 ** 6,
                                   as_candidates=False, quota={"single": 1, "multi": 1, "pair": 1})
    except Timeout:
        return f"{kind}: caps lifted, timed out (large function)"
    finally:
        signal.alarm(0)
        ST.PER_STEP, ST.PER_MATCH, ST.PAIR_FILLINGS = saved
    target = D.code_only(after)
    if any(D.code_only(c) == target for c, _ in cands):
        return f"{kind}: reproduced once the per-step caps are lifted"
    return f"{kind}: UNEXPLAINED"


def _one(f):
    return f, classify(f, _G["recs"][f["id"]])


def main():
    _G["recs"] = {r["id"]: r for f in FILES for r in read_records(R / f)[1]}
    fails = [json.loads(line) for line in open(sys.argv[1]) if '"id"' in line]
    fails = [f for f in fails if not f.get("reproduced") and not f.get("code_reproduced") and not f.get("timeout")]
    tally, unexplained = collections.Counter(), []
    with multiprocessing.get_context("fork").Pool(4) as pool:
        for f, c in pool.imap(_one, fails, chunksize=1):  # in the self-check's order
            tally[c] += 1
            print(f"{f['id']}\t{c}", flush=True)
            if c.endswith("UNEXPLAINED"):
                unexplained.append(f["id"])
    print(f"\n{len(fails)} self-check failures:")
    for k, v in sorted(tally.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"{v:4d}  {k}")
    print("UNEXPLAINED:", unexplained)


if __name__ == "__main__":
    main()
