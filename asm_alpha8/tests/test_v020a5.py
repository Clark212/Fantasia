import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from asm import ASMConfig, ASMEngine
from asm.cognitive_packet import CognitivePacket
from asm.recurrent_writer import RecurrentWriter


class TestLearnedWriter(unittest.TestCase):
    def engine(self, **kwargs):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        engine = ASMEngine(Path(td.name) / "state.db", ASMConfig(**kwargs))
        self.addCleanup(engine.close)
        return engine

    def test_learned_writer_is_the_normal_chat_path(self):
        e = self.engine()
        for text in ["hi", "how are you", "who are you", "thanks", "bye",
                     "im angry at u", "I'm happy", "zxwq", "Where is the silver canoe?",
                     "The blue controller was repaired yesterday", "what did i just say?"]:
            r = e.chat(text)
            self.assertEqual(r["conversation"]["writer"]["backend"], "recurrent-writer", r)
            self.assertFalse(r["conversation"]["writer"]["fallback"])

    def test_new_fact_can_be_learned_with_frozen_writer(self):
        e = self.engine()
        before = {k: v.clone() for k, v in e.writer.model.state_dict().items()}
        e.chat("Zorina believes the zephyr switch is open")
        r = e.chat("what does Zorina believe about the zephyr switch?")
        self.assertIn("Zorina", r["reply"])
        self.assertIn("zephyr", r["reply"])
        self.assertFalse(r["conversation"]["writer"]["fallback"])
        self.assertTrue(all(not p.requires_grad for p in e.writer.model.parameters()))
        self.assertTrue(all(v.equal(e.writer.model.state_dict()[k]) for k, v in before.items()))

    def test_missing_writer_clean_fallback(self):
        e = self.engine(writer_model_path="/definitely/missing/writer.pt")
        r = e.chat("hello")
        self.assertTrue(r["conversation"]["writer"]["fallback"])
        self.assertIn("Hey", r["reply"])
        self.assertFalse(e.language_core_status()["writer"]["ready"])

    def test_crashed_writer_clean_fallback(self):
        e = self.engine()
        with patch.object(e.writer, "generate", side_effect=RuntimeError("injected failure")):
            r = e.chat("thanks")
        self.assertIn("welcome", r["reply"])
        self.assertIn("injected failure", r["conversation"]["writer"]["fallback_reason"])

    def test_missing_memory_does_not_become_remembered_fact(self):
        e = self.engine()
        r = e.chat("Do you remember Priya winning the canoe race?")
        self.assertNotIn("Priya winning", r["reply"])
        self.assertEqual(r["conversation"]["packet"]["user_intent"], "uncertainty")

    def test_no_cross_agent_belief_claim(self):
        e = self.engine()
        e.chat("Tessa believes the lantern is broken")
        r = e.chat("what does Marin believe about the lantern?")
        self.assertIn("don't have", r["reply"])
        self.assertNotIn("Marin believes", r["reply"])

    def test_opaque_content_is_copied_once(self):
        writer = RecurrentWriter()
        content = 'new names: Velora 917; <claim> <confidence> 日本語'
        r = writer.generate(CognitivePacket("memory_report", {"claim": content}))
        self.assertFalse(r["fallback"])
        self.assertEqual(r["text"].count(content), 1)

    def test_invalid_slots_and_low_confidence_are_rejected(self):
        writer = RecurrentWriter()
        for draft in [(["I", "remember", "<claim>"], .99), (["Hi"], .2)]:
            with patch.object(writer, "draft", return_value=draft):
                self.assertTrue(writer.generate(CognitivePacket("greeting"))["fallback"])

    def test_budget_exhaustion_abstains(self):
        writer = RecurrentWriter(max_tokens=1)
        self.assertTrue(writer.generate(CognitivePacket("greeting"))["fallback"])

    def test_ablation_changes_observable_reply(self):
        e = self.engine()
        learned = e.chat("hello")["reply"]
        e.writer = None
        hybrid = e.chat("hello")["reply"]
        self.assertNotEqual(learned, hybrid)

    def test_style_condition_changes_learned_tokens(self):
        writer = RecurrentWriter()
        a = writer.generate(CognitivePacket("identity", style="brief"))
        b = writer.generate(CognitivePacket("identity", style="full"))
        self.assertFalse(a["fallback"] or b["fallback"])
        self.assertNotEqual(a["text"], b["text"])

    def test_self_state_numbers_match_actual_signals(self):
        e = self.engine()
        r = e.chat("how are you")
        for value in r["conversation"]["packet"]["slots"].values():
            self.assertIn(value, r["reply"])
        self.assertIn("computational", r["reply"])

    def test_fear_report_preserves_negative_outcome(self):
        e = self.engine()
        r = e.chat("Lina fears the mission failed")
        self.assertIn("failed", r["reply"])
        self.assertNotIn("about mission succeed", r["reply"])

    def test_database_restart_preserves_facts(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "restart.db"
            e = ASMEngine(path)
            e.chat("Vanya believes the violet lock is sealed")
            e.close()
            e = ASMEngine(path)
            try:
                r = e.chat("what does Vanya believe about the violet lock?")
                self.assertIn("sealed", r["reply"])
                self.assertFalse(r["conversation"]["writer"]["fallback"])
            finally:
                e.close()


if __name__ == "__main__":
    unittest.main()
