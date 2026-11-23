# DEV29 pre-registration: learned knowledge in the repair workflow, on real bugs

Written and committed to git before the learned configuration was run on any real bug. Its SHA-256 is recorded in the
DEV29 run manifests. Anything not listed here is exploratory. Alpha 8 (= milestone 0.4.9) plan items: alpha.8.1 and
alpha.8.2 on real data, with alpha.8.5. Nothing is promoted in DEV29, no default changes, and no ASM code changes.

## Question
DEV17–DEV20 learned repair knowledge from real fixes in about 45 projects: procedures (DEV17), shapes (DEV18) and edit
steps that combine (DEV20). On fresh fixes, each was offered the whole function, and it reproduced almost nothing the
built-in operations did not (0 of 59, 2 of 472, 0 of 103, 1 of 483). DEV20's analysis: learned steps are generic, so
without knowing where the bug is, the right place competes with every other place in the function.

ASM's repair workflow does know where to look: it localizes the fault (the lines the failing tests execute) and tries
learned knowledge as phase 3, inside the suspects, after the built-in phases 1 and 2 accept nothing. That has never been
measured on real bugs. DEV29 asks: on DEV15's real historical bugs, does the workflow with learned knowledge correctly
repair bugs that the same workflow without it does not?

## Configuration (no ASM code changes)
- **Bugs:** DEV15's real historical bugs (BugsInPy: PySnooper, thefuck, tqdm, cookiecutter, httpie, youtube-dl),
  rebuilt from scratch with DEV14's unchanged prepare, envs and validate stages. The BugsInPy corpus is at commit
  `11c5f1eea954a42132cfd06bf257766a7963e0fd`; bugs run under Python 3.8 in per-bug environments; tests run only through
  ASM's `SafeTestRunner`. The bug set is whatever the validate stage finds valid now. DEV15 found 83 of 96; differences
  are reported.
- **The two arms**, paired and run one after the other for each bug in the same process
  (`benchmarks/dev29_realbugs.py`, 150 s workflow budget per arm, as DEV15):
  - **control:** the shipped workflow with DEV15's repair families (DEV15's configuration);
  - **learned:** the same, plus DEV20's sealed `KnowledgeBase`, `ShapeLibrary` and `StepLibrary` (files in
    `benchmarks/results/dev20/`, hashes recorded in every manifest) in phase 3.
- **Sharding:** 3 shards run in parallel over the bugs (bug index modulo 3), so both arms of a bug see the same load.
- **No leakage, and fresh to the knowledge.** The libraries were trained in DEV17–DEV20 on about 45 other projects, none
  of these six. The bugs were used in DEV14 and DEV15 to evaluate the built-in workflow, but nothing in the libraries,
  the workflow, or this configuration was chosen by looking at them. The learned arm is run on them for the first time
  after this commit.

## Judging each accepted patch
- **The oracle.** DEV15's oracle classifies every accepted patch against the developer's fixed program; the harness
  records the class and its details.
- **A person's reading.** Every accepted patch in either arm is then read against the developer's patch. The verdict —
  correct, partial or wrong — goes into `benchmarks/results/dev29/REALBUGS_REVIEW.md`, with the reason. When the reading
  and the oracle disagree, a probe on a distinguishing input decides, and it is recorded. DEV15 showed the oracle's
  `equivalent` needs a person on real bugs.
- **Correct** means the patched program behaves like the developer's fix on the behaviour the bug concerns (DEV15's
  standard): the bug's tests pass and no probe finds a difference.

## Development before this commit
- **Harness:** `benchmarks/dev29_realbugs.py` repeats DEV15's per-bug evaluation (localization rank, workflow, oracle)
  for both arms.
- **Tests:** `tests/test_alpha8_dev29.py` (2). The sealed libraries load as the committed files, and the learned
  configuration runs the workflow end to end on a small synthetic project.
- **Smoke test:** the control arm (DEV15's known configuration) ran on one real bug to check the harness. The learned
  arm ran on no real bug before this commit.

## Gate G29-A (person-read verdicts)
- **C1 learned repairs:** at least 2 bugs are repaired correctly by the learned arm and not by the control.
- **C2 no loss:** at most 1 bug that the control repairs correctly is not repaired correctly by the learned arm. The
  arms are identical up to phase 3, but run under a wall-clock budget.
- **C3 safety:** the learned arm's wrong accepted patches (person-read verdict wrong) number at most the control's plus 1.
- **Passes iff C1–C3 all hold.**
- **Reported, not gated:**
  - the valid bug set against DEV15's;
  - localization ranks;
  - how often phase 3 was reached and with what result;
  - every accepted patch with both diffs and both verdicts;
  - time budgets;
  - each project.
- **Prediction (honest prior).** DEV17–DEV20 reproduced at most 2 fresh fixes per run outside the lab, so C1 is hard.
  The outcome most likely to teach something is how often phase 3 is reached within the 150 s budget, and what it
  proposes there.

## Decision rules
- **No promotion, no default change.**
- **R3.** Bugs found during the run are fixed with a regression test; affected runs are discarded, kept, and re-run in
  full. Nothing else changes after seeing DEV29 data.
- **R4.** Every result is reported, including unfavourable ones.
