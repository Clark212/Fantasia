"""DEV28 tests: one tolerated contradiction (ProcedureCortex(contradiction_policy='tolerant'), opt-in)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
import dev24_transfer as D24  # noqa: E402
import dev28_transfer as D  # noqa: E402
from asm.learning import structtransfer as T  # noqa: E402
from asm.procedure_cortex import ProcedureCortex  # noqa: E402
from asm.procedure_program import Program  # noqa: E402

XYZ = dict.fromkeys(D24.TARGET, "int")
TRUE = Program(XYZ, ("add", ("mul", "x", "y"), "z"))
POINTS = ((1, 2, 3), (2, 0, 5), (4, 3, 1), (0, 5, 2), (3, 3, 3))


def cortex(policy):
    return ProcedureCortex(":memory:", trust_provider=T.TRUST, contradiction_policy=policy)


def observe(c, points, wrong=(), start=0, prefix="f"):
    for i, p in enumerate(points):
        v = dict(zip(D24.TARGET, p))
        c.observe("m", v, TRUE.run(v) + (1 if i + start in wrong else 0), evidence_id=f"{prefix}{i}", source_id="oracle")


class ContradictionPolicyTests(unittest.TestCase):
    def test_the_default_is_strict_and_an_unknown_value_is_refused(self):
        c = ProcedureCortex(":memory:", trust_provider=T.TRUST)
        try:
            self.assertEqual(c.contradiction_policy, "strict")
            self.assertFalse(c._tolerates(1, 100))
        finally:
            c.close()
        with self.assertRaises(ValueError):
            ProcedureCortex(":memory:", trust_provider=T.TRUST, contradiction_policy="lenient")

    def test_tolerant_allows_one_contradiction_beside_four_agreeing_labels(self):
        c = cortex("tolerant")
        try:
            self.assertEqual([c._tolerates(m, a) for m, a in ((0, 0), (1, 4), (1, 3), (2, 9))], [True, True, False, False])
        finally:
            c.close()

    def test_propose_with_one_wrong_fit_label(self):
        for policy, expected in (("strict", "rejected"), ("tolerant", "proposed")):
            c = cortex(policy)
            try:
                observe(c, POINTS, wrong={1})
                self.assertEqual(c.propose("m", TRUE, provenance="external")["status"], expected)
                if policy == "tolerant":
                    self.assertEqual(c.versions("m")[0]["contradictions"], 1)
            finally:
                c.close()

    def test_validation_keeps_one_contradiction_in_total_and_suspends_at_the_second(self):
        c = cortex("tolerant")
        try:
            observe(c, POINTS)
            c.propose("m", TRUE, provenance="external")
            observe(c, D.VALIDATION[:9], wrong={3}, prefix="v")  # one wrong label among nine
            self.assertEqual(c.versions("m")[0]["state"], "active")
            observe(c, D.VALIDATION[9:], wrong={0}, prefix="w")  # a second contradiction
            self.assertNotEqual(c.versions("m")[0]["state"], "active")
        finally:
            c.close()
        c = cortex("strict")
        try:
            observe(c, POINTS)
            c.propose("m", TRUE, provenance="external")
            observe(c, D.VALIDATION[:9], wrong={3}, prefix="v")
            self.assertEqual(c.versions("m")[0]["state"], "suspended")
        finally:
            c.close()

    def test_solving_outvotes_one_wrong_label(self):
        c = cortex("tolerant")
        try:
            family = {"parameters": 1, "template": ("add", ("mul", "x", "y"), ("add", "z", "$0"))}
            ex = [{"inputs": dict(zip(D24.TARGET, p)), "expected": TRUE.run(dict(zip(D24.TARGET, p))) + 7} for p in POINTS]
            ex[0] = {**ex[0], "expected": ex[0]["expected"] + 2}  # the first label, which strict solving would trust, is wrong
            self.assertEqual(c._solve_tolerant(family, {}, XYZ, ex, [0]), (7,))
            self.assertEqual(c._solve_parameters(family, {}, XYZ, ex, [0]), (9,))  # strict trusts the first label
            ex[1] = {**ex[1], "expected": ex[1]["expected"] - 3}  # two wrong labels: no longer tolerated
            self.assertIsNone(c._solve_tolerant(family, {}, XYZ, ex, [0]))
        finally:
            c.close()

    def test_a_noisy_transfer_that_strict_loses_and_tolerant_wins_without_a_wrong_answer(self):
        runs = {m: D.attempt(D.DEV, "dev_mul_add", "noise05_r0", c, s, D.DEV_SEED, m, D24.DEV_UNRELATED)
                for m in D.MODES for c, s in [(-5, 1)]}
        self.assertFalse(runs["strict"]["success"])
        self.assertTrue(runs["tolerant"]["success"])
        self.assertEqual(runs["tolerant"]["wrong"], 0)


if __name__ == "__main__":
    unittest.main()
