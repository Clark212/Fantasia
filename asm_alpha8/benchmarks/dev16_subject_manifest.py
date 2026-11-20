"""Write tools/dev16_subjects.json: the projects the PC generator may draw functions from, and which functions each
project's own tests execute (a bug in an unexecuted function can never be verified, so asking for one wastes the model).
Each entry pins the PyPI sdist by SHA-256 and each source file by SHA-256, so the generator and the verifier work on the
same bytes. Usage: ASM_INDEP_DIR=/tmp/asm_indep python benchmarks/dev16_subject_manifest.py [subject ...]

TRAINING subjects only. Projects in any evaluation set (BugsInPy's projects, DEV15's real-bug corpus) are never listed
here; benchmarks/dev16_subjects.py enforces that."""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
import dev16_subjects as S  # noqa: E402
from asm.coding import SafeTestRunner  # noqa: E402
from asm.coding.faultloc import collect_spectrum  # noqa: E402
from asm.coding.integrity import file_sha256  # noqa: E402
from asm.coding.understanding import CodeUnderstanding  # noqa: E402

MIN_LINES, MAX_LINES = 3, 80


def subject_entry(name: str) -> dict:
    spec = S.SUBJECTS[name]
    runner = SafeTestRunner(timeout_seconds=300)
    with tempfile.TemporaryDirectory() as td:
        repo = S.make_template(name, Path(td))
        sp = collect_spectrum(repo, spec["tests"], runner, timeout=300)
        if not sp.complete and not sp.failing:
            raise SystemExit(f"{name}: traced run unusable ({sp.incomplete_reason})")
        # tests failing on the CLEAN project under tracing (e.g. cachetools' TTL timing tests) only lose coverage here;
        # the verifier compares every bug against a plain run of the original, so they never count as caught bugs
        flaky = sorted(sp.failing)
        executed: dict = {}
        for t in sp.passing:
            for rel, lines in sp.lines.get(t, {}).items():
                executed.setdefault(rel, set()).update(lines)
        funcs = []
        for f in CodeUnderstanding().analyze(repo).functions:
            if f.path not in spec["files"] or f.kind == "nested" or not MIN_LINES <= f.end_line - f.line + 1 <= MAX_LINES:
                continue
            body = set(range(f.line + 1, f.end_line + 1))
            if body & executed.get(f.path, set()):
                funcs.append({"path": f.path, "sdist_path": S.sdist_path(name, f.path), "qualname": f.qname,
                              "line": f.line, "end_line": f.end_line, "file_sha256": file_sha256(repo / f.path)})
    sd = S.sdist_file(name)
    return {"name": name, "pypi_name": spec["pypi_name"], "version": spec["version"], "sdist_filename": sd.name,
            "sdist_sha256": file_sha256(sd), "functions": funcs, "tests_passing": len(sp.passing),
            "tests_failing_when_traced": flaky}


def main():
    names = sys.argv[1:] or list(S.TRAINING)
    out = ROOT / "tools" / "dev16_subjects.json"
    entries = []
    for n in names:
        e = subject_entry(n)
        print(n, len(e["functions"]), "executed functions,", e["tests_passing"], "passing tests", flush=True)
        entries.append(e)
    out.write_text(json.dumps({"manifest_version": 1, "subjects": entries}, indent=1, sort_keys=True) + "\n")
    print("wrote", out)


if __name__ == "__main__":
    main()
