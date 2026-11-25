# ASM Alpha 8 DEV32 — A Guard Against Test-Copied Patches, on Freshly Mined Real Bugs (implementation report)

Status: **experimental; NOT promoted; no default changed** (pre-registered; design approved by the project owner).
**Neither gate passed.** G32-A (the guard) had nothing to stop on fresh bugs. G32-B met its main criterion for the
first time: 2 fresh real bugs were repaired correctly only with learned knowledge. It failed on safety: learned knowledge
also added 2 wrong patches, and at most 1 is allowed. Alpha 8 (= milestone 0.4.9) plan items: alpha.8.4 (negative
transfer protection) on real data, alpha.8.5, and alpha.8.1/8.2 on real data. ASM contains no language model and no
transformer.

## Headline (read this first)
- **What DEV32 tests.**
  - **G32-A:** in DEV31's development run, learned knowledge wrote a failing test's expected value into the code twice,
    and both patches were wrong. DEV32 adds an opt-in guard that drops such candidates before they are tested, and asks
    whether it stops wrong patches without losing correct ones.
  - **G32-B:** DEV31's question again, on new fresh bugs: does learned knowledge repair bugs the workflow without it
    does not?
- **Fresh data.** 172 bugs mined BugsInPy-style from 16 light projects ASM never used (`benchmarks/dev32_mine_bugs.py`,
  committed with the pre-registration before any was mined). 143 are valid.
- **Result** (every accepted patch read by a person against the developer's fix, with probes:
  `benchmarks/results/dev32/REALBUGS_REVIEW.md`):

  | | control (150 s) | learned (+ phase 3's own 150 s) | guarded (learned + guard) |
  |---|---|---|---|
  | bugs with an accepted patch | 10 | 14 | 14 (the learned arm's, byte-identical) |
  | correct | 2 | **4** | 4 |
  | wrong | 8 | 10 | 10 |
  | resolved only with learned knowledge | — | 4: astroid-4 ✔, sqlglot-14 ✔, autoflake-2 ✘, marko-4 ✘ | the same 4 |

  The 300 s control (`control_long`) repaired none of the 4.
- **G32-A not passed.** No accepted patch on the fresh bugs wrote a test string into the code, so the guard had nothing
  to stop. A1 (≥ 2 such patches in the learned arm) failed with 0, and A2 (≥ 2 fewer wrong patches) failed with 0 fewer.
  A3 (no loss) and A4 (cost: 1 of 143 developer fixes flagged, 0.7%) held.
  - The guard dropped 1,030 untested candidates in 79 bugs and changed no accepted patch.
  - On DEV15's bugs (development) it did what it was built for: youtube-dl-13 and youtube-dl-41 were no longer accepted
    wrongly, and thefuck-19 was still repaired.
- **G32-B not passed, on safety.**
  - **B1 (≥ 2 bugs repaired correctly only with learned knowledge) is met for the first time on fresh real bugs.**
    astroid-4 is identical to the developer's fix. sqlglot-14 behaves the same as the developer's fix, by an odd route.
  - **B3 fails:** the two other learned-only patches are wrong, 10 wrong against the control's 8 + 1 allowed.
    - autoflake-2 fixes one of two cases and changes a third.
    - In marko-4, a learned step put the failing test's error type (`AssertionError`) where a class name was.
  - B2 (no loss) and B4 (the clock: longest learned run 345 s, limit 360) held.
- **What it means.**
  - Learned knowledge now repairs some fresh real bugs: 2 of 143, both string-content procedures. As often, it makes
    wrong patches that pass the bug's tests.
  - The guard's rule targets one failure, whole test strings copied into the code. It does not catch the wrong patches
    that actually occurred on fresh bugs: a test's error type used as a name, or a partial edit.
  - The control's own patches are mostly wrong (8 of 10). The bugs' tests are weak oracles; see the limitations.

## What DEV32 changed
| piece | code |
|---|---|
| the guard | `RepairWorkflow(test_copy_guard=False\|True)`, opt-in, default off. In phase 3, a learned candidate whose patch writes into the code a string constant that is a whole literal of the failing tests (or quoted in their failure text), and not already in the module, is dropped before testing (`reasons['test_copy']`, a `test_copy` entry in the dossier). Allowed: name-like strings (`zero`, `--force`, `utf-8`) and strings inside error, warning and log messages. The rule is `asm.coding.content.copied_test_strings` (≈ 30 lines) |
| the miner | `benchmarks/dev32_mine_bugs.py`: BugsInPy-format bugs from a project's history (window, fix-like subject, 1-2 source files and ≤ 20 lines, test modules only, ≤ 20 bugs per project by a seeded sample), with dependencies resolved for Python 3.11 as of the day after the fix. DEV14's envs and validate stages and DEV29's per-bug evaluation run on them unchanged |
| harness and analysis | `benchmarks/dev32_realbugs.py` (arms, shards, `--resume`, time control, summary), `benchmarks/dev32_analysis.py`, `benchmarks/dev32_development.py`, `benchmarks/dev32_probes.py`. DEV29's per-bug evaluation records what the guard dropped (`test_copy_dropped`), only when it dropped something |
| tests | `tests/test_alpha8_dev32.py` (10 tests: the rule on DEV31's two wrong patches and on allowed cases, the workflow with the guard on and off, the miner, the arms) |

## Development (data already seen; `benchmarks/results/dev32/development/`)
- **Every patch ASM had accepted** in DEV15, DEV29 and DEV31 (59): the rule flags exactly youtube-dl-13 and youtube-dl-41.
- **1,843 real developer fixes** (DEV18-DEV21): it flags 4 (0.22%), none of them a fix learned knowledge had reproduced.
- **DEV31's 74 fresh bugs:** a first version flagged the encoding names `'latin-1'` and `'utf-8'` in two developer fixes.
  Names may now contain dashes, and it flags none.
- **The guarded arm on DEV15's 83 bugs:** 9 resolved. youtube-dl-13 and -41 were no longer accepted, and thefuck-19 is
  still repaired.
  - youtube-dl-29 was lost to the clock. It is repaired in phases 1-2, where the guard does not act, and resolves in
    167 s when run alone.
- **The pipeline on tabulate and toolz:** 13 valid bugs and no repair; it ran end to end.

## Fresh bugs
- **Projects:** sqlglot, pyupgrade, astroid, rich, loguru, inflect, num2words, jsonpickle, markdownify, marko, soupsieve,
  parsel, pypika, yapf, autoflake and w3lib (`benchmarks/preregistration/dev32_projects.json`, heads in
  `results/dev32/environment/repos_heads.txt`).
- **Mined:** 1,426 candidate commits, of which 172 were chosen (sqlglot 20 of 1,220, astroid 20 of 71, rich 20 of 23;
  every candidate elsewhere).
- **Valid:** 143 of 172. The rest:

  | reason | bugs |
  |---|---|
  | the tests do not fail on the buggy version | 15 |
  | not runnable (usage error) | 7 |
  | not runnable (timeout) | 5 |
  | not runnable (startup error) | 1 |
  | the fixed version fails | 1 |

  By project, valid of mined: sqlglot 20/20, astroid 18/20, rich 17/20, loguru 14/17, soupsieve 14/15, inflect 9/10,
  pypika 8/8, w3lib 8/11, pyupgrade 7/8, num2words 6/9, jsonpickle 5/8, marko 5/6, autoflake 5/7, markdownify 4/5,
  parsel 2/4, yapf 1/4.
- **Localization:** 19 bugs had no spectrum: 18 because the traced run timed out, 1 because no test failed. Of the
  other 124, the developer-changed function was ranked first in 69, in the top 5 in 93, and was not a suspect in 23.

## Pre-registered evaluation — both gates not passed
Pre-registration: `benchmarks/preregistration/dev32_study.md` (committed in `5ebaa35`, before mining). Raw records:
`results/dev32/dev32_control_learned_guarded_*.jsonl`, `dev32_time_control.jsonl` (hash-chained); analysis
`analysis.json`; probes `probes.jsonl`; verdicts `REALBUGS_REVIEW.md`.

| criterion | needed | reached | |
|---|---|---|---|
| A1 flagged patches the learned arm accepts | ≥ 2 | 0 | ✘ |
| A2 fewer wrong patches, guarded vs learned | ≥ 2 | 0 (10 vs 10) | ✘ |
| A3 learned-correct bugs lost by the guard (timing allowed: 1) | 0 | 0 | ✔ |
| A4 developer fixes flagged | ≤ 2% | 1 of 143 (0.7%) | ✔ |
| B1 correct only with learned knowledge (vs control and control_long) | ≥ 2 | **2** (astroid-4, sqlglot-14) | ✔ |
| B2 control-correct bugs lost | ≤ 1 | 0 | ✔ |
| B3 learned wrong patches | ≤ control's 8 + 1 | 10 | ✘ |
| B4 longest learned run | ≤ 360 s | 345 s | ✔ |

### The interruptions (reported under R4)
- **Three restarts.** The machine restarted three times during the three-arm run. Every time, the session had been idle
  with no background task, and the container was reclaimed with the detached shards.
- **Resuming.** Each stop was finished with `--resume`, which re-runs every arm of any bug not finished in all three,
  into the `resume` files. The analysis takes each bug's latest record. Each bug's three arms always ran together, one
  after the other.
- **Keeping it alive.** A background task kept the session active until the end.

### Reported, not gated
- **Phase 3** was reached in 110 bugs and tested a median of 107 candidates there (DEV31: 44 bugs, 89). It resolved 4
  and ran out of time in 99.
- **The guard** dropped candidates in 79 bugs (1,030 in all).
  - It changed no accepted patch.
  - In 4 bugs the guarded arm ran out of time where the learned arm ended unresolved.
  - In autoflake-2 it dropped 10 candidates before the same wrong patch was accepted.
- **Time:** median 148 s (control), 296 s (learned), 296 s (guarded). Learned over 300 s: 2 runs. Guarded over 300 s:
  5 runs; 1 over 360 s (sqlglot-12, 361.3 s; reported, not gated).
- **The flagged developer fix** is loguru-10, which adds the string `'#'`.
- **The oracle** agreed with the reading on 5 patches and was wrong on 2: it called markdownify-4 and inflect-9
  equivalent. It could not judge 7.

## Validation
- `python3 -m pytest -q tests/test_alpha8_*.py`: **627 passed, 3 skipped** (617 + 10 new). The 57 PyTorch failures
  elsewhere in `tests/` are unchanged and not caused by DEV32.
- With the guard off, behaviour is unchanged: `tests/test_alpha8_dev32.py` checks that `test_copy_guard=False` (the
  default) drops nothing. The DEV29 and DEV31 tests pass unchanged.

## Limitations
- **The bugs' own tests are weak oracles.** The control's accepted patches are 8 of 10 wrong: negated comparisons and
  conditions that pass only the bug's tests. Running more of each project's suite, or the developer's whole test file,
  is the obvious next step for every arm.
- **The guard's rule is narrow by design** (owner's choice). It does not catch test-derived names (marko-4) or partial
  edits (autoflake-2).
- **One run per arm.** Phase-3 outcomes depend on time; youtube-dl-29 in development shows a ±1 swing.
- **Localization** still times out on some suites (18 bugs), as on black in DEV31.

## What this means, and what is next
- **Recorded, not decided:** learned knowledge repairing 2 fresh bugs is new evidence for the M4 real-data question. It
  is not a promotion: the gate failed on safety.
- **Recommended next DEV:** a stronger acceptance check for all arms, testing a candidate against more of the project's
  own tests than the bug's, with probes for value changes. This would cut wrong patches in every arm and is the
  precondition for B3.
- **Owner decisions:**
  - keep `test_copy_guard` (opt-in, free when off) or drop it;
  - whether DEV32's B1 changes the M4 picture.
