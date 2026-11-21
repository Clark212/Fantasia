"""
ASM v0.1.1 micro-benchmark.

This is intentionally small and reproducible. It measures architecture behavior,
not general intelligence:
  1) Does repeated experience improve next-state prediction?
  2) Does surprise decrease for a learned transition?
  3) Can an old memory survive >400 later events?
  4) Can online context learning connect two surface forms?
"""

from pathlib import Path
from tempfile import TemporaryDirectory

from asm import ASMEngine


def score(result, concept):
    return dict(result["predicted_next"]).get(concept, 0.0)


def main():
    with TemporaryDirectory() as td:
        asm = ASMEngine(Path(td) / "bench.db")

        start = asm.process("red cue")
        baseline = score(start, "STEM:blue")
        first_blue = asm.process("blue response")
        surprise_before = first_blue["surprise"]

        for _ in range(12):
            asm.process("red cue")
            asm.process("blue response")

        after_red = asm.process("red cue")
        prediction_after = score(
            after_red,
            "STEM:blue",
        )
        after_blue = asm.process("blue response")
        surprise_after = after_blue["surprise"]

        for _ in range(4):
            asm.process("doctor examines patient clinic")
            asm.process("physician examines patient clinic")

        semantic = asm.encoder.encode("physician")
        semantic_pass = "STEM:doctor" in semantic

        old = asm.process("ancientmarker uniquevault")
        old_id = old["event_id"]
        for i in range(425):
            asm.process(f"noise{i} filler")
        hits = asm.memory.recall(
            asm.encoder.encode("uniquevault"),
            limit=5,
        )
        old_memory_pass = old_id in {
            item["id"]
            for item in hits
        }

        print("ASM v0.1.1 micro-benchmark")
        print("-" * 36)
        print(
            f"next-state prediction gain : "
            f"{prediction_after - baseline:+.4f}"
        )
        print(
            f"surprise reduction         : "
            f"{surprise_before - surprise_after:+.4f}"
        )
        print(
            f"semantic context alias     : "
            f"{'PASS' if semantic_pass else 'FAIL'}"
        )
        print(
            f">400-event memory retrieval: "
            f"{'PASS' if old_memory_pass else 'FAIL'}"
        )
        print(f"final stats                : {asm.stats()}")

        asm.close()


if __name__ == "__main__":
    main()
