import json
import re
import unittest
from pathlib import Path

from asm.learning import simlab as S
from asm.learning import structlab as L
from asm.learning import structtransfer as T
from asm.learning.structlab_prereg import PREREG

ROOT = Path(__file__).resolve().parents[1]
SEED = 5


def a_factories(asm=False):
    f = {"memorizer": S.MemorizerLearner, "majority": S.MajorityLearner, "grid_reference": L.GridReferenceLearner,
         "shuffled_grid_reference": lambda: S.ShuffledControl(L.GridReferenceLearner())}
    if asm:
        f["asm_struct"] = L.ASMStructLearner
        f["shuffled_asm_struct"] = lambda: S.ShuffledControl(L.ASMStructLearner())
    return f


def small_a(factories=None, tasks=8, ks=(8, 16, 24), families=L.FAMILIES):
    return L.run_struct_benchmark(factories or a_factories(), seed=SEED, tasks_per_family=tasks, ks=list(ks), families=families)


class PartATaskTests(unittest.TestCase):
    def test_tasks_are_deterministic_well_formed_interior_and_determined(self):
        for fam in L.FAMILIES:
            a, b = L.make_struct_suite(fam, 12, SEED), L.make_struct_suite(fam, 12, SEED)
            self.assertEqual([t.truth for t in a], [t.truth for t in b])
            hyps = L.grid(fam)
            for t in a:
                self.assertIn(dict(t.truth), hyps)
                self.assertFalse(set(t.queries) & set(t.pool))
                self.assertGreaterEqual(len(t.queries), 2)
                dims = len(L.SCHEMAS[fam])
                for d in range(dims):                                             # interior: inside the pool's range in every dimension
                    pv = [(u if dims == 1 else u[d]) for u in t.pool]
                    for q in t.queries:
                        self.assertTrue(min(pv) <= (q if dims == 1 else q[d]) <= max(pv))
                labels = [L.evaluate(fam, {}, t.truth, u) for u in t.pool]
                consistent = [h for h in hyps if all(L.evaluate(fam, {}, h, u) == y for u, y in zip(t.pool, labels))]
                for q in t.queries:
                    self.assertEqual(len({L.evaluate(fam, {}, h, q) for h in consistent}), 1)
                self.assertEqual(t.label(t.queries[0]), L.evaluate(fam, {}, t.truth, t.queries[0]))

    def test_family_formulas_hand_values(self):
        ev = L.evaluate
        self.assertEqual(ev("affine", {}, {"a": 2, "b": 3}, 5), 13)
        self.assertEqual(ev("quad", {}, {"a": 2, "b": 1}, 3), 19)
        self.assertEqual(ev("quad", {}, {"a": -3, "b": 4}, 2), -8)
        self.assertEqual((ev("clamp", {}, {"op": "min", "c": 4}, 7), ev("clamp", {}, {"op": "min", "c": 4}, 2)), (4, 2))
        self.assertEqual((ev("clamp", {}, {"op": "max", "c": 4}, 7), ev("clamp", {}, {"op": "max", "c": 4}, 2)), (7, 4))
        self.assertEqual((ev("threshold", {}, {"c": 5, "p": 1, "q": 9}, 4), ev("threshold", {}, {"c": 5, "p": 1, "q": 9}, 5)), (1, 9))
        self.assertEqual(ev("linear2", {}, {"a": 2, "b": -1}, (3, 4)), 2)
        self.assertEqual(ev("product2", {}, {"c": 3}, (2, 5)), 13)
        self.assertEqual((len(L.grid("affine")), len(L.grid("quad")), len(L.grid("clamp")), len(L.grid("threshold")), len(L.grid("linear2")), len(L.grid("product2"))),
                         (12 * 19, 4 * 19, 22, 8 * 110, 36, 11))

    def test_seeds_differ_and_unknown_family_rejected(self):
        self.assertNotEqual([t.truth for t in L.make_struct_suite("threshold", 10, 1)], [t.truth for t in L.make_struct_suite("threshold", 10, 2)])
        with self.assertRaises(ValueError):
            L.grid("nope")
        with self.assertRaises(ValueError):
            L.evaluate("nope", {}, {}, 1)

    def test_pool_is_large_enough_for_asm_to_activate(self):
        for fam in L.FAMILIES:
            self.assertGreaterEqual(len({*L.make_struct_task(fam, 0, SEED).pool}), 8)


class PartAHarnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.res = small_a()

    def cell(self, name, fam, k):
        return self.res["cells"][name][fam][str(k)]

    def test_reference_is_safe_and_learns_controls_collapse(self):
        for fam in L.FAMILIES:
            for k in self.res["ks"]:
                self.assertEqual(self.cell("grid_reference", fam, k)["wrong_rate"], 0.0)
                self.assertEqual(self.cell("memorizer", fam, k)["correct_rate"], 0.0)
            self.assertGreaterEqual(self.cell("grid_reference", fam, 24)["correct_rate"], 0.95)
            self.assertLessEqual(self.cell("shuffled_grid_reference", fam, 24)["correct_rate"], 0.25)
            self.assertGreater(self.cell("grid_reference", fam, 24)["correct_rate"] - self.cell("majority", fam, 24)["correct_rate"], 0.15)

    def test_run_is_deterministic(self):
        again = small_a({"grid_reference": L.GridReferenceLearner})
        self.assertEqual(again["cells"]["grid_reference"], self.res["cells"]["grid_reference"])

    def test_verdicts_pass_for_good_learners_and_fail_for_sabotaged_ones(self):
        good = {x["id"]: x for x in L.evaluate_part_a(self.res, PREREG)}
        self.assertTrue(all(good[i]["passed"] for i in ("A-H1", "A-H2", "A-H3", "A-H4", "A-H5")), good)
        self.assertNotIn("A1", good)

        class Liar(S.Learner):
            name = "liar"
            def fit(self, ctx, shots): pass
            def predict(self, x): return 10**6, 1.0                        # always answers, always wrong

        class Quitter(S.Learner):
            name = "quitter"
            def fit(self, ctx, shots): pass
            def predict(self, x): return S.ABSTAIN, 0.0

        def verdicts(**overrides):
            f = a_factories()
            f["asm_struct"] = overrides.get("asm", Quitter)
            f["shuffled_asm_struct"] = overrides.get("shuffled", Quitter)
            for k, v in overrides.items():
                if k not in ("asm", "shuffled"):
                    f[k] = v
            return {x["id"]: x for x in L.evaluate_part_a(small_a(f, tasks=6, ks=(8, 24)), PREREG)}

        v = verdicts()                                                      # an abstaining stand-in is safe but covers nothing
        self.assertTrue(v["A1"]["passed"] and v["A2"]["passed"]); self.assertFalse(v["A3"]["passed"])
        v = verdicts(asm=Liar)
        self.assertFalse(v["A1"]["passed"])
        v = verdicts(shuffled=Liar)
        self.assertFalse(v["A2"]["passed"])
        v = verdicts(grid_reference=Liar)
        self.assertFalse(v["A-H1"]["passed"]); self.assertFalse(v["A-H2"]["passed"])

        class Peeker(S.Learner):                                            # reads ground truth: the canary must catch it
            name = "memorizer"
            def fit(self, ctx, shots): self.fam, self.tid = ctx["family"], int(ctx["task_id"].split("-")[1])
            def predict(self, x): return L.make_struct_task(self.fam, self.tid, SEED).label(x), 1.0

        v = verdicts(memorizer=Peeker)
        self.assertFalse(v["A-H3"]["passed"])


class ASMAdapterTests(unittest.TestCase):
    def test_value_mapping_follows_the_schema(self):
        one, two = L.ASMStructLearner(), L.ASMStructLearner()
        one.schema, two.schema = ("x",), ("x", "y")
        self.assertEqual(one._values(4), {"x": 4}); self.assertEqual(two._values((2, 5)), {"x": 2, "y": 5})

    def test_adapter_learns_an_in_grammar_family_and_reports_no_errors(self):
        res = L.run_struct_benchmark({"asm_struct": L.ASMStructLearner}, seed=SEED, tasks_per_family=6, ks=[24], families=["affine"])
        self.assertEqual(res["errors"], {})
        cell = res["cells"]["asm_struct"]["affine"]["24"]
        self.assertEqual(cell["wrong_rate"], 0.0)
        self.assertGreaterEqual(cell["correct_rate"], 0.8)

    def test_adapter_surfaces_exceptions(self):
        learner = L.ASMStructLearner()
        learner.fit({"family": "affine", "public": {"schema": ["x"]}, "task_id": "affine-9999"}, [(1, 10**13)])
        self.assertGreater(learner.errors, 0)


class PartBTests(unittest.TestCase):
    def test_donors_never_contain_the_target_constant_and_are_distinct(self):
        for c in T.IN_RANGE + T.OUT_OF_RANGE:
            for s in range(3):
                d = T.donor_constants(c, s, SEED)
                self.assertEqual(len(set(d)), 2); self.assertNotIn(c, d); self.assertTrue(all(x in T.IN_RANGE for x in d))
                self.assertEqual(d, T.donor_constants(c, s, SEED))

    def test_derangement_moves_every_label_and_is_deterministic(self):
        import random
        values = [20, 68, 85]
        for seed in range(50):                                                 # a plain shuffle of 3 items is the identity 1 time in 6
            out = T.derange(values, random.Random(seed))
            self.assertEqual(sorted(out), sorted(values))
            self.assertTrue(all(a != b for a, b in zip(out, values)))
        self.assertEqual(T.derange(values, random.Random(7)), T.derange(values, random.Random(7)))
        with self.assertRaises(ValueError):
            T.derange([5], random.Random(0))
        with self.assertRaises(ValueError):
            T.derange([5, 5, 5], random.Random(0))

    def test_arms_install_the_intended_number_of_active_donors(self):
        expected = {"none": 0, "one_relevant": 1, "relevant": 2, "unrelated": 4, "mixed": 6, "relevant_shuffled": 2}
        for arm, n in expected.items():
            r = T.run_attempt(arm, 3, 0, SEED)
            self.assertEqual((len(r["donor_constants"]), r["active_donors"]), (n, n), arm)
        with self.assertRaises(ValueError):
            T.donors_for("bogus", 3, 0, SEED)

    def test_attempts_are_deterministic(self):
        self.assertEqual(T.run_attempt("relevant", 5, 1, SEED), T.run_attempt("relevant", 5, 1, SEED))

    def test_discovered_transfer_capability_is_pinned(self):
        # Pins what the exploratory probe found: two relevant donors turn an unresolved induction into a solved one via the family mechanism.
        none, one, rel, shuf = (T.run_attempt(a, 3, 0, SEED) for a in ("none", "one_relevant", "relevant", "relevant_shuffled"))
        self.assertEqual(none["status"], "unresolved"); self.assertFalse(none["success"])
        self.assertEqual(one["status"], "unresolved")                          # one donor yields no family: no transfer
        self.assertTrue(rel["success"]); self.assertTrue(str(rel["origin"]).startswith("family:"))
        self.assertLess(rel["evaluator_calls"], none["evaluator_calls"] / 5)
        self.assertFalse(shuf["success"])                                      # no signal, no success
        for c in (1, 2, 4, 5, 6, 7):                                           # induction itself must not "find" a structure in shuffled fit labels
            self.assertNotEqual(T.run_attempt("relevant_shuffled", c, 0, SEED)["status"], "proposed")
            self.assertEqual(T.run_attempt("relevant", c, 0, SEED)["status"], "proposed")      # while the same donors DO solve the unshuffled task

    def test_out_of_range_constant_is_not_reachable_even_with_relevant_donors(self):
        self.assertFalse(T.run_attempt("relevant", 11, 0, SEED)["success"])

    def test_evaluator_flips_with_synthetic_results(self):
        def fake(rel=1.0, none=0.0, one=0.0, unr=0.0, mixed=1.0, shuf=0.0, out=0.0, wrong=0.0, cost_unr=300.0, cost_none=300.0):
            def arm(sr, c=300.0, w=0.0):
                return {"n": 48, "success_rate": sr, "mean_evaluator_calls": c, "family_origin_rate": 0.0, "wrong_answers": 0, "answered": 0, "wrong_per_query": w}
            ins = {"none": arm(none, cost_none, wrong), "one_relevant": arm(one), "relevant": arm(rel), "unrelated": arm(unr, cost_unr),
                   "mixed": arm(mixed), "relevant_shuffled": arm(shuf)}
            outs = {a: arm(out if a == "relevant" else 0.0) for a in ins}
            return {"summary": {"in_range": ins, "out_of_range": outs}, "attempts": [{"target_c": 3, "donor_constants": ["sq_p1", "sq_m2"]}]}
        ok = {v["id"]: v["passed"] for v in T.evaluate_part_b(fake(), PREREG)}
        self.assertTrue(all(ok.values()), ok)
        for kwargs, failing in (({"rel": 0.3}, "T1"), ({"one": 0.5}, "T2"), ({"unr": 0.0, "none": 0.4, "rel": 1.0}, "T3"), ({"cost_unr": 400.0}, "T3"),
                                ({"mixed": 0.2}, "T3b"), ({"wrong": 0.05}, "T4"), ({"out": 0.5}, "T5"), ({"shuf": 0.5}, "B-V2")):
            self.assertFalse({v["id"]: v["passed"] for v in T.evaluate_part_b(fake(**kwargs), PREREG)}[failing], (kwargs, failing))
        leak = fake(); leak["attempts"] = [{"target_c": 3, "donor_constants": ["sq_p3"]}]
        self.assertFalse({v["id"]: v["passed"] for v in T.evaluate_part_b(leak, PREREG)}["B-V1"])


class PreregistrationTests(unittest.TestCase):
    def test_document_matches_code_and_hash(self):
        doc = (ROOT / "ALPHA8_DEV4_PREREGISTRATION.md").read_text()
        self.assertEqual(json.loads(re.search(r"```json\n(.*?)\n```", doc, re.S).group(1)), PREREG)
        self.assertIn(S.prereg_hash(PREREG), doc)


if __name__ == "__main__":
    unittest.main()
