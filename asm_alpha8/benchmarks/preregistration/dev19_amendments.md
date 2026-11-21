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

## A2: a full candidate budget still received one learned-shape candidate (81 tried instead of 80); the evaluation run is discarded and re-run in full (R3)

**Found:** while the first DEV19 evaluation run was in its learning cycle, its stack showed `s18_programs` called with
`limit 0` (P17 alone had filled K = 80). `ShapeLibrary.candidates_for` appended a candidate before checking the limit, so
`limit=0` returned one candidate: the D18 list (`dev18_evaluate.score`) and the learning cycle (DEV18 and DEV19) could
try 81 programs. `KnowledgeBase.candidates_for` had the same check order (no caller passed 0).

**Fix:** both return no candidates for `limit <= 0`, so the shape library is not searched when the budget is full. Every
other limit is unchanged (the first `limit` of the same ranked list). Regression tests:
`tests/test_alpha8_coding_dev19.py::BudgetTests` (the two limit-0 tests fail without the fix).

**Which results could it change?** Only a fix found at position 80 (the 81st program). No scored row has one: D18 hit
positions are at most 77 in the first DEV19 run (all 309 rows complete) and at most 57 in DEV18 run 3, so every scored row,
G18-1 and G19-1 are unchanged by the fix. A learning cycle can differ (positions are not recorded there). ASM's own repair
workflow could not reach it: learned procedures give at most 60 candidates there, so the shape limit is at least 20.

**Seen before the fix:** the first run's per-level counts (L91, L563, LALL; LALL: 0 new by D18), and the ids and
positions of its D18 hits, read to check the effect above; part of one problem's buggy function in the stack dump. No
fix in the fresh set was opened.

**Action:** the first evaluation run is discarded and kept (`discarded_eval1/`) and the evaluation is re-run in full on
the fixed code. Its scored rows must equal the first run's; any difference is reported. DEV18's learning cycle (reported
5 online) is re-checked on the fixed code, with the online hits that only the 81st program gave counted separately.
