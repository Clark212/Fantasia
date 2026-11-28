import tempfile
import unittest
from pathlib import Path

from asm import ASMEngine, __version__


class TestASM0115(unittest.TestCase):
    def make_engine(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        db = Path(td.name) / "asm.db"
        asm = ASMEngine(db)
        self.addCleanup(asm.close)
        return asm

    def test_version(self):
        self.assertEqual(__version__, '0.4.0-alpha.7.9')

    def test_false_belief_is_separate_from_world(self):
        asm = self.make_engine()
        asm.process(
            "Alex believes that the door is locked",
            training=True,
        )
        asm.process(
            "Actually, the door is not locked",
            training=True,
        )

        comparison = asm.compare_belief(
            "Alex",
            "the door is locked",
        )

        self.assertEqual(
            comparison["agent"]["status"],
            "believed_true",
        )
        self.assertTrue(comparison["agent"]["truth"])

        self.assertEqual(
            comparison["world"]["status"],
            "believed_false",
        )
        self.assertFalse(comparison["world"]["truth"])

    def test_belief_revision_adapts(self):
        asm = self.make_engine()

        asm.process(
            "Alex believes the door is locked",
            training=True,
        )
        asm.process(
            "Alex believes the door is locked",
            training=True,
        )
        before = asm.belief("Alex", "door is locked")
        self.assertTrue(before["truth"])

        asm.process(
            "Alex believes the door is not locked",
            training=True,
        )
        middle = asm.belief("Alex", "door is locked")
        self.assertIn(
            middle["status"],
            {"uncertain", "believed_false"},
        )

        asm.process(
            "Alex believes the door is not locked",
            training=True,
        )
        after = asm.belief("Alex", "door is locked")
        self.assertEqual(after["status"], "believed_false")
        self.assertFalse(after["truth"])

    def test_learns_emotion_labels_from_examples(self):
        asm = self.make_engine()

        examples = [
            "Maya felt disappointed because the goal failed",
            "Kai felt disappointed because the plan failed",
            "Noah felt relieved because the danger ended",
            "Lina felt relieved because the threat ended",
            "Iris felt frustrated because the attempt failed repeatedly",
            "Omar felt frustrated because the task failed repeatedly",
        ]
        for text in examples:
            asm.process(text, training=True)

        failed = asm.infer_emotion("the project failed")
        ended = asm.infer_emotion("the danger ended")

        self.assertTrue(failed)
        self.assertEqual(failed[0]["emotion"], "disappointed")
        self.assertTrue(ended)
        self.assertEqual(ended[0]["emotion"], "relieved")

    def test_self_created_concept_forms_and_reactivates(self):
        asm = self.make_engine()

        observations = [
            "repeated requests increase queue pressure; queue pressure crosses threshold, server fails",
            "repeated charging increases battery heat; battery heat crosses threshold, battery shuts down",
            "repeated traffic increases road pressure; road pressure crosses threshold, traffic flow fails",
        ]
        for text in observations:
            asm.process(text, training=True)

        promoted = asm.latent_concepts()
        self.assertTrue(promoted)
        concept_id = promoted[0]["id"]
        self.assertTrue(concept_id.startswith("LATENT:"))

        query = (
            "repeated computation increases processor temperature; "
            "processor temperature crosses threshold, processor fails"
        )
        expansion = asm.expand_problem(query)
        active_ids = {
            item["id"]
            for item in expansion["latent_concepts"]
        }
        self.assertIn(concept_id, active_ids)

    def test_persistence_of_new_cognition(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "persist.db"
            asm = ASMEngine(db)

            asm.process(
                "Alex believes the door is locked",
                training=True,
            )
            asm.process(
                "Maya felt disappointed because the goal failed",
                training=True,
            )
            asm.process(
                "Kai felt disappointed because the plan failed",
                training=True,
            )
            for text in [
                "repeated requests increase queue pressure; queue pressure crosses threshold, server fails",
                "repeated charging increases battery heat; battery heat crosses threshold, battery shuts down",
                "repeated traffic increases road pressure; road pressure crosses threshold, traffic flow fails",
            ]:
                asm.process(text, training=True)
            before = asm.stats()
            asm.close()

            asm2 = ASMEngine(db)
            try:
                self.assertEqual(
                    asm2.belief("Alex", "door is locked")["status"],
                    "believed_true",
                )
                self.assertEqual(
                    asm2.infer_emotion("the project failed")[0]["emotion"],
                    "disappointed",
                )
                self.assertEqual(
                    asm2.stats()["latent_concepts"],
                    before["latent_concepts"],
                )
            finally:
                asm2.close()


if __name__ == "__main__":
    unittest.main()
