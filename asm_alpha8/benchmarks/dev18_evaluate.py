"""DEV18 evaluation, as pre-registered in benchmarks/preregistration/dev18_study.md.

Knowledge is learned ONLY from the 91 real fixes of the DEV17 training histories. Evaluation problems:
  fresh     fix commits mined from 8 projects never inspected before the pre-registration (dev18_mine_fresh.py), each
            with its problem context (literals of the test functions the commit changed; the module's own content)
  bugsinpy  the 59 single-function BugsInPy fixes (secondary: the designer has read these fixes, see the
            pre-registration), with the failing tests' literals from the fixed version's test files
Systems, each scored by whether a candidate AST-equal to the developer's fixed function appears within the first K=80
candidates (and, for the built-in operations and DEV17, also with no limit):
  B    DEV15 built-in operations (phases 1-2)          P17  DEV17 procedures (content kept from training fixes)
  S18  DEV18 shapes with content from the problem      D18  DEV18 phase 3 as the workflow runs it: P17 then S18, K total
Ablations (descriptive): S18 without test-derived content; S18 without the learned string vocabulary.
Learning cycle (descriptive): fresh problems in date order; attempt with D18, then learn shapes and procedures from the
revealed fix.
Usage: python benchmarks/dev18_evaluate.py <history.jsonl> <fresh.jsonl> <bugsinpy_work_dir> <out_dir>
"""
import ast
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
import dev14_realbugs as R14  # noqa: E402
import dev17_evaluate as E17  # noqa: E402
from asm.coding.content import ProblemContext  # noqa: E402
from asm.coding.integrity import ChainedWriter, code_hash, environment_provenance, file_sha256, read_records  # noqa: E402
from asm.coding.knowledge import KnowledgeBase  # noqa: E402
from asm.coding.patterns import in_repair_space  # noqa: E402
from asm.coding.shapes import ShapeLibrary  # noqa: E402

K = 80
PREREG = ROOT / "benchmarks" / "preregistration" / "dev18_study.md"


def norm(s):
    try:
        return ast.unparse(ast.parse(s))
    except (SyntaxError, ValueError):
        return None


def first_hit(programs, target) -> int | None:
    for i, p in enumerate(programs):
        if norm(p) == target:
            return i
    return None


def builtin_position(before: str, after: str) -> int | None:
    ok, _, pos = in_repair_space(before, after, "m.py", "m.f", [("m.f", 1, before.count("\n") + 1)])
    return pos if ok else None


def p17_programs(kb: KnowledgeBase, before: str, limit=None) -> list:
    out = []
    for _, progs in kb.retrieve(before, (1, before.count("\n") + 1), max_programs=limit):  # A2: same programs
        out += progs
        if limit and len(out) >= limit:
            return out[:limit]
    return out


def s18_programs(lib: ShapeLibrary, before: str, ctx: ProblemContext, limit: int) -> list:
    return lib.candidates_for(before, "m.py", (1, before.count("\n") + 1), ctx, limit=limit, as_candidates=False)


def score(problem: dict, kb: KnowledgeBase, lib: ShapeLibrary, ctx: ProblemContext) -> dict:
    before, target = problem["before"], norm(problem["after"])
    b = builtin_position(before, problem["after"])
    p17_all = p17_programs(kb, before)
    p17 = first_hit(p17_all, target)
    s18 = s18_programs(lib, before, ctx, K)
    s18_hit = first_hit([p for p, _ in s18], target)
    d18 = p17_all[:K] + [p for p, _ in s18_programs(lib, before, ctx, max(0, K - min(K, len(p17_all))))]
    d18_hit = first_hit(d18, target)
    no_test = ProblemContext.from_dict(dict(ctx.to_dict(), test_strings=[], test_numbers=[]))
    abl_test = first_hit([p for p, _ in s18_programs(lib, before, no_test, K)], target)
    saved = lib.vocab
    from asm.coding.content import StringVocabulary
    lib.vocab = StringVocabulary()
    abl_vocab = first_hit([p for p, _ in s18_programs(lib, before, ctx, K)], target)
    lib.vocab = saved
    return {"builtin_any": b is not None, "builtin_within_k": b is not None and b < K, "builtin_position": b,
            "p17_any": p17 is not None, "p17_within_k": p17 is not None and p17 < K, "s18": s18_hit is not None,
            "s18_position": s18_hit, "s18_ops": s18[s18_hit][1]["ops"] if s18_hit is not None else None,
            "s18_shape": s18[s18_hit][1]["shape"] if s18_hit is not None else None,
            "d18": d18_hit is not None, "d18_position": d18_hit,
            "s18_without_test_content": abl_test is not None, "s18_without_vocab": abl_vocab is not None,
            "s18_candidates": len(s18)}


def bugsinpy_problems(work: Path) -> list:
    probs = E17.bug_problems(work)
    recs = {f"{r['project']}-{r['bug']}": r for f in sorted(work.glob("rb15_*.jsonl")) for r in read_records(f)[1]}
    out = []
    for p in probs:
        r = recs[p["id"]]
        project, bug = p["id"].rsplit("-", 1)
        base = work / "bugs" / project / bug
        tests, names = [], []
        for t in r.get("targets", []):
            path = t.split("::", 1)[0]
            names.append(t.split("::")[-1].split("[", 1)[0])
            fp = base / "fixed" / path
            if fp.exists() and fp.read_text(errors="replace") not in tests:
                tests.append(fp.read_text(errors="replace"))
        module = (base / "buggy" / r["changed_files"][0]).read_text(errors="replace")
        p = dict(p, context=ProblemContext.build(module, tests, names, []).to_dict())
        out.append(p)
    return out


def main():
    hist_path, fresh_path, work, out = map(Path, sys.argv[1:5])
    out.mkdir(parents=True, exist_ok=True)
    w = ChainedWriter(out / "dev18_eval.jsonl", {"run": "dev18_evaluate", "provenance": environment_provenance(),
                                                 "asm_coding_sha256": code_hash(), "history_sha256": file_sha256(hist_path),
                                                 "fresh_sha256": file_sha256(fresh_path), "K": K,
                                                 "preregistration_sha256": file_sha256(PREREG)})
    _, hist = read_records(hist_path)
    kb, lib = KnowledgeBase(), ShapeLibrary()
    for r in hist:
        ex = [(r["before"], r["after"], r["id"])]
        kb.learn(ex, f"history:{r['repo']}")
        lib.learn(ex, f"history:{r['repo']}")
    kb.save(out / "knowledge_dev18.json")
    lib.save(out / "shapes_dev18.json")
    w.append({"part": "learned", "procedures": kb.summary(), "shapes": lib.summary(),
              "top_shapes": [(len(set(s.support)), s.status, s.describe()[:160]) for s in
                             sorted(lib.shapes.values(), key=lambda s: -len(set(s.support)))[:15]],
              "vocab": lib.vocab.to_dict()["edits"][:30]})
    summaries = {}
    for name, problems in (("fresh", [r for r in read_records(fresh_path)[1]]), ("bugsinpy", bugsinpy_problems(work))):
        rows = []
        for p in problems:
            ctx = ProblemContext.from_dict(p["context"])
            row = {"id": p["id"], **score(p, kb, lib, ctx)}
            rows.append(row)
            w.append({"part": name, **row})
        new = [r["id"] for r in rows if r["d18"] and not r["builtin_any"] and not r["p17_any"]]
        n = len(rows)
        summaries[name] = {"problems": n, "builtin_any": sum(r["builtin_any"] for r in rows),
                           "builtin_within_k": sum(r["builtin_within_k"] for r in rows),
                           "p17_any": sum(r["p17_any"] for r in rows), "p17_within_k": sum(r["p17_within_k"] for r in rows),
                           "s18": sum(r["s18"] for r in rows), "d18": sum(r["d18"] for r in rows),
                           "new_by_d18": new, "s18_without_test_content": sum(r["s18_without_test_content"] for r in rows),
                           "s18_without_vocab": sum(r["s18_without_vocab"] for r in rows),
                           "s18_ops": sorted("+".join(r["s18_ops"]) for r in rows if r["s18_ops"])}
        if name == "fresh":
            summaries[name]["G18-1"] = "passed" if len(new) >= 5 and len(new) >= 0.02 * n else "not passed"
    # ---- learning cycle over the fresh problems (date order)
    kb2, lib2 = copy.deepcopy(kb), copy.deepcopy(lib)
    fresh = sorted(read_records(fresh_path)[1], key=lambda r: (r["date"], r["id"]))
    cyc_online = cyc_static = 0
    for p in fresh:
        ctx = ProblemContext.from_dict(p["context"])
        target = norm(p["after"])
        progs = p17_programs(kb2, p["before"], K)
        progs += [x for x, _ in s18_programs(lib2, p["before"], ctx, max(0, K - len(progs)))]
        cyc_online += first_hit(progs, target) is not None
        ex = [(p["before"], p["after"], p["id"])]
        kb2.learn(ex, f"revealed:{p['repo']}")
        lib2.learn(ex, f"revealed:{p['repo']}")
    cyc_static = summaries["fresh"]["d18"]
    summaries["cycle"] = {"online_reproduced": cyc_online, "static_reproduced": cyc_static,
                          "shapes_after": lib2.summary(), "procedures_after": kb2.summary()}
    w.append({"part": "summary", **summaries})
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk not in ("s18_ops",)} for k, v in summaries.items()}, indent=1))


if __name__ == "__main__":
    main()
