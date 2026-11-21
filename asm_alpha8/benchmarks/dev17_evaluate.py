"""DEV17 evaluation, as pre-registered in benchmarks/preregistration/dev17_study.md.

  A  learn from the oldest 70% of each training project's mined fixes; validate on the newest 30%      (Q2)
  B  transfer: which of the 59 single-function BugsInPy fixes do ACTIVE (and, secondary, CANDIDATE) learned
     procedures reproduce, and which of those can DEV15's built-in operations not produce? -> gate G17-1      (Q1)
  C  the learning cycle: the 59 bugs in fix-date order; attempt, record outcomes, learn from the revealed fix  (Q4)
A "reproduction" means: a learned procedure applied to the buggy function yields a function AST-equal to the
developer's fixed function. No tests are run here (Q3, the workflow run, is dev17_realbugs.py).
Usage: python benchmarks/dev17_evaluate.py <history.jsonl> <bugsinpy_work_dir> <out_dir>
"""
import ast
import copy
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
import dev14_realbugs as R14  # noqa: E402
import dev17_mine_history as M  # noqa: E402
from asm.coding.integrity import ChainedWriter, code_hash, environment_provenance, file_sha256, read_records  # noqa: E402
from asm.coding.knowledge import KnowledgeBase  # noqa: E402
from asm.coding.patterns import in_repair_space  # noqa: E402

PREREG = ROOT / "benchmarks" / "preregistration" / "dev17_study.md"


def norm(s):
    try:
        return ast.unparse(ast.parse(s))
    except SyntaxError:
        return None


def split_history(recs):
    by = {}
    for r in recs:
        by.setdefault(r["repo"], []).append(r)
    learn, held = [], []
    for repo, rs in sorted(by.items()):
        rs.sort(key=lambda r: (r["date"], r["id"]))
        k = max(1, int(len(rs) * 0.7))
        learn += rs[:k]
        held += rs[k:]
    return learn, held


def module_of(path):
    m = path[:-3].replace("/", ".")
    return m[: -len(".__init__")] if m.endswith(".__init__") else m


def bug_problems(work: Path) -> list:
    """The single-function BugsInPy fixes: buggy/fixed function sources plus what the built-in operations can do."""
    recs = []
    for f in sorted(work.glob("rb15_*.jsonl")):
        recs += read_records(f)[1]
    out = []
    for r in recs:
        if len(r.get("truth", [])) != 1 or len(r.get("changed_files", [])) != 1:
            continue
        path, q = r["changed_files"][0], r["truth"][0]
        mod = module_of(path)
        if not q.startswith(mod + "."):
            continue
        local = q[len(mod) + 1:]
        base = work / "bugs" / r["project"] / str(r["bug"])
        bsrc, fsrc = (base / "buggy" / path).read_text(), (base / "fixed" / path).read_text()
        fb, ff = M.functions(bsrc), M.functions(fsrc)
        if local not in fb or local not in ff:
            continue
        b_fn, f_fn = M.fn_source(bsrc, fb[local][0]), M.fn_source(fsrc, ff[local][0])
        nb, nf = fb[local][0], ff[local][0]
        bl, fl = bsrc.splitlines(keepends=True), fsrc.splitlines(keepends=True)
        sb = min([nb.lineno] + [d.lineno for d in nb.decorator_list])
        sf = min([nf.lineno] + [d.lineno for d in nf.decorator_list])
        target = "".join(bl[:sb - 1] + fl[sf - 1:nf.end_lineno] + bl[nb.end_lineno:])
        ranges = [(mod + "." + k, v[0].lineno, v[0].end_lineno) for k, v in fb.items()]
        builtin, fam, _ = in_repair_space(bsrc, target, path, q, ranges)
        meta = R14.info(work / "corpus" / "projects" / r["project"] / "bugs" / str(r["bug"]) / "bug.info")
        date = subprocess.run(["git", "-C", str(work / "repos" / r["project"]), "show", "-s", "--format=%ct",
                               meta["fixed_commit_id"]], capture_output=True, text=True).stdout.strip()
        out.append({"id": f"{r['project']}-{r['bug']}", "before": b_fn, "after": f_fn, "builtin": builtin,
                    "builtin_family": fam, "date": int(date or 0), "dev15_status": r.get("status")})
    return out


def attempt(kb: KnowledgeBase, p: dict, include_candidates: bool) -> tuple:
    """(reproduced?, procedure ids that produced the fix, procedure ids that fired)."""
    target = norm(p["after"])
    fired, hit = [], []
    for ent, progs in kb.retrieve(p["before"], (1, p["before"].count("\n") + 1), include_candidates=include_candidates):
        fired.append(ent.id)
        if any(norm(x) == target for x in progs):
            hit.append(ent.id)
    return bool(hit), hit, fired


def main():
    hist_path, work, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    out.mkdir(parents=True, exist_ok=True)
    w = ChainedWriter(out / "dev17_eval.jsonl", {"run": "dev17_evaluate", "provenance": environment_provenance(),
                                                 "asm_coding_sha256": code_hash(), "history_sha256": file_sha256(hist_path),
                                                 "preregistration_sha256": file_sha256(PREREG)})
    hist_manifest, hist = read_records(hist_path)
    learn, held = split_history(hist)
    # ---- A: learn + validate (Q2)
    kb = KnowledgeBase()
    for r in learn:
        kb.learn([(r["before"], r["after"], r["id"])], f"history:{r['repo']}")
    after_learning = kb.summary()
    kb.validate([(r["before"], r["after"], r["id"]) for r in held])
    held_rows = []
    for r in held:
        p = {"before": r["before"], "after": r["after"]}
        ok_a, hit_a, _ = attempt(kb, p, include_candidates=False)
        held_rows.append({"id": r["id"], "repo": r["repo"], "reproduced_active": ok_a, "by": hit_a})
    kb.save(out / "knowledge_history.json")
    w.append({"part": "A", "learned_examples": len(learn), "held_out_examples": len(held), "after_learning": after_learning,
              "after_validation": kb.summary(), "held_out": held_rows,
              "procedures": [{"id": e.id, "status": e.status, "support": e.support, "sources": e.sources,
                              "validation": e.validation, "describe": e.procedure.describe()} for e in kb.entries.values()]})
    # ---- B: transfer (Q1, gate G17-1)
    probs = bug_problems(work)
    rows = []
    for p in probs:
        ok_a, hit_a, fired_a = attempt(kb, p, include_candidates=False)
        ok_c, hit_c, fired_c = attempt(kb, p, include_candidates=True)
        rows.append({"id": p["id"], "builtin": p["builtin"], "builtin_family": p["builtin_family"], "active": ok_a,
                     "active_by": hit_a, "active_fired": len(fired_a), "with_candidates": ok_c, "candidates_by": hit_c,
                     "candidates_fired": len(fired_c), "dev15_status": p["dev15_status"]})
    new_by_active = [r["id"] for r in rows if r["active"] and not r["builtin"]]
    gate = {"G17-1": "passed" if new_by_active else "not passed", "new_fixes_by_active": new_by_active,
            "active_reproduced": sum(r["active"] for r in rows), "with_candidates_reproduced": sum(r["with_candidates"] for r in rows),
            "builtin_reproducible": sum(r["builtin"] for r in rows), "problems": len(rows)}
    w.append({"part": "B", "rows": rows, **gate})
    # ---- C: the learning cycle (Q4)
    online = copy.deepcopy(kb)
    cyc = []
    for p in sorted(probs, key=lambda x: (x["date"], x["id"])):
        ok, hit, fired = attempt(online, p, include_candidates=True)
        for pid in fired:
            online.record_outcome(pid, pid in hit, p["id"])
        new = online.learn([(p["before"], p["after"], p["id"])], "revealed:bugsinpy")
        cyc.append({"id": p["id"], "date": p["date"], "reproduced": ok, "by": hit, "fired": len(fired),
                    "new_procedures": len(new), "static_reproduced": next(r["with_candidates"] for r in rows if r["id"] == p["id"])})
    bug_ids = {x["id"] for x in probs}
    learned_then_used = sorted({pid for c in cyc for pid in c["by"] if set(online.entries[pid].support) & bug_ids})
    online.save(out / "knowledge_online.json")
    w.append({"part": "C", "sequence": cyc, "online_reproduced": sum(c["reproduced"] for c in cyc),
              "static_reproduced": sum(c["static_reproduced"] for c in cyc), "final": online.summary(),
              "procedures_learned_from_bugs_that_later_succeeded": learned_then_used})
    summary = {"Q2": {"held_out": len(held), "reproduced_by_active": sum(r["reproduced_active"] for r in held_rows),
                      "status_after_validation": kb.summary()},
               "Q1": gate,
               "Q4": {"online_reproduced": sum(c["reproduced"] for c in cyc), "static_reproduced": sum(c["static_reproduced"] for c in cyc),
                      "procedures_learned_from_bugs_that_later_succeeded": len(learned_then_used), "final": online.summary()}}
    w.append({"part": "summary", **summary})
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
