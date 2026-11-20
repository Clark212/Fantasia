import tempfile
import unittest
from pathlib import Path

from asm import ASMEngine, __version__


def teach_appraisals(asm):
    sequences = [
        [
            "Alice wants that project succeeds",
            "Alice believes that project succeeds",
            "Alice felt proud because the project succeeded",
        ],
        [
            "Ben wants that project succeeds",
            "Ben believes that project does not succeed",
            "Ben felt disappointed because the project failed",
        ],
        [
            "Cara fears that danger continues",
            "Cara believes that danger continues",
            "Cara felt anxious because the danger continued",
        ],
        [
            "Dan fears that danger continues",
            "Dan believes that danger does not continue",
            "Dan felt relieved because the danger ended",
        ],
    ]
    for seq in sequences:
        for text in seq:
            asm.process(text, training=True)


class TestASM0116(unittest.TestCase):
    def make_engine(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        db = Path(td.name) / "asm.db"
        asm = ASMEngine(db)
        self.addCleanup(asm.close)
        return asm

    def test_version(self):
        self.assertEqual(__version__, '0.4.0-alpha.7.9')

    def test_goal_blocked_appraisal_transfers(self):
        asm = self.make_engine()
        teach_appraisals(asm)

        asm.process("Eli wants that mission succeeds", training=True)
        asm.process("Eli believes that mission does not succeed", training=True)

        state = asm.appraisal_state("Eli")
        self.assertIn("APPRAISAL:GOAL_BLOCKED", state["features"])

        emotions = asm.infer_agent_emotion("Eli")
        self.assertTrue(emotions)
        self.assertEqual(emotions[0]["emotion"], "disappointed")
        self.assertEqual(emotions[0]["source"], "appraisal")

    def test_goal_achieved_appraisal_transfers(self):
        asm = self.make_engine()
        teach_appraisals(asm)

        asm.process("Faye wants that mission succeeds", training=True)
        asm.process("Faye believes that mission succeeds", training=True)

        emotions = asm.infer_agent_emotion("Faye")
        self.assertTrue(emotions)
        self.assertEqual(emotions[0]["emotion"], "proud")

    def test_threat_present_and_removed(self):
        asm = self.make_engine()
        teach_appraisals(asm)

        asm.process("Gus fears that storm continues", training=True)
        asm.process("Gus believes that storm continues", training=True)

        asm.process("Hope fears that storm continues", training=True)
        asm.process("Hope believes that storm does not continue", training=True)

        self.assertEqual(
            asm.infer_agent_emotion("Gus")[0]["emotion"],
            "anxious",
        )
        self.assertEqual(
            asm.infer_agent_emotion("Hope")[0]["emotion"],
            "relieved",
        )

    def test_same_outcome_different_agent_state(self):
        asm = self.make_engine()
        teach_appraisals(asm)

        asm.process("Ivy wants that red_team wins", training=True)
        asm.process("Ivy believes that red_team wins", training=True)

        asm.process("Jay fears that red_team wins", training=True)
        asm.process("Jay believes that red_team wins", training=True)

        ivy = asm.infer_agent_emotion("Ivy")[0]["emotion"]
        jay = asm.infer_agent_emotion("Jay")[0]["emotion"]

        self.assertEqual(ivy, "proud")
        self.assertEqual(jay, "anxious")
        self.assertNotEqual(ivy, jay)

    def test_appraisal_updates_after_belief_revision(self):
        asm = self.make_engine()
        teach_appraisals(asm)

        asm.process("Kira wants that mission succeeds", training=True)
        asm.process("Kira believes that mission does not succeed", training=True)
        before = asm.infer_agent_emotion("Kira")[0]["emotion"]
        self.assertEqual(before, "disappointed")

        # Repeated contradictory evidence shifts the holder's belief.
        asm.process("Kira believes that mission succeeds", training=True)
        asm.process("Kira believes that mission succeeds", training=True)
        after = asm.infer_agent_emotion("Kira")[0]["emotion"]
        self.assertEqual(after, "proud")

    def test_appraisal_persists(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "persist.db"
            asm = ASMEngine(db)
            teach_appraisals(asm)
            asm.process("Milo wants that mission succeeds", training=True)
            asm.process("Milo believes that mission does not succeed", training=True)
            asm.close()

            asm2 = ASMEngine(db)
            try:
                self.assertEqual(
                    asm2.infer_agent_emotion("Milo")[0]["emotion"],
                    "disappointed",
                )
            finally:
                asm2.close()


if __name__ == "__main__":
    unittest.main()
