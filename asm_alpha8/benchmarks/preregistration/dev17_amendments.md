# DEV17 amendments log (the pre-registration file itself is never edited)

## A1 — four bugs in `Procedure.apply`, found after the first evaluation; evaluation discarded and re-run in full
- First evaluation (kept in `results/dev17/discarded_run1/`): G17-1 not passed (0/59 transfer), Q2 2/28, Q4 0/59.
- Before reporting it, a diagnostic asked whether each learned procedure reproduces the very fix it was learned from.
  It did for only 80/91 history and 58/59 BugsInPy examples, which exposed bugs in how rewrites were written back:
  1. multi-line strings inside a rewritten statement window were re-indented (their content changed): toolz `interpose`;
  2. an `elif` branch was written back as `if`, moving it out of its chain: semver `match`;
  3. a decorated definition was rewritten from its `def` line, duplicating the decorator: semver `Version.parse`;
  4. an expression replacing a generator expression that borrows a call's parentheses lost them:
     more_itertools `run_length.decode`.
- Fixes in `asm/coding/induction.py`, each with a regression test that fails without it; every expression rewrite is now
  checked against the intended syntax tree. After the fixes: 91/91 and 59/59 self-reproduce.
- Nothing else changed: no policy constant, mining criterion, split or evaluation rule. The history data is unchanged
  (mining does not use `apply`). The evaluation was re-run in full on the fixed code.
