# ASM Alpha 8 DEV29 — Learned Knowledge on Real Bugs, Where Fault Localization Points (implementation report)

Status: **experimental; NOT promoted; no default changed** (pre-registered). **The gate G29-A did not pass:** learned
knowledge correctly repaired 1 real bug that the workflow without it does not; the gate needed 2. One ASM bug was found
during the run and fixed under rule R3, and the evaluation was re-run in full. Alpha 8 (= milestone 0.4.9) plan items:
alpha.8.1 and alpha.8.2 on real data, with alpha.8.5. ASM contains no language model and no transformer.

## Headline (read this first)
- **What DEV29 tests.** DEV17–DEV20 learned repair knowledge from real fixes in about 45 projects: procedures, shapes
  and edit steps. Offered whole functions on fresh fixes, it reproduced almost nothing the built-in operations did not.
  The repair workflow instead tries learned knowledge as phase 3, inside the suspects that fault localization finds,
  after the built-in phases 1 and 2 accept nothing. DEV29 measures that for the first time on real bugs: DEV15's 83
  BugsInPy bugs, with the workflow with and without DEV20's sealed libraries, paired on every bug.
- **Result: G29-A not passed.** Every accepted patch was read by a person against the developer's fix
  (`benchmarks/results/dev29/REALBUGS_REVIEW.md`):

  | | control (DEV15's configuration) | learned (+ DEV20's libraries in phase 3) |
  |---|---|---|
  | bugs with an accepted patch | 9 | 10 |
  | correct | 4 | **5** |
  | wrong | 5 | 5 |
  | correct only in this arm | 0 | **1** (thefuck-19) |

  C1 needed 2 bugs correct only with the learned arm and got 1. C2 (no loss: 0) and C3 (safety: 5 wrong against 5)
  held.
- **The first real bug repaired by ASM's learned knowledge.** In thefuck-19, `'push --force'` became
  `'push --force-with-lease'`, byte-identical to the developer's fix. The control arm does not repair it, and DEV15 did
  not. The edit came from a shape learned from other projects' real fixes: a string argument of a call changed. Its
  content was the old string extended to the failing test's expected `'git push --force-with-lease'`. It was phase 3's
  40th candidate, found at 144 s of the 150 s budget. The re-run reproduced it exactly.
- **What limits phase 3 is mostly time, not knowledge.** Phase 3 runs only after phases 1 and 2 have used their share of
  the budget:
  - **reached in 37 of 83 bugs.** In the other 46, phases 1–2 accepted a patch (9 resolved, 2 partial), used the whole
    budget (32), or found no suspect at all (3);
  - **where reached,** phase 3 had a median of 91 s and ran out of time in 30 of the 37;
  - **in 11 of the 37 it tested no candidate at all:** 10 youtube-dl bugs and 1 tqdm bug. Building learned candidates on
    youtube-dl's large modules (`utils.py` has 3,643 lines) outlasted the time left. It ran up to 11 minutes past the
    budget, which is checked only between candidates.

  The pre-registration's prediction was right: whether phase 3 is reached, and with how much time, is the main lesson.
- **Safety.** Phase 3 accepted one patch, and it is correct. Every other accepted patch is the same built-in patch in
  both arms, identical to DEV15's.
- **An ASM bug, found and fixed (R3).** The first run crashed on tqdm bugs:
  - `FailureAnalyzer` failed on test output that begins mid-word;
  - the runner keeps only the last 12,000 characters, and here they began with `onError`, the tail of a cut-off
    `AssertionError`.

  The fix is one line with a regression test. The first run is kept unused, and the evaluation was re-run in full with
  nothing else on the machine.
- **What it means.** On real bugs, learned knowledge now repairs a bug that nothing else in ASM repairs, once fault
  localization says where to look. One bug is not the two the gate asked for, and the time budget, not the knowledge,
  decides most phase-3 outcomes.

## What DEV29 ran (no ASM code changes except the R3 fix)
| piece | file |
|---|---|
| harness | `benchmarks/dev29_realbugs.py`: DEV15's per-bug evaluation (localization rank, workflow, oracle) for both arms |
| environments | DEV14's prepare, envs and validate stages, unchanged (`benchmarks/results/dev29/environment/`) |
| evaluation | `benchmarks/results/dev29/dev29_evaluate_{0,1,2}of3.jsonl` (3 shards, bug index modulo 3), `summary.json` |
| person-read review | `benchmarks/results/dev29/REALBUGS_REVIEW.md`; probes `benchmarks/dev29_probes.py` → `probes.jsonl` |
| analysis | `benchmarks/dev29_analysis.py` → `analysis.json` (the reported-not-gated items) |
| discarded first run | `benchmarks/results/dev29/discarded_run1/` (kept, not used; README) |
| R3 fix | `asm/coding/diagnostics.py`, one line |
| tests | `tests/test_alpha8_dev29.py` (3; one is the R3 regression test) |

- **The bugs:** DEV15's BugsInPy corpus, rebuilt from scratch (corpus commit `11c5f1e`).
  - All 96 bug environments were built under Python 3.8.20.
  - The validate stage found **83 valid, exactly DEV15's 83.** The rest: 5 whose buggy version does not import,
    3 not runnable, 3 whose fixed version fails, 1 that does not fail when buggy, 1 with no test command.
  - The developer patches are identical to DEV15's records on all 166 records.
- **The arms**, paired and run one after the other in one process for each bug, 150 s workflow budget each:
  - **control:** the shipped workflow with DEV15's repair families;
  - **learned:** the same, plus DEV20's sealed `KnowledgeBase`, `ShapeLibrary` and `StepLibrary` in phase 3, which runs
    only when phases 1 and 2 accept nothing.

  The library hashes are recorded in every manifest.
- **Tests run only through ASM's `SafeTestRunner`.** The review probes run inside `run_python_worker`, under the same
  protections.

## The first run, and the bug (R3)
The first pre-registered run (15:41 UTC) stopped with 34 of 83 bugs done in both arms.
- **The crash.** Shards 0 and 2 crashed in the control arms of tqdm-4 and tqdm-3.
  - `SafeTestRunner` keeps the last 12,000 characters of a test run's output.
  - tqdm's output contains timing figures, so where that cut falls varies from run to run.
  - Here the kept text began with `onError`, the tail of a cut-off `AssertionError`.
  - `FailureAnalyzer.analyze` read it as an exception without a message, and `None.strip()` raised through the
    evaluation.
  - The code dates from the DEV14 baseline; DEV15's run never cut at such a place.
- **The fix** reads a missing message as empty. The regression test fails on the old code and passes on the fix, and
  wherever the old code did not crash it behaves as before. The crash reproduced on tqdm-4's control arm, and the fixed
  analyzer reads the saved input.
- **Kept, not used:** the first run is in `discarded_run1/`, with what it showed (R4). On its 34 bugs the control
  matched DEV15 on every one, and the learned arm repaired thefuck-19.
- **A second reason for the full re-run.** From 15:46 to 16:07 UTC, DEV30's runs shared the 4-CPU machine with the
  first run's shards. The workflow has a wall-clock budget, so that load could have changed outcomes. The re-run
  (16:51–19:27 UTC) had the machine to itself; nothing else ran until it ended.

## Pre-registered evaluation — G29-A not passed
Pre-registration `5fe3650` (SHA-256 `a0b0bf13…`, in every manifest), committed before the learned arm ran on any real
bug. Code: `asm.coding` SHA-256 `d2d21cf8…` (with the R3 fix). The evaluation: 166 workflow runs, no crash.

| check | rule | observed | |
|---|---|---|---|
| C1 learned repairs | ≥ 2 bugs correct with the learned arm and not with the control | 1 (thefuck-19) | ✗ |
| C2 no loss | ≤ 1 bug correct with the control and not with the learned arm | 0 | ✓ |
| C3 safety | the learned arm's wrong patches ≤ the control's + 1 | 5 against 5 | ✓ |

### Reported, not gated
- **The valid set** is exactly DEV15's 83 bugs.
  - The control arm's status matches DEV15's on 81 of 83. The other two lie at the budget's edge: tqdm-2 (DEV15
    `time_budget` at 148.1 s, now `partial` at 148.1 s) and youtube-dl-21 (148.6 s → `unresolved` at 142.7 s).
  - The control's 9 accepted patches are DEV15's 9, byte for byte.
- **Localization** (rank of the developer-changed function among the suspects): 1 in 59 bugs, 2 in 11, 3 in 2, 4 in 1,
  6 in 2, not ranked in 8.
- **Phase 3:**

  | | bugs |
  |---|---|
  | phases 1–2 accepted a patch (resolved / partial) | 9 / 2 |
  | phases 1–2 used the whole budget | 32 (youtube-dl 24, tqdm 5, thefuck 2, httpie 1) |
  | no phase ran (the workflow found no suspect with a positive score) | 3 |
  | **phase 3 reached** | **37** (median 91 s left) |
  | — no phase-3 candidate tested (building candidates outlasted the time left) | 11 (youtube-dl 10, tqdm 1) |
  | — candidates tested (median 80, 14–160): time ran out / exhausted / **resolved** | 19 / 6 / **1** |

- **Time:**
  - the control averaged 102 s per bug, and 32 runs hit the budget;
  - the learned arm averaged 165 s, and 62 hit the budget;
  - 11 learned runs ran past the 150 s budget:
    - 9 youtube-dl runs, where phase 3 tested no candidate. They took 155–809 s, spent building phase-3 candidates for
      suspects in large modules;
    - youtube-dl-29, resolved in phases 1–2 (166 s; the control also ran over, at 157 s);
    - PySnooper-3, which tested 160 phase-3 candidates (166 s).
- **Each project** (accepted / time budget / unresolved or partial, control → learned):
  - thefuck (32): 4/2/26 → 5/19/8;
  - youtube-dl (38): 3/24/11 → 3/35/0;
  - tqdm (9): 2/5/2 → 2/6/1;
  - httpie (2): 0/1/1 → 0/1/1;
  - PySnooper (1): 0/0/1 → 0/1/0;
  - cookiecutter (1): 0/0/1 → 0/0/1.
- **Every accepted patch**, with both diffs and verdicts: `REALBUGS_REVIEW.md`. In short:
  - **correct in both arms:** thefuck-9, youtube-dl-28, youtube-dl-29 and thefuck-22. thefuck-22 now has a probe as well
    as DEV15's reasoning.
  - **wrong in both arms:** thefuck-15, thefuck-21, tqdm-6, tqdm-8 and youtube-dl-11. All of DEV15's probes give the
    same results in the rebuilt environments.
  - **correct in the learned arm only:** thefuck-19.
- **The oracle against the reading:**
  - its `equivalent` was wrong 3 times (tqdm-8 control, youtube-dl-11 in both arms) and right once (youtube-dl-29);
  - on the identical tqdm-8 patch it said `equivalent` in one arm and `wrong` in the other;
  - its `restored` (3 bugs) and `wrong`/`wrong_generated` (2 bugs) calls were right.

## Validation
- `tests/test_alpha8_dev29.py`, 3 tests:
  - the sealed libraries load as the committed files;
  - the learned configuration runs the workflow end to end;
  - **R3:** an exception name without a message is analyzed instead of crashing.
- Full `test_alpha8_*`: 611 passed, 3 skipped, 0 failed (with the fix; see DEV30's report).

## Limitations
- **83 bugs from six projects,** mostly thefuck (32) and youtube-dl (38). One learned-only repair is one case, not a rate.
  These bugs have now been used to evaluate phase 3, so a follow-up should be measured on fresh real bugs.
- **The budget decides most outcomes.** Phase 3 is reached only when phases 1–2 fail inside the budget, and then it has
  what is left. A different budget split is a different experiment.
- **Unbounded candidate building.** The workflow's budget is checked only between candidates, so building learned
  candidates on large modules can run minutes past the budget. No outcome changes: no candidate was tested in those
  runs, and none would have been. But phase 3 never tried anything on youtube-dl.
- **What made thefuck-19 possible.** The fix's content was in the failing test's expected output. A bug whose tests do
  not contain the fix's content cannot be completed this way.
- **Wall-clock budgets make outcomes load-dependent.** Two control statuses differ from DEV15's at the budget's edge.

## What this means, and what is next
DEV29 is the real-data half of the M4 question. In the lab (DEV21–DEV30), learned structure transfers under every
condition measured. On real bugs, learned repair knowledge has now repaired one bug that nothing else in ASM repairs,
correctly, with no wrong patch added, but not the two the gate asked for. Nothing is promoted; M4 ("verified cross-task
structural transfer") is not met on real data.
- **Highest-value next step:** a pre-registered DEV on fresh real bugs that gives phase 3 its own time. Two changes:
  - bound and speed up learned candidate building per suspect, so large modules are not skipped;
  - a separate phase-3 budget, so phase 3 gets time even when phases 1–2 use theirs.

  The question: does learned knowledge then repair 2 or more real bugs the workflow without it does not?
- **No owner decision is required by DEV29 itself.** The R3 fix is a bug fix in shipped code, made under the
  pre-registered rule.

Consciousness-related architecture: not touched.
