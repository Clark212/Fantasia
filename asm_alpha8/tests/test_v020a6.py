import tempfile
import unittest
from pathlib import Path

from asm import ASMEngine, __version__, CallableLanguageCore, LanguageProposal, LanguageReadResult, LanguageGenerationResult


def scripted_core(proposals):
    def reader(text):
        return LanguageReadResult(
            text=text,
            backend="scripted-alpha6",
            tokens=text.lower().split(),
            embedding=[0.0] * 8,
            proposals=list(proposals),
            metadata={"test": True},
        )
    def writer(state, instruction):
        return LanguageGenerationResult("", "scripted-alpha6")
    return CallableLanguageCore(reader, writer, name="scripted-alpha6", capabilities={"learned_language": True})


class TestSemanticEventCortexAlpha6(unittest.TestCase):
    def make_engine(self, core=None):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        asm = ASMEngine(Path(td.name) / "asm.db", language_core=core)
        self.addCleanup(asm.close)
        return asm

    def test_version(self):
        self.assertEqual(__version__, "0.4.0-alpha.7.9")

    def test_expectation_is_not_written_as_belief(self):
        asm = self.make_engine()
        r = asm.process("Oren expects the bridge to open", training=True)
        self.assertEqual(r["semantic_event"]["primary"]["event_type"], "expectation")
        self.assertEqual(r["semantic_event"]["primary"]["epistemic"], "expected")
        self.assertIsNone(r["mind_event"])
        self.assertIsNotNone(r["drive_event"])
        self.assertEqual(r["drive_event"]["kind"], "expectation")
        self.assertEqual(asm.belief("Oren", "bridge open")["status"], "unknown")

    def test_fear_is_not_written_as_belief(self):
        asm = self.make_engine()
        r = asm.process("Kelan worries that the fence has collapsed", training=True)
        self.assertEqual(r["semantic_event"]["primary"]["event_type"], "fear")
        self.assertEqual(r["semantic_event"]["primary"]["epistemic"], "feared")
        self.assertIsNone(r["mind_event"])
        self.assertEqual(r["drive_event"]["kind"], "fear")
        self.assertEqual(asm.belief("Kelan", "fence collapsed")["status"], "unknown")

    def test_goal_is_not_written_as_belief(self):
        asm = self.make_engine()
        r = asm.process("Mira hopes the mission succeeds", training=True)
        self.assertEqual(r["semantic_event"]["primary"]["event_type"], "goal")
        self.assertIsNone(r["mind_event"])
        self.assertEqual(r["drive_event"]["kind"], "goal")

    def test_belief_remains_belief(self):
        asm = self.make_engine()
        r = asm.process("Alice believes the silver valve is closed", training=True)
        ev = r["semantic_event"]["primary"]
        self.assertEqual(ev["event_type"], "belief")
        self.assertEqual(ev["epistemic"], "believed")
        self.assertEqual(ev["proposition"]["surface"], "silver valve is closed")
        self.assertIn("silver valve", ev["proposition"]["canonical"])
        self.assertIsNotNone(r["mind_event"])

    def test_query_cannot_become_persistent_belief(self):
        asm = self.make_engine()
        before = asm.memory.count_events()
        r = asm.process("Does Alice believe the gate is open?")
        self.assertEqual(r["semantic_event"]["primary"]["event_type"], "question")
        self.assertIsNone(r["mind_event"])
        self.assertFalse(r["consolidation"]["persist"])
        self.assertEqual(asm.memory.count_events(), before)

    def test_hypothetical_belief_abstains_from_write(self):
        asm = self.make_engine()
        r = asm.process("Alice believes the gate might be open")
        self.assertTrue(r["semantic_event"]["abstained"])
        self.assertEqual(r["semantic_event"]["primary"]["epistemic"], "hypothetical")
        self.assertFalse(r["semantic_event"]["primary"]["persistent_eligible"])
        self.assertIsNone(r["mind_event"])
        self.assertEqual(asm.belief("Alice", "gate open")["status"], "unknown")

    def test_bad_neural_belief_conflicting_with_native_fear_is_rejected(self):
        core = scripted_core([
            LanguageProposal(
                "belief",
                {"holder": "Kelan", "proposition_text": "fence has collapsed", "polarity": True},
                0.9991,
                source="bad-extractor",
            )
        ])
        asm = self.make_engine(core)
        r = asm.process("Kelan worries that the fence has collapsed", training=True)
        self.assertEqual(r["language_core"]["accepted"], [])
        self.assertEqual(r["language_core"]["rejected"][0]["reason"], "semantic_type_conflict")
        self.assertIsNone(r["mind_event"])
        self.assertEqual(r["drive_event"]["kind"], "fear")
        self.assertEqual(asm.belief("Kelan", "fence collapsed")["status"], "unknown")

    def test_opaque_external_proposal_still_works_when_no_conflicting_evidence(self):
        core = scripted_core([
            LanguageProposal(
                "belief",
                {"holder": "Nova", "proposition_text": "reactor is safe", "polarity": True},
                0.95,
                source="external-reader",
            )
        ])
        asm = self.make_engine(core)
        r = asm.process("opaque neural input", training=True)
        self.assertEqual(len(r["language_core"]["accepted"]), 1)
        self.assertEqual(r["semantic_event"]["primary"]["event_type"], "belief")
        self.assertTrue(asm.belief("Nova", "reactor is safe")["truth"])


    def test_multiple_neural_semantic_proposals_cannot_double_write(self):
        core = scripted_core([
            LanguageProposal(
                "belief",
                {"holder": "Kelan", "proposition_text": "fence has collapsed", "polarity": True},
                0.98,
                source="noisy-extractor",
            ),
            LanguageProposal(
                "drive",
                {"holder": "Kelan", "kind": "fear", "proposition_text": "fence has collapsed", "priority": 0.7},
                0.96,
                source="noisy-extractor",
            ),
        ])
        asm = self.make_engine(core)
        r = asm.process("opaque multi-head neural input", training=True)
        self.assertEqual(len(r["language_core"]["accepted"]), 1)
        self.assertEqual(r["language_core"]["accepted"][0]["kind"], "drive")
        self.assertTrue(any(x["reason"] == "semantic_proposal_conflict" for x in r["language_core"]["rejected"]))
        self.assertIsNone(r["mind_event"])
        self.assertEqual(r["drive_event"]["kind"], "fear")
        self.assertEqual(asm.belief("Kelan", "fence collapsed")["status"], "unknown")

    def test_semantic_event_features_enter_seismic_field(self):
        asm = self.make_engine()
        asm.process("Oren expects the bridge to open", training=True)
        self.assertIn("SEMEVENT:TYPE:EXPECTATION", asm.field.nodes)
        self.assertIn("SEMEVENT:EPISTEMIC:EXPECTED", asm.field.nodes)
        self.assertIn("SEMEVENT:AGENT:oren", asm.field.nodes)

    def test_semantic_cortex_health_exposed(self):
        asm = self.make_engine()
        status = asm.language_core_status()["semantic_event_cortex"]
        self.assertTrue(status["ready"])
        self.assertEqual(status["architecture"], "typed-semantic-event-arbitration")


if __name__ == "__main__":
    unittest.main()
