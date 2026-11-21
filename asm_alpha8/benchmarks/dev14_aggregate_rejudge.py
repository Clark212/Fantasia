"""Summarize dev14_rejudge.py output: how DEV13 oracle verdicts change when inputs beyond the test suite are added."""
import collections
import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from asm.coding.integrity import read_records  # noqa: E402
from dev13_stats import pct  # noqa: E402


def summarize(paths):
    rows = []
    for p in paths:
        m, recs = read_records(p)  # raises on a broken evidence chain
        rows += [dict(r, subject=m["subject"]) for r in recs]
    errors = [r for r in rows if "error" in r]
    ambiguous = [r for r in errors if r["error"] == "ambiguous description"]
    ok = [r for r in rows if "error" not in r]
    trans = collections.Counter((r["kind"], r["dev13_class"], r["dev14_class"]) for r in ok)
    # a decoy is "original + one edit", independent of the fault it was built for: count each distinct program once
    seen, uniq = set(), []
    for r in ok:
        if r["patch_sha256"] not in seen:
            seen.add(r["patch_sha256"])
            uniq.append(r)
    ok = uniq
    blind = [r for r in ok if r["kind"] == "decoy" and r["dev13_class"] in ("equivalent", "unknown")]
    exposed = [r for r in blind if r["dev14_class"] in ("wrong", "wrong_generated")]
    singles_eq = [r for r in ok if r["kind"] == "single" and r["dev13_class"] == "equivalent"]
    return {"rows": len(rows), "errors": len(errors), "ambiguous_records": len(ambiguous),
            "ambiguous_by_dev13_class": dict(collections.Counter(r.get("dev13_class") for r in ambiguous)),
            "unique_programs_judged": len({r["patch_sha256"] for r in ok}),
            "transitions": {f"{k[0]}: {k[1]} -> {k[2]}": v for k, v in sorted(trans.items())},
            "blind_decoys": len(blind), "exposed": len(exposed),
            "exposed_generated_only": sum(r["dev14_class"] == "wrong_generated" for r in exposed),
            "exposed_generated_original_ok": sum(r["dev14_class"] == "wrong_generated" and bool(r.get("original_ok")) for r in exposed),
            "exposed_in_dist": sum(r["dev14_class"] == "wrong" for r in exposed),
            "exposed_by_subject": dict(collections.Counter(r["subject"] for r in exposed)),
            "blind_by_subject": dict(collections.Counter(r["subject"] for r in blind)),
            "singles_previously_equivalent": len(singles_eq),
            "singles_now_wrong": sum(r["dev14_class"] in ("wrong", "wrong_generated") for r in singles_eq),
            "dev13_wrong_still_wrong": sum(1 for r in ok if r["dev13_class"] == "wrong" and r["dev14_class"] in ("wrong", "wrong_generated")),
            "dev13_wrong_total": sum(1 for r in ok if r["dev13_class"] == "wrong"),
            "examples": [(r["subject"], r["desc"][:60], r["dev14_class"], r.get("example")) for r in exposed[:6]]}


if __name__ == "__main__":
    s = summarize(sorted(glob.glob(sys.argv[1])))
    print(json.dumps({k: v for k, v in s.items() if k != "examples"}, indent=1))
    print(f"\nDEV13 blind-spot decoys exposed by generated inputs: {pct(s['exposed'], s['blind_decoys'])}")
    for e in s["examples"]:
        print("  ", e)
