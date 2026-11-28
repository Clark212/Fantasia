import argparse
import json
import time
from pathlib import Path

from asm import ASMEngine, __version__


def load_lines(path: Path):
    if path.suffix.lower() == ".jsonl":
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                if isinstance(obj, str):
                    yield obj
                elif isinstance(obj, dict):
                    text = obj.get("text")
                    if text:
                        yield str(text)
    else:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield line


def main():
    parser = argparse.ArgumentParser(
        description="Feed text data into ASM's continuous-learning core."
    )
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--db", type=Path, default=Path("asm_state.db"))
    parser.add_argument(
        "--reset-sequence",
        action="store_true",
        help="Treat each line as an independent observation instead of a temporal sequence.",
    )
    args = parser.parse_args()

    asm = ASMEngine(args.db)
    start = time.perf_counter()

    count = 0
    surprise_sum = 0.0

    for text in load_lines(args.dataset):
        if args.reset_sequence:
            asm.previous_workspace = []

        result = asm.process(text, training=True)
        surprise_sum += result["surprise"]
        count += 1

        if count % 250 == 0:
            print(f"trained {count:,} events...")

    asm.save()
    elapsed = time.perf_counter() - start

    print(f"\nASM v{__version__} training complete")
    print(f"events trained : {count:,}")
    print(f"elapsed        : {elapsed:.3f} s")
    print(f"events/second  : {(count / elapsed) if elapsed else 0:.1f}")
    print(f"mean surprise  : {(surprise_sum / count) if count else 0:.4f}")
    print(f"state          : {asm.stats()}")

    asm.close()


if __name__ == "__main__":
    main()
