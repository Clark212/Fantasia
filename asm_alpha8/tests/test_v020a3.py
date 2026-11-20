import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from asm import ASMEngine, __version__


class TestASM020Alpha3(unittest.TestCase):
    def make_engine(self):
        td=tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        asm=ASMEngine(Path(td.name)/"asm.db")
        self.addCleanup(asm.close)
        return asm

    def test_version(self):
        self.assertEqual(__version__, '0.4.0-alpha.7.9')

    def test_social_greeting_is_transient_and_not_graph_persistent(self):
        asm=self.make_engine()
        before_events=asm.memory.count_events()
        before_nodes=len(asm.field.nodes)
        r=asm.process("hi")
        self.assertFalse(r["consolidation"]["persist"])
        self.assertEqual(r["consolidation"]["reason"],"high_confidence_social")
        self.assertEqual(r["decision"]["type"],"SOCIAL")
        self.assertIsNone(r["event_id"])
        self.assertEqual(asm.memory.count_events(),before_events)
        self.assertEqual(len(asm.field.nodes),before_nodes)
        self.assertTrue(any(k=="LCORE:INTENT:SOCIAL" for k,_ in r["workspace"]))

    def test_real_user_failure_examples_stay_transient(self):
        asm=self.make_engine()
        for text in ("how are you","buhh hole","im angry at u"):
            before=asm.memory.count_events()
            r=asm.process(text)
            self.assertFalse(r["consolidation"]["persist"],text)
            self.assertEqual(asm.memory.count_events(),before,text)

    def test_structured_knowledge_overrides_false_social_probe(self):
        asm=self.make_engine()
        r=asm.process("signal triggers alarm")
        self.assertTrue(r["structure"]["supported"])
        self.assertTrue(r["consolidation"]["persist"])
        self.assertEqual(r["consolidation"]["reason"],"structured_cognitive_event")
        self.assertIsNotNone(r["event_id"])

    def test_meaningful_relation_persists(self):
        asm=self.make_engine()
        r=asm.process("pressure increases temperature")
        self.assertTrue(r["consolidation"]["persist"])
        self.assertEqual(asm.memory.count_events(),1)
        self.assertIn("STEM:pressure",asm.field.nodes)

    def test_attention_metadata_does_not_recurse(self):
        asm=self.make_engine()
        for text in ("hi","how are you","pressure increases temperature","buhh hole","practice increases skill"):
            asm.process(text)
        self.assertFalse(any(k.startswith("ATTEND:ATTEND:") for k in asm.field.nodes))
        self.assertFalse(any(x["concept"].startswith("ATTEND:") for x in asm.attention_state()["targets"]))

    def test_semantic_ann_retrieves_related_belief(self):
        asm=self.make_engine()
        asm.process("Alice believes the gate is open",training=True)
        asm.process("Bob believes the lamp is on",training=True)
        read=asm._read_language("Alice thinks the gate is open")
        rows=asm.semantic_memory.recall(read.embedding,limit=2)
        self.assertTrue(rows)
        self.assertEqual(rows[0]["text"],"Alice believes the gate is open")

    def test_semantic_vectors_persist_and_backfill(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/"persist.db"
            asm=ASMEngine(db)
            asm.process("Alice believes the gate is open",training=True)
            count=asm.semantic_memory.count()
            self.assertEqual(count,1)
            asm.close()
            asm2=ASMEngine(db)
            try:
                self.assertGreaterEqual(asm2.semantic_memory.count(),1)
            finally:
                asm2.close()

    def test_social_probe_and_semantic_index_report_health(self):
        asm=self.make_engine()
        status=asm.language_core_status()
        self.assertTrue(status["social_probe"]["ready"])
        self.assertGreaterEqual(status["social_probe"]["validation_accuracy"],0.80)
        self.assertEqual(status["semantic_memory_vectors"],0)

    def test_incomplete_embed_command_does_not_become_event(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/"cli.db"
            proc=subprocess.run(
                [sys.executable,"main.py","--empty","--db",str(db)],
                input="/embed\n/quit\n",
                text=True,
                capture_output=True,
                cwd=Path(__file__).resolve().parents[1],
                timeout=30,
            )
            self.assertEqual(proc.returncode,0,proc.stderr)
            self.assertIn("Use: /embed <text>",proc.stdout)
            asm=ASMEngine(db)
            try:
                self.assertEqual(asm.memory.count_events(),0)
            finally:
                asm.close()


if __name__=="__main__":
    unittest.main()
