from pathlib import Path
from tempfile import TemporaryDirectory

from asm import ASMEngine, __version__


def relation_hypotheses(expansion):
    return [
        item
        for item in expansion["hypotheses"]
        if item["hypothesis"].startswith("RELATION:")
    ]


def top_relation(expansion):
    rels = relation_hypotheses(expansion)
    return rels[0]["hypothesis"] if rels else None


def names(expansion):
    return {x["hypothesis"] for x in expansion["hypotheses"]}


def main():
    assert __version__ == "0.4.0-alpha.7.9"

    with TemporaryDirectory() as td:
        asm = ASMEngine(Path(td) / "test.db")

        training = [
            # Same first relation: INCREASE, different continuation.
            "repeated requests increase queue pressure; queue pressure crosses threshold, server fails",
            "repeated charging increases battery heat; battery heat crosses threshold, battery shuts down",
            "repeated traffic increases road pressure; road pressure crosses threshold, traffic flow fails",

            "daily practice increases skill; skill enables accurate performance",
            "study increases knowledge; knowledge enables problem solving",
            "training increases strength; strength enables lifting",

            "signal increases voltage; high voltage triggers alarm",
            "current increases circuit voltage; high circuit voltage triggers protection",
            "electrical load increases current; high current triggers breaker",

            # Separate CAUSE family.
            "high wind causes branch motion; branch motion triggers sensor alarm",
            "strong sound causes membrane motion; membrane motion triggers detector response",
        ]

        for _ in range(3):
            for observation in training:
                asm.process(observation, training=True)

        heat = asm.expand_problem(
            "repeated computation increases processor temperature"
        )
        learning = asm.expand_problem(
            "practice increases ability"
        )
        electrical = asm.expand_problem(
            "electrical input increases voltage"
        )
        motion = asm.expand_problem(
            "ground movement causes building motion"
        )

        assert top_relation(heat) == "RELATION:THRESHOLD", heat["hypotheses"]
        assert "CUE:FAILURE" in names(heat), heat["hypotheses"]
        assert top_relation(learning) == "RELATION:ENABLE", learning["hypotheses"]
        assert top_relation(electrical) == "RELATION:TRIGGER", electrical["hypotheses"]
        assert top_relation(motion) == "RELATION:TRIGGER", motion["hypotheses"]

        assert "ABS:INCREASE>THRESHOLD" in asm.structural_memory.abstractions
        assert "ABS:INCREASE>ENABLE" in asm.structural_memory.abstractions
        assert "ABS:INCREASE>TRIGGER" in asm.structural_memory.abstractions

        before = asm.stats()
        asm.close()

        asm2 = ASMEngine(Path(td) / "test.db")
        assert asm2.stats()["structural_abstractions"] == before["structural_abstractions"]
        assert top_relation(
            asm2.expand_problem(
                "repeated computation increases processor temperature"
            )
        ) == "RELATION:THRESHOLD"

        print("ASM v0.4.0-alpha.7.9 smoke test passed.")
        print({
            "heat_top_relation": top_relation(heat),
            "learning_top_relation": top_relation(learning),
            "electrical_top_relation": top_relation(electrical),
            "motion_top_relation": top_relation(motion),
            "heat_top_hypotheses": heat["hypotheses"][:5],
            "abstractions": before["structural_abstractions"],
        })

        asm2.close()


if __name__ == "__main__":
    main()
