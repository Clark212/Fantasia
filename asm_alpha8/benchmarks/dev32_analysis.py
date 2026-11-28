"""DEV32 analysis of an evaluation run (dev32_realbugs.py): what the pre-registration's gates need, except the person-read
verdicts (REALBUGS_REVIEW.md).
  - per arm: statuses, resolved bugs, repairs not made by the control, the longest runs;
  - the guard: the accepted patches that its rule flags (content.copied_test_strings, with the failing tests' literals
    from their source; the live guard also uses quoted failure text, so it can drop more), and what the guarded arm
    dropped (rejected_by_reason['test_copy'], candidates it never tested);
  - its cost: the valid bugs whose DEVELOPER fix the rule flags (the fix applied to the buggy version).
Usage: python benchmarks/dev32_analysis.py <work_dir> [records glob]
"""
import collections
import json
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
import dev14_realbugs as R14  # noqa: E402
from dev31_realbugs import records  # noqa: E402
from dev32_development import patched_files  # noqa: E402
from asm.coding.content import ProblemContext, copied_test_strings, literals  # noqa: E402
from asm.coding.integrity import read_records  # noqa: E402

ARMS = ("control", "learned", "guarded")


def flagged(work: Path, project: str, bug: int, targets: list, diff: str) -> list | None:
    """The strings the guard's rule flags in a patch of the bug's buggy version (None: the diff does not apply)."""
    buggy = work / "bugs" / project / str(bug) / "buggy"
    names = {t.split("::")[-1].split("[", 1)[0] for t in targets}
    ctx = ProblemContext(test_strings=[s for p in sorted({t.split("::", 1)[0] for t in targets}) if (buggy / p).exists()
                                       for s in literals((buggy / p).read_text(encoding="utf-8", errors="replace"), names)[0]])
    new = patched_files(buggy, diff, re.findall(r"^\+\+\+ b/(.+)$", diff, re.M))
    return None if new is None else sorted({s for f, src in new.items()
                                            for s in copied_test_strings((buggy / f).read_text(encoding="utf-8"), src, ctx)})


def main():
    work = Path(sys.argv[1])
    pattern = sys.argv[2] if len(sys.argv) > 2 else "dev32_control_learned_guarded_*of*.jsonl"
    extra = records(work, "dev32_time_control.jsonl")
    by = {k: {**v, **extra.get(k, {})} for k, v in records(work, pattern).items()}
    arms = [a for a in ARMS if any(a in v for v in by.values())]
    full = {k: v for k, v in by.items() if set(arms) <= set(v)}
    res = {m: {k for k, v in full.items() if v[m]["status"] == "resolved"} for m in arms}
    tried = lambda r: sum(n for k, n in (r.get("rejected_by_reason") or {}).items() if k != "test_copy") + (r["status"] == "resolved")  # noqa: E731
    flags = {m: {f"{k[0]}-{k[1]}": flagged(work, k[0], k[1], v[m]["targets"], v[m]["asm_diff"]) for k, v in full.items()
                 if v[m].get("asm_diff") and v[m]["status"] == "resolved"} for m in arms}
    secs = {m: sorted(v[m].get("repair_seconds", 0) for v in full.values()) for m in arms}
    out = {"bugs": len(full), "arms": arms,
           "status": {m: dict(collections.Counter(v[m]["status"] for v in full.values())) for m in arms},
           "no_spectrum_reasons": dict(collections.Counter(v[arms[0]].get("reason") for v in full.values() if v[arms[0]]["status"] == "no_spectrum")),
           "resolved": {m: sorted(f"{k[0]}-{k[1]}" for k in res[m]) for m in arms},
           "not_by_control": {m: sorted(f"{k[0]}-{k[1]}" for k in res[m] - res.get("control", set())) for m in arms if m != "control"},
           "control_only": sorted(f"{k[0]}-{k[1]}" for k in res.get("control", set()) - set().union(*(res[m] for m in arms if m != "control"))),
           "flagged_accepted": {m: {b: s for b, s in f.items() if s} for m, f in flags.items()},
           "diffs_not_applying": {m: sorted(b for b, s in f.items() if s is None) for m, f in flags.items()},
           "seconds": {m: {"median": statistics.median(s), "max": s[-1], "over_300": sum(x > 300 for x in s), "over_360": sum(x > 360 for x in s)}
                       for m, s in secs.items() if s},
           "tried_median": {m: statistics.median([tried(v[m]) for v in full.values()]) for m in arms}}
    if "control" in arms:  # DEV31's measure: where phases 1-2 tried candidates and accepted nothing, phase 3's extra ones
        for m in set(arms) - {"control"}:
            extra = {k: tried(v[m]) - tried(v["control"]) for k, v in full.items()
                     if v["control"]["status"] in ("unresolved", "time_budget") and tried(v["control"]) > 0}
            out.setdefault("phase3", {})[m] = {"reached": len(extra), "candidates_tested_median": statistics.median(extra.values()) if extra else None,
                                               "none_tested": sum(n <= 0 for n in extra.values()),
                                               "outcome": dict(collections.Counter(full[k][m]["status"] for k in extra))}
    if "guarded" in arms:
        drops = {f"{k[0]}-{k[1]}": v["guarded"]["rejected_by_reason"]["test_copy"] for k, v in full.items()
                 if (v["guarded"].get("rejected_by_reason") or {}).get("test_copy")}
        out["guard_dropped"] = {"bugs": len(drops), "candidates": sum(drops.values()), "by_bug": drops}
    if "control_long" in {m for v in by.values() for m in v}:
        out["time_control"] = {f"{k[0]}-{k[1]}": v["control_long"]["status"] for k, v in by.items() if "control_long" in v}
    valid = [r for r in read_records(work / "validate.jsonl")[1] if r.get("status") == "valid"]
    dev = {f"{r['project']}-{r['bug']}": flagged(work, r["project"], r["bug"], r["targets"],
                                                   (R14.corpus_dir(work) / r["project"] / "bugs" / str(r["bug"]) / "bug_patch.txt").read_text())
           for r in valid if (work / "bugs" / r["project"] / str(r["bug"]) / "buggy").exists()}
    out["developer_fixes"] = {"valid_bugs": len(valid), "checked": sum(v is not None for v in dev.values()),
                              "flagged": {b: s for b, s in dev.items() if s}, "not_applying": sorted(b for b, s in dev.items() if s is None)}
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
