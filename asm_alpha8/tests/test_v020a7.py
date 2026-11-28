import tempfile
import unittest
from pathlib import Path

from asm import ASMEngine, __version__


class TestSemanticMemory2Alpha7(unittest.TestCase):
    def make_engine(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        asm = ASMEngine(Path(td.name) / "asm.db")
        self.addCleanup(asm.close)
        return asm

    def test_version(self):
        self.assertEqual(__version__, "0.4.0-alpha.7.9")

    def test_persistent_episode_gets_structured_event_record(self):
        asm = self.make_engine()
        r = asm.process("Alice believes the gate is open", training=True)
        self.assertIsNotNone(r["event_id"])
        update = r["semantic_event_memory_update"]
        self.assertEqual(update["event_id"], r["event_id"])
        rows = asm.event_memory.recall("what does Alice believe about the gate?", limit=3)
        self.assertEqual(rows[0]["event_type"], "belief")
        self.assertEqual(rows[0]["agents"], ["alice"])
        self.assertEqual(rows[0]["proposition_surface"], "gate is open")
        self.assertTrue(rows[0]["truth"])

    def test_typed_query_separates_expectation_from_belief(self):
        asm = self.make_engine()
        asm.process("Oren expects the bridge to open", training=True)
        asm.process("Oren believes the tunnel is blocked", training=True)
        rows = asm.event_memory.recall("what does Oren expect?", limit=5)
        self.assertTrue(rows)
        self.assertEqual(rows[0]["event_type"], "expectation")
        self.assertIn("bridge", rows[0]["text"].lower())

    def test_explicit_agent_query_never_crosses_agents(self):
        asm = self.make_engine()
        asm.process("Tessa believes the lantern is broken", training=True)
        rows = asm.event_memory.recall("does Mina believe the lantern is broken?", limit=5)
        self.assertEqual(rows, [])
        r = asm.chat("does Mina believe the lantern is broken?")
        self.assertIn("don't have", r["reply"].lower())

    def test_typed_query_separates_fear_from_other_mental_states(self):
        asm = self.make_engine()
        asm.process("Mina fears the server will fail", training=True)
        asm.process("Mina wants the backup to finish", training=True)
        rows = asm.event_memory.recall("what does Mina fear?", limit=5)
        self.assertEqual(rows[0]["event_type"], "fear")
        self.assertIn("server", rows[0]["text"].lower())

    def test_generic_topic_query_uses_proposition_terms(self):
        asm = self.make_engine()
        asm.process("The battery became hot after charging", training=True)
        asm.process("The archive contains old maps", training=True)
        rows = asm.event_memory.recall("what did i say about the battery?", limit=3)
        self.assertTrue(rows)
        self.assertIn("battery", rows[0]["text"].lower())
        self.assertTrue(any(x.startswith("term:battery") for x in rows[0]["matched_by"]))

    def test_belief_flip_creates_revision_and_contradiction_links(self):
        asm = self.make_engine()
        first = asm.process("Alice believes the gate is open", training=True)
        second = asm.process("Alice doubts the gate is open", training=True)
        links = asm.event_memory.links_for(second["event_id"])
        relations = {x["relation"] for x in links}
        self.assertIn("revises", relations)
        self.assertIn("contradicts", relations)
        self.assertIn("proposition_next", relations)
        self.assertIn("agent_next", relations)
        latest = asm.event_memory.latest_state("belief", "alice", "gate open")
        self.assertEqual(latest["event_id"], second["event_id"])
        self.assertFalse(latest["truth"])
        self.assertNotEqual(first["event_id"], second["event_id"])

    def test_repeated_belief_creates_reaffirmation_not_contradiction(self):
        asm = self.make_engine()
        asm.process("Alice believes the gate is open", training=True)
        second = asm.process("Alice believes the gate is open", training=True)
        relations = {x["relation"] for x in asm.event_memory.links_for(second["event_id"])}
        self.assertIn("reaffirms", relations)
        self.assertNotIn("contradicts", relations)

    def test_epistemic_shift_is_descriptive_not_causal(self):
        asm = self.make_engine()
        asm.process("Oren believes the bridge is open", training=True)
        second = asm.process("Oren expects the bridge to open", training=True)
        relations = {x["relation"] for x in asm.event_memory.links_for(second["event_id"])}
        self.assertIn("epistemic_shift", relations)
        self.assertNotIn("causes", relations)
        self.assertNotIn("caused_by", relations)

    def test_question_recall_works_without_persisting_question(self):
        asm = self.make_engine()
        asm.process("Alice believes the gate is open", training=True)
        before = asm.memory.count_events()
        r = asm.process("what does Alice believe about the gate?")
        self.assertFalse(r["consolidation"]["persist"])
        self.assertEqual(asm.memory.count_events(), before)
        self.assertTrue(r["recalled"])
        self.assertEqual(r["recalled"][0]["event_type"], "belief")
        self.assertIn("structured_relevance", r["recalled"][0])

    def test_conversation_uses_typed_memory_for_expectation(self):
        asm = self.make_engine()
        asm.chat("Oren expects the bridge to open")
        r = asm.chat("what does Oren expect?")
        self.assertIn("Oren expects the bridge to open", r["reply"])

    def test_conversation_uses_typed_memory_for_generic_topic(self):
        asm = self.make_engine()
        asm.chat("The battery became hot after charging")
        r = asm.chat("what did i say about the battery?")
        self.assertIn("battery became hot", r["reply"].lower())

    def test_event_memory_status_is_exposed(self):
        asm = self.make_engine()
        asm.process("Alice believes the gate is open", training=True)
        status = asm.language_core_status()["semantic_event_memory"]
        self.assertGreaterEqual(status["records"], 1)
        self.assertIn("belief", status["by_type"])

    def test_event_memory_stats_are_in_engine_stats(self):
        asm = self.make_engine()
        asm.process("Alice believes the gate is open", training=True)
        stats = asm.stats()
        self.assertEqual(stats["semantic_event_records"], 1)
        self.assertGreaterEqual(stats["semantic_event_links"], 0)

    def test_backfill_indexes_existing_episodes(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        db = Path(td.name) / "asm.db"
        first = ASMEngine(db)
        first.process("Alice believes the gate is open", training=True)
        first.close()
        second = ASMEngine(db)
        self.addCleanup(second.close)
        self.assertEqual(second.event_memory.count(), second.memory.count_events())
        rows = second.event_memory.recall("what does Alice believe about the gate?", limit=2)
        self.assertTrue(rows)
        self.assertEqual(rows[0]["event_type"], "belief")

    def test_event_memory_does_not_replace_neural_semantic_index(self):
        asm = self.make_engine()
        asm.process("Alice believes the gate is open", training=True)
        self.assertEqual(asm.event_memory.count(), 1)
        self.assertEqual(asm.semantic_memory.count(), 1)


if __name__ == "__main__":
    unittest.main()
