"""Shared DEV15 benchmark plumbing: run manifests (DEV14's, plus the code hash, the DEV15 pre-registration hash, the
oracle module and any subject ini override)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
import dev14_bench as B14  # noqa: E402
from dev14_bench import text_sha  # noqa: E402,F401
from asm.coding.integrity import code_hash, file_sha256  # noqa: E402

PREREG = ROOT / "benchmarks/preregistration/dev15_study.md"


def manifest(run: str, subject: str, spec: dict, template: Path, args: dict) -> dict:
    m = B14.manifest(run, subject, spec, template, args)
    m.pop("preregistration_sha256", None)  # DEV14's pre-registration is not the one this run follows
    m["asm_coding_sha256"] = code_hash()
    m["oracle"] = "dev15_oracle"
    if spec.get("ini_override"):
        m["ini_override"] = spec["ini_override"]
    if PREREG.exists():
        m["preregistration_sha256"] = file_sha256(PREREG)
    return m
