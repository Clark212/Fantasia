import os
import tempfile
import unittest

from asm import ASMEngine, ASMConfig, __version__
from asm.semantic_event import Proposition, SemanticDecision, SemanticEvent
from asm.world_model import PersistentWorldModel


def decision(event_type, epistemic, holder, surface, *, truth=True, confidence=0.9, persistent=True):
    prop = Proposition.from_surface(surface, polarity=truth)
    event = SemanticEvent(
        event_type=event_type,
        epistemic=epistemic,
        confidence=confidence,
        source="test",
        agents=[holder] if holder else [],
        proposition=prop,
        persistent_eligible=persistent,
    )
    return SemanticDecision(primary=event)


class WorldModelTests(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        self.model = PersistentWorldModel(self.path, max_schedule_candidates=5)

    def tearDown(self):
        self.model.close()
        for suffix in ('', '-wal', '-shm'):
            try:
                os.remove(self.path + suffix)
            except FileNotFoundError:
                pass

    def test_version(self):
        self.assertEqual(__version__, '0.4.0-alpha.7.9')

    def test_new_state_is_persistent(self):
        out = self.model.observe(1, decision('belief', 'believed', 'Alice', 'the gate is open'), raw_text='Alice believes the gate is open')
        self.assertEqual(len(out['states']), 1)
        rows = self.model.current(holder='alice', event_type='belief')
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]['truth'])
        self.assertEqual(rows[0]['source_event_id'], 1)

    def test_truth_revision_updates_slot_and_records_transition(self):
        self.model.observe(1, decision('belief', 'believed', 'Alice', 'the gate is open'), raw_text='x')
        self.model.observe(2, decision('belief', 'believed', 'Alice', 'the gate is open', truth=False), raw_text='x')
        rows = self.model.current(holder='alice', event_type='belief')
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]['truth'])
        transitions = self.model.transitions(state_key=rows[0]['state_key'])
        self.assertEqual(transitions[0]['transition_kind'], 'truth_revision')
        self.assertFalse(transitions[0]['causal'])
        self.assertEqual(transitions[0]['source_event_id'], 1)
        self.assertEqual(transitions[0]['target_event_id'], 2)

    def test_belief_and_reality_are_separate_slots(self):
        self.model.observe(1, decision('belief', 'believed', 'Alice', 'the gate is open'), raw_text='x')
        self.model.observe(2, decision('observation', 'asserted', '__world__', 'the gate is open', truth=False), raw_text='x')
        rows = self.model.current(limit=10)
        self.assertEqual(len(rows), 2)
        self.assertEqual({r['event_type'] for r in rows}, {'belief', 'observation'})

    def test_nested_belief_preserves_perspective_path(self):
        prop = Proposition.from_surface('the gate is open')
        event = SemanticEvent('nested_belief', 'reported', .9, 'test', ['Alice', 'Bob'], prop, persistent_eligible=True)
        out = self.model.observe(1, SemanticDecision(primary=event), raw_text='x')
        self.assertEqual(len(out['states']), 1)
        self.assertEqual(out['states'][0]['holder'], 'alice>bob')
        self.assertEqual(self.model.current(holder='alice', event_type='nested_belief'), [])
        node = self.model._state_node_key(out['states'][0]['state_key'])
        self.assertIn('holds_nested_state', {x['relation'] for x in self.model.graph_neighbors(node)})

    def test_question_does_not_mutate_world(self):
        event = SemanticEvent('question', 'queried', .99, 'test', [], None, persistent_eligible=False)
        out = self.model.observe(1, SemanticDecision(primary=event), raw_text='Is the gate open?')
        self.assertEqual(out['states'], [])
        self.assertEqual(self.model.stats()['current_states'], 0)

    def test_scheduler_is_bounded_and_state_first(self):
        out = self.model.observe(1, decision('belief', 'believed', 'Alice', 'silver valve pressure rises quickly'), raw_text='x')
        self.assertLessEqual(len(out['scheduled']), 5)
        self.assertEqual(out['scheduled'][0]['dependency_type'], 'state')
        self.assertEqual(out['scheduled'][0]['priority'], 1.0)

    def test_graph_is_queryable(self):
        out = self.model.observe(1, decision('belief', 'believed', 'Alice', 'the gate is open'), raw_text='x')
        state_key = out['states'][0]['state_key']
        node_key = self.model._state_node_key(state_key)
        edges = self.model.graph_neighbors(node_key)
        relations = {x['relation'] for x in edges}
        self.assertIn('holds_state', relations)
        self.assertIn('mentions', relations)

    def test_all_transition_evidence_is_noncausal(self):
        self.model.observe(1, decision('belief', 'believed', 'Alice', 'the gate is open'), raw_text='x')
        self.model.observe(2, decision('belief', 'believed', 'Alice', 'the gate is open', truth=False), raw_text='x')
        self.model.observe(3, decision('belief', 'believed', 'Alice', 'the gate is open'), raw_text='x')
        self.assertTrue(self.model.transitions())
        self.assertTrue(all(not x['causal'] for x in self.model.transitions()))


class EngineIntegrationTests(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        cfg = ASMConfig(snapshot_every_events=999999)
        self.engine = ASMEngine(self.path, config=cfg)

    def tearDown(self):
        self.engine.close()
        for suffix in ('', '-wal', '-shm'):
            try:
                os.remove(self.path + suffix)
            except FileNotFoundError:
                pass

    def test_live_persistent_event_updates_world_model(self):
        result = self.engine.process('Alice believes the gate is open.')
        self.assertIsNotNone(result['event_id'])
        self.assertIsNotNone(result['world_model_update'])
        self.assertEqual(result['world_model_update']['states'][0]['holder'], 'alice')
        self.assertTrue(self.engine.world_state(holder='alice'))

    def test_question_does_not_create_world_state(self):
        before = self.engine.world_model.stats()['state_history']
        result = self.engine.process('What does Alice believe?')
        after = self.engine.world_model.stats()['state_history']
        self.assertEqual(before, after)
        self.assertIsNone(result['world_model_update'])

    def test_status_exposes_world_model(self):
        status = self.engine.language_core_status()
        self.assertIn('world_model', status)
        self.assertIn('current_states', status['world_model'])


if __name__ == '__main__':
    unittest.main()
