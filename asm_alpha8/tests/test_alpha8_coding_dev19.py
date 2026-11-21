"""DEV19 tests: the miners' decoding of git output (amendment A1)."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmarks"))
import dev17_mine_history as M  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
