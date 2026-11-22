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
    def test_the_default_is_one_input_and_an_unknown_scope_is_refused(self):
        cortex = ProcedureCortex(":memory:", trust_provider=T.TRUST)
        try:
            self.assertEqual(cortex.family_scope, "one_input")
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


if __name__ == "__main__":
    unittest.main()
