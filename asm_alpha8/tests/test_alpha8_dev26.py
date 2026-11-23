"""DEV26 tests: asking for the input that separates fitting family candidates (ProcedureCortex(family_ambiguity='ask'), opt-in)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
import dev24_transfer as D24  # noqa: E402
import dev26_transfer as D  # noqa: E402
from asm.learning import structtransfer as T  # noqa: E402
from asm.procedure_cortex import ProcedureCortex  # noqa: E402
from asm.procedure_program import Program  # noqa: E402

DEV_SEED = 20261125
XYZ = dict.fromkeys(D24.TARGET, "int")


def run(arm, c, fit_seed, mode, structure="dev_mul_add"):
    return D.attempt(D.DEV, structure, arm, c, fit_seed, DEV_SEED, mode, D24.DEV_UNRELATED)


class FamilyAmbiguityTests(unittest.TestCase):
    def test_the_default_is_first_and_an_unknown_value_is_refused(self):
        c = ProcedureCortex(":memory:", trust_provider=T.TRUST)
        try:
            self.assertEqual(c.family_ambiguity, "first")
        finally:
            c.close()
        with self.assertRaises(ValueError):
            ProcedureCortex(":memory:", trust_provider=T.TRUST, family_ambiguity="vote")

    def test_disagreement_query(self):
        c = ProcedureCortex(":memory:", trust_provider=T.TRUST)
        try:
            ex = [{"inputs": {"x": 1, "y": 2, "z": 1}, "expected": 3}, {"inputs": {"x": 2, "y": 0, "z": 2}, "expected": 2},
                  {"inputs": {"x": 0, "y": 5, "z": 0}, "expected": 5}]
            xz, zy = Program(XYZ, ("add", "x", "y")), Program(XYZ, ("add", "z", "y"))  # equal wherever x = z
            q = c._disagreement_query([xz, zy], ex, XYZ)
            self.assertNotEqual(q["input"]["x"], q["input"]["z"])  # a point that separates them
            self.assertNotIn(q["input"], [e["inputs"] for e in ex])
            self.assertIsNone(c._disagreement_query([xz, Program(XYZ, ("add", "y", "x"))], ex, XYZ))  # the same function
            self.assertIsNone(c._disagreement_query([xz], ex, XYZ))
        finally:
            c.close()

    def test_asking_recovers_an_ambiguous_fit_that_first_loses(self):
        first, ask = (run("deg_relevant_r5", -5, 0, m) for m in D.MODES)
        self.assertEqual((first["success"], first["asked"]), (False, 0))
        self.assertTrue(ask["success"])
        self.assertEqual(ask["asked"], 1)
        self.assertEqual(ask["wrong"], 0)

    def test_an_unambiguous_fit_asks_nothing(self):
        first, ask = (run("relevant_r0", 3, 0, m) for m in D.MODES)
        self.assertTrue(first["success"] and ask["success"])
        self.assertEqual(ask["asked"], 0)

    def test_without_solved_candidates_ask_changes_nothing(self):
        out = []
        for ambiguity in D.MODES:
            c = ProcedureCortex(":memory:", trust_provider=T.TRUST, family_parameters="enumerate", family_ambiguity=ambiguity)
            try:
                D24.install(c, D24.donors_for(D.DEV, "dev_mul_add", "relevant_r5", -5, 0, DEV_SEED, ()))
                for i, p in enumerate(((0, 1, 1), (1, 2, 1), (2, 0, 2))):
                    c.observe("target", dict(zip(D24.TARGET, p)), p[0] * (p[1] - 5) + p[2], evidence_id=f"t{i}", source_id="oracle")
                out.append({k: v for k, v in c.induce("target", use_families=True).items() if k != "version"})
            finally:
                c.close()
        self.assertEqual(out[0], out[1])


if __name__ == "__main__":
    unittest.main()
