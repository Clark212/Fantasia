# DEV31 pre-registration: learned knowledge on fresh real bugs, with phase 3 on its own clock

Written and committed to git before any repair arm ran on the fresh bugs. Its SHA-256 is recorded in the DEV31 run
manifests. Anything not listed here is exploratory. Alpha 8 (= milestone 0.4.9) plan items: alpha.8.8 (transfer scaling
and efficiency) and alpha.8.1/8.2 on real data, with alpha.8.5. Nothing is promoted in DEV31 and no default changes.
Design approved by the project owner (2026-11-24): the 7 unused light BugsInPy projects, 150 s of phase-3 time, and the
stricter time control.

## Question
In DEV29, learned knowledge repaired one real bug that nothing else in ASM repairs (thefuck-19); the gate needed two.
Phase 3 ran out of time in 30 of the 37 bugs where it ran. On youtube-dl it tested no candidate at all: building learned
candidates for a suspect took longer than the time left, up to 11 minutes past the budget.

DEV31 asks: on real bugs no ASM run has touched, does learned knowledge repair bugs that the workflow without it does
not, once phase 3 has 150 s of its own and builds its candidates fast enough to test them? A repair counts only if the
workflow without learned knowledge, given the same total time, does not also make it.

## What changed before this commit (development only)
- **Phase 3's own clock** (`RepairWorkflow(phase3_seconds=...)`, opt-in, default unchanged):
  - phase 3 gets that many seconds of its own once it starts, whatever phases 1-2 used;
  - the three learned libraries stop building when that clock runs out.
- **Faster learned candidate building, with identical candidates.** On 55 developer-changed functions of DEV15's bugs,
  the code before and after DEV31 gave the same 4,400 candidates in 2,434 s and 74 s
  (`benchmarks/results/dev31/development/phase3_equivalence.txt`). Tests compare the new checks with the whole-module
  ones they replace.
- **The environment stages:** DEV14's harness reads UTF-16 requirement files. Black, fastapi, luigi, sanic and scrapy
  ship them; the reader gives identical lines on every file of the six DEV15 projects.

## Fresh bugs
- **Projects:** 7 BugsInPy projects that no ASM run had used: black, luigi, tornado, fastapi, scrapy, ansible and sanic
  (151 bugs, corpus commit `11c5f1e`).
- **Environments:** built and validated with DEV14's stages under Python 3.8.20.
- **Valid: 75.** scrapy 33, black 19, fastapi 15, tornado 6, sanic 2.
  - luigi 0: pytest cannot start. A requirement that failed its pin was installed unpinned, which pulled in a modern
    anyio; its pytest plugin needs a newer typing_extensions than luigi pins.
  - ansible 0: its bugs do not reproduce under Python 3.8 (8 do not fail when buggy, 5 fail when fixed, 5 do not run).
- **Records:** `benchmarks/results/dev31/environment/` (validate.jsonl SHA-256 `13a22055…`).
- No repair arm has run on any of these bugs, and none will before this commit.

## Arms (`benchmarks/dev31_realbugs.py`; DEV29's per-bug evaluation)
- **control:** the shipped workflow with DEV15's repair families, 150 s (DEV29's control).
- **learned:** the same 150 s for phases 1-2, then DEV20's sealed `KnowledgeBase`, `ShapeLibrary` and `StepLibrary`
  in phase 3, with 150 s of its own.
- **control_long:** the control with the learned arm's total time, 300 s. It runs on every bug the learned arm resolves
  and the control does not.
- **Running:** control and learned are paired, one after the other in one process per bug. 3 shards over the bugs (bug
  index modulo 3), and nothing else runs on the machine while they do.
- **Sandbox:** tests run only through ASM's `SafeTestRunner`.

## Judging each accepted patch
- **The oracle:** DEV15's oracle classifies every accepted patch against the developer's fixed program.
- **A person's reading:** every accepted patch in every arm is read against the developer's patch, with the verdict
  correct, partial or wrong. Verdicts and reasons go into `benchmarks/results/dev31/REALBUGS_REVIEW.md`.
- **Probes:** when the reading and the oracle disagree, or reading alone does not settle a patch, a probe on a
  distinguishing input decides. It runs in the bug's environment inside ASM's sandbox, and is recorded.
- **Correct:** as DEV15 and DEV29 define it. The bug's tests pass and no probe finds a difference from the developer's
  fix on the behaviour the bug concerns.

## Development (DEV15's 83 bugs, already seen; development data only)
The learned arm (phase 3 with 150 s of its own) on DEV15's 83 bugs, compared with DEV29's committed control records. The
control's code is unchanged since DEV29's re-run: phases 1-2 use none of the modules DEV31 changed. The run is in
`benchmarks/results/dev31/development/dev31_learned_{0,1,2}of3.jsonl`, on a quiet machine.
- **Resolved:** 12 (DEV29: control 9, learned arm 10). No bug the control resolves was lost.
- **Resolved only with learned knowledge:** 3.
  - **thefuck-19:** correct, identical to the developer's fix (as in DEV29).
  - **youtube-dl-13 and youtube-dl-41:** wrong. Both overfit the tests. One learned shape (`s591385f62a4ee08c`, its
    content from the failing test's strings) replaced `None` with a test's expected value: `return 'rtmp://foo.de'` in
    `urljoin`, and `upload_date = '19681210'` in `unified_strdate`. They pass the bug's tests and break every other
    input.
- **Phase 3** ran in all 69 bugs where phases 1-2 found nothing, and tested candidates in every one: a median of 80, and
  on youtube-dl 19 to 153. In DEV29 it tested none in 11 bugs (10 of them youtube-dl).
- **Time:** the median learned run took 262 s and the longest 323 s. One run passed 300 s; the checks after a patch is
  accepted run past the clock.
- **On these bugs:** C3 below would fail (7 wrong patches against the control's 5, plus the 1 allowed) and C1 would fail
  (1 learned-only repair).
- **Prediction (honest prior).** C1 is hard: one correct learned-only repair in 83 bugs. C3 is at risk, because more
  phase-3 time also gives learned shapes more chances to write a test's expected value into the code. No guard against
  this is added: that would be a new mechanism, tuned on two development cases, and would need its own pre-registered
  test.

## Gate G31-A (person-read verdicts)
- **C1 learned repairs:** at least 2 bugs are repaired correctly by the learned arm, and correctly neither by the
  control nor by control_long.
- **C2 no loss:** at most 1 bug that the control repairs correctly is not repaired correctly by the learned arm.
- **C3 safety:** the learned arm's wrong accepted patches number at most the control's plus 1.
- **C4 the clock holds:** no learned run takes longer than 360 s: the 300 s budget plus 60 s for the checks after
  acceptance (development: at most 323 s).
- **Passes iff C1-C4 all hold.**
- **Reported, not gated:**
  - the valid set, and the attrition by project;
  - localization ranks;
  - how often phase 3 is reached, how long building takes, and how many candidates it tests;
  - time per arm;
  - each project;
  - every accepted patch with both diffs and every verdict;
  - the oracle against the reading.

## Decision rules
- **No promotion, no default change.** Making `phase3_seconds` a default, and promoting 0.4.9 or M4, are the owner's
  decisions.
- **R3.** Bugs found during the run are fixed with a regression test; affected runs are discarded, kept, and re-run in
  full. Nothing else changes after seeing DEV31 data.
- **R4.** Every result is reported, including unfavourable ones.
