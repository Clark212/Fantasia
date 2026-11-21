# ASM Alpha 8 Coding DEV13 — Generalized Behavioural Verification (implementation report)

Status: **experimental; NOT promoted. DEV11 and DEV12 remain unpromoted.** Built on `asm_alpha8_dev12` (verified 11/11
against its manifest before use). Earlier releases preserved.
Roadmap note: the user-defined DEV13 replaces the roadmap's DEV13 (Advanced Debugging), which DEV11 partly covered.
Rebuild note: the workspace was reset mid-development; DEV13 was rebuilt from the DEV12 zip and **every test and benchmark
was re-run**. No number from before the reset is reused.

## What was built, by requested item
1. **Object-valued argument recording and replay.** The tracing plugin pickles the real argument tuples (receivers
   included) that tests pass to every repository function, with per-test attribution; failing tests' inputs are always
   kept, passing ones sampled. The replay worker unpickles them in the DEV8.1 sandbox. Perturbation edits literal
   arguments and literal attributes of recorded objects.
2. **Class and method counterexample testing.** Methods replay with their recorded receiver object.
3. **Nested-function verification.** A closure is verified by replaying its outermost enclosing function or method.
4. **State and side-effect comparison.** Per input: return value, exception, final state of every argument (deep object
   state), printed output, files written, module globals. Files and globals are restored between runs.
5. **Nondeterminism.** Randomness is re-seeded and the clock reset before every run; `time.sleep`, `os.urandom` are
   controlled. Inputs that still differ between two identical runs are excluded and counted, never compared.
6. **The two DEV11 overfit patterns.** New flags: `competing_patches_in_other_functions` (another function with equally
   strong evidence can ALSO be patched to pass, explored before the patch lands), `behaviour_changed_where_tests_passed`
   (the patch changes outputs on inputs passing tests already used), `behaviour_unverified`, plus exhaustive search for
   same-function alternatives beyond the round where the repair loop stopped.
7. **Calibration against deliberately incorrect repairs** (below).
8. **Independent repository testing:** toolz 1.2.0 and cachetools 8.0.0 (PyPI sdists; sha256 in
   `benchmarks/results/dev13/independent_repo_sdists.sha256`). Faults are **injected**, not historical bugs.

## Bugs found by the independent repositories (all fixed, all with regression tests)
- **Test IDs collapsed for inherited/mixin tests (a DEV8.1 bug).** JUnit's `file` names where a test is defined, not where
  it is collected: cachetools' 416 tests mapped onto 278 IDs, so vanished-test/regression comparison was wrong and
  targeted re-runs failed. IDs are now resolved from JUnit `classname` against real files.
- **Failing subtests were recorded as passing.** pytest 9 reports each failing subtest, then a final "passed" call
  report; the plugin kept the last one. The worst outcome now wins. (Teardown failures are also recorded; that path is
  tested but was not the cause here.)
- **Instrumentation sensitivity was conflated with flakiness.** Four cachetools TTL tests fail under `sys.settrace` even
  on the correct program. Plain runs now define what fails (two must agree, else `unstable_baseline`); tests whose
  traced outcome differs are excluded from localization and reported; a failure seen only under tracing is refused.
The DEV12 completeness guard is what surfaced the second bug: it refused to localize until the cause was found.

## Validation actually run
- **Tests:** 37 new DEV13 tests; one DEV12 assertion updated for new dossier wording. **Fresh full run:
  `test_alpha8_*` 404 passed** (336 s). Historical groups identical to the earlier baseline (v01 72 passed; v02 13 failed;
  v03 3 errors; v04 6 failed; PyTorch absent), under this environment's pytest 9.1.1.
- **Mutation check:** 19 deliberate defects (14 core verification/recording, 4 spectrum fidelity, 1 test-ID).
  18 caught first time; the survivor showed the randomness test only used values that never vary, fixed. **19/19.**

## Calibration benchmark (32 detected faults: toolz 12, cachetools 12, ASM `understanding.py` 8; seed 31)
Each fault is repaired with a realistic suite (failing tests + half of the rest) and a deliberately weak one (failing tests
only). The oracle compares against the known-correct original program on the original suite's inputs plus perturbations.

| | realistic suite | weak suite |
|---|---|---|
| plausible patches (pass the suite) | 36: 26 restored, 10 equivalent, **0 wrong** | 33: 20 restored, 9 equivalent, **4 wrong** |
| behavioural verification available | 34/36 | 31/33 |
| real workflow resolved | 28/32 | 20/32 |
| ...accepted patch correct | **28/28** (95% CI 88–100%) | 18/20 |
| ...accepted patch WRONG | 0/28 | **2/20, both labelled `low`** (competing + tied) |
| localization top-1 / top-3 | 21/32 / 26/32 | 13/32 / 19/32 |

Verification coverage moved from **1/13** accepted patches (DEV12, different subjects) to **34/36** here.
With realistic suites, single-site wrong patches essentially never pass on these subjects; the weak suite is where they appear.

## Decoys: deliberately incorrect repairs at scale
A decoy = the true fix + one extra single-site edit in the faulty function, kept only if it still passes the suite.
744 constructed, 158 kept. Oracle: **11 confirmed wrong**, 139 no observable difference, 8 unknown.
- Wrong decoys flagged (any flag): **9/11**; labelled `low`: 5/11. Correct controls flagged: 69/144 (any), 12/144 (`low`).
- **P(wrong | label): `high` 2/77 (3%), `medium` 4/61 (7%), `low` 5/17 (29%).** The labels order risk correctly; they are
  ordinal, not calibrated probabilities.
- `alternatives_disagree`: 6/11 wrong decoys, **0/144** correct controls (the most specific signal).
  `tied_localization`: high false-alarm rate (51/144).
- Two wrong decoys got no flag (weak suite: no passing tests to compare against, no disagreeing alternative).
- **Oracle limit:** the 139 "no observable difference" decoys are not proven benign. The oracle's inputs derive from the
  same test suite, so a change no test input exercises is invisible to the oracle as well as to the tests.

## The two known DEV11 overfits, re-run with the final code
- **#1 (fault in `scan`, patch in `visit_ImportFrom`): detected.** Label `low`; the competing patch found is the true fix
  (`scan`, `'==' -> '!='`); oracle: wrong.
- **#2 (`analyze_static`): reclassified.** On 120 compared inputs (18 recorded) the patch is behaviourally equivalent to the
  correct program. DEV11 counted it as an overfit because it was not a textual restoration; the better statement is
  **DEV11 had 1 confirmed overfit and 1 equivalent patch** (evidence, not proof).

## Not done / limits
- Independent testing used injected faults in 2 repositories, not 100 real historical bugs.
- No calibrated probabilities: 11 + 4 confirmed-wrong cases are too few; intervals are wide.
- I did not retune the flags or label rule on these results (`tied_localization` looks like a weak signal); doing so on
  the same data would overfit the safeguards themselves. A fresh benchmark should decide.
- Not replayable: unpicklable arguments (open files, locks, generators, lambdas), classmethods, `*args/**kwargs`.
  `datetime.now()`, `time.time_ns()` and C-level clocks are not controlled (such inputs are excluded).
- Repair candidates are still single-site templates. One CPU core: a calibration fault took ~1–2 min.
- The sandbox remains defense in depth, not an OS security boundary; replay unpickles data from the repository's own tests.
- No consciousness-related claim: everything here is tracing, sandboxed replay, comparison and counting.

## Promotion gate (DEV11–DEV13)
Real historical bugs from independent repositories (>=100) with intervals; baselines (random order, coverage-only, DEV8.1);
a fresh calibration set with enough wrong patches to estimate P(wrong | label) tightly; a decision on `tied_localization`
from new data; inputs beyond the test suite's own distribution (e.g. property-based generation) to shrink the oracle
blind spot; human review of the apply path in a real container.
