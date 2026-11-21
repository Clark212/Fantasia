import tempfile
import unittest
from pathlib import Path

from asm import ASMEngine, __version__
from asm.attention import AttentionSystem
from asm.config import ASMConfig


class TestASM0117(unittest.TestCase):
    def make_engine(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        asm = ASMEngine(Path(td.name) / "asm.db")
        self.addCleanup(asm.close)
        return asm

    def test_version(self):
        self.assertEqual(__version__, '0.4.0-alpha.7.9')

    def test_second_order_belief_is_separate(self):
        asm = self.make_engine()
        asm.process(
            "Alice believes Bob believes that the box is full",
            training=True,
        )

        nested = asm.nested_belief(
            ["Alice", "Bob"],
            "the box is full",
        )
        direct_bob = asm.belief("Bob", "the box is full")

        self.assertEqual(nested["status"], "believed_true")
        self.assertTrue(nested["truth"])
        self.assertEqual(nested["order"], 2)
        self.assertEqual(direct_bob["status"], "unknown")

    def test_third_order_belief(self):
        asm = self.make_engine()
        asm.process(
            "Alice believes Bob thinks Cara believes that the key is hidden",
            training=True,
        )
        state = asm.nested_belief(
            ["Alice", "Bob", "Cara"],
            "the key is hidden",
        )
        self.assertEqual(state["status"], "believed_true")
        self.assertEqual(state["order"], 3)

    def test_nested_revision_does_not_rewrite_direct_agent(self):
        asm = self.make_engine()

        asm.process(
            "Alice believes Bob believes that the door is locked",
            training=True,
        )
        asm.process(
            "Bob believes that the door is not locked",
            training=True,
        )

        alice_model = asm.nested_belief(
            ["Alice", "Bob"],
            "door is locked",
        )
        bob_direct = asm.belief("Bob", "door is locked")

        self.assertTrue(alice_model["truth"])
        self.assertFalse(bob_direct["truth"])

    def test_self_capability_revises_from_outcomes(self):
        asm = self.make_engine()

        for _ in range(4):
            asm.report_strategy_outcome(
                "symbolic_math",
                "direct_rule",
                True,
            )
        high = asm.capability("symbolic_math")

        for _ in range(8):
            asm.report_strategy_outcome(
                "symbolic_math",
                "direct_rule",
                False,
            )
        low = asm.capability("symbolic_math")

        self.assertGreater(high["success_probability"], 0.6)
        self.assertLess(low["success_probability"], high["success_probability"])
        self.assertLess(low["success_probability"], 0.5)

    def test_strategy_adaptation(self):
        asm = self.make_engine()

        for _ in range(5):
            asm.report_strategy_outcome(
                "search_problem",
                "strategy_a",
                False,
            )
        for _ in range(3):
            asm.report_strategy_outcome(
                "search_problem",
                "strategy_b",
                True,
            )

        ranked = asm.choose_strategy(
            "search_problem",
            ["strategy_a", "strategy_b"],
        )
        self.assertEqual(ranked[0]["strategy"], "strategy_b")

    def test_frustration_like_state_rises_after_repeated_failure(self):
        asm = self.make_engine()
        before = asm.self_state()["internal"]["frustration_like"]

        for _ in range(5):
            asm.report_strategy_outcome(
                "reasoning",
                "same_failed_path",
                False,
            )

        after = asm.self_state()["internal"]["frustration_like"]
        self.assertGreater(after, before)
        self.assertGreater(after, 0.4)

    def test_attention_switches_epicenter(self):
        cfg = ASMConfig()
        attention = AttentionSystem(cfg)

        first = attention.update(
            [("CONCEPT:A", 1.0), ("CONCEPT:B", 0.2)],
            surprise=0.2,
            magnitude=0.3,
            event_id=1,
        )
        second = attention.update(
            [("CONCEPT:Z", 5.0), ("CONCEPT:Y", 0.1)],
            surprise=1.0,
            magnitude=1.0,
            event_id=2,
        )

        self.assertEqual(first["epicenter"], "CONCEPT:A")
        self.assertEqual(second["epicenter"], "CONCEPT:Z")
        self.assertTrue(second["shifted"])

    def test_prediction_surprise_drives_curiosity(self):
        asm = self.make_engine()
        # First encounter should be highly novel to an empty model.
        result = asm.process(
            "quantum pineapple rotates invisible lattice",
            training=True,
        )
        self.assertGreater(
            result["self_state"]["curiosity"],
            0.2,
        )

    def test_persistence(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "persist.db"
            asm = ASMEngine(db)

            asm.process(
                "Alice believes Bob believes that the key is hidden",
                training=True,
            )
            asm.report_strategy_outcome(
                "reasoning",
                "analogy",
                False,
            )
            asm.report_strategy_outcome(
                "reasoning",
                "simulation",
                True,
            )
            before_attention = asm.attention_state()["epicenter"]
            asm.close()

            asm2 = ASMEngine(db)
            try:
                self.assertTrue(
                    asm2.nested_belief(
                        ["Alice", "Bob"],
                        "key is hidden",
                    )["truth"]
                )
                self.assertEqual(
                    asm2.choose_strategy(
                        "reasoning",
                        ["analogy", "simulation"],
                    )[0]["strategy"],
                    "simulation",
                )
                self.assertEqual(
                    asm2.attention_state()["epicenter"],
                    before_attention,
                )
            finally:
                asm2.close()


if __name__ == "__main__":
    unittest.main()
