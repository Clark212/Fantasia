"""DEV31 tests: fresh real-bug setup and the repair workflow's phase-3 clock."""
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
import dev14_realbugs as R14  # noqa: E402
import dev29_realbugs as D29  # noqa: E402
import dev31_realbugs as D31  # noqa: E402
from asm.coding import induction  # noqa: E402
from asm.coding.content import ProblemContext  # noqa: E402
from asm.coding.faultloc import RepairWorkflow  # noqa: E402

SOURCE = "def get_new_command(command):\n    return replace_argument(command.script, 'push', 'push --force')\n"
CTX = ProblemContext(test_strings=["git push --force-with-lease"])


class FreshBugSetupTests(unittest.TestCase):
    def test_requirement_files_in_utf16_and_utf8_read_the_same(self):
        # black, fastapi, luigi, sanic and scrapy ship UTF-16 requirement files; reading them as UTF-8 crashed the envs stage
        lines = ["aiohttp==3.6.2", "click==7.1.2"]
        with tempfile.TemporaryDirectory() as td:
            for enc in ("utf-16", "utf-8"):
                path = Path(td) / enc
                path.write_bytes("\r\n".join(lines).encode(enc))
                self.assertEqual(R14.requirement_lines(path), lines)

    def test_the_arms(self):
        # phases 1-2 get the same 150 s in every arm; only the learned arm has phase 3, with 150 s of its own; the time
        # control gives the control the learned arm's total time
        self.assertEqual(D31.ARMS, {"control": ("control", 150.0, {}), "learned": ("learned", 150.0, {"phase3_seconds": 150.0}),
                                    "control_long": ("control", 300.0, {})})


class PhaseThreeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.libs = D29.libraries()

    def test_the_shared_parse_gives_what_a_fresh_parse_gives(self):
        procs = [e.procedure for e in list(self.libs["knowledge"].entries.values())[:300]]
        source = SOURCE + "\n\ndef other(x):\n    return [x + 1, 'a' + str(x)]\n"
        together = [p.apply_detailed(source, span) for span in ((1, 2), (5, 6)) for p in procs]
        alone = []
        for span in ((1, 2), (5, 6)):
            for p in procs:
                induction._parsed.cache_clear()
                induction._in_span.cache_clear()
                alone.append(p.apply_detailed(source, span))
        self.assertEqual(together, alone)
        self.assertTrue(any(together))

    def test_chunk_checks_give_what_whole_module_checks_give(self):
        # forcing every rewrite onto the whole module is the pre-DEV31 algorithm; awkward layouts must not change a result
        source = ("import os; x = f(1)\n\x0c\n@decorate(\n    'name')\ndef get(command, items=[1, 2]):\n"
                  "    \"\"\"Doc 'push'.\"\"\"\n    if command: return replace_argument(command.script, 'push', 'push --force')\n"
                  "    a = 1; b = len(items) + a\n    total = sum(\n        v * 2 for v in items)\n"
                  "    def inner(y):\n        return f'{y}' + str(y - 1)\n    return [inner(v) for v in items if v > b], total\n")
        libs, span = self.libs, (3, 14)
        run = lambda: (libs["knowledge"].candidates_for(source, "m.py", span, limit=500),  # noqa: E731
                       libs["shapes"].candidates_for(source, "m.py", span, CTX, limit=500, as_candidates=False),
                       libs["steps"].candidates_for(source, "m.py", span, CTX, limit=500, as_candidates=False))
        chunked = run()
        real = induction._parsed
        induction._in_span.cache_clear()
        with mock.patch.object(induction, "_parsed", lambda src: real(src)[:6] + ({None: None},)):
            whole = run()
        self.assertEqual([[c.replacement for c in chunked[0]], chunked[1], chunked[2]],
                         [[c.replacement for c in whole[0]], whole[1], whole[2]])
        self.assertTrue(all(chunked))

    def test_every_learned_library_stops_at_its_deadline(self):
        k, sh, st = self.libs["knowledge"], self.libs["shapes"], self.libs["steps"]
        made = sh.candidates_for(SOURCE, "m.py", (1, 2), CTX, as_candidates=False)
        self.assertIn("'push --force-with-lease'", "".join(prog for prog, _ in made))  # DEV29's thefuck-19 repair
        past = 0.0  # time.monotonic() is far beyond it
        self.assertEqual(k.candidates_for(SOURCE, "m.py", (1, 2), deadline=past), [])
        self.assertEqual(sh.candidates_for(SOURCE, "m.py", (1, 2), CTX, deadline=past), [])
        self.assertEqual(st.candidates_for(SOURCE, "m.py", (1, 2), CTX, deadline=past), [])

    def test_phase_three_gets_its_own_clock(self):
        class Recorder:  # a knowledge base that records the deadline phase 3 builds under
            calls = []

            def candidates_for(self, source, path, span, limit=30, deadline=None):
                Recorder.calls.append(None if deadline is None else deadline - time.monotonic())
                return []
        files = {"m.py": "def answer():\n    return 1\n", "tests/test_m.py": "from m import answer\ndef test_answer(): assert answer() == 12345\n"}
        with tempfile.TemporaryDirectory() as td:
            for name, text in files.items():
                (Path(td) / name).parent.mkdir(parents=True, exist_ok=True)
                (Path(td) / name).write_text(text)
            for seconds in (None, 40):
                Recorder.calls = []
                RepairWorkflow(time_budget_seconds=120, knowledge=Recorder(), phase3_seconds=seconds, max_iterations=1).run(td)
                self.assertTrue(Recorder.calls)  # nothing built-in reaches 12345, so phase 3 ran
                if seconds is None:
                    self.assertEqual(set(Recorder.calls), {None})  # DEV29's behaviour: no clock of its own, no deadline
                else:
                    self.assertTrue(30 < Recorder.calls[0] <= 35)  # 40 s from phase 3's start, less the 5 s margin


if __name__ == "__main__":
    unittest.main()
