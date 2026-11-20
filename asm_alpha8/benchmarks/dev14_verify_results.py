"""Independent check of every published DEV14 number.

For each entry of benchmarks/results/dev14/summary.json:
  1. every listed raw record file is a valid hash chain (integrity.verify_chain), and its SHA-256 matches the one listed;
  2. manifests that cite the pre-registration carry the hash of the pre-registration file as shipped;
  3. the summary is recomputed from the raw records with the same pure functions and must equal the published one.
Exit status 0 only if everything matches. Usage: python benchmarks/dev14_verify_results.py [summary.json]
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
import dev14_summaries as SUM  # noqa: E402
from asm.coding.integrity import file_sha256, read_records, verify_chain  # noqa: E402

RESULTS = ROOT / "benchmarks" / "results" / "dev14"
PREREG = ROOT / "benchmarks" / "preregistration" / "dev14_fresh_calibration.md"


def recompute(kind: str, paths: list):
    records = []
    for p in paths:
        _, recs = read_records(p)
        records += recs
    if kind == "decoys":
        return SUM.summarize_decoys(records)
    if kind == "calibration":
        return SUM.summarize_calibration(records)
    if kind == "rejudge":
        import dev14_aggregate_rejudge as AR
        return AR.summarize([str(p) for p in paths])
    if kind == "realbugs_validate":
        return SUM.summarize_validate(records)
    if kind == "realbugs_evaluate":
        return SUM.summarize_evaluate(records)
    raise ValueError(f"unknown kind {kind}")


def normalize(x):
    return json.loads(json.dumps(x, sort_keys=True))


def main():
    summary_path = Path(sys.argv[1]) if len(sys.argv) > 1 else RESULTS / "summary.json"
    published = json.loads(summary_path.read_text())
    prereg_sha = file_sha256(PREREG)
    problems = []
    for name, entry in published.items():
        paths = [summary_path.parent / f for f in entry["files"]]
        for p in paths:
            ok, probs, _ = verify_chain(p)
            if not ok:
                problems.append(f"{name}: {p.name}: chain broken: {probs[:3]}")
                continue
            want = entry["file_sha256"].get(p.name)
            if want != file_sha256(p):
                problems.append(f"{name}: {p.name}: file hash differs from the published one")
            manifest, _ = read_records(p)
            cited = (manifest or {}).get("preregistration_sha256")
            if cited and cited != prereg_sha:
                problems.append(f"{name}: {p.name}: cites pre-registration {cited[:12]}, shipped file is {prereg_sha[:12]}")
        if any(n.startswith(name + ":") for n in problems):
            continue
        again = normalize(recompute(entry["kind"], paths))
        if again != normalize(entry["summary"]):
            diff = [k for k in set(again) | set(entry["summary"]) if again.get(k) != entry["summary"].get(k)]
            problems.append(f"{name}: recomputed summary differs in {sorted(diff)}")
        else:
            print(f"ok  {name}: {len(paths)} file(s), summary reproduced")
    for p in problems:
        print("FAIL", p)
    print(f"pre-registration sha256 {prereg_sha}")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
