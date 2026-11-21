"""Re-judge DEV13's decoys and single-site plausible patches with the DEV14 oracle (inputs beyond the test suite).

Question: of the decoys DEV13's oracle saw as "no observable difference", how many does generated input expose, and do
correct patches stay correct (no false 'wrong')? Patches are reconstructed exactly from benchmarks/results/dev13 records:
the fault is pool[abs_index - 1] of the seed-31 shuffled mutation pool (as in dev13_decoys.py), decoys are the original
program plus the described extra edit, singles are the described edit applied to the faulty program.
Output: a hash-chained JSONL (integrity.ChainedWriter) with a run manifest.
Usage: python benchmarks/dev14_rejudge.py <subject> <out.jsonl>
"""
import glob
import hashlib
import json
import random
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
import dev13_subjects as S  # noqa: E402
import dev14_oracle as O  # noqa: E402
from asm.coding import SafeTestRunner  # noqa: E402
from asm.coding.faultloc import apply_site, ast_normal, collect_spectrum, enumerate_sites  # noqa: E402
from asm.coding.integrity import ChainedWriter, environment_provenance, file_sha256  # noqa: E402
from asm.coding.understanding import CodeUnderstanding  # noqa: E402

SEED = 31


def legacy_desc(s, o) -> str:
    """The DEV11-DEV13 description format (no column), which is what DEV13's records contain."""
    return f"{s.kind}: {s.original!r} -> {o!r} at line {s.line}"


def sites_for(source: str, rel: str, ranges: list, desc: str) -> list:
    """Every (site, option) whose legacy description equals desc. More than one = the record is ambiguous."""
    return [(s, o) for s in enumerate_sites(source, rel, ranges) for o in s.options if legacy_desc(s, o) == desc]


def main():
    subject, out = sys.argv[1], sys.argv[2]
    spec = S.SUBJECTS[subject]
    srcs = sorted(glob.glob(str(ROOT / f"benchmarks/results/dev13/dec_{subject}.jsonl")))
    recs = [json.loads(l) for f in srcs for l in open(f)]
    runner = SafeTestRunner(timeout_seconds=60)
    writer = ChainedWriter(out, {"run": "dev14_rejudge", "subject": subject, "seed": SEED, "provenance": environment_provenance(),
                                 "inputs": {Path(f).name: file_sha256(f) for f in srcs}, "oracle": {"gen_budget": O.GEN_BUDGET, "gen_seed": O.GEN_SEED}})
    with tempfile.TemporaryDirectory(prefix="dev14_rejudge_") as td:
        td = Path(td)
        template = S.make_template(subject, td)
        und = CodeUnderstanding().analyze(template)
        infos = {f.qname: f for f in und.functions}
        ranges = {}
        for f in und.functions:
            ranges.setdefault(f.path, []).append((f.qname, f.line, f.end_line))
        orig_spectrum = collect_spectrum(template, spec["tests"], runner)
        pool = []
        for rel in spec["files"]:
            src = (template / rel).read_text()
            for site in enumerate_sites(src, rel, ranges.get(rel, [])):
                for opt in site.options:
                    pool.append((rel, site, opt))
        random.Random(SEED).shuffle(pool)
        done = set()
        for r in recs:
            rel, fault, fopt = pool[r["abs_index"] - 1]
            if (rel, fault.line, fault.kind, fault.function) != (r["file"], r["line"], r["kind"], r["truth"]):
                writer.append({"abs_index": r["abs_index"], "error": "fault reconstruction mismatch"})
                continue
            original = (template / rel).read_text()
            mutated = apply_site(original, fault, fopt)
            for strength in ("half", "weak"):
                for row in r.get(strength, {}).get("rows", []):
                    if row["kind"] == "true_fix":
                        continue
                    key = (r["abs_index"], row["kind"], row["desc"])
                    if key in done:
                        continue  # the same patch kept under both suites is judged once (the judgement depends only on code)
                    done.add(key)
                    if row["kind"] == "decoy":
                        matches = sites_for(original, rel, ranges[rel], row["desc"].replace("true fix + ", "", 1))
                        base_text = original
                    else:
                        work_tmp = td / "mut"
                        if work_tmp.exists():
                            shutil.rmtree(work_tmp)
                        shutil.copytree(template, work_tmp)
                        (work_tmp / rel).write_text(mutated)
                        mfun = CodeUnderstanding().analyze(work_tmp).functions
                        mr = [(f.qname, f.line, f.end_line) for f in mfun if f.path == rel]
                        matches = sites_for(mutated, rel, mr, row["desc"])
                        base_text = mutated
                    if len(matches) != 1:
                        writer.append({"abs_index": r["abs_index"], "kind": row["kind"], "desc": row["desc"],
                                       "dev13_class": row["class"],
                                       "error": "ambiguous description" if matches else "patch reconstruction failed",
                                       "candidates": len(matches)})
                        continue
                    text = apply_site(base_text, *matches[0])
                    pdir = td / "patched"
                    if pdir.exists():
                        shutil.rmtree(pdir)
                    shutil.copytree(template, pdir)
                    (pdir / rel).write_text(text)
                    restored = ast_normal(text) == ast_normal(original)
                    cls = O.classify_patch(template, pdir, restored, [fault.function], infos, orig_spectrum)
                    d = next(iter(cls["details"].values()), {})
                    writer.append({"abs_index": r["abs_index"], "kind": row["kind"], "desc": row["desc"],
                                   "patch_sha256": hashlib.sha256(text.encode()).hexdigest(),
                                   "dev13_class": row["class"], "dev14_class": cls["class"], "original_ok": cls.get("original_ok"),
                                   "inputs_by_origin": d.get("inputs_by_origin"), "n_diff_in_dist": d.get("n_diff_in_dist"),
                                   "n_diff_generated": d.get("n_diff_generated"), "example": d.get("example"),
                                   "dev13_flags": row["flags"], "dev13_label": row["label"]})
    print(json.dumps({"subject": subject, "judged": len(done), "head": writer.head}))


if __name__ == "__main__":
    main()
