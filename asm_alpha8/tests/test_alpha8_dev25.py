"""DEV25 tests: family parameters solved exactly from the fit examples (ProcedureCortex(family_parameters='solve'), opt-in)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
import dev24_transfer as D24  # noqa: E402
import dev25_transfer as D  # noqa: E402
from asm.learning import structtransfer as T  # noqa: E402
from asm.procedure_cortex import ProcedureCortex  # noqa: E402
from asm.procedure_program import Program  # noqa: E402

DEV_SEED = 20261124
STRUCTURES = {**D.DEV, **D.DEV_NONAFFINE}
XYZ = dict.fromkeys(D24.TARGET, "int")


def run(structure, arm, c, mode, fit_seed=0):
    return D.attempt(STRUCTURES, structure, arm, c, fit_seed, DEV_SEED, mode, D24.DEV_UNRELATED)


def cortex(**options):
    return ProcedureCortex(":memory:", trust_provider=T.TRUST, **options)


def examples(f, points):
    return [{"inputs": dict(zip(D24.TARGET, p)), "expected": f(*p)} for p in points]


class FamilyParameterTests(unittest.TestCase):
    def test_the_default_is_enumerate_and_an_unknown_value_is_refused(self):
        c = cortex()
        try:
            self.assertEqual(c.family_parameters, "enumerate")
        finally:
            c.close()
        with self.assertRaises(ValueError):
            cortex(family_parameters="guess")

    def test_solve_parameters(self):
        c = cortex(family_parameters="solve")
        try:
            one = {"parameters": 1, "template": ("add", ("mul", "x", ("add", "y", "$0")), "z")}
            pts = [(2, 3, 4), (5, 1, 0), (7, 7, 7)]
            cost = [0]
            self.assertEqual(c._solve_parameters(one, {}, XYZ, examples(lambda x, y, z: x * (y + 11) + z, pts), cost), (11,))
            self.assertEqual(cost, [4])  # f(0), f(1) on the first example give the slope; neighbours 10 and 12 fail there
            self.assertIsNone(c._solve_parameters(one, {}, XYZ, examples(lambda x, y, z: x * y + z + 1, pts), [0]))  # 1/2
            flat = examples(lambda x, y, z: z, [(0, 3, 4), (0, 1, 0), (0, 7, 7)])  # x = 0: the parameter is undetermined
            self.assertIsNone(c._solve_parameters(one, {}, XYZ, flat, [0]))
            piecewise = {"parameters": 1, "template": ("max", ("add", "x", "$0"), ("mul", 2, "y"))}
            ranged = examples(lambda x, y, z: max(x - 7, 2 * y), [(4, 2, 0), (1, 3, 0), (2, 5, 0)])  # 0 and -1 both fit
            self.assertIsNone(c._solve_parameters(piecewise, {}, XYZ, ranged, [0]))  # not identified: not proposed
            two = {"parameters": 2, "template": ("add", ("add", ("mul", "$0", "x"), "y"), "$1")}
            cost = [0]
            self.assertIsNone(c._solve_parameters(two, {}, XYZ, examples(lambda x, y, z: 3 * x + y + 5, pts), cost))
            self.assertEqual(cost, [0])  # two parameters from three points leave one check: not solved, nothing spent
        finally:
            c.close()

    def test_constants_beyond_the_parameter_grid_transfer_only_when_solved(self):
        for c_, arm in ((11, "relevant_r0"), (-20, "relevant_r5")):
            enumerate_, solve = (run("dev_mul_add", arm, c_, m) for m in D.MODES)
            self.assertFalse(enumerate_["success"])
            self.assertTrue(solve["success"] and solve["origin"].endswith("#solved"))
            self.assertLess(solve["evaluator_calls"], 40)

    def test_constants_beyond_the_budgets_reach_transfer_when_solved(self):
        enumerate_, solve = (run("dev_sq_sub", "mixed_r5", 7, m) for m in D.MODES)
        self.assertFalse(enumerate_["success"])  # 18 sources share 256 proposals: values -8..5 only
        self.assertTrue(solve["success"])

    def test_a_family_not_affine_in_its_parameter_falls_back_to_enumeration(self):
        enumerate_, solve = (run("dev_shift_sq", "relevant_r0", 3, m) for m in D.MODES)
        self.assertTrue(enumerate_["success"] and solve["success"])
        self.assertFalse(solve["origin"].endswith("#solved"))
        self.assertEqual(solve["candidates"], enumerate_["candidates"])  # here the affine reading gave no integral solution

    def test_one_input_targets_solve_too(self):
        origins = {}
        for mode in D.MODES:
            c = cortex(family_parameters=mode)
            try:
                for k in (2, 6):
                    for i, n in enumerate((0, 1, 2)):
                        c.observe(f"sq{k}", {"n": n}, n * n + k, evidence_id=f"sq{k}-fit-{i}", source_id="oracle")
                    c.propose(f"sq{k}", Program({"n": "int"}, ("add", ("mul", "n", "n"), k)), provenance="external")
                    for i, n in enumerate(range(10, 18)):
                        c.observe(f"sq{k}", {"n": n}, n * n + k, evidence_id=f"sq{k}-val-{i}", source_id="oracle")
                for i, x in enumerate((1, 4, 7)):
                    c.observe("target", {"x": x}, x * x + 30, evidence_id=f"t{i}", source_id="oracle")
                origins[mode] = c.induce("target", use_families=True).get("origin")
            finally:
                c.close()
        self.assertTrue(str(origins["solve"]).endswith("@n=x#solved"))
        self.assertFalse(str(origins["enumerate"]).startswith("family:"))


if __name__ == "__main__":
    unittest.main()
