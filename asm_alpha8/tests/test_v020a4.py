import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from asm import ASMEngine, __version__


class TestASM020Alpha4(unittest.TestCase):
    def make_engine(self):
        td=tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        asm=ASMEngine(Path(td.name)/"chat.db")
        self.addCleanup(asm.close)
        return asm

    def test_version(self):
        self.assertEqual(__version__,"0.4.0-alpha.7.9")

    def test_greeting_is_conversational_and_transient(self):
        asm=self.make_engine()
        before=asm.memory.count_events()
        r=asm.chat("hi")
        self.assertIn("Hey",r["reply"])
        self.assertNotIn("New pattern registered",r["reply"])
        self.assertFalse(r["consolidation"]["persist"])
        self.assertEqual(asm.memory.count_events(),before)

    def test_wellbeing_uses_functional_internal_state_not_fake_feelings(self):
        asm=self.make_engine()
        r=asm.chat("how are you")
        low=r["reply"].lower()
        self.assertIn("internal confidence signal",low)
        self.assertIn("curiosity signal",low)
        self.assertNotIn("i feel",low)

    def test_negative_affect_gets_social_response(self):
        asm=self.make_engine()
        r=asm.chat("im angry at u")
        self.assertIn("upset",r["reply"].lower())
        self.assertFalse(r["consolidation"]["persist"])

    def test_nonsense_does_not_pollute_memory(self):
        asm=self.make_engine()
        before=asm.memory.count_events()
        r=asm.chat("buhh hole")
        self.assertIn("not sure what you mean",r["reply"].lower())
        self.assertEqual(asm.memory.count_events(),before)

    def test_structured_belief_can_be_told_and_queried_conversationally(self):
        asm=self.make_engine()
        a=asm.chat("Alice believes the gate is open")
        self.assertIn("Alice",a["reply"])
        self.assertIn("remember",a["reply"].lower())
        b=asm.chat("what does Alice believe about the gate?")
        self.assertIn("Alice",b["reply"])
        self.assertIn("gate",b["reply"].lower())
        self.assertIn("open",b["reply"].lower())

    def test_persistent_event_can_be_recalled_in_conversation(self):
        asm=self.make_engine()
        asm.chat("The server crashed after memory pressure")
        r=asm.chat("what did i say about the server?")
        self.assertIn("server crashed",r["reply"].lower())

    def test_session_last_message_followup(self):
        asm=self.make_engine()
        asm.chat("hello")
        asm.chat("The battery became hot")
        r=asm.chat("what did i just say?")
        self.assertIn("The battery became hot",r["reply"])

    def test_identity_reply_describes_actual_architecture(self):
        asm=self.make_engine()
        r=asm.chat("who are you")
        self.assertIn("ASM",r["reply"])
        self.assertIn("memory-centric",r["reply"])
        self.assertIn("recurrent",r["reply"])

    def test_gratitude_and_farewell(self):
        asm=self.make_engine()
        self.assertIn("welcome",asm.chat("thanks")["reply"].lower())
        self.assertIn("see you",asm.chat("bye")["reply"].lower())

    def test_dialogue_status_is_visible(self):
        asm=self.make_engine()
        status=asm.language_core_status()
        self.assertIn("dialogue",status)
        self.assertTrue(status["dialogue"]["ready"])
        self.assertEqual(status["dialogue"]["architecture"],"safe dialogue router + ASM recurrent language reader")

    def test_cli_defaults_to_chat_not_internal_dump(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/"cli.db"
            proc=subprocess.run(
                [sys.executable,"main.py","--empty","--db",str(db)],
                input="hi\n/quit\n",
                text=True,capture_output=True,
                cwd=Path(__file__).resolve().parents[1],timeout=30,
            )
            self.assertEqual(proc.returncode,0,proc.stderr)
            self.assertIn("ASM> Hey.",proc.stdout)
            self.assertNotIn("workspace:",proc.stdout)
            self.assertNotIn("action=LEARN",proc.stdout)

    def test_cli_debug_can_show_internals(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/"cli.db"
            proc=subprocess.run(
                [sys.executable,"main.py","--empty","--db",str(db)],
                input="/debug on\nhi\n/quit\n",
                text=True,capture_output=True,
                cwd=Path(__file__).resolve().parents[1],timeout=30,
            )
            self.assertEqual(proc.returncode,0,proc.stderr)
            self.assertIn("Debug enabled.",proc.stdout)
            self.assertIn("[workspace]",proc.stdout)
            self.assertIn("[dialogue=greeting",proc.stdout)


if __name__=="__main__":
    unittest.main()
