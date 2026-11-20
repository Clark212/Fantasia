"""DEV16 pipeline DRY RUN only: a non-LLM stand-in for tools/generate_pairs.py, writing records in the same format.
Bugs are single edits drawn from ASM's own DEV14/DEV15 edit sites (inverted: the edit is the bug, the original is the
fix), so every one is inside ASM's repair space by construction. Results from this data test the PIPELINE and the
learner's mechanics; they say nothing about realistic bugs. Every record carries generator="standin_mutation".
Usage: ASM_INDEP_DIR=/tmp/asm_indep python benchmarks/dev16_standin_generator.py <out.jsonl> --per-function=2 --seed=3"""
import hashlib
import json
import random
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
import dev16_subjects as S  # noqa: E402
from asm.coding.faultloc import _offsets, apply_site, enumerate_sites  # noqa: E402
from asm.coding.repair_ops import site_edits  # noqa: E402
sys.path.insert(0, str(ROOT / "tools"))
from generate_pairs import strip_indent  # noqa: E402


def main():
    out = Path(sys.argv[1])
    per = int(next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--per-function=")), "2"))
    seed = int(next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--seed=")), "3"))
    manifest = json.loads((ROOT / "tools" / "dev16_subjects.json").read_text())
    rng = random.Random(seed)
    n = 0
    with tempfile.TemporaryDirectory() as td, out.open("w") as f:
        for subj in manifest["subjects"]:
            repo = S.make_template(subj["name"], Path(td) / subj["name"])
            for fn in subj["functions"]:
                text = (repo / fn["path"]).read_text()
                lines = text.splitlines(keepends=True)
                orig_fn = "".join(lines[fn["line"] - 1: fn["end_line"]])
                ranges = [(fn["qualname"], fn["line"], fn["end_line"])]
                sites = [s for s in enumerate_sites(text, fn["path"], ranges) if s.function == fn["qualname"]]
                sites += [s for s in site_edits(text, fn["path"], ranges, fn["qualname"], _offsets(text.encode()))
                          if s.kind in ("name", "drop_clause")]
                options = [(s, o) for s in sites for o in s.options if fn["line"] < s.line <= fn["end_line"]]
                rng.shuffle(options)
                for s, o in options[:per]:
                    mutated = apply_site(text, s, o).splitlines(keepends=True)
                    delta = len(mutated) - len(lines)
                    bfn = "".join(mutated[fn["line"] - 1: fn["end_line"] + delta])
                    indent = lines[fn["line"] - 1][: len(lines[fn["line"] - 1]) - len(lines[fn["line"] - 1].lstrip())]
                    jid = hashlib.sha256(f"standin|{seed}|{subj['name']}|{fn['qualname']}|{s.start}|{o}".encode()).hexdigest()[:24]
                    rec = {"id": jid, "generator": "standin_mutation", "prompt_version": None, "subject": subj["name"],
                           "version": subj["version"], "sdist_sha256": subj["sdist_sha256"], "path": fn["path"],
                           "qualname": fn["qualname"], "line": fn["line"], "end_line": fn["end_line"],
                           "file_sha256": fn["file_sha256"], "original_sha256": hashlib.sha256(strip_indent(orig_fn, indent).encode()).hexdigest(),
                           "indent": indent, "bug_kind": f"standin:{s.kind}", "model": None, "model_digest": None,
                           "accepted_locally": True, "reject_reason": None, "buggy_function": strip_indent(bfn, indent)}
                    f.write(json.dumps(rec, sort_keys=True) + "\n")
                    n += 1
    print(n, "stand-in records ->", out)


if __name__ == "__main__":
    main()
