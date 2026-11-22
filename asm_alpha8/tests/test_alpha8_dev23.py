"""DEV23 tests: learned families also apply to targets whose inputs differ only by name (family_mapping='rename', opt-in)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
import dev23_transfer as D  # noqa: E402
from asm.learning import structtransfer as T  # noqa: E402
from asm.procedure_cortex import ProcedureCortex  # noqa: E402
from asm.procedure_program import Program  # noqa: E402

DEV_SEED = 20261122
STRUCTURES = {**D.DEV, **D.DEV_REGRESSION}
AB, XY = {"a": "int", "b": "int"}, {"x": "int", "y": "int"}


def run(structure, arm, c, fit_seed, mode):
    return D.attempt(STRUCTURES, structure, arm, c, fit_seed, DEV_SEED, mode, D.DEV_UNRELATED)


def cortex(**options):
    return ProcedureCortex(":memory:", trust_provider=T.TRUST, **options)


class FamilyMappingTests(unittest.TestCase):
    def test_the_default_is_exact_and_an_unknown_mapping_is_refused(self):
        c = cortex()
        try:
            self.assertEqual(c.family_mapping, "exact")
        finally:
            c.close()
        with self.assertRaises(ValueError):
            cortex(family_mapping="fuzzy")

    def test_renamings_keep_types_and_try_the_positional_order_first(self):
        exact, rename = cortex(), cortex(family_mapping="rename")
        try:
            self.assertEqual((exact._renamings(XY, XY), exact._renamings(AB, XY)), ([{}], []))
            self.assertEqual(rename._renamings(XY, XY), [{}])  # equal names keep their roles
            self.assertEqual(rename._renamings(AB, XY), [{"a": "x", "b": "y"}, {"a": "y", "b": "x"}])
            self.assertEqual(rename._renamings({"a": "int", "f": "bool"}, {"x": "bool", "y": "int"}), [{"a": "y", "f": "x"}])
            self.assertEqual(rename._renamings(AB, {"x": "int"}), [])
        finally:
            exact.close()
            rename.close()

    def test_a_family_over_other_names_transfers_in_both_role_orders(self):
        for arm, tag in (("relevant_aligned", "@a=x,b=y"), ("relevant_swapped", "@a=y,b=x")):
            control, candidate = (run("dev_mul_shift", arm, -5, 0, m) for m in D.MODES)
            self.assertEqual((control["status"], control["success"]), ("unresolved", False))
            self.assertTrue(candidate["success"])
            self.assertTrue(candidate["origin"].startswith("family:") and candidate["origin"].endswith(tag))
            self.assertEqual(candidate["wrong"], 0)

    def test_exact_name_families_give_the_same_attempt(self):
        a, b = (run("dev_mul_shift", "exact_names", 3, 0, m) for m in D.MODES)
        self.assertTrue(a["success"])
        self.assertEqual({k: v for k, v in a.items() if k != "mode"}, {k: v for k, v in b.items() if k != "mode"})

    def test_the_family_budget_grows_to_one_parameter_range_per_source_up_to_the_ceiling(self):
        c = cortex(family_mapping="rename")
        try:
            D.install(c, D.DEV_UNRELATED)  # two families over (p, q): four sources for a target over (x, y)
            origins = [o for _, o in c._family_candidates(XY, 64, 256)]
            self.assertEqual(len(origins), 68)
            self.assertEqual(sorted({origins.count(o) for o in origins}), [17])
            self.assertEqual(len(list(c._family_candidates(XY, 64, 0))), 64)  # never below the old budget
        finally:
            c.close()

    def test_an_input_named_like_an_operator_is_renamed_as_an_input_only(self):
        c = cortex(family_mapping="rename", family_scope="any_int")
        try:
            D.install(c, [(f"clamp{k}", ("add", ("min", "min", "n"), k), lambda m, n, k=k: min(m, n) + k) for k in (2, 5)])
            first = next(c._family_candidates(XY, 64, 256))[0]
            self.assertEqual(first.expression, ("add", ("min", "x", "y"), -8))
            for i, (x, y) in enumerate(((0, 4), (7, 2), (5, 9))):
                c.observe("target", {"x": x, "y": y}, min(x, y) - 3, evidence_id=f"t{i}", source_id="oracle")
            self.assertTrue(c.induce("target", use_families=True)["origin"].startswith("family:"))
        finally:
            c.close()

    def test_one_input_families_over_another_name_apply_only_when_renaming(self):
        origins = {}
        for mode in D.MODES:
            c = cortex(family_mapping=mode)
            try:
                for k in (2, 6):
                    for i, n in enumerate((0, 1, 2)):
                        c.observe(f"sq{k}", {"n": n}, n * n + k, evidence_id=f"sq{k}-fit-{i}", source_id="oracle")
                    c.propose(f"sq{k}", Program({"n": "int"}, ("add", ("mul", "n", "n"), k)), provenance="external")
                    for i, n in enumerate(range(10, 18)):
                        c.observe(f"sq{k}", {"n": n}, n * n + k, evidence_id=f"sq{k}-val-{i}", source_id="oracle")
                for i, x in enumerate((1, 4, 7)):
                    c.observe("target", {"x": x}, x * x - 3, evidence_id=f"t{i}", source_id="oracle")
                origins[mode] = c.induce("target", use_families=True).get("origin")
            finally:
                c.close()
        self.assertTrue(origins["rename"].startswith("family:") and origins["rename"].endswith("@n=x"))
        self.assertFalse(str(origins["exact"]).startswith("family:"))

    def test_one_input_labs_with_same_name_donors_are_unchanged(self):
        for arm in ("relevant", "mixed", "unrelated"):
            a, b = (T.run_attempt(arm, 5, 1, 20261102, {"family_mapping": m}) for m in D.MODES)
            self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
