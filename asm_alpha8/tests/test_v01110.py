import tempfile
import unittest
from pathlib import Path

from asm import ASMEngine, __version__
from asm.config import ASMConfig


class TestASM01110(unittest.TestCase):
    def make_engine(self, config=None):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        asm = ASMEngine(Path(td.name) / "asm.db", config=config)
        self.addCleanup(asm.close)
        return asm

    def test_version(self):
        self.assertEqual(__version__, '0.4.0-alpha.7.9')

    def test_self_discovered_negation_preserves_polarity(self):
        asm = self.make_engine()
        for text in [
            "box glarps item",
            "crate glarps object",
            "container glarps component",
        ]:
            asm.process(text, training=True)

        d = asm.relation_discovery.infer_text(
            "vessel does not glarp module"
        )
        self.assertTrue(d.frame.supported)
        self.assertTrue(d.frame.relations[0].negated)

    def test_same_connector_can_form_two_senses(self):
        asm = self.make_engine()
        for text in [
            "acid morks metal",
            "heat morks vapor",
            "pressure morks fracture",
            "acid morks alloy",
            "heat morks steam",
            "pressure morks crack",
            "box morks tool",
            "bag morks coin",
            "shelf morks book",
            "crate morks part",
            "pocket morks key",
            "drawer morks file",
        ]:
            asm.process(text, training=True)

        physics = asm.infer_discovered_relation(
            "temperature morks gas"
        )
        container = asm.infer_discovered_relation(
            "cabinet morks document"
        )
        self.assertTrue(physics["supported"])
        self.assertTrue(container["supported"])
        self.assertNotEqual(
            physics["relation_ids"][0],
            container["relation_ids"][0],
        )

    def test_free_language_nested_belief(self):
        asm = self.make_engine()
        asm.process(
            "Alice suspects Bob thinks the key is hidden",
            training=True,
        )
        state = asm.nested_belief(
            ["Alice", "Bob"],
            "key is hidden",
        )
        self.assertTrue(state["truth"])

    def test_newer_natural_belief_can_revise_nested_state(self):
        asm = self.make_engine()
        asm.process(
            "Mina thinks Theo believes that the lamp is not on",
            training=True,
        )
        asm.process(
            "Mina is convinced Theo believes the lamp is on",
            training=True,
        )
        state = asm.nested_belief(
            ["Mina", "Theo"],
            "lamp is on",
        )
        self.assertTrue(state["truth"])

    def test_natural_appraisal_language(self):
        asm = self.make_engine()
        teaching = [
            "Dan fears that danger continues",
            "Dan believes that danger does not continue",
            "Dan felt relieved because the danger ended",
        ]
        for text in teaching:
            asm.process(text, training=True)

        asm.process(
            "Hugo had been afraid the danger would remain",
            training=True,
        )
        asm.process(
            "Hugo found out the danger was gone",
            training=True,
        )
        emotions = asm.infer_agent_emotion("Hugo")
        self.assertTrue(emotions)
        self.assertEqual(emotions[0]["emotion"], "relieved")

    def test_language_updates_self_model(self):
        asm = self.make_engine()
        for text in [
            "I tried analogy and it failed",
            "I used analogy again and it failed",
            "simulation worked successfully",
        ]:
            asm.process(text, training=True)

        cap = asm.capability("reasoning")
        self.assertEqual(cap["attempts"], 3)
        ranked = asm.choose_strategy(
            "reasoning",
            ["analogy", "simulation"],
        )
        self.assertEqual(ranked[0]["strategy"], "simulation")

    def test_relation_capacity_is_hard_bounded(self):
        cfg = ASMConfig(relation_discovery_max_relations=12)
        asm = self.make_engine(config=cfg)
        for i in range(18):
            for _ in range(3):
                asm.process(
                    f"left{i} connector{i} right{i}",
                    training=True,
                )
        stats = asm.relation_discovery.stats()
        self.assertLessEqual(stats["relations"], 12)
        self.assertGreater(stats["capacity_rejections"], 0)


if __name__ == "__main__":
    unittest.main()
