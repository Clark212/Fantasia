"""DEV23 development check: re-run DEV21's and DEV22's committed lab runs with ProcedureCortex(family_mapping=M) forced,
and compare every attempt record with the committed one ('exact' must reproduce them all).
Usage: python benchmarks/dev23_lab_check.py exact|rename <scratch dir>
"""
import importlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
RUNS = (("dev21_transfer", (), "dev21/transfer.jsonl"),
        ("dev21_transfer", ("--development",), "dev21/development/transfer_dev4_lab.jsonl"),
        ("dev22_transfer", (), "dev22/transfer.jsonl"),
        ("dev22_transfer", ("--development",), "dev22/development/transfer_dev.jsonl"))


def run_forced(mapping, harness, out, flags):
    import asm.procedure_cortex as PC

    class Forced(PC.ProcedureCortex):
        def __init__(self, *args, **options):
            super().__init__(*args, **{**options, "family_mapping": mapping})
    PC.ProcedureCortex = Forced  # before the harness (and structtransfer) import it
    module = importlib.import_module(harness)
    sys.argv = [harness, out, *flags]
    module.main()


def main():
    if sys.argv[1] == "--run":
        return run_forced(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5:])
    from asm.coding.integrity import read_records
    mapping, scratch = sys.argv[1], Path(sys.argv[2])
    scratch.mkdir(parents=True, exist_ok=True)
    counts = lambda r: {k: v for k, v in r.items() if k not in ("candidates", "evaluator_calls")}  # noqa: E731
    for harness, flags, committed in RUNS:
        out = scratch / committed.replace("/", "_")
        subprocess.run([sys.executable, __file__, "--run", mapping, harness, str(out), *flags], check=True,
                       stdout=subprocess.DEVNULL)
        a, b = ([r for r in read_records(p)[1] if r.get("part") == "attempt"]
                for p in (out, ROOT / "benchmarks" / "results" / committed))
        assert len(a) == len(b), (committed, len(a), len(b))
        pairs = list(zip(a, b))
        print(f"{committed}: {len(a)} attempts; identical {sum(x == y for x, y in pairs)}; differ beyond counts "
              f"{sum(counts(x) != counts(y) for x, y in pairs)}; gained {sum(x['success'] > y['success'] for x, y in pairs)}; "
              f"lost {sum(x['success'] < y['success'] for x, y in pairs)}; wrong {sum(x['wrong'] for x in a)}", flush=True)


if __name__ == "__main__":
    main()
