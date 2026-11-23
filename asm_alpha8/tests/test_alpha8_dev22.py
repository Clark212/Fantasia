"""DEV22 tests: learned families also propose for integer targets with several inputs (family_scope='any_int', opt-in)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
import dev22_transfer as D  # noqa: E402
from asm.learning import structtransfer as T  # noqa: E402
from asm.procedure_cortex import ProcedureCortex  # noqa: E402

DEV_SEED = 20261122


def run(structure, arm, c, fit_seed, mode):
    return D.attempt(D.STRUCTURES, structure, arm, c, fit_seed, DEV_SEED, mode)


class FamilyScopeTests(unittest.TestCase):
    def test_the_default_is_any_int_and_an_unknown_scope_is_refused(self):
        cortex = ProcedureCortex(":memory:", trust_provider=T.TRUST)
        try:
            self.assertEqual(cortex.family_scope, "any_int")  # the default since the owner's approval after G22-A
        finally:
            cortex.close()
        with self.assertRaises(ValueError):
            ProcedureCortex(":memory:", trust_provider=T.TRUST, family_scope="everything")

    def test_families_transfer_to_a_two_input_target_where_the_affine_fit_preempts_today(self):
        control, candidate = (run("dev_mulxy", "relevant", -8, 1, m) for m in ("one_input", "any_int"))
        self.assertEqual((control["status"], control["origin"], control["success"]), ("proposed", "multi_affine", False))
        self.assertTrue(candidate["success"])
        self.assertTrue(candidate["origin"].startswith("family:"))
        self.assertEqual(candidate["wrong"], 0)

    def test_an_affine_target_still_solves_and_the_family_cost_is_counted(self):
        control, candidate = (run("dev_affine", "unrelated", 3, 0, m) for m in ("one_input", "any_int"))
        self.assertTrue(control["success"] and candidate["success"])
        self.assertEqual(candidate["origin"], "multi_affine")
        self.assertEqual(candidate["candidates"], control["candidates"] + 64)  # the 64 unrelated family proposals

    def test_one_input_targets_are_unchanged_by_the_scope(self):
        for arm in ("relevant", "mixed", "unrelated"):
            a, b = (T.run_attempt(arm, 5, 1, 20261102, {"family_scope": s}) for s in ("one_input", "any_int"))
            self.assertEqual(a, b)


    def test_queries_for_a_fit_near_the_top_corner(self):
        """Amendment A1: the held-out run stopped when the region from the fit's lowest coordinates to 9 had < 6 pairs."""
        import random
        fit = [(7, 9), (8, 8), (9, 9)]
        q = D.queries_for(fit, random.Random(1))
        self.assertEqual(len(q), 6)
        self.assertFalse(set(q) & (set(fit) | set(D.VALIDATION)))
        self.assertTrue(all(7 <= x <= 17 and 8 <= y <= 17 for x, y in q))  # inside the evidence range
        typical = [(1, 2), (4, 0), (6, 5)]                                   # a typical fit draws exactly as before
        old = random.Random(3).sample(sorted({(x, y) for x in range(1, 10) for y in range(0, 10)} - set(typical)), 6)
        self.assertEqual(D.queries_for(typical, random.Random(3)), old)


if __name__ == "__main__":
    unittest.main()
