# DEV15 amendments log (the pre-registration file itself is never edited; its hash stays as committed)

## A1 — ASM bug found during the first run; all runs discarded and restarted (pre-registered bug clause)
- When: about 12 minutes into the first launch of the pre-registered runs (2 real-bug shards, semver and parse
  calibration). No decoy run had started.
- What: real bug cookiecutter-4 was "resolved" by `try_except`: the `yield` of the `work_in` context manager was wrapped
  in `try/except AttributeError: pass`. An exception raised at a `yield` comes from the caller's `with` block, here the
  test itself, so the test's own failure was swallowed. Label high, oracle `wrong`.
- Fix: no wrapper or guard is placed around a statement containing yield / yield from / await, and generator functions
  get no early-return guard (`repair_ops._suspends`). Regression tests:
  `test_no_wrapper_or_guard_around_a_suspension_point`, `test_contextmanager_yield_wrapper_cannot_hide_a_failing_test`
  (both fail when the fix is reverted).
- Runs: every record of the first launch is discarded and kept for the report in
  `benchmarks/results/dev15/discarded_run1/`. All runs were restarted from the beginning on the fixed code. Nothing else
  changed (no rule, flag, threshold, budget or other operator).
- An even earlier launch (seconds long, before detaching the processes) wrote only run manifests; those files were
  deleted, not kept.
