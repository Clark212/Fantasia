from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from asm import ASMConfig, ASMEngine, __version__
from asm.evidence_lineage import EvidenceLineageGraph
from asm.planning import DiscreteBeliefState


class Alpha62EvidenceLineageTests(unittest.TestCase):
    def make_engine(self, root: Path, **kwargs) -> ASMEngine:
        cfg = ASMConfig(snapshot_every_events=999999, prune_every_events=999999, **kwargs)
        return ASMEngine(root / "x.db", config=cfg)

    def test_version(self):
        self.assertEqual(__version__, "0.4.0-alpha.7.9")

    def test_exact_copy_does_not_multiply_confidence(self):
        with tempfile.TemporaryDirectory() as td:
            e = self.make_engine(Path(td))
            b = e.update_belief_from_source(
                {"A": .5, "B": .5}, source_id="camera", observation="A",
                supplied_reliability=.7, evidence_id="raw-1",
            )
            self.assertAlmostEqual(b.as_dict()["A"], .7, places=12)
            for i in range(8):
                b = e.update_belief_from_source(
                    b, source_id=f"relay-{i}", observation="A",
                    supplied_reliability=.7, evidence_id=f"copy-{i}",
                    parent_evidence_ids=["raw-1"],
                )
            self.assertAlmostEqual(b.as_dict()["A"], .7, places=12)
            self.assertEqual(b.evidence_count, 9)
            self.assertEqual(len(b.evidence_roots()), 1)

    def test_independent_evidence_keeps_full_bayesian_update(self):
        with tempfile.TemporaryDirectory() as td:
            e = self.make_engine(Path(td))
            a = DiscreteBeliefState.from_mapping({"A": .5, "B": .5})
            b = a
            for i, obs in enumerate(["A", "A", "B", "A", "A"]):
                likes = {"A": .7 if obs == "A" else .3, "B": .7 if obs == "B" else .3}
                a = a.update(likes)
                b = e.update_belief_from_source(
                    b, source_id=f"s{i}", observation=obs, supplied_reliability=.7,
                    evidence_id=f"independent-{i}",
                )
            self.assertAlmostEqual(a.as_dict()["A"], b.as_dict()["A"], places=14)
            self.assertEqual(len(b.evidence_roots()), 5)

    def test_three_independent_roots_repeated_three_times_equal_three_clues(self):
        with tempfile.TemporaryDirectory() as td:
            e = self.make_engine(Path(td))
            b = {"A": .5, "B": .5}
            observations = ["A", "B", "A"]
            for group, obs in enumerate(observations):
                root = f"root-{group}"
                b = e.update_belief_from_source(
                    b, source_id=f"sensor-{group}", observation=obs,
                    supplied_reliability=.7, evidence_id=root,
                )
                for copy in range(2):
                    b = e.update_belief_from_source(
                        b, source_id=f"relay-{group}-{copy}", observation=obs,
                        supplied_reliability=.7, evidence_id=f"copy-{group}-{copy}",
                        parent_evidence_ids=[root],
                    )
            direct = DiscreteBeliefState.from_mapping({"A": .5, "B": .5})
            for obs in observations:
                direct = direct.update({"A": .7 if obs == "A" else .3, "B": .7 if obs == "B" else .3})
            self.assertAlmostEqual(b.as_dict()["A"], direct.as_dict()["A"], places=14)
            self.assertEqual(len(b.evidence_roots()), 3)

    def test_partial_overlap_uses_fractional_novelty(self):
        graph = EvidenceLineageGraph()
        graph.register("e1", source_id="s1", root_ids=["shared", "unique-1"])
        graph.register("e2", source_id="s2", root_ids=["shared", "unique-2"])
        self.assertEqual(graph.novelty([], graph.roots("e1")), 1.0)
        self.assertEqual(graph.novelty(graph.roots("e1"), graph.roots("e2")), .5)
        prior = DiscreteBeliefState.from_mapping({"A": .5, "B": .5})
        first = prior.update_weighted({"A": .8, "B": .2}, evidence_weight=1.0, evidence_roots=graph.roots("e1"))
        second = first.update_weighted({"A": .8, "B": .2}, evidence_weight=.5, evidence_roots=graph.roots("e2"))
        # Odds should be 4^(1 + .5) rather than 4^2.
        expected = (4.0 ** 1.5) / (1.0 + 4.0 ** 1.5)
        self.assertAlmostEqual(second.as_dict()["A"], expected, places=14)

    def test_unknown_parent_fails_closed(self):
        g = EvidenceLineageGraph()
        with self.assertRaises(ValueError):
            g.register("copy", source_id="relay", parent_ids=["missing"])

    def test_conflicting_evidence_id_fails_closed(self):
        g = EvidenceLineageGraph()
        g.register("e", source_id="s")
        with self.assertRaises(ValueError):
            g.register("e", source_id="different")

    def test_duplicate_with_zero_weight_cannot_create_structural_zero(self):
        prior = DiscreteBeliefState.from_mapping({"A": .5, "B": .5})
        first = prior.update_weighted({"A": .9, "B": .1}, evidence_roots=["r"])
        duplicate = first.update_weighted(
            {"A": 0.0, "B": 1.0}, evidence_weight=0.0, evidence_roots=["r"],
        )
        self.assertEqual(first.structural_zero_hypotheses(), ())
        self.assertEqual(duplicate.structural_zero_hypotheses(), ())
        self.assertAlmostEqual(first.as_dict()["A"], duplicate.as_dict()["A"], places=15)

    def test_snapshot_roundtrip_preserves_lineage(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            e = self.make_engine(path)
            e.register_evidence_lineage("root", source_id="camera")
            e.register_evidence_lineage("copy", source_id="relay", parent_evidence_ids=["root"])
            e.save()
            restored = self.make_engine(path)
            self.assertEqual(restored.evidence_lineage.roots("root"), ("evidence:root",))
            self.assertEqual(restored.evidence_lineage.roots("copy"), ("evidence:root",))
            self.assertEqual(restored.evidence_lineage.stats()["evidence_nodes"], 2)

    def test_lineage_disabled_preserves_alpha61_behavior(self):
        with tempfile.TemporaryDirectory() as td:
            e = self.make_engine(Path(td), evidence_lineage_enabled=False)
            b = {"A": .5, "B": .5}
            for i in range(3):
                b = e.update_belief_from_source(
                    b, source_id="s", observation="A", supplied_reliability=.7,
                    evidence_id=f"e{i}", parent_evidence_ids=["ignored"] if i else None,
                )
            direct = DiscreteBeliefState.from_mapping({"A": .5, "B": .5})
            for _ in range(3):
                direct = direct.update({"A": .7, "B": .3})
            self.assertAlmostEqual(b.as_dict()["A"], direct.as_dict()["A"], places=14)

    def test_malformed_snapshot_cycle_or_missing_parent_rejected(self):
        g = EvidenceLineageGraph()
        payload = {"schema": 1, "records": [
            {"evidence_id": "a", "source_id": "s", "parent_ids": ["b"], "roots": ["r"]},
            {"evidence_id": "b", "source_id": "s", "parent_ids": ["a"], "roots": ["r"]},
        ]}
        with self.assertRaises(ValueError):
            g.import_state(payload)

    def test_belief_lineage_capacity_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            e = self.make_engine(Path(td), evidence_lineage_max_roots_per_belief=2)
            b = {"A": .5, "B": .5}
            for i in range(2):
                b = e.update_belief_from_source(
                    b, source_id="s", observation="A", supplied_reliability=.7,
                    evidence_id=f"ind-{i}",
                )
            with self.assertRaises(RuntimeError):
                e.update_belief_from_source(
                    b, source_id="s", observation="A", supplied_reliability=.7,
                    evidence_id="ind-2",
                )


if __name__ == "__main__":
    unittest.main()
