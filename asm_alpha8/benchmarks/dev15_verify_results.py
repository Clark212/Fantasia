"""Independent check of every published DEV15 number (same procedure as dev14_verify_results.py):
  1. every listed raw record file is an intact hash chain and matches its published SHA-256;
  2. every run manifest cites the DEV15 pre-registration as shipped, and all runs that one entry uses share one code hash;
  3. each summary is recomputed from the raw records and must equal the published one.
Usage: python benchmarks/dev15_verify_results.py [summary.json]"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
import dev14_summaries as S14  # noqa: E402
import dev15_summaries as SUM  # noqa: E402
from asm.coding.integrity import file_sha256, read_records, verify_chain  # noqa: E402

RESULTS = ROOT / "benchmarks" / "results" / "dev15"
PREREG = ROOT / "benchmarks" / "preregistration" / "dev15_study.md"
KINDS = {"decoys": SUM.summarize_decoys, "calibration": SUM.summarize_calibration, "realbugs": SUM.summarize_realbugs,
         "realbugs_validate": S14.summarize_validate}


def recompute(kind: str, paths: list):
    records = []
    for p in paths:
        records += read_records(p)[1]
    return KINDS[kind](records)


def normalize(x):
    return json.loads(json.dumps(x, sort_keys=True))


def main():
    summary_path = Path(sys.argv[1]) if len(sys.argv) > 1 else RESULTS / "summary.json"
    published = json.loads(summary_path.read_text())
    prereg_sha = file_sha256(PREREG)
    problems = []
    for name, entry in published.items():
        paths = [summary_path.parent / f for f in entry["files"]]
        codes = set()
        for p in paths:
            ok, probs, _ = verify_chain(p)
            if not ok:
                problems.append(f"{name}: {p.name}: chain broken: {probs[:3]}")
                continue
            if entry["file_sha256"].get(p.name) != file_sha256(p):
                problems.append(f"{name}: {p.name}: file hash differs from the published one")
            manifest, _ = read_records(p)
            manifest = manifest or {}
            if entry["kind"] != "realbugs_validate" and manifest.get("preregistration_sha256") != prereg_sha:
                problems.append(f"{name}: {p.name}: does not cite the shipped DEV15 pre-registration")
            if manifest.get("asm_coding_sha256"):
                codes.add(manifest["asm_coding_sha256"])
        if len(codes) > 1:
            problems.append(f"{name}: runs used different code hashes {sorted(c[:12] for c in codes)}")
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
