"""Shared DEV14 benchmark plumbing: run manifests for hash-chained result files."""
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from asm.coding.integrity import environment_provenance, file_sha256  # noqa: E402

PREREG = ROOT / "benchmarks/preregistration/dev14_fresh_calibration.md"


def manifest(run: str, subject: str, spec: dict, template: Path, args: dict) -> dict:
    import dev14_subjects as S
    m = {"run": run, "subject": subject, "args": args, "provenance": environment_provenance(),
         "subject_files": {f: file_sha256(template / f) for f in spec["files"]}}
    if spec.get("kind") == "dir":
        m["sdist_dir"] = spec["dir"]
        sd = sorted((S.INDEP / "dl").glob(spec["dir"].replace("-", "*", 1) + "*.tar.gz")) or sorted((S.INDEP / "dl").glob("*" + spec["dir"].split("-")[0] + "*"))
        m["sdist_sha256"] = {p.name: file_sha256(p) for p in sd}
    if PREREG.exists():
        m["preregistration_sha256"] = file_sha256(PREREG)
    return m


def text_sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
