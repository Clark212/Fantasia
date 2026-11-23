"""DEV24 tests: family transfer across input names on three-input targets (six mappings per family), and the label-noise
arms (each label wrong with probability NOISE)."""
import collections
import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
import dev24_transfer as D  # noqa: E402
from asm.learning import structtransfer as T  # noqa: E402
from asm.procedure_cortex import ProcedureCortex  # noqa: E402
from asm.procedure_program import Program  # noqa: E402

DEV_SEED = 20261123
XYZ = dict.fromkeys(D.TARGET, "int")


def run(arm, c, fit_seed, mode, structure="dev_mul_add"):
    return D.attempt(D.DEV, structure, arm, c, fit_seed, DEV_SEED, mode, D.DEV_UNRELATED)


class ThreeInputTests(unittest.TestCase):
    def test_role_donors_match_their_expressions(self):
        for order in range(6):
            expr, fn = D.role_donor(D.DEV, "dev_sq_sub", 4, order)
            program = Program(dict.fromkeys(D.DONOR, "int"), expr)
            for p in ((0, 1, 2), (3, -1, 5), (7, 4, 2)):
                self.assertEqual(program.run(dict(zip(D.DONOR, p))), fn(*p))

    def test_role_order_k_is_solved_by_the_kth_mapping(self):
        orders = [run(f"relevant_r{k}", -5, 0, "rename") for k in range(6)]
        self.assertTrue(all(r["success"] for r in orders))
        self.assertEqual([r["candidates"] for r in orders], [19, 20, 21, 22, 23, 24])  # turn 3 of 6 sources, then k + 1
        self.assertFalse(run("relevant_r3", -5, 0, "exact")["success"])  # no renaming: no transfer

    def test_eighteen_sources_share_256_proposals_and_reach_minus_8_to_5(self):
        c = ProcedureCortex(":memory:", trust_provider=T.TRUST)
        try:
            D.install(c, D.donors_for(D.DEV, "dev_mul_add", "mixed_r0", 3, 0, DEV_SEED, D.DEV_UNRELATED))
            origins = collections.Counter(o for _, o in c._family_candidates(XYZ, 64, 256))
            self.assertEqual((len(origins), sum(origins.values())), (18, 256))
            self.assertEqual(sorted(set(origins.values())), [14, 15])  # 14 full turns; 4 sources start a 15th
            self.assertEqual(D.MIXED_REACH, tuple(range(-8, 0)) + tuple(range(1, 6)))
        finally:
            c.close()

    def test_corrupt_is_deterministic_and_offsets_are_nonzero(self):
        labels = list(range(1000))
        a, n = D.corrupt(labels, random.Random(1))
        self.assertEqual((a, n), D.corrupt(labels, random.Random(1)))
        self.assertTrue(70 <= n <= 130)  # NOISE = 0.10
        self.assertTrue(all(x - y in D.OFFSETS for x, y in zip(a, labels) if x != y))

    def test_a_donor_with_a_wrong_label_never_becomes_active_and_the_harness_goes_on(self):
        donors = D.donors_for(D.DEV, "dev_mul_add", "relevant_r0", 3, 0, DEV_SEED, ())
        c = ProcedureCortex(":memory:", trust_provider=T.TRUST)
        try:
            rng = random.Random(0)
            while True:  # a seed that corrupts at least one label of the first donor
                state = rng.getstate()
                if D.corrupt([0] * 11, rng)[1]:
                    break
            rng.setstate(state)
            active, wrong = D.install(c, donors[:1], rng)
            self.assertEqual(active, 0)
            self.assertGreater(wrong, 0)
        finally:
            c.close()

    def test_noise_never_produces_an_answer_from_a_corrupted_target(self):
        for c in (-6, 2, 7):
            for fit_seed in range(3):
                r = run("noise_target", c, fit_seed, "rename")
                if r["wrong_target_labels"]:
                    self.assertEqual((r["answered"], r["success"]), (0, False))
                else:
                    self.assertEqual(r["success"], run("relevant_r0", c, fit_seed, "rename")["success"])

    def test_queries_stay_inside_the_evidence_range(self):
        corner = [(8, 9, 8), (9, 8, 9), (9, 9, 9)]  # fewer than 6 points between the fit's minima and 9
        q = D.queries_for(corner, random.Random(2))
        self.assertEqual(len(q), 6)
        self.assertFalse(set(q) & (set(corner) | set(D.VALIDATION)))
        self.assertTrue(all(8 <= x <= 17 and 8 <= y <= 17 and 8 <= z <= 17 for x, y, z in q))


if __name__ == "__main__":
    unittest.main()
