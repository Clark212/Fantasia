"""DEV18 EXPLORATORY (not pre-registered): why the content operators missed. For every fix whose own shape exists, the
content value of each hole is looked up in what the operators can see at the fix location (scope, module names,
builtins, module attributes, test literals, module strings) and each miss is classified. A miss marked "(check)" would be
a candidate bug and is printed for a person to read.
Usage: python benchmarks/dev18_selfcheck_misses.py <history.jsonl> <fresh.jsonl> <bugsinpy_work_dir>
"""
import collections
import difflib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
import asm.coding.shapes as SH
from asm.coding import content as C
from asm.coding.integrity import read_records
import dev18_selfcheck as X
import dev18_evaluate as E
HIST, FRESH, WORK = sys.argv[1:4]
lib = SH.ShapeLibrary()
for r in read_records(HIST)[1]:
    lib.learn([(r["before"], r["after"], r["id"])], "h")
fresh = read_records(FRESH)[1]
bugs = E.bugsinpy_problems(Path(WORK))
for name, probs in (("fresh", fresh), ("bugsinpy", bugs)):
    why = collections.Counter()
    examples = collections.defaultdict(list)
    for p in probs:
        shapes, status = X.own_shapes(p["before"], p["after"])
        if not shapes:
            continue
        before, target = p["before"], X.norm(p["after"])
        ctx = C.ProblemContext.from_dict(p["context"])
        scope = C.scope_names(SH.C_strip(before))
        best = None
        for sh, hv in shapes:
            if not sh.holes:
                best = "covered"
                break
            got = {}
            def fill(binding, node, tree, sh=sh, hv=hv):
                if not X.var_types_ok(sh, binding):
                    return []
                return [(SH._subst(SH._fill_term(sh.rhs, hv), binding), {"b": binding})]
            for prog, info in X.apply_with(sh, before, fill):
                if X.norm(prog) == target:
                    got = info["b"]
                    break
            if not got and best is None:
                best = "location not found"
                continue
            res = []
            for cid, t in sorted(sh.holes.items()):
                v = hv[cid]
                offered = [x for x, _ in lib._fillers(t, got, ctx, scope)]
                if v in offered:
                    res.append(None)
                    continue
                olds = [b[1] for b in got.values() if b[0] == "=" and isinstance(b[1], str)]
                if t == "str":
                    old = olds[0] if olds else ""
                    full = {x for o in (olds or [""]) for x, _ in C.string_fillers(o, ctx, lib.vocab, limit=10 ** 6)}
                    in_test = v in ctx.test_strings
                    ext = bool(old) and old in v and any(v in s for s in ctx.test_strings)  # EXTEND can only grow `old`
                    ratio = difflib.SequenceMatcher(None, old, v, autojunk=False).ratio()
                    if v in full:
                        k = "str: produced by the operators but cut by the 12-value filler list"
                    elif in_test and ratio >= C.SIMILARITY:
                        k = "str: in test literals and similar, NOT offered (check)"
                    elif in_test:
                        k = "str: in test literals but dissimilar to old (similarity < 0.6)"
                    elif ext:
                        k = "str: inside a test literal (extend) but not offered (check)"
                    elif v in ctx.module_strings:
                        k = "str: in module strings, dissimilar or cut"
                    elif not ctx.test_strings:
                        k = "str: no test literals in context"
                    else:
                        k = "str: not in the problem's context"
                elif t == "name":
                    if v in scope:
                        k = "name: in scope but cut by the top-10 limit"
                    elif v in ctx.module_names:
                        k = "name: module-level, cut by the top-10 limit"
                    elif v in C.COMMON_BUILTINS:
                        k = "name: common builtin, cut by the top-10 limit"
                    else:
                        k = "name: not in scope, module names or common builtins"
                elif t == "attr":
                    k = "attr: in module attributes but cut by the top-10 limit" if v in ctx.attributes else "attr: not in module attributes or test identifiers"
                elif t == "num":
                    k = "num: not old+-1, a test number or 0/1/-1/2"
                else:
                    k = f"{t}: other"
                res.append(k)
                examples[k].append((p["id"], repr(v)[:50]))
            if all(x is None for x in res):
                best = "covered"
                break
            if best is None or best == "location not found":
                best = tuple(x for x in res if x)
        if best == "covered":
            why["covered"] += 1
        elif isinstance(best, tuple):
            for k in set(best):
                why[k] += 1
        else:
            why[best] += 1
    print(f"== {name}")
    for k, v in why.most_common():
        print(f"  {v:4d}  {k}")
    for k in examples:
        if "check" in k:
            print("  CHECK", k, examples[k][:10])
