# DEV29, first evaluation run: discarded under rule R3 (kept, not used)

The first pre-registered evaluation started at 15:41:01Z: 3 shards, pre-registration SHA-256 `a0b0bf13…`, `asm.coding`
SHA-256 `9a106b80…`. It stopped incomplete, with 34 of 83 bugs done in both arms. Shards 0 and 2 crashed on an ASM bug,
and shard 1 was stopped by hand at 16:22.

## The bug
- **Where:** `asm/coding/diagnostics.py`, `FailureAnalyzer.analyze`, in the code since the DEV14 baseline.
- **The trigger:** `SafeTestRunner` keeps the last 12,000 characters of a test run's output, so the kept text can begin
  mid-word. tqdm's test output contains timing figures (for example `233016.89it/s`), so the cut point varies from run to
  run. Here the kept output began with the line `onError`, the tail of a cut-off `AssertionError`
  (`crash_input_tqdm4_control.txt`).
- **The failure:** that line matches the exception pattern without its optional message group, and
  `None.strip()` raised `AttributeError` through the whole evaluation.
- **The crashes:** shard 0 in tqdm-4's control arm, shard 2 in tqdm-3's control arm.
- **Reproduction:** the crash reproduced on tqdm-4's control arm with the analyzer wrapped to save its input.
- **The fix:** a missing message is read as empty, one line. The regression test is
  `tests/test_alpha8_dev29.py::test_an_exception_name_without_a_message_is_analyzed`; it fails on the old code and
  passes on the fix. Wherever the old code did not crash, it behaves exactly as before.

## What else happened during this run
From 15:46:36Z to 16:07:09Z, DEV30's development run, held-out run and analyses shared the 4-CPU machine, one process at
a time. The workflow runs under a 150 s wall-clock budget, so that load could have changed outcomes. The full re-run
makes this moot; it runs with nothing else on the machine.

## What was seen before the discard (reported under R4)
On the 34 completed bugs:
- **the control matched DEV15's status on every bug;**
- **the learned arm repaired one bug the control did not:** thefuck-19, a patch identical to the developer's;
- **phase 3 was reached in 24 bugs.** There the learned arm hit the time budget 18 times, ended unresolved 5 times and
  resolved once. A first count said 26, wrongly including 2 bugs where no phase ran (`benchmarks/dev29_analysis.py`
  now separates them).

Nothing was changed because of these results. The only change before the re-run is the fix above.

## Files
- `dev29_evaluate_{0,1,2}of3.jsonl`: the hash-chained records as written;
- `shard{0,1,2}_log_without_warnings.txt`: the shard logs, without the projects' `SyntaxWarning` lines (thousands per
  shard);
- `crash_input_tqdm4_control.txt`: the output that crashed the analyzer, saved by the reproduction.
