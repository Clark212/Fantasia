import tempfile
import unittest
from pathlib import Path

from asm import ASMEngine, __version__


CANON = [
    "practice increases skill",
    "study increases knowledge",
    "training increases ability",
    "charging increases battery heat",
    "traffic increases road pressure",
    "rendering increases component temperature",

    "filtering reduces signal noise",
    "maintenance reduces system error",
    "cooling reduces component temperature",
    "compression reduces processing delay",
    "rest reduces muscle fatigue",
    "optimization reduces latency",

    "wind causes branch motion",
    "sound causes membrane motion",
    "vibration causes machine motion",
    "pressure causes membrane movement",
    "force causes object motion",
    "heat causes material expansion",

    "signal triggers alarm",
    "motion triggers detector response",
    "voltage triggers protection",
    "current triggers breaker",
    "pulse triggers reaction",
    "movement triggers sensor response",

    "practice enables accurate performance",
    "training enables lifting",
    "knowledge enables problem solving",
    "permission enables access",
    "power enables operation",
    "preparation enables success",

    "filter prevents contamination",
    "firewall prevents intrusion",
    "brake prevents motion",
    "shield prevents damage",
    "cooling prevents overheating",
    "validation prevents error",

    "water becomes vapor",
    "material becomes brittle",
    "signal becomes stable",
    "ice becomes liquid",
    "seed becomes plant",
    "system becomes ready",
]


class TestASM0118(unittest.TestCase):
    def make_engine(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        asm = ASMEngine(Path(td.name) / "asm.db")
        self.addCleanup(asm.close)
        for _ in range(3):
            for text in CANON:
                asm.process(text, training=True)
        return asm

    def test_version(self):
        self.assertEqual(__version__, '0.4.0-alpha.7.9')

    def assert_relation(self, asm, text, expected):
        result = asm.parse_open(text)
        self.assertTrue(result["supported"], result)
        self.assertEqual(result["signature"][0], expected, result)
        return result

    def test_unlisted_relation_words_generalize_from_context(self):
        asm = self.make_engine()
        cases = [
            ("practice sharpens ability", "INCREASE"),
            ("optimization trims system error", "DECREASE"),
            ("wind induces antenna motion", "CAUSE"),
            ("electrical pulse provokes alarm", "TRIGGER"),
            ("practice unlocks performance", "ENABLE"),
            ("firewall thwarts intrusion", "PREVENT"),
            ("water transforms into vapor", "BECOME"),
        ]
        for text, expected in cases:
            first = asm.parse_open(text)
            self.assertFalse(first["supported"], first)
            observed = asm.process(text, training=True)
            self.assertTrue(
                observed["perception"]["learned_after_observation"],
                observed["perception"],
            )
            self.assert_relation(asm, text, expected)

    def test_multiword_and_modifier_heavy_wording(self):
        asm = self.make_engine()
        for text, expected in [
            ("sustained rendering drives temperature higher", "INCREASE"),
            ("material morphs into brittle state", "BECOME"),
        ]:
            asm.process(text, training=True)
            self.assert_relation(asm, text, expected)

    def test_simple_negation_survives_learned_parse(self):
        asm = self.make_engine()
        asm.process(
            "practice does not sharpen ability",
            training=True,
        )
        self.assert_relation(
            asm,
            "practice does not sharpen ability",
            "NOT:INCREASE",
        )

    def test_one_experience_teaches_new_connector(self):
        asm = self.make_engine()

        before = asm.parse_open("exercise sharpens capability")
        self.assertFalse(before["supported"])

        learned = asm.process(
            "practice sharpens ability",
            training=True,
        )
        self.assertEqual(learned["perception"]["source"], "abstain")
        self.assertTrue(learned["perception"]["learned_after_observation"])

        after = asm.parse_open("exercise sharpens capability")
        self.assertTrue(after["supported"], after)
        self.assertEqual(after["signature"], ["INCREASE"])
        self.assertGreater(after["confidence"], before["confidence"])

    def test_open_perception_abstains_when_evidence_is_not_enough(self):
        asm = self.make_engine()
        for text in [
            "purple banana glorp quantum sandwich",
            "mysterious object flarns unrelated entity",
        ]:
            result = asm.parse_open(text)
            self.assertFalse(result["supported"], result)

    def test_questions_and_conditionals_do_not_become_facts(self):
        asm = self.make_engine()
        for text in [
            "Could practice sharpen ability?",
            "if practice sharpens ability then performance improves",
        ]:
            result = asm.parse_open(text)
            self.assertFalse(result["supported"], result)
            self.assertEqual(result["source"], "abstain")

    def test_learned_connector_persists(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "persist.db"
            asm = ASMEngine(db)
            for _ in range(3):
                for text in CANON:
                    asm.process(text, training=True)
            asm.process("practice sharpens ability", training=True)
            asm.close()

            asm2 = ASMEngine(db)
            try:
                result = asm2.parse_open("exercise sharpens capability")
                self.assertTrue(result["supported"], result)
                self.assertEqual(result["signature"], ["INCREASE"])
                self.assertGreaterEqual(
                    asm2.stats()["perception_inferred_phrases"],
                    1,
                )
            finally:
                asm2.close()


if __name__ == "__main__":
    unittest.main()
