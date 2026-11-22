"""DEV20 DEVELOPMENT (exploratory; development data only, all of it already inspected): what each limit of the DEV20
step design costs. Leave-one-project-out over the 1,254 DEV17-DEV19 fixes: a fix is step-covered when every one of its
steps also occurs in a fix of another project (as `dev20_dev_coverage.py`). Each fix is put in one composition class;
for the covered ones, a pair also records whether the two steps were learned together in >= 2 fixes of other projects
(a pair candidate needs that).
Usage: python benchmarks/dev20_dev_limits.py
"""
import ast
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import asm.coding.steps as ST  # noqa: E402
from asm.coding.induction import match, term_to_json, to_term  # noqa: E402
from asm.coding.integrity import read_records  # noqa: E402

R = ROOT / "benchmarks" / "results"
FILES = ("dev17/history.jsonl", "dev18/fresh.jsonl", "dev19/train.jsonl", "dev19/fresh.jsonl")


def fstring(cs):
    return cs.ctx.startswith(("JoinedStr", "FormattedValue")) or cs.gctx.startswith(("JoinedStr", "FormattedValue"))


def rename_split(st):
    """Two expression steps that are one rename (same old and new name) split by the name's Load/Store context."""
    if len(st) != 2 or any(cs.kind != "expr" for cs in st):
        return False
    if not all(cs.lhs[0] == "Name" and cs.rhs[0] == "Name" for cs in st):
        return False
    a, b = st
    g = lambda t, f: dict(t[1])[f]  # noqa: E731
    return g(a.lhs, "id") == g(b.lhs, "id") and g(a.rhs, "id") == g(b.rhs, "id")


def partial(before, cs, ab):
    """A multi-site step whose fix changed fewer places than the step's match-group has (a multi-site candidate
    rewrites every place of the group)."""
    tree = ast.parse(before)
    groups = collections.Counter()
    for n, _, _ in ST._sites(tree, (1, before.count("\n") + 1)):
        b: dict = {}
        if match(ab[0], to_term(n), b):
            groups[json.dumps(term_to_json(tuple(sorted(b.items()))), default=repr)] += 1
    return bool(groups) and max(groups.values()) > cs.sites


def main():
    recs = [r for f in FILES for r in read_records(R / f)[1]]
    rows = []
    for r in recs:
        st = ST.extract_steps(r["before"], r["after"])
        ab = [ST.abstract_step(cs) for cs in st]
        ids = [None if a is None else ST.Step(cs.kind, *a).id for cs, a in zip(st, ab)]
        rows.append((r, st, ab, ids))
    projects = collections.defaultdict(set)  # step id -> projects it occurs in
    pair_fixes = collections.defaultdict(list)  # pair key -> [project of each fix that has both steps]
    for r, st, ab, ids in rows:
        for i in ids:
            if i:
                projects[i].add(r["repo"])
        here = [i for i in ids if i]
        keys = {"|".join(sorted((here[a], here[b]))) for a in range(len(here)) for b in range(a + 1, len(here))}
        for k in keys:
            pair_fixes[k].append(r["repo"])
    every, covered, examples = collections.Counter(), collections.Counter(), collections.defaultdict(list)
    for r, st, ab, ids in rows:
        n = len(st)
        if n == 0:
            c = "no steps"
        elif None in ids:
            c = "a step with > 2 new values"
        elif n == 1:
            cs = st[0]
            if cs.sites == 1:
                c = "single"
            elif cs.kind == "stmts":
                c = "multi: statement step"
            else:
                c = "multi: expression step" + (" (partial: the fix changed only some matching places)"
                                                if partial(r["before"], cs, ab[0]) else "")
        elif n == 2:
            if rename_split(st):
                c = "pair: one rename split by Load/Store"
            elif any(cs.kind == "stmts" for cs in st):
                c = "pair: with a statement step"
            elif any(cs.sites > 1 for cs in st):
                c = "pair: with a multi-site element"
            else:
                c = "pair: two single expression steps"
        else:
            c = f"{min(n, 5)}{'+' if n >= 5 else ''} steps"
        if n and None not in ids and any(fstring(cs) for cs in st):
            c += " [f-string]"
        every[c] += 1
        if ids and None not in ids and all(projects[i] - {r["repo"]} for i in ids):
            if n == 2:
                other = sum(1 for repo in pair_fixes.get("|".join(sorted(ids)), []) if repo != r["repo"])
                c += " | learned together in >= 2 fixes of other projects" if other >= 2 else \
                    " | NOT learned together in 2 fixes of other projects"
            covered[c] += 1
            examples[c].append(r["id"])
    print(f"ALL {len(rows)} FIXES by composition:")
    for k, v in sorted(every.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"{v:5d}  {k}")
    print(f"\nSTEP-COVERED (every step also occurs in another project): {sum(covered.values())}")
    for k, v in sorted(covered.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"{v:5d}  {k}   e.g. {examples[k][:3]}")


if __name__ == "__main__":
    main()
