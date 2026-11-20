import math
import tempfile
import unittest
from pathlib import Path

from asm import (
    ASMEngine,
    ASMConfig,
    CallableLanguageCore,
    LanguageGenerationResult,
    LanguageProposal,
    LanguageReadResult,
    __version__,
)
from asm.language_core import LanguageCore


class BrokenCore(LanguageCore):
    name = "broken"
    native_passthrough = False

    def read(self, text):
        raise RuntimeError("simulated reader failure")

    def generate(self, state, *, instruction=""):
        return LanguageGenerationResult("broken", self.name)


def scripted_core(proposals, *, generated="scripted response", name="scripted"):
    def reader(text):
        return LanguageReadResult(
            text=text,
            backend=name,
            tokens=["opaque"],
            embedding=[0.25, 0.5, -0.25, 0.0],
            proposals=list(proposals),
            metadata={"test": True},
        )

    def writer(state, instruction):
        return LanguageGenerationResult(
            text=f"{generated}:{instruction}",
            backend=name,
            confidence=0.91,
            metadata={"saw_self_state": "internal" in state},
        )

    return CallableLanguageCore(
        reader,
        writer,
        name=name,
        capabilities={"learned_language": True, "test_backend": True},
    )


class TestASM020Alpha1(unittest.TestCase):
    def make_engine(self, core=None, config=None):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        asm = ASMEngine(Path(td.name) / "asm.db", language_core=core, config=config)
        self.addCleanup(asm.close)
        return asm

    def test_version(self):
        self.assertEqual(__version__, '0.4.0-alpha.7.9')

    def test_fallback_language_core_contract(self):
        asm = self.make_engine(config=ASMConfig(language_core_backend="fallback"))
        result = asm.process(
            "Alice suspects Bob thinks the key is hidden",
            training=True,
        )
        lc = result["language_core"]
        self.assertEqual(lc["backend"], "fallback")
        self.assertEqual(lc["embedding_dims"], asm.cfg.language_core_embedding_dims)
        self.assertTrue(lc["proposals"])
        self.assertTrue(all(x["reason"] == "native_passthrough" for x in lc["rejected"]))
        # Native parser remains authoritative in fallback mode, so no double write.
        state = asm.nested_belief(["Alice", "Bob"], "key is hidden")
        self.assertEqual(state["observations"], 1)

    def test_external_nested_belief_proposal_updates_asm(self):
        core = scripted_core([
            LanguageProposal(
                "nested_belief",
                {"path": ["Nova", "Iris"], "proposition_text": "gate is open", "polarity": True},
                0.93,
                source="mock-recurrent",
            )
        ])
        asm = self.make_engine(core)
        result = asm.process("opaque neural input", training=True)
        state = asm.nested_belief(["Nova", "Iris"], "gate is open")
        self.assertTrue(state["truth"])
        self.assertEqual(len(result["language_core"]["accepted"]), 1)

    def test_low_confidence_proposal_is_rejected(self):
        core = scripted_core([
            LanguageProposal(
                "belief",
                {"holder": "Nova", "proposition_text": "reactor is safe", "polarity": True},
                0.31,
                source="uncertain-core",
            )
        ])
        asm = self.make_engine(core)
        result = asm.process("opaque input", training=True)
        self.assertEqual(asm.belief("Nova", "reactor is safe")["status"], "unknown")
        self.assertEqual(result["language_core"]["rejected"][0]["reason"], "below_confidence_gate")

    def test_external_drive_proposal_enters_appraisal_store(self):
        core = scripted_core([
            LanguageProposal(
                "drive",
                {"holder": "Mira", "kind": "goal", "proposition_text": "mission succeeds", "priority": 0.9},
                0.95,
                source="mock-recurrent",
            )
        ])
        asm = self.make_engine(core)
        asm.process("opaque goal expression", training=True)
        state = asm.appraisal_state("Mira")
        self.assertEqual(len(state["drives"]), 1)
        self.assertEqual(state["drives"][0]["kind"], "goal")

    def test_external_self_outcome_updates_self_model(self):
        core = scripted_core([
            LanguageProposal(
                "self_outcome",
                {"task_family": "reasoning", "strategy": "simulation", "success": True, "score": 0.9},
                0.94,
                source="mock-recurrent",
            )
        ])
        asm = self.make_engine(core)
        before = asm.capability("reasoning")["attempts"]
        asm.process("opaque self experience", training=True)
        after = asm.capability("reasoning")
        self.assertEqual(after["attempts"], before + 1)
        self.assertGreater(after["success_probability"], 0.5)

    def test_generation_is_routed_through_active_core(self):
        asm = self.make_engine(scripted_core([], generated="hello-from-core"))
        out = asm.generate_text("summarize")
        self.assertEqual(out["backend"], "scripted")
        self.assertEqual(out["text"], "hello-from-core:summarize")
        self.assertTrue(out["metadata"]["saw_self_state"])

    def test_fallback_embedding_is_deterministic_and_normalized(self):
        asm = self.make_engine()
        a = asm.embed_text("practice improves skill")
        b = asm.embed_text("practice improves skill")
        self.assertEqual(a, b)
        self.assertEqual(len(a), asm.cfg.language_core_embedding_dims)
        norm = math.sqrt(sum(x*x for x in a))
        self.assertAlmostEqual(norm, 1.0, places=6)

    def test_broken_backend_fails_open_to_fallback(self):
        asm = self.make_engine(BrokenCore())
        result = asm.process("Alice suspects Bob thinks the key is hidden", training=True)
        lc = result["language_core"]
        self.assertEqual(lc["backend"], "fallback")
        self.assertEqual(lc["metadata"]["failover_from"], "broken")
        self.assertIn("simulated reader failure", lc["metadata"]["failover_error"])
        self.assertTrue(asm.nested_belief(["Alice", "Bob"], "key is hidden")["truth"])


if __name__ == "__main__":
    unittest.main()
