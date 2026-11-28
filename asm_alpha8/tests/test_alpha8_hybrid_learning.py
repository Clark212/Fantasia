import json
import tempfile
import unittest
from pathlib import Path

from asm.learning import (Experience, ExperienceStore, ExperienceIntegrator,
                          ExperienceRunner, evaluate_predictions, iter_records,
                          stable_split, split_records)


class TinyCounter:
    def reset(self, seed=None):
        self.value = int(seed or 0)
        return {"value": self.value}

    def step(self, action):
        self.value += int(action["delta"])
        return {"value": self.value}, self.value >= 3, {"valid": True}


class Policy:
    def __call__(self, observation):
        return {"delta": 1}

    def predict(self, observation, action):
        return {"value": observation["value"] + action["delta"]}


def rec(eid="a", *, source="dataset", evidence="labeled", task="task-a", obs=None, pred=None, out=None, meta=None):
    return Experience(eid, source, "math", task, obs or {"x": 1}, pred, out, evidence, 1.0, meta or {})


class Alpha8HybridLearningTests(unittest.TestCase):
    def test_experience_validation_and_fingerprint(self):
        a = rec(); b = rec("b")
        self.assertEqual(a.fingerprint, b.fingerprint)
        with self.assertRaises(ValueError):
            rec(source="unknown")
        with self.assertRaises(ValueError):
            Experience("x", "dataset", "math", "t", {"x": float("nan")})

    def test_store_is_bounded_and_deduplicates(self):
        store = ExperienceStore(2)
        self.assertTrue(store.add(rec("a", obs={"x": 1})))
        self.assertFalse(store.add(rec("b", obs={"x": 1})))
        self.assertTrue(store.add(rec("c", obs={"x": 2})))
        self.assertTrue(store.add(rec("d", obs={"x": 3})))
        self.assertEqual(len(store), 2)
        self.assertIsNone(store.get("a"))
        self.assertEqual(store.stats()["dropped_oldest"], 1)

    def test_stable_split_is_repeatable_and_group_consistent(self):
        self.assertEqual(stable_split("same"), stable_split("same"))
        self.assertIn(stable_split("same"), {"train", "validation", "test"})
        with self.assertRaises(ValueError):
            stable_split("x", train=.9, validation=.2)

    def test_jsonl_ingestion_and_source_override(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "data.jsonl"
            p.write_text(json.dumps({"experience_id":"e1", "source":"interaction", "domain":"math", "task_id":"t", "observation":{"x":1}, "outcome":{"y":2}}) + "\n", encoding="utf-8")
            items = list(iter_records(p))
            self.assertEqual(items[0].source, "dataset")
            self.assertEqual(items[0].outcome, {"y": 2})

    def test_csv_ingestion(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "data.csv"
            import csv
            with p.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=["experience_id", "source", "domain", "task_id", "observation", "outcome"])
                writer.writeheader()
                writer.writerow({"experience_id":"e1", "source":"dataset", "domain":"math", "task_id":"t", "observation":json.dumps({"x":1}), "outcome":json.dumps({"y":2})})
            items = list(iter_records(p))
            self.assertEqual(items[0].observation, {"x": 1})

    def test_split_records_returns_all_splits(self):
        result = split_records(iter([rec("a", task="one"), rec("b", task="two")]))
        self.assertEqual(set(result), {"train", "validation", "test"})
        self.assertEqual(sum(map(len, result.values())), 2)

    def test_simulation_runner_uses_observations_and_caps_steps(self):
        result = ExperienceRunner(domain="toy", max_steps=5).run(TinyCounter(), Policy(), episode_id="ep", seed=0)
        self.assertTrue(result.terminated)
        self.assertEqual(result.steps, 3)
        self.assertEqual(result.experiences[-1].outcome["next_state"], {"value": 3})
        self.assertEqual(result.experiences[0].prediction, {"value": 1})

    def test_simulation_runner_honors_step_limit(self):
        result = ExperienceRunner(domain="toy", max_steps=2).run(TinyCounter(), Policy(), episode_id="ep2")
        self.assertEqual(result.steps, 2)
        self.assertFalse(result.terminated)

    def test_simulation_rejects_non_mapping_action(self):
        with self.assertRaises(TypeError):
            ExperienceRunner(domain="toy").run(TinyCounter(), lambda _: "bad", episode_id="bad")

    def test_integrator_does_not_auto_promote_knowledge(self):
        store = ExperienceStore()
        integrator = ExperienceIntegrator(store)
        result = integrator.ingest([rec("a"), rec("b", obs={"x":2})])
        self.assertEqual(result["accepted"], 2)
        self.assertEqual(len(store), 2)
        self.assertEqual(len(integrator.review_queue()), 2)

    def test_generated_examples_rank_below_observed_prediction_error(self):
        observed = rec("o", source="simulation", evidence="observed", pred={"x":1}, out={"x":9})
        generated = rec("g", source="dataset", evidence="generated", pred={"x":1}, out={"x":9}, obs={"x":2})
        self.assertGreater(ExperienceIntegrator.priority(observed), ExperienceIntegrator.priority(generated))

    def test_prediction_evaluator_reports_numeric_mae(self):
        a = rec("a", pred={"x": 2}, out={"x": 4})
        b = rec("b", pred={"x": 3}, out={"x": 3}, obs={"x":2})
        metrics = evaluate_predictions([a, b])
        self.assertEqual(metrics.compared, 2)
        self.assertEqual(metrics.exact_matches, 1)
        self.assertEqual(metrics.numeric_mae, 1.0)

    def test_prediction_evaluator_handles_no_comparable_values(self):
        self.assertIsNone(evaluate_predictions([rec(pred={"a":"x"}, out={"a":"y"})]).numeric_mae)

    def test_store_rejects_wrong_record_type(self):
        with self.assertRaises(TypeError):
            ExperienceStore().add({"not":"experience"})

    def test_recent_domain_filter(self):
        store = ExperienceStore()
        store.add(rec("a", obs={"x":1}))
        other = Experience("b", "dataset", "physics", "t2", {"x":2})
        store.add(other)
        self.assertEqual([x.domain for x in store.recent(10, domain="physics")], ["physics"])

    def test_duplicate_ids_rejected_even_if_content_differs(self):
        store = ExperienceStore()
        self.assertTrue(store.add(rec("same", obs={"x":1})))
        self.assertFalse(store.add(rec("same", obs={"x":2})))

    def test_same_content_from_distinct_sources_preserves_provenance(self):
        store = ExperienceStore()
        self.assertTrue(store.add(rec("dataset-1", source="dataset", obs={"x":7})))
        self.assertTrue(store.add(rec("sim-1", source="simulation", obs={"x":7})))
        self.assertEqual(len(store), 2)

    def test_invalid_file_extension_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "data.txt"; p.write_text("x")
            with self.assertRaises(ValueError):
                list(iter_records(p))

    def test_jsonl_line_errors_include_line_number(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bad.jsonl"; p.write_text('{bad}\n')
            with self.assertRaisesRegex(ValueError, r":1:"):
                list(iter_records(p))

    def test_split_group_key_uses_metadata(self):
        a = rec("a", task="fallback", meta={"group":"shared"})
        b = rec("b", task="different", meta={"group":"shared"}, obs={"x":2})
        result = split_records(iter([a,b]), group_key="group")
        memberships = {name for name, values in result.items() if values}
        self.assertEqual(len(memberships), 1)

if __name__ == "__main__":
    unittest.main()
