"""DEV30 tests: the M4-candidate battery's harness (configurations, donors in any role order, queries in n dimensions)."""
import itertools
import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
import dev30_battery as D  # noqa: E402
from asm.learning import structtransfer as T  # noqa: E402
from asm.procedure_cortex import ProcedureCortex  # noqa: E402
from asm.procedure_program import Program  # noqa: E402


class BatteryHarnessTests(unittest.TestCase):
    def test_the_configurations(self):
        defaults, stack = (ProcedureCortex(":memory:", trust_provider=T.TRUST, **D.CONFIGS[k]) for k in ("defaults", "stack"))
        try:
            attrs = ("family_sharing", "family_scope", "family_mapping", "family_parameters", "family_ambiguity", "family_memory",
                     "contradiction_policy")
            self.assertEqual([getattr(defaults, a) for a in attrs], ["round_robin", "any_int", "rename", "enumerate", "first", "window", "strict"])
            self.assertEqual([getattr(stack, a) for a in attrs], ["round_robin", "any_int", "rename", "solve", "ask", "index", "tolerant"])
        finally:
            defaults.close()
            stack.close()

    def test_arity_and_donors_in_every_role_order(self):
        for structure in D.DEV:
            n = D.arity(structure, D.DEV)
            self.assertEqual(n, 2 if structure.startswith("dev2") else 3)
            for order in itertools.permutations(range(n)):
                for name, expr, fn in D.relevant_donors(D.DEV, structure, 3, 0, D.DEV_SEED, order):
                    program = Program(dict.fromkeys(D.DONOR[:n], "int"), expr)
                    for p in itertools.product(range(-2, 3), repeat=n):
                        self.assertEqual(program.run(dict(zip(D.DONOR, p))), fn(*p))

    def test_queries_stay_inside_the_evidence_range(self):
        for n in (2, 3):
            corner = [tuple([9] * n), tuple([8] * n)] + [tuple([9] * (n - 1) + [8])]
            q = D.queries_for(corner, n, random.Random(1))
            self.assertEqual(len(q), 6)
            self.assertFalse(set(q) & (set(corner) | {v[:n] for v in D.VALIDATION}))
            self.assertTrue(all(8 <= x <= 17 for p in q for x in p))


if __name__ == "__main__":
    unittest.main()
