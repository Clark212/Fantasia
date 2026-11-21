# DEV19 amendments

## A1: the miners lost a whole project on one non-UTF-8 file; both mining runs discarded and re-run in full (R3)

**Found:** mining the training project dateutil, whose history contains a source file declared and encoded as
ISO-8859-1. The miners' `git()` helper (`benchmarks/dev17_mine_history.py`, also used by `dev18_mine_fresh.py` and
`dev19_mine.py`) decoded git output as strict UTF-8, raised `UnicodeDecodeError`, and the whole project was reported as
an error and left out.

**Fix:** `decode_output`: output that is valid UTF-8 is decoded exactly as before (UTF-8 with universal newlines, which
`text=True` did); otherwise the encoding a Python source declares (PEP 263), else UTF-8 with replacement characters.
DEV17 and DEV18 data are unaffected: every output those runs read was valid UTF-8 (anything else had raised), and it
decodes identically. Regression tests: `tests/test_alpha8_coding_dev19.py::MinerDecodingTests` (each fails without the fix).

**Seen before the fix:** only the per-project counts printed by the miner (fresh: pluggy 27, wcwidth 5, xmltodict 9,
python-slugify 1 examples; training: dateutil error). No mined fix was opened.

**Action:** both first mining runs are stopped, discarded and kept (`discarded_mining1/`), and re-run in full on the
fixed miner. Fresh projects mined without error in the first run must give identical records; any difference is reported.
