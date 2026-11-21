"""Manual audit of every real-bug patch the workflow ACCEPTED, made executable.

For each resolved bug the auditor (a person or Claude reading ASM's diff next to the developer's) writes a probe: a short
program that exercises the behaviour where the two fixes could differ. The probe runs against the developer's FIXED tree
and ASM's PATCHED tree, under the bug's own interpreter. Different output = ASM's patch is not the developer's
behaviour, whatever the tests and the oracle said. The probes are fixed in this file, so the judgement can be re-run.
Usage: python benchmarks/dev14_realbugs_audit.py <work_dir> <eval1.jsonl,eval2.jsonl> <out.jsonl>
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from asm.coding.integrity import ChainedWriter, environment_provenance, file_sha256, read_records  # noqa: E402

PROBES = {
    # developer: match() requires only "did not match any file(s) known to git."; ASM negated the second condition
    "thefuck-15": {
        "why": "stderr that contains BOTH messages: the developer's match() accepts it, ASM's patched match() rejects it",
        "code": "from thefuck.types import Command\nfrom thefuck.rules.git_add import match\n"
                "e = \"error: pathspec 'x' did not match any file(s) known to git.\\nDid you forget to 'git add'?\"\n"
                "print(match(Command('git submodule update x', '', e)))\n"},
    # developer: the final fallback becomes getattr(self, "total", None); ASM negated the __len__ test instead, so a
    # sized iterable now reports `total` and an unsized one has len() called on it
    "tqdm-6": {
        "why": "len() of a progress bar over a 3-item list given total=10: the developer's tqdm says 3",
        "code": "import sys\nfrom tqdm import tqdm\nt = tqdm([1, 2, 3], total=10, file=sys.stdout, disable=True)\n"
                "print(len(t))\ntry:\n    print(len(tqdm(iter([1, 2]), total=5, file=sys.stdout, disable=True)))\n"
                "except Exception as e:\n    print(type(e).__name__)\n"},
}


def main():
    work, evals, out = Path(sys.argv[1]), sys.argv[2].split(","), sys.argv[3]
    _, vrecs = read_records(work / "validate.jsonl")
    venv = {(r["project"], r["bug"]): r.get("venv") for r in vrecs}
    resolved = [r for e in evals for r in read_records(work / e)[1] if r.get("status") == "resolved"]
    w = ChainedWriter(out, {"run": "dev14_realbugs_audit", "provenance": environment_provenance(),
                            "inputs": {e: file_sha256(work / e) for e in evals}, "probes_sha256": file_sha256(__file__)})
    for r in resolved:
        key = f'{r["project"]}-{r["bug"]}'
        probe = PROBES.get(key)
        rec = {"bug": key, "asm_patch": r.get("desc"), "asm_label": r.get("label"), "asm_flags": r.get("flags"),
               "oracle_class": r.get("oracle_class")}
        if probe is None:
            w.append(dict(rec, verdict="not audited (no probe written)"))
            continue
        py = str(work / "venvs" / venv[(r["project"], r["bug"])] / "bin" / "python")
        outs = {}
        for side in ("fixed", "patched"):
            p = subprocess.run([py, "-c", probe["code"]], cwd=work / "bugs" / r["project"] / str(r["bug"]) / side,
                               capture_output=True, text=True, timeout=120)
            outs[side] = (p.stdout.strip() or p.stderr.strip()[-200:])
        verdict = "same as developer on the probe" if outs["fixed"] == outs["patched"] else "differs from the developer's fix"
        w.append(dict(rec, why=probe["why"], probe=probe["code"], outputs=outs, verdict=verdict))
        print(json.dumps({"bug": key, "verdict": verdict, "outputs": outs}))


if __name__ == "__main__":
    main()
