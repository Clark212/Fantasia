"""DEV27 tests: a family index kept in the database (ProcedureCortex(family_memory='index'), opt-in)."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
import dev24_transfer as D24  # noqa: E402
import dev27_transfer as D  # noqa: E402
from asm.learning import structtransfer as T  # noqa: E402
from asm.procedure_cortex import ProcedureCortex  # noqa: E402


def relevant(structure="dev_mul_add", c=-5):
    return D24.donors_for(D.DEV, structure, "relevant_r0", c, 0, D.DEV_SEED, ())


class FamilyMemoryTests(unittest.TestCase):
    def test_the_default_is_window_and_an_unknown_value_is_refused(self):
        c = ProcedureCortex(":memory:", trust_provider=T.TRUST)
        try:
            self.assertEqual(c.family_memory, "window")
        finally:
            c.close()
        with self.assertRaises(ValueError):
            ProcedureCortex(":memory:", trust_provider=T.TRUST, family_memory="everything")

    def test_a_small_memory_gives_the_same_families_in_both_modes(self):
        found = {}
        for mode in D.MODES:
            c = ProcedureCortex(":memory:", trust_provider=T.TRUST, family_memory=mode)
            try:
                D.install_memory(c, D.memory(12, D.DEV_MEMORY_SEED))
                D24.install(c, relevant())
                found[mode] = [(f["id"], f["template"], f["parameters"]) for f in c.families()]
            finally:
                c.close()
        self.assertTrue(found["window"])
        self.assertEqual(found["window"], found["index"])

    def test_past_32_active_versions_only_the_index_still_sees_the_relevant_family(self):
        seen = {}
        for mode in D.MODES:
            c = ProcedureCortex(":memory:", trust_provider=T.TRUST, family_memory=mode)
            try:
                D.install_memory(c, D.memory(48, D.DEV_MEMORY_SEED))
                D24.install(c, relevant())
                seen[mode] = any(p[0].startswith("z_rel_") for f in c.families() for p in f["parents"])
            finally:
                c.close()
        self.assertEqual(seen, {"window": False, "index": True})

    def test_the_index_survives_reopening_and_is_not_rebuilt(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "memory.db"
            c = ProcedureCortex(path, trust_provider=T.TRUST, family_memory="index")
            D.install_memory(c, D.memory(40, D.DEV_MEMORY_SEED))
            D24.install(c, relevant())
            before = [f["id"] for f in c.families()]
            c.close()
            c = ProcedureCortex(path, trust_provider=T.TRUST, family_memory="index")
            try:
                rows = c.db.execute("SELECT COUNT(*) FROM procedure_family_index").fetchone()[0]
                self.assertEqual(rows, 42)  # 40 background procedures and 2 donors, indexed once
                self.assertEqual([f["id"] for f in c.families()], before)
            finally:
                c.close()

    def test_a_family_is_used_only_while_both_parents_are_active(self):
        c = ProcedureCortex(":memory:", trust_provider=T.TRUST, family_memory="index")
        try:
            D24.install(c, relevant())
            self.assertEqual(len(c.families()), 1)
            name = relevant()[0][0]
            c.db.execute("UPDATE procedure_versions SET state='retired' WHERE mechanism=?", (name,))
            self.assertEqual(c.families(), [])
        finally:
            c.close()

    def test_the_gate_result_survives_the_hash_chain(self):
        """Development bug: integer keys (memory sizes) became strings on reading, so the result's hash broke."""
        import json
        recs = [{"structure": "dev_mul_add", "arm": a, "memory": m, "c": 1, "fit_seed": 0, "mode": mode, "success": a != "none",
                 "queries": 6, "wrong": 0, "evaluator_calls": 10 if a != "none" else 100, "families": 1}
                for a in D.ARMS for m in D.SIZES for mode in D.MODES]
        canonical = json.dumps(D.gate(recs, D.DEV), sort_keys=True)  # what the chain hashes
        self.assertEqual(json.dumps(json.loads(canonical), sort_keys=True), canonical)


if __name__ == "__main__":
    unittest.main()
