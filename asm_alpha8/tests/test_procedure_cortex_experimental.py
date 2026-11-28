from __future__ import annotations

import unittest

from asm.procedure_cortex import ExperimentalProcedureCortex, evaluate_expression


class ProcedureCortexExperimentalTests(unittest.TestCase):
    def test_affine_induction_and_execution(self):
        c = ExperimentalProcedureCortex(min_support=4)
        for x in range(1, 6):
            c.record("f", (x,), 2*x+3, evidence_id=f"e{x}")
        v = c.induce_affine("f")
        self.assertIsNotNone(v)
        self.assertEqual(v.status, "active")
        self.assertEqual(c.execute("f", (11,))["value"], 25.0)

    def test_boolean_induction(self):
        c = ExperimentalProcedureCortex(min_support=4)
        rows = [((False, False), False), ((False, True), True),
                ((True, False), True), ((True, True), False)]
        for i, (x, y) in enumerate(rows):
            c.record("xor", x, y, evidence_id=f"b{i}")
        v = c.induce_boolean("xor")
        self.assertIsNotNone(v)
        self.assertEqual(v.status, "active")
        self.assertTrue(c.execute("xor", (True, False))["value"])

    def test_contradictions_suspend_compiled_version(self):
        c = ExperimentalProcedureCortex(min_support=4, suspend_after=2)
        for x in range(4):
            c.record("f", (x,), 2*x+3, evidence_id=f"e{x}")
        v = c.induce_affine("f")
        self.assertEqual(v.status, "active")
        c.record("f", (10,), 999, evidence_id="bad1")
        self.assertEqual(v.status, "suspicious")
        c.record("f", (11,), 999, evidence_id="bad2")
        self.assertEqual(v.status, "suspended")
        self.assertEqual(c.execute("f", (2,))["status"], "no_active_procedure")

    def test_context_revision_preserves_old_version(self):
        c = ExperimentalProcedureCortex(min_support=4)
        for x in range(4):
            c.record("f", (x,), 2*x+3, evidence_id=f"a{x}", context="day")
        v1 = c.induce_affine("f", context="day")
        for x in range(4):
            c.record("f", (x,), 3*x+1, evidence_id=f"b{x}", context="night")
        v2 = c.induce_affine("f", context="night")
        self.assertNotEqual(v1.version, v2.version)
        self.assertEqual(c.execute("f", (5,), context="day")["value"], 13.0)
        self.assertEqual(c.execute("f", (5,), context="night")["value"], 16.0)

    def test_disagreement_probe_selects_distinguishing_input(self):
        c = ExperimentalProcedureCortex(min_support=10)
        c.propose("f", ("add", ("var", 0), ("const", 1)), input_arity=1)
        c.propose("f", ("add", ("var", 0), ("const", 2)), input_arity=1)
        result = c.disagreement_probe("f", [(0,), (5,)])
        self.assertEqual(result["status"], "disagreement")
        self.assertEqual(result["distinct_outputs"], 2)

    def test_affine_family_abstraction(self):
        c = ExperimentalProcedureCortex(min_support=4)
        for name, b in (("f", 3), ("g", 8)):
            for x in range(4):
                c.record(name, (x,), 2*x+b, evidence_id=f"{name}{x}")
            self.assertEqual(c.induce_affine(name).status, "active")
        families = c.affine_families()
        self.assertEqual(len(families), 1)
        self.assertEqual(families[0].parameter, "$b")
        self.assertEqual(set(families[0].members), {"f@1", "g@1"})

    def test_malformed_expression_fails_closed_no_eval(self):
        c = ExperimentalProcedureCortex()
        with self.assertRaises(ValueError):
            c.propose("pwn", ("__import__", ("const", "os")), input_arity=1)
        with self.assertRaises(ValueError):
            evaluate_expression(("var", 99), (1,))

    def test_snapshot_roundtrip(self):
        c = ExperimentalProcedureCortex(min_support=3)
        for x in range(3):
            c.record("f", (x,), 4*x+2, evidence_id=f"e{x}")
        c.induce_affine("f")
        payload = c.export_state()
        d = ExperimentalProcedureCortex.import_state(payload)
        self.assertEqual(d.execute("f", (7,))["value"], 30.0)
        self.assertEqual(d.versions["f"][0].evidence_ids, c.versions["f"][0].evidence_ids)


if __name__ == "__main__":
    unittest.main()
