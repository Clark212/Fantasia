# DEV32 pre-registration: a guard against patches that hard-code the failing tests' data, on freshly mined real bugs

Written and committed to git before any fresh bug was mined. Its SHA-256 is recorded in the DEV32 run manifests. Anything
not listed here is exploratory. Alpha 8 (= milestone 0.4.9) plan items: alpha.8.4 (negative transfer protection) on real
data, with alpha.8.5 and, for G32-B, alpha.8.1/8.2 on real data. Nothing is promoted in DEV32 and no default changes.
Design approved by the project owner (2026-11-24): the test-copy guard; fresh bugs mined BugsInPy-style from light
projects ASM never used; the narrow rule (name-like strings and error or warning messages allowed); three arms (control,
learned, guarded).

## Question
In DEV31's development run, learned knowledge wrote a failing test's expected value into the code twice:
`return None` became `return 'rtmp://foo.de'` (youtube-dl-13) and `upload_date = None` became `upload_date = '19681210'`
(youtube-dl-41). Both passed the bug's tests and were wrong. The one correct learned repair so far (thefuck-19) also took
its content from a failing test, but only part of a test string: `'push --force'` became `'push --force-with-lease'`.

DEV32 asks two questions on real bugs no ASM run has touched:
- **G32-A (the guard):** does dropping the learned candidates that write the failing tests' data into the code stop wrong
  patches, without losing correct repairs, at a small cost to real fixes?
- **G32-B (DEV31's question on new bugs):** does learned knowledge repair bugs that the workflow without it does not?

## What changed before this commit (development only)
- **The guard** (`RepairWorkflow(test_copy_guard=True)`, opt-in, default off; `asm.coding.content.copied_test_strings`).
  - A phase-3 candidate is dropped before it is tested when its patch writes into the code a string that is a whole
    literal of the failing tests (or quoted in their failure messages) and is not already a string of the module.
  - **Allowed:** name-like strings (letters, digits, `_` and `-`, starting with a letter, `_` or dashes: `zero`,
    `--force`, `utf-8`), and strings inside error or warning messages (what a `raise` raises; arguments of exception or
    warning constructors and of warn/log/fail calls).
  - Dropped candidates are counted as `test_copy` (they are never tested) and listed in the dossier.
  - Phases 1-2 are unchanged: no built-in family writes a test's string into the code.
- **The bug miner** (`benchmarks/dev32_mine_bugs.py`) writes BugsInPy's corpus format, so DEV14's envs and validate stages
  and DEV29's per-bug evaluation run unchanged.
- **The harness** (`benchmarks/dev32_realbugs.py`) and the analysis (`benchmarks/dev32_analysis.py`). DEV29's per-bug
  evaluation also records what the guard dropped (`test_copy_dropped`), only when it dropped something; records without
  the guard are unchanged.
- Tests: `tests/test_alpha8_dev32.py`.

## Development (data already seen)
- **Every patch ASM accepted** in DEV15, DEV29 and DEV31 (59; `results/dev32/development/guard_on_accepted_patches.jsonl`):
  the rule flags exactly youtube-dl-13 and youtube-dl-41. It flags neither thefuck-19 nor any other accepted patch.
- **Real developer fixes** mined in DEV18-DEV21 (1,843; `guard_on_developer_fixes.json`): the rule flags 4 (0.22%): an
  error message stored in a table, `'0.00'`, `'\t'` and `'\x0c'`. It flags none of the developer fixes that learned
  knowledge reproduced in the DEV18-DEV21 evaluations.
- **DEV31's 74 fresh bugs** (now seen): with identifiers only as names, the rule flagged 2 developer fixes, the encoding
  names `'latin-1'` (scrapy-18) and `'utf-8'` (scrapy-30). Names were then widened to allow dashes; it now flags none.
- **The guarded arm on DEV15's 83 bugs** (`results/dev32/development/dev32_guarded_*of3.jsonl`), against DEV31's learned
  arm and DEV29's control:
  - **Resolved:** guarded 9 (control 9, DEV31's learned arm 12). The 3 DEV31 learned acceptances not in the guarded arm:
    youtube-dl-13 and youtube-dl-41, the two wrong test-copied patches, are no longer accepted (the guard dropped 12 and
    14 candidates there); youtube-dl-29 was lost (below).
  - **thefuck-19** (the one correct learned-only repair) is still repaired, restored: the guard dropped some of its
    candidates but not the repair.
  - **Dropped:** the guard dropped candidates in 46 bugs. Outcomes changed in 5 bugs against DEV31's learned arm: those
    three, tqdm-7 and youtube-dl-21 (time_budget to unresolved; no acceptance either way).
  - **youtube-dl-29 (timing):** control and DEV31's learned arm repaired it with a phases 1-2 family (guard_stmt); the
    guarded arm ended unresolved at 255.9 s. The guard acts only in phase 3. Run alone, the guarded arm resolves it in
    166.7 s with the same family (`youtube-dl-29_rerun.txt`): the loss was the clock, not the guard. This is the one
    allowed timing loss of A3; the full run is kept as it is.
  - **Time:** the longest guarded run 297 s (DEV31's learned arm: 323 s).
- **The new pipeline on bugs mined from two projects ASM already used** (tabulate and toolz;
  `results/dev32/development/pipeline_tabulate_toolz/`):
  - **Mining:** 15 bugs, 13 valid under Python 3.11. tabulate-3 is a work-in-progress commit whose own tests fail.
    tabulate-10 fixes an infinite loop, so its buggy version times out.
  - **The three arms:** no arm repaired any of the 13. 9 ended at the time budget, 1 unresolved. 3 have no spectrum:
    tracing tabulate's text-wrapping tests timed out, as DEV31's tracer did on black.
  - **The guard** dropped 26 learned candidates in 5 bugs, and changed no outcome.
  - **Time:** the longest learned run took 296 s and the longest guarded one 298 s.
  - **Cost:** the rule flags none of the 13 developer fixes.

## Fresh bugs
- **Projects** (`benchmarks/preregistration/dev32_projects.json`, with the dependency names given to the resolver):
  sqlglot, pyupgrade, astroid, rich, loguru, inflect, num2words, jsonpickle, markdownify, marko, soupsieve, parsel,
  pypika, yapf, autoflake and w3lib.
  - **Chosen as:** pure Python; the package at the repository root, so the tests import it from the tree; pytest-runnable
    tests; active 2023-2026; light dependencies.
  - **Never used by ASM:** none is a BugsInPy project, a DEV13-DEV21 subject, or a mined project. Some were only
    installed as dependencies of DEV31's bugs.
  - **Seen before this commit:** only depth-1 clones (the latest commit) were made, to read the top-level file list and
    the packaging files. No history, no commit and no test was looked at.
  - **Left out:** httpx (its tests need a local server; the sandbox has no network), starlette (asynchronous, heavy test
    dependencies), vulture and tinydb (their pytest options need a coverage plugin), emoji and bottle (very large modules
    or few recent commits).
- **Mining** (`dev32_mine_bugs.py`, unchanged after this commit):
  - Window: 2023-01-01 to 2026-10-31.
  - A fix-like subject (DEV17's FIX_RE), not a merge.
  - 1-2 modified Python files outside the tests, at most 20 changed lines in all.
  - Test modules added or modified, and no other test code (no conftest.py, helpers or data files).
  - Nothing else but documentation.
  - At least one test function added or changed; repeated identical fixes once.
  - At most 20 bugs per project: a seeded random sample (seed 32) of its candidates.
- **Environments:** each bug's dependencies are resolved for Python 3.11 as of the day after the fix. DEV14's envs and
  validate stages run unchanged under CPython 3.11.18.
- **VALID:** as BugsInPy defines it, the bug's tests fail on the buggy version (the parent with the fixed test modules)
  and pass on the fixed one. Attrition is reported per project and reason.

## Arms (`benchmarks/dev32_realbugs.py`; DEV29's per-bug evaluation)
- **control:** the shipped workflow with DEV15's repair families, 150 s (DEV31's control).
- **learned:** DEV31's learned arm. Phases 1-2 in 150 s, then DEV20's sealed libraries in phase 3 with 150 s of its own.
- **guarded:** the learned arm with the guard.
- **control_long:** the control with 300 s. It runs on every bug the learned or the guarded arm resolves and the control
  does not.
- **Running:** the three arms are paired, one after the other in one process per bug. 3 detached shards (bug index modulo
  3), and nothing else runs on the machine while they do. A run stopped by the machine is finished with `--resume`.
- **Sandbox:** tests run only through ASM's `SafeTestRunner`.

## Judging each accepted patch (as DEV31)
Every patch accepted (`resolved`) in any arm is read against the developer's patch, with the verdict correct, partial or
wrong. DEV15's oracle classifies each one too. When reading alone does not settle a patch, a probe on a distinguishing
input decides; it runs in the bug's environment inside ASM's sandbox. Verdicts, reasons and probes go into
`benchmarks/results/dev32/REALBUGS_REVIEW.md`. **Correct** is as DEV15, DEV29 and DEV31 define it.

**Flagged:** an accepted patch the guard's rule flags, by `dev32_analysis.py`: the patch applied to the buggy version,
with the failing tests' literals from their source. The live guard also uses quoted failure text, so the guarded arm can
drop more than this counts. It never accepts a flagged patch.

## Gate G32-A: the guard (person-read verdicts)
- **A1 something to stop:** the learned arm accepts at least 2 flagged patches.
- **A2 fewer wrong patches:** the guarded arm's wrong accepted patches number at least 2 fewer than the learned arm's.
- **A3 no loss:** no bug the learned arm repairs correctly is lost because its patch was flagged. At most 1 bug that the
  learned arm repairs correctly is not repaired correctly by the guarded arm for any other reason (timing).
- **A4 small cost:** the rule flags at most 2% of the valid bugs' developer fixes: each fix applied to its buggy version,
  with its failing tests' literals, over the valid bugs whose fix applies (DEV31: 74 of 75).
- **Passes iff A1-A4 all hold.**

## Gate G32-B: learned knowledge on new fresh bugs (DEV31's G31-A, unchanged, on these bugs)
- **B1 learned repairs:** at least 2 bugs are repaired correctly by the learned arm, and correctly neither by the
  control nor by control_long.
- **B2 no loss:** at most 1 bug that the control repairs correctly is not repaired correctly by the learned arm.
- **B3 safety:** the learned arm's wrong accepted patches number at most the control's plus 1.
- **B4 the clock holds:** no learned run takes longer than 360 s.
- **Passes iff B1-B4 all hold.** The guarded arm is reported against B1-B4 too, not gated.

## Reported, not gated
- the mining counts and the attrition, per project and reason;
- localization ranks, and how often phase 3 is reached;
- the guard's drops (bugs and candidates), and every flagged string;
- time per arm;
- each project;
- every accepted patch with both diffs and its verdict, and the oracle against the reading.

## Predictions (honest prior)
- **A1 is the main risk.** On DEV31's fresh bugs phase 3 ran in 44 bugs and accepted nothing, so the guard had nothing to
  stop. Two flagged acceptances need learned shapes to fit these projects' code.
- **B1 is hard:** one correct learned-only repair in DEV29, none in DEV31.

## Decision rules
- **No promotion, no default change.** Making the guard or `phase3_seconds` a default, and promoting 0.4.9 or M4, are the
  owner's decisions.
- **R3.** Bugs found during the run are fixed with a regression test; affected runs are discarded, kept, and re-run in
  full. Nothing else changes after seeing DEV32 data.
- **R4.** Every result is reported, including unfavourable ones.
