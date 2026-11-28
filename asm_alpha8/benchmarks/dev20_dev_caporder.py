"""DEV20 DEVELOPMENT (exploratory; development data only, all of it already inspected): which candidates the per-step
cap (`steps.PER_STEP` single-site candidates per step) keeps. Found while explaining misses (`dev20_gap.py`): a generic
step (e.g. `V0 -> V0 is not None`) matches almost every expression, and the cap keeps the places that come first.
  V0  as `steps.py`: every place's j-th filling before any place's (j+1)-th, places in source order;
  V1  the step's best candidates by its ranking key (operator rank, filling rank, seen context);
  V2  places in a context the step was seen in first (key: seen context, operator rank, filling rank).
S20 within K = 80 in the two development settings of `dev20_dev_eval.py`; "new" = reproduced by none of B, P17, S18
(from that run's rows). The variant is a copy of `StepLibrary.proposals` differing only in the cap's order.
Usage: python benchmarks/dev20_dev_caporder.py <V0|V1|V2> <dev19|dev18>   (prints one JSON line)
"""
import ast, collections, json, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import asm.coding.steps as ST
import asm.coding.shapes as SH
import asm.coding.content as C
from asm.coding.content import ProblemContext
from asm.coding.induction import Procedure, match, term_to_json, to_term
from asm.coding.integrity import read_records
VARIANT, SETTING = sys.argv[1], sys.argv[2]
R = ROOT / "benchmarks" / "results"
SET = {"dev19": (["dev17/history.jsonl", "dev18/fresh.jsonl", "dev19/train.jsonl"], "dev19/fresh.jsonl", "dev19_setting.jsonl"),
       "dev18": (["dev17/history.jsonl"], "dev18/fresh.jsonl", "dev18_setting.jsonl")}
class Lib(ST.StepLibrary):
    def proposals(self, source, span, ctx):
        try: tree = ast.parse(source)
        except SyntaxError: return None, {}
        text = ST._Text(source, tree)
        lines = source.splitlines(keepends=True)
        scope = C.scope_names(SH.C_strip("".join(lines[span[0] - 1: span[1]])))
        sites = ST._sites(tree, span); terms = [to_term(n) for n, _, _ in sites]
        live = sorted((s for s in self.steps.values() if s.status in ("active", "candidate")), key=lambda s: (s.status != "active", -len(s.support), s.id))
        rank_of = {s.id: r for r, s in enumerate(live)}
        props = {"single": [], "multi": [], "pair": []}; best = {}
        for rank, st in enumerate(live):
            if st.kind == "expr":
                groups = collections.defaultdict(list)
                for i, t in enumerate(terms):
                    b = {}
                    if match(st.lhs, t, b): groups[json.dumps(term_to_json(tuple(sorted(b.items()))), default=repr)].append((i, b))
                filled = []
                for items in groups.values():
                    built = []
                    for values, ops, j in self._fillings(st, items[0][1], ctx, scope):
                        try: built.append((ops, j, SH._subst(SH._fill_term(st.rhs, values), items[0][1])))
                        except Exception: continue
                    if built: filled.append((items, built))
                sc, mc = [], []
                for jj in range(max((len(b) for _, b in filled), default=0)):
                    for items, built in filled:
                        if jj >= len(built): continue
                        ops, j, new = built[jj]
                        opr = max(SH.OP_RANK.get(o, 6) for o in ops)
                        for i, _ in items:
                            seen = 0 if sites[i][1] in st.contexts else 1
                            sc.append(((seen, opr, j) if VARIANT == "V2" else (opr, j, seen), len(sc), i, ops, j, new))
                        if len(items) >= 2: mc.append(((opr, j, -min(st.multi, 9)), len(mc), items, ops, new))
                if VARIANT != "V0":
                    sc.sort(key=lambda x: (x[0], x[1])); mc.sort(key=lambda x: (x[0], x[1]))
                for n, (k, _, i, ops, j, new) in enumerate(sc[:ST.PER_STEP]):
                    props["single"].append(((*k, rank, n), [(sites[i][0], new)], {"step": st.id, "ops": ops, "kind": "single"}))
                    if j < ST.PAIR_FILLINGS: best.setdefault(st.id, []).append((i, ops, j, new))
                for n, (k, _, items, ops, new) in enumerate(mc[:ST.PER_STEP]):
                    props["multi"].append(((*k, rank, n), [(sites[i][0], new) for i, _ in items], {"step": st.id, "ops": ops, "kind": "multi", "sites": len(items)}))
            else:
                def fill(binding, node, tree_, st=st):
                    return [(SH._subst(SH._fill_term(st.rhs, values), binding), {"ops": ops, "rank": j}) for values, ops, j in self._fillings(st, binding, ctx, scope)]
                got = Procedure("stmts", st.lhs, st.rhs, 0).apply_detailed(source, span, fill, max_results=ST.PER_STEP)
                for k, (prog, info) in enumerate(got):
                    opr = max(SH.OP_RANK.get(o, 6) for o in info.get("ops", ["structural"]))
                    key = (0, opr, info.get("rank", 0)) if VARIANT == "V2" else (opr, info.get("rank", 0), 0)
                    props["single"].append(((*key, rank, k), prog, {"step": st.id, "ops": info.get("ops"), "kind": "single"}))
        inner, below = {}, {}
        def stmts_in(s):
            if id(s) not in inner: inner[id(s)] = {id(x) for x in ast.walk(s) if isinstance(x, ast.stmt)}
            return inner[id(s)]
        def nodes_in(n):
            if id(n) not in below: below[id(n)] = {id(x) for x in ast.walk(n)}
            return below[id(n)]
        for key, eids in self.pairs.items():
            if len(eids) < ST.PAIR_MIN_SUPPORT: continue
            a, b = key.split("|")
            if a not in best or b not in best: continue
            prank = min(rank_of.get(a, 10 ** 6), rank_of.get(b, 10 ** 6))
            for (i, oa, ja, na), (k, ob, jb, nb) in __import__("itertools").product(best[a], best[b]):
                if i == k or (a == b and i > k): continue
                n1, n2 = sites[i][0], sites[k][0]
                if id(n2) in nodes_in(n1) or id(n1) in nodes_in(n2): continue
                s1, s2 = sites[i][2], sites[k][2]
                near = 0 if s1 is s2 else (1 if s1 is not None and s2 is not None and (id(s2) in stmts_in(s1) or id(s1) in stmts_in(s2)) else 2)
                opr = max(SH.OP_RANK.get(o, 6) for o in oa + ob)
                props["pair"].append(((near, opr, ja + jb, -len(eids), prank), [(n1, na), (n2, nb)], {"step": f"{a}+{b}", "ops": oa + ob, "kind": "pair"}))
        for k in props: props[k].sort(key=lambda x: x[0])
        return text, props
def norm(s):
    try: return ast.unparse(ast.parse(s))
    except Exception: return None
trains, test, base = SET[SETTING]
lib = Lib()
for f in trains:
    by = collections.defaultdict(list)
    for r in read_records(R / f)[1]: by[r["repo"]].append((r["before"], r["after"], r["id"]))
    for repo, ex in by.items(): lib.learn(ex, repo)
baseline = {json.loads(l)["id"]: json.loads(l) for l in open(R / "dev20/development" / base) if '"id"' in l}
hits, new, t0 = [], [], time.time()
for p in read_records(R / test)[1]:
    before = p["before"]
    c = lib.candidates_for(before, "m.py", (1, before.count("\n") + 1), ProblemContext.from_dict(p.get("context", {})), limit=80, as_candidates=False)
    tgt = norm(p["after"]); h = next((i for i, (x, _) in enumerate(c) if norm(x) == tgt), None)
    if h is not None:
        b = baseline[p["id"]]; hits.append((p["id"], h, c[h][1]["kind"]))
        if not b["builtin_any"] and not b["p17_any"] and not b["s18"]: new.append(p["id"])
print(json.dumps({"variant": VARIANT, "setting": SETTING, "s20": len(hits), "new": len(new), "hits": hits, "new_ids": new, "s": round(time.time() - t0)}))
