"""Re-run every committed structure-transfer lab run (DEV21-DEV24, development and held-out) with ProcedureCortex options
applied where the harness does not set them itself, and compare each attempt record with the committed one.
Usage: python benchmarks/lab_check.py <scratch dir> [option=value ...]
  e.g. family_mapping=exact reproduces all of them (DEV21's held-out lab needs it since the 2026-11-23 defaults).
"""
import importlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
RUNS = (("dev21_transfer", (), "dev21/transfer.jsonl"), ("dev21_transfer", ("--development",), "dev21/development/transfer_dev4_lab.jsonl"),
        ("dev22_transfer", (), "dev22/transfer.jsonl"), ("dev22_transfer", ("--development",), "dev22/development/transfer_dev.jsonl"),
        ("dev23_transfer", (), "dev23/transfer.jsonl"), ("dev23_transfer", ("--development",), "dev23/development/transfer_dev.jsonl"),
        ("dev24_transfer", (), "dev24/transfer.jsonl"), ("dev24_transfer", ("--development",), "dev24/development/transfer_dev.jsonl"))


def run_with(options, harness, out, flags):
    import asm.procedure_cortex as PC

    class Configured(PC.ProcedureCortex):
        def __init__(self, *args, **given):
            super().__init__(*args, **{**options, **given})  # the harness's own options win
    PC.ProcedureCortex = Configured  # before the harness (and structtransfer) import it
    module = importlib.import_module(harness)
    sys.argv = [harness, out, *flags]
    module.main()


def main():
    if sys.argv[1] == "--run":
        return run_with(dict(o.split("=", 1) for o in sys.argv[2].split(",") if o), sys.argv[3], sys.argv[4], sys.argv[5:])
    from asm.coding.integrity import read_records
    scratch, options = Path(sys.argv[1]), ",".join(sys.argv[2:])
    scratch.mkdir(parents=True, exist_ok=True)
    counts = lambda r: {k: v for k, v in r.items() if k not in ("candidates", "evaluator_calls")}  # noqa: E731
    for harness, flags, committed in RUNS:
        out = scratch / committed.replace("/", "_")
        subprocess.run([sys.executable, __file__, "--run", options, harness, str(out), *flags], check=True, stdout=subprocess.DEVNULL)
        a, b = ([r for r in read_records(p)[1] if r.get("part") == "attempt"] for p in (out, ROOT / "benchmarks" / "results" / committed))
        assert len(a) == len(b), (committed, len(a), len(b))
        pairs = list(zip(a, b))
        print(f"{committed}: {len(a)} attempts; identical {sum(x == y for x, y in pairs)}; differ beyond counts "
              f"{sum(counts(x) != counts(y) for x, y in pairs)}; gained {sum(x['success'] > y['success'] for x, y in pairs)}; "
              f"lost {sum(x['success'] < y['success'] for x, y in pairs)}; wrong {sum(x['wrong'] for x in a)} "
              f"(committed {sum(y['wrong'] for y in b)}); evaluator calls {sum(x['evaluator_calls'] for x in a)} "
              f"(committed {sum(y['evaluator_calls'] for y in b)})", flush=True)


if __name__ == "__main__":
    main()
