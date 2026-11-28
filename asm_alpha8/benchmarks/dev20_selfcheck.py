"""DEV20 EXPLORATORY self-check (development data; before the pre-registered run): is applying steps correct?

For every fix of 1 or 2 steps (each with at most 2 new values), a library is learned from that fix ALONE, every step and
pair is made usable, and each hole is filled with the fix's OWN value (an oracle in place of the content operators).
Applying the steps to the BEFORE function must then reproduce the AFTER function. A failure is a candidate bug in
extraction, matching, multi-site grouping, pairing or splicing, and is printed for a person to read.
Usage: python benchmarks/dev20_selfcheck.py <out.jsonl> <records.jsonl> ...
"""
import ast
import collections
import json
import signal
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
import asm.coding.steps as ST  # noqa: E402
import dev18_selfcheck as SC  # noqa: E402
from asm.coding.content import ProblemContext  # noqa: E402
from asm.coding.integrity import read_records  # noqa: E402

BUDGET_S = 120


def code_only(src):
    """The program without docstrings and other bare string statements: steps do not learn those (they do not change
    behaviour), so a fix that also rewrote its docstring is compared on its code."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return None
    for n in ast.walk(tree):
        for fld in ("body", "orelse", "finalbody"):
            body = getattr(n, fld, None)
            if isinstance(body, list):
                kept = [x for x in body if not (isinstance(x, ast.Expr) and isinstance(x.value, ast.Constant)
                                                 and isinstance(x.value.value, str))]
                setattr(n, fld, kept or [ast.Pass()])
    return ast.unparse(tree)


def main():
    out = open(sys.argv[1], "w")
    recs = [r for f in sys.argv[2:] for r in read_records(Path(f))[1]]
    signal.signal(signal.SIGALRM, SC._alarm)
    tally = collections.Counter()
    for r in recs:
        before, after = r["before"], r["after"]
        steps = ST.extract_steps(before, after)
        abst = [ST.abstract_step(cs) for cs in steps]
        if not steps:
            tally["no steps"] += 1
            continue
        if None in abst:
            tally["a step with > 2 new values"] += 1
            continue
        if len(steps) > 2:
            tally["3+ steps (not composed)"] += 1
            continue
        lib = ST.StepLibrary()
        lib.learn([(before, after, r["id"])], "self")
        for s in lib.steps.values():
            s.status = "active"
        for k in lib.pairs:
            lib.pairs[k] = lib.pairs[k] * ST.PAIR_MIN_SUPPORT
        oracle = collections.defaultdict(list)  # step id -> the fix's own hole values (one dict per place)
        for cs, ab in zip(steps, abst):
            hv: dict = {}
            SC.hole_values(cs.rhs, ab[1], hv)
            sid = ST.Step(cs.kind, *ab).id
            if hv not in oracle[sid]:
                oracle[sid].append(hv)

        def fillings(st, binding, ctx, scope, oracle=oracle):
            for var, tname in st.var_types.items():
                b = binding.get(var)
                if b is not None and b[0] == "=" and type(b[1]).__name__ != tname:
                    return []
            return [(hv, ["oracle"], j) for j, hv in enumerate(oracle.get(st.id, [{}]))]
        lib._fillings = fillings
        kind = "single" if len(steps) == 1 and steps[0].sites == 1 else ("multi" if len(steps) == 1 else "pair")
        row = {"id": r["id"], "kind": kind, "sites": [cs.sites for cs in steps]}
        signal.alarm(BUDGET_S)
        try:
            cands = lib.candidates_for(before, "m.py", (1, before.count("\n") + 1), ProblemContext(), limit=10 ** 6,
                                       as_candidates=False, quota={"single": 1, "multi": 1, "pair": 1})
            target, target_code = SC.norm(after), code_only(after)
            hit = next((i for i, (c, _) in enumerate(cands) if SC.norm(c) == target), None)
            code_hit = next((i for i, (c, _) in enumerate(cands) if code_only(c) == target_code), None)
            row.update(reproduced=hit is not None, position=hit, code_reproduced=code_hit is not None,
                       candidates=len(cands))
        except SC.Timeout:
            row["timeout"] = True
        finally:
            signal.alarm(0)
        verdict = ("timeout" if row.get("timeout") else "reproduced" if row.get("reproduced") else
                   "reproduced apart from a docstring change" if row.get("code_reproduced") else "NOT reproduced")
        tally[f"{kind}: {verdict}"] += 1
        out.write(json.dumps(row) + "\n")
        out.flush()
        if verdict == "NOT reproduced":
            print("NOT reproduced:", r["id"], kind, row["sites"], flush=True)
    out.write(json.dumps({"tally": dict(tally)}) + "\n")
    print(json.dumps(dict(sorted(tally.items())), indent=1))


if __name__ == "__main__":
    main()
