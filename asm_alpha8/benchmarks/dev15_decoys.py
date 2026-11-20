"""DEV15 decoy benchmark: DEV14's protocol (benchmarks/dev14_decoys.py, unchanged and hash-pinned in the DEV14
manifest) run on the FRESH subjects with the DEV15 oracle and DEV15 run manifests. The decoy construction, suites,
flag re-derivation and controls are DEV14's, so the label-rule study (pre-registered as L15 in
benchmarks/preregistration/dev15_study.md) is evaluated on the same kind of data that suggested it.
The flags reflect DEV15 verification (constants mined from every version; import-time functions compared by state).
Usage: python benchmarks/dev15_decoys.py <subject> <n_keep> <out.jsonl> --seed=N [--skip=K] [--per-fault=8]
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
import dev15_bench  # noqa: E402
import dev15_oracle  # noqa: E402
import dev15_subjects  # noqa: E402
import dev14_calibration as C  # noqa: E402
import dev14_decoys as D  # noqa: E402

C.O = dev15_oracle  # dev14_decoys judges through dev14_calibration.classify, which uses C.O
D.S = dev15_subjects
D.manifest = lambda run, *a, **k: dev15_bench.manifest(run.replace("dev14", "dev15"), *a, **k)

if __name__ == "__main__":
    D.main()
