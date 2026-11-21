"""DEV19 tests: the miners' decoding of git output (amendment A1); candidate budgets (amendment A2)."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmarks"))
import dev17_mine_history as M  # noqa: E402
import dev18_evaluate as E  # noqa: E402
from asm.coding.content import ProblemContext  # noqa: E402
from asm.coding.knowledge import KnowledgeBase  # noqa: E402
from asm.coding.shapes import ShapeLibrary  # noqa: E402

TRY_FIX = ("def a(parts, i):\n    parts.pop(i)\n    return parts\n",
           "def a(parts, i):\n    try:\n        parts.pop(i)\n    except IndexError:\n        pass\n    return parts\n", "x3")
TRY_FIX2 = ("def b(xs, k):\n    xs.pop(k)\n    return xs\n",
            "def b(xs, k):\n    try:\n        xs.pop(k)\n    except IndexError:\n        pass\n    return xs\n", "x4")


def text_mode(b: bytes) -> str:
    """What the miner returned before A1 (subprocess text=True, UTF-8 locale)."""
    import io
    return io.TextIOWrapper(io.BytesIO(b), encoding="utf-8", newline=None).read()


class MinerDecodingTests(unittest.TestCase):
    def test_valid_utf8_output_is_decoded_exactly_as_before(self):
        for b in (b"def f():\n    return 'caf\xc3\xa9'\n", b"a\r\nb\rc\n", b"", "☃ x\n".encode()):
            self.assertEqual(M.decode_output(b), text_mode(b))

    def test_a_latin1_source_with_its_coding_declaration_is_decoded_not_lost(self):
        b = "# -*- coding: iso-8859-1 -*-\ndef f():\n    return 'Fran\xe7ois'\n".encode("latin-1")
        with self.assertRaises(UnicodeDecodeError):
            text_mode(b)
        self.assertIn("Fran\xe7ois", M.decode_output(b))
        self.assertEqual(set(M.functions(M.decode_output(b))), {"f"})

    def test_undeclared_bad_bytes_become_replacement_characters(self):
        self.assertEqual(M.decode_output(b"x = '\xff'\n"), "x = '�'\n")

    def test_git_show_of_a_latin1_file_works_end_to_end(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            (repo / "m.py").write_bytes("# coding: latin-1\nNAME = 'Andr\xe9'\n".encode("latin-1"))
            subprocess.run(["git", "add", "m.py"], cwd=repo, check=True)
            subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "x"],
                           cwd=repo, check=True)
            self.assertIn("Andr\xe9", M.git(repo, "show", "HEAD:m.py"))


class BudgetTests(unittest.TestCase):
    """A2: a caller whose budget is already full (limit 0) gets no candidates; before the fix it got one, so the
    evaluation's D18 list and learning cycle could try 81 programs when P17 alone filled K = 80."""

    def setUp(self):
        self.lib = ShapeLibrary()
        self.lib.learn([TRY_FIX], "test")
        self.src = "def pick(xs, j):\n    xs.remove(j)\n    return xs\n"
        self.ctx = ProblemContext.build(self.src, [], None, ["ValueError: list.remove(x): x not in list"])

    def shapes(self, limit):
        return self.lib.candidates_for(self.src, "m.py", (1, 3), self.ctx, limit=limit, as_candidates=False)

    def test_a_full_budget_gets_no_shape_candidates(self):
        self.assertEqual(self.shapes(0), [])
        self.assertEqual(E.s18_programs(self.lib, self.src, self.ctx, 0), [])

    def test_every_other_shape_limit_gives_exactly_the_first_candidates(self):
        full = self.shapes(10 ** 6)
        self.assertGreaterEqual(len(full), 2)
        for n in range(1, len(full) + 2):
            self.assertEqual(self.shapes(n), full[:n])

    def test_a_full_budget_gets_no_procedure_candidates(self):
        kb = KnowledgeBase()
        kb.learn([TRY_FIX, TRY_FIX2], "test")
        src = "def c(ys, n):\n    ys.pop(n)\n    ys.pop(n)\n    return ys\n"
        full = kb.candidates_for(src, "m.py", (1, 4))
        self.assertGreaterEqual(len(full), 2)
        self.assertEqual(kb.candidates_for(src, "m.py", (1, 4), limit=0), [])
        self.assertEqual([c.replacement for c in kb.candidates_for(src, "m.py", (1, 4), limit=1)], [full[0].replacement])


if __name__ == "__main__":
    unittest.main()
