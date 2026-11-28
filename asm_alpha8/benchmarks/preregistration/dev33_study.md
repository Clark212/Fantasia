# DEV33 pre-registration: the project's own test suite as an acceptance check, on freshly mined real bugs

Written and committed to git before any fresh bug was mined. Its SHA-256 is recorded in the DEV33 run manifests. Anything
not listed here is exploratory. Alpha 8 (= milestone 0.4.9) plan items: alpha.8.4 (negative transfer protection) and
alpha.8.1/8.2 on real data, with alpha.8.5. Nothing is promoted in DEV33 and no default changes. Design chosen by the
assistant at the project owner's request ("U pick", 2026-11-27), after DEV32's report recommended it.

## Question
In DEV32, 12 of the 14 bugs ASM resolved got a wrong patch: it passed the bug's own tests and was wrong. The workflow
accepts a patch when the bug's tests pass and no executed test regresses, and only the bug's test files are executed.
DEV33 asks two questions on real bugs no ASM run has touched:
- **G33-A (the check):** does also requiring every test of the project's own suite that passes on the buggy version to
  keep passing stop wrong patches, without losing correct repairs, at a small cost to real fixes?
- **G33-B (learned knowledge, with the check):** does learned knowledge then repair fresh real bugs that the checked
  workflow without it does not, without extra wrong patches (DEV31's G31-A with DEV32's safety criterion)?

## What changed before this commit (development only)
- **The check** (`RepairWorkflow(regression_suite=[...])`, opt-in, default off).
  - The suite runs once on the original working copy; the tests that pass there are recorded.
  - A candidate that passes the bug's tests (and DEV10's behavioural contract) is then run against the suite on a copy;
    if any recorded test no longer passes, it is rejected (`rejected_regression_suite`, with the broken tests in the
    dossier) and the search goes on, as for any rejected candidate.
  - A test module that cannot be imported counts as one error, not the end of the run (`--continue-on-collection-errors`).
  - The time it takes counts against the workflow's budget.
- **The suite** of a bug (`benchmarks/dev33_development.py: project_suite`): its project's `tests/` or `test/`
  directory, else its top-level test modules, on the buggy tree.
- **The harness** (`benchmarks/dev33_realbugs.py`). DEV29's per-bug evaluation accepts per-bug options (a callable of
  the buggy tree) and records the regression suite; records without one are unchanged.
- Tests: `tests/test_alpha8_dev33.py`.

## Development (data already seen)
- **The whole suite on DEV32's 14 accepted patches** (`results/dev33/development/whole_suite_on_dev32_accepted.jsonl`):
  it breaks tests in 8 of the 10 wrong ones (inflect-2, -7, -9, jsonpickle-3, marko-4, rich-15, soupsieve-2, -4), in
  none of the 4 correct ones, and in none of the 14 developer fixes. It misses autoflake-2 and markdownify-4, whose wrong
  behaviour no existing test covers. A first run stopped at sqlglot's collection errors and is kept
  (`whole_suite_run1_stopped_at_collection_errors.jsonl`).
- **All 143 developer fixes of DEV32** (`whole_suite_on_dev32_developer_fixes_*of3.jsonl`): 134 have a suite. The check
  would reject 1 (0.7%): sqlglot-6's fix breaks `test_merge_subqueries`. 9 have no suite (pypika's tests live inside the
  package, and yapf-1), so the check is off for them. The suite takes a median of 6.6 s on a buggy tree, at most 89 s.
- **The checked arms on 30 of DEV32's bugs** (`dev33_checked_checked_learned_*of3.jsonl`; the 14 resolved bugs and 16
  of the others, seed 33, `checked_arms_bugs.txt`), against DEV32's control and learned arms with DEV32's verdicts:

  | | accepted | correct | wrong |
  |---|---|---|---|
  | DEV32 control | 10 | 2 | 8 |
  | checked | 3 (astroid-1, rich-11, markdownify-4) | 2 | 1 |
  | DEV32 learned | 14 | 4 | 10 |
  | checked_learned | 6 (+ astroid-4, sqlglot-14, autoflake-2) | 4 | 2 |

  - Every correct patch is still accepted, byte for byte the same edit; no rejected bug got another patch instead.
  - The check rejected candidates in 10 bugs (1-10 per arm). The longest checked run took 170 s, the longest
    checked_learned run 325 s (DEV32: 220 s and 345 s on the same bugs).

## Fresh bugs
- **Projects** (`benchmarks/preregistration/dev33_projects.json`, with the dependency names given to the resolver):
  markdown-it-py, mdit-py-plugins, mistletoe, uncertainties, bitstring, ftfy, add-trailing-comma, autopep8, pycodestyle,
  freezegun, feedparser, reorder-python-imports, tokenize-rt, idna, construct and dataclasses-json.
  - **Chosen as:** pure Python; the package at the repository root and a `tests/` or `test/` directory (so the suite is
    found); no coverage plugin in the pytest options; pytest-runnable; active in the window; light dependencies.
  - **Never used by ASM:** none is a BugsInPy project, a DEV13–DEV21 subject or mined project, or a DEV31–DEV32 project.
    tokenize-rt was installed before as a dependency of DEV32's pyupgrade bugs; no ASM run repaired it.
  - **Seen before this commit:** only depth-1 clones, to read the top-level file list and the packaging and pytest
    configuration. No history, no commit and no test was looked at.
  - **Left out:** pint, fire, docstring_parser and h11 (tests inside the package), jsonpath-ng (`src/` layout), asteval,
    rsa and cmd2 (their pytest options need a coverage plugin), fastjsonschema (its tests need a git submodule), typer
    (slow subprocess tests) and executing (its tests depend on the exact Python version).
- **Mining, environments, VALID:** DEV32's, unchanged (`dev32_mine_bugs.py`; window 2023-01-01 to 2026-10-31; ≤ 20
  bugs per project, seed 32; Python 3.11; DEV14's envs and validate).

## Arms (`benchmarks/dev33_realbugs.py`; DEV29's per-bug evaluation)
- **control:** the shipped workflow with DEV15's repair families, 150 s (DEV31's and DEV32's control).
- **learned:** DEV31's learned arm: phases 1-2 in 150 s, then DEV20's sealed libraries in phase 3 with 150 s of its own.
- **checked:** the control with the project's suite as regression suite.
- **checked_learned:** the learned arm with the project's suite as regression suite.
- **checked_long:** the checked control with 300 s. It runs on every bug checked_learned resolves and checked does not.
- **Running:** the four arms are paired, one after the other in one process per bug. 3 detached shards (bug index
  modulo 3), a background task keeps the session alive, and nothing else runs on the machine. A run stopped by the
  machine is finished with `--resume`.
- **Sandbox:** tests run only through ASM's `SafeTestRunner`.

## Judging each accepted patch (as DEV31 and DEV32)
Every patch accepted (`resolved`) in any arm is read against the developer's patch, with the verdict correct or wrong
(DEV15's definition: correct means the developer's behaviour on every input a probe or the reading finds). A probe on a
distinguishing input decides when reading alone does not; it runs in the bug's environment inside ASM's sandbox.
Verdicts, reasons and probes go into `benchmarks/results/dev33/REALBUGS_REVIEW.md`.

## Gate G33-A: the check (person-read verdicts)
- **A1 fewer wrong patches:** checked_learned's wrong accepted patches number at most half of learned's, and at least 2
  fewer.
- **A2 no loss:** at most 1 bug that learned repairs correctly is not repaired correctly by checked_learned.
- **A3 small cost:** the check rejects at most 5% of the valid bugs' developer fixes: the fixed version against the
  buggy one on the project's suite, over the valid bugs.
- **Passes iff A1-A3 all hold.** The control pair (checked against control) is reported the same way, not gated.

## Gate G33-B: learned knowledge with the check (DEV32's G32-B on the checked arms)
- **B1 learned repairs:** at least 2 bugs are repaired correctly by checked_learned, and correctly neither by checked
  nor by checked_long.
- **B2 no loss:** at most 1 bug that checked repairs correctly is not repaired correctly by checked_learned.
- **B3 safety:** checked_learned's wrong accepted patches number at most checked's plus 1.
- **B4 the clock holds:** no checked_learned run takes longer than 360 s (as DEV31 and DEV32).
- **Passes iff B1-B4 all hold.**

## Reported, not gated
- the mining counts and the attrition, per project and reason;
- the suites: size, time, and the bugs where none is found or it does not run;
- the check's rejections (bugs, candidates, broken tests) and what each arm accepted instead;
- localization ranks, how often phase 3 is reached, time per arm;
- every accepted patch with both diffs and its verdict, and the oracle against the reading.

## Predictions (honest prior)
- **A1 is likely if the arms accept wrong patches at DEV32's rate;** the risk is too few accepted patches on these
  projects for 2 fewer.
- **B1 is hard:** 2 learned-only correct repairs happened once (DEV32), on 143 bugs.

## Decision rules
- **No promotion, no default change.** Making `regression_suite` a default, and promoting 0.4.9 or M4, are the
  owner's decisions.
- **R3.** Bugs found during the run are fixed with a regression test; affected runs are discarded, kept, and re-run in
  full. Nothing else changes after seeing DEV33 data.
- **R4.** Every result is reported, including unfavourable ones.
