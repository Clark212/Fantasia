"""DEV18 EXPLORATORY self-check (not pre-registered): is a negative result due to a bug in ASM, or to what ASM knows?

For every fix (fresh, BugsInPy, and the 91 history fixes), the fix's OWN shape is learned from the fix alone, and three
questions are asked, each isolating one part of the system:

  A  apply correctness   With the fix's own content handed over (oracle values for the content holes), and no
                         budget caps, does applying the fix's own shape to the BEFORE function reproduce the AFTER
                         function?  A failure here, for a fix whose edit was extracted and abstracted, is a candidate
                         ASM bug and is read by a person.
  B  content coverage    Using the real content operators on the problem's own context (and the vocabulary learned
                         from the 91 history fixes, never the fix's own string edit), is each content value of the fix
                         among the fillers offered at the fix location? Which operator offers it?
     own-shape within K  If ASM had learned exactly this shape (and nothing else), would the real candidate generator,
                         with the pre-registered caps and K = 80, reproduce the fix?
  C  shape transfer      Does any shape learned from the 91 history fixes reproduce the fix when given oracle content
                         (no caps)? This is the fraction of fixes whose SHAPE is known.
  D  S18 ceiling         The real S18 (history shapes, the pre-registered content operators and their own filler lists)
                         with the BUDGET caps lifted (per match, per shape, K): is the fix produced at all, and at
                         which position? The gap to S18 within K is what ranking and budget cost.

Nothing here changes the pre-registered evaluation; it only explains it. Results are labelled exploratory.
The history library is learned exactly as dev18_evaluate.py learns it (all 91 fixes, in file order).
Usage: python benchmarks/dev18_selfcheck.py <history.jsonl> <fresh.jsonl> <bugsinpy_work_dir> <out.jsonl> [--parts=ABC]
"""
import ast
import json
import signal
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
import asm.coding.shapes as SH  # noqa: E402
from asm.coding import content as C  # noqa: E402
from asm.coding.induction import Procedure, extract_edits, is_var  # noqa: E402
from asm.coding.integrity import ChainedWriter, code_hash, file_sha256, read_records  # noqa: E402

K = 80
BUDGET_S = 240


class Timeout(Exception):
    pass


def _alarm(signum, frame):
    raise Timeout()


def norm(s):
    try:
        return ast.unparse(ast.parse(s))
    except (SyntaxError, ValueError):
        return None


def hole_values(conc, abst, acc):
    """Concrete value of each content hole: walk the edit's concrete replacement and the shape's abstract one together."""
    if is_var(abst):
        if isinstance(abst[1], str):
            acc[abst[1]] = conc[1]
        return
    if abst[0] == "=":
        return
    if abst[0] == "[]":
        for c, a in zip(conc[1], abst[1]):
            hole_values(c, a, acc)
        return
    for (_, v1), (_, v2) in zip(conc[1], abst[1]):
        hole_values(v1, v2, acc)


def own_shapes(before, after):
    """[(Shape, {cid: value})] for the fix's own edits (one per context level), plus a status string."""
    edits = extract_edits(before, after)
    if not edits:
        return [], "no_single_region"
    out, why = [], []
    for e in edits:
        if e.kind == "string":
            continue
        ab = SH._abstract(e)
        if ab is None:
            why.append("abstract_none")
            continue
        sh = SH.Shape(e.kind, ab[0], ab[1], ab[2], e.level, ab[3])
        hv = {}
        hole_values(e.rhs, ab[1], hv)
        out.append((sh, hv))
    if not out:
        return [], "+".join(sorted(set(why))) or "string_only"
    return out, "ok"


def var_types_ok(sh, binding):
    for var, tname in sh.var_types.items():
        b = binding.get(var)
        if b is not None and b[0] == "=" and type(b[1]).__name__ != tname:
            return False
    return True


def apply_with(sh, before, fill):
    span = (1, before.count("\n") + 1)
    return Procedure(sh.kind, sh.lhs, sh.rhs, sh.level).apply_detailed(before, span, fill)


def check_a(shapes, before, target):
    """A: own shape + oracle content, no caps. Returns (reproduced, per-shape results)."""
    res = []
    for sh, hv in shapes:
        def fill(binding, node, tree, sh=sh, hv=hv):
            if not var_types_ok(sh, binding):
                return []
            return [(SH._subst(SH._fill_term(sh.rhs, hv), binding), {})]
        progs = [p for p, _ in apply_with(sh, before, fill)]
        res.append({"level": sh.level, "kind": sh.kind, "holes": sh.holes, "matches": len(progs),
                    "reproduced": any(norm(p) == target for p in progs)})
    return any(r["reproduced"] for r in res), res


def check_b(shapes, before, target, ctx, vocab):
    """B: for the fix location, are the hole values among the real fillers? And own shape within K with real caps."""
    lib = SH.ShapeLibrary()
    lib.vocab = vocab
    scope = C.scope_names(SH.C_strip(before))
    cover = None
    for sh, hv in shapes:
        if not sh.holes:
            cover = {"holes": {}, "covered": True}
            break
        found = {}

        def fill(binding, node, tree, sh=sh, hv=hv):
            if not var_types_ok(sh, binding):
                return []
            offered = {cid: lib._fillers(t, binding, ctx, scope) for cid, t in sorted(sh.holes.items())}
            return [(SH._subst(SH._fill_term(sh.rhs, hv), binding), {"offered": offered})]
        for p, info in apply_with(sh, before, fill):
            if norm(p) == target:
                for cid, t in sorted(sh.holes.items()):
                    vals = [v for v, _ in info["offered"][cid]]
                    i = vals.index(hv[cid]) if hv[cid] in vals else None
                    found[cid] = {"type": t, "value": repr(hv[cid])[:80], "offered": i is not None,
                                  "rank": i, "op": info["offered"][cid][i][1] if i is not None else None,
                                  "n_offered": len(vals)}
                break
        if found:
            c = {"holes": found, "covered": all(f["offered"] for f in found.values()), "level": sh.level}
            if cover is None or (c["covered"] and not cover["covered"]):
                cover = c
    own = SH.ShapeLibrary()
    own.vocab = vocab
    for sh, _ in shapes:
        own.shapes[sh.id] = sh
        sh.status = "active"
    progs = [p for p, _ in own.candidates_for(before, "m.py", (1, before.count("\n") + 1), ctx, limit=K,
                                              as_candidates=False)]
    pos = next((i for i, p in enumerate(progs) if norm(p) == target), None)
    return cover, pos


def check_c(library, shapes, before, target):
    """C: any history shape + oracle content of this fix (by hole type), no caps."""
    by_type: dict = {}
    for sh, hv in shapes:
        for cid, t in sh.holes.items():
            by_type.setdefault(t, [])
            if hv[cid] not in by_type[t]:
                by_type[t].append(hv[cid])
    import itertools
    hits = []
    for lsh in library.shapes.values():
        opts = [[(cid, v) for v in by_type.get(t, [])] for cid, t in sorted(lsh.holes.items())]
        if any(not o for o in opts):
            continue

        def fill(binding, node, tree, lsh=lsh, opts=opts):
            if not var_types_ok(lsh, binding):
                return []
            return [(SH._subst(SH._fill_term(lsh.rhs, dict(combo)), binding), {}) for combo in itertools.product(*opts)]
        if any(norm(p) == target for p, _ in apply_with(lsh, before, fill)):
            hits.append({"shape": lsh.id, "support": len(set(lsh.support)), "status": lsh.status,
                         "describe": lsh.describe()[:120]})
    return hits


def check_d(library, before, target, ctx):
    saved = SH.PER_MATCH, SH.PER_SHAPE
    SH.PER_MATCH = SH.PER_SHAPE = 10 ** 9
    try:
        out = library.candidates_for(before, "m.py", (1, before.count("\n") + 1), ctx, limit=10 ** 9, as_candidates=False)
    finally:
        SH.PER_MATCH, SH.PER_SHAPE = saved
    pos = next((i for i, (p, _) in enumerate(out) if norm(p) == target), None)
    return pos, len(out), (out[pos][1]["ops"] if pos is not None else None)


def main():
    hist_path, fresh_path, work, out = sys.argv[1:5]
    parts = next((a.split("=", 1)[1] for a in sys.argv[5:] if a.startswith("--parts=")), "ABC")
    library = SH.ShapeLibrary()
    for r in read_records(Path(hist_path))[1]:
        library.learn([(r["before"], r["after"], r["id"])], f"history:{r['repo']}")
    w = ChainedWriter(Path(out), {"run": "dev18_selfcheck (exploratory)", "asm_coding_sha256": code_hash(),
                                  "history_sha256": file_sha256(hist_path), "fresh_sha256": file_sha256(fresh_path),
                                  "library": library.summary(), "parts": parts, "K": K, "budget_s": BUDGET_S})
    import dev18_evaluate as E
    sets = [("history", [dict(r, context={}) for r in read_records(Path(hist_path))[1]]),
            ("fresh", read_records(Path(fresh_path))[1]),
            ("bugsinpy", E.bugsinpy_problems(Path(work)))]
    signal.signal(signal.SIGALRM, _alarm)
    for name, problems in sets:
        for p in problems:
            t0 = time.time()
            before, after = p["before"], p["after"]
            target = norm(after)
            row = {"set": name, "id": p["id"], "lines": before.count("\n") + 1}
            shapes, status = own_shapes(before, after)
            row["status"] = status
            row["own_shapes"] = [{"level": s.level, "kind": s.kind, "holes": s.holes, "values": {k: repr(v)[:80] for k, v in hv.items()},
                                  "describe": s.describe()[:120]} for s, hv in shapes]
            if "D" in parts and name != "history" and status != "no_single_region":
                signal.alarm(BUDGET_S)
                try:
                    row["D_position"], row["D_candidates"], row["D_ops"] = check_d(library, before, target,
                                                                                   C.ProblemContext.from_dict(p["context"]))
                except Timeout:
                    row["D_timeout"] = True
                finally:
                    signal.alarm(0)
            if shapes and parts.strip("D"):
                signal.alarm(BUDGET_S)
                try:
                    if "A" in parts:
                        row["A"], row["A_detail"] = check_a(shapes, before, target)
                    if "B" in parts and name != "history":
                        ctx = C.ProblemContext.from_dict(p["context"])
                        row["B_cover"], row["B_own_within_k"] = check_b(shapes, before, target, ctx, library.vocab)
                    if "C" in parts and name != "history":
                        row["C_hits"] = check_c(library, shapes, before, target)
                except Timeout:
                    row["timeout"] = True
                finally:
                    signal.alarm(0)
            row["seconds"] = round(time.time() - t0, 2)
            w.append(row)
            print(json.dumps({k: row.get(k) for k in ("set", "id", "status", "A", "B_own_within_k", "D_position", "seconds")}), flush=True)
    print(json.dumps({"head": w.head}))


if __name__ == "__main__":
    main()
