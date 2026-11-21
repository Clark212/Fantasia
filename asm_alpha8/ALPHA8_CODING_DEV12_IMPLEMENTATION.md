# ASM Alpha 8 Coding DEV12 — Repair Reliability (implementation report)

Status: **experimental; NOT promoted. DEV11 is also not promoted.** Built on `asm_alpha8_dev11`; earlier releases preserved.
Origin: an external review of DEV11 (verified below) recommended this direction. Scope here is the subset that can be
built and *measured* in this environment; what was not done is listed explicitly.

## Review claims, checked against the code
- **Incomplete spectrum — confirmed, and worse than stated.** `spectrum_ok` was only ever set False in the "no failing
  tests" branch. A traced run that timed out or crashed never writes its trace file, which looked identical to "no
  failing tests", so a repo with a real failure plus one hanging test was reported **`no_failures`**. Reproduced before
  fixing. Now: the spectrum carries `complete` / `incomplete_reason` (timeout, unusable run, missing trace, plugin/pytest
  disagreement); the localizer refuses to rank on partial evidence; the workflow reports `incomplete_spectrum`.
- **DEV10 weight unjustified — agreed.** Semantic evidence is now a **tie-breaker only** (`semantic_mode="tiebreak"`,
  default): it orders suspects whose coverage+traceback scores are exactly equal and can never outvote them.
  `"weighted"` remains available. Fresh-seed result below: it fired for 0 of 15 faults.
- **Manifest:** all 10 entries of the DEV11 manifest matched the delivered zip (the review counted 9). **Test claim:**
  the earlier "335 passed" was a run made before the last test was added; a fresh full run is reported below.

## What was added
1. Spectrum completeness (above) with 7 tests, including the exact reproduction of the bug.
2. Semantic tie-break mode with 5 tests.
3. **Counterexample search** (`counterexamples.py`): the tracing plugin records the literal arguments the tests pass to
   each repository function; they are perturbed one argument at a time (type-preserving); the original and every
   *passing* candidate patch are executed on them in the sandbox. Output per accepted patch: behavioural footprint vs the
   original, and **concrete distinguishing inputs** where candidates that all pass the tests disagree.
4. **Learning from a human answer**: `run(..., examples=[{"function","args","expected"}])` turns an answer to a
   distinguishing input into a test that exists only in the working copy; the repair must satisfy it. Demonstrated: for
   `g(n)=n*3+2` with one test the workflow first picks the wrong edit (`*`->`+`) at "medium" confidence and prints
   "g(3): chosen 8, alternative 10, original 11"; with the answer g(3)=10 it picks the right edit (`2`->`1`), "high".
5. **Confidence label** (`high/medium/low`) from independent warning signs: alternatives that disagree or cannot be
   compared, coverage ties, a persisting DEV10 deviation. Alternatives that behave identically on all tested inputs are
   noted, not flagged. It is an ordinal label with measured accuracy, **not a calibrated probability.**

## Validation actually run
- **Tests:** 31 new DEV12 tests; 3 DEV11 tests updated for the new behaviour. **Fresh full run: `test_alpha8_*` 367 passed**
  (201 s). Historical groups identical to the baseline recorded earlier (v01 72 passed; v02 13 failed; v03 3 errors; v04 6
  failed; PyTorch absent here). `compileall` clean.
- **Mutation check:** 15 deliberate defects in the new logic; 13 caught first time. One was an invalid mutant (my edit
  broke the syntax), one survived because the `self`/`cls` filter is redundant for ordinary objects (fixed with an
  int-subclass test); one real bug was found by a test instead (`perturb_inputs(limit=…)` capped only the variants):
  **15/15 caught after fixes.** Two guards remain only indirectly covered: "plugin and pytest disagree about failing
  tests", and "no trace file".

## Benchmark on a FRESH seed (15 faults; design had been informed by the first 17, so this is the held-out check)
Oracle: each accepted patch is compared with the known-correct original by differential execution on perturbed real
inputs (stronger than the held-out tests, which both earlier overfits had passed).
- **Localization replicated:** top-1 10/15 (67%), top-3 13/15 (87%) vs 68% / 88% on the first seed.
- **Repair:** 13/15 resolved. Oracle: **9 restored, 1 equivalent, 3 unknown, 0 confirmed wrong.** Unresolved: 1; out of time: 1.
- **The overfit rate seen before (2/11) did not recur, so this sample contains nothing for the new safeguards to catch.
  Calibration of the confidence labels and the usefulness of the flags are therefore UNMEASURED.** What the table does
  show: `high` 8 (7 restored, 1 equivalent, 0 wrong); `medium` 4 (2 restored, 2 unknown); `low` 1 (unknown); flags fired on
  5/13, including 2 of the 10 correct repairs (false alarms).
- **Counterexample search was available on only 1 of 13 accepted patches** (non-literal arguments, methods, nested
  functions). The differential oracle was unavailable for 3 of 13 for the same reasons.
- **Selection policy (minimum footprint vs evidence order): unresolved.** Footprints existed for one ambiguous fault, where both
  candidates were equivalent. A constructed case (inverted condition) shows minimum-footprint can pick the *wrong*
  candidate, so evidence order stays the default.
- **DEV10 evidence:** non-zero for 0 of 15 faults; ranks identical with and without it.

### The two known overfits from the first seed, re-run (post hoc)
Both are **still accepted**. Counterexample search is unavailable for both (a nested/method function; no literal-argument
test calls) and so is the differential oracle ("unknown"). The only warning each gets is the coverage-tie caveat DEV11
already had (`medium`). **The new machinery does not address the failures that motivated it.**

## Not done (explicitly)
Multi-fault dependency analysis beyond the existing iterative partial-fix loop; behavioural equivalence checking for
non-literal inputs; learning from rejected patches beyond the existing failure ledger; confidence *calibration*;
evaluation on real bugs from independent repositories (needs a bug corpus with runnable environments, which this
environment cannot supply honestly). Repair candidates are still only single-site template edits.

## Limits
- Counterexample search needs module-level functions called with literal-reprable arguments in the tests; behaviour on
  other inputs is judged by agreement on perturbed ones, which is evidence, not proof.
- The benchmark is optimistic (repair templates invert the injection templates), small (15 + 17 faults), single-codebase.
- No baseline (random order, coverage-only, DEV8.1-only) was run; no claim that localization improves repair.
- Sandbox is defense in depth, not an OS security boundary.

## Promotion gate (DEV11 and DEV12)
>=100 real bugs from independent repositories with intervals; baselines (random order, coverage-only, DEV8.1); a sample
that actually contains overfits so the flags/labels can be calibrated; counterexample coverage well above 1/13 (e.g. object-valued arguments via
recorded-call replay or generated fixtures); a way to detect the two known overfit patterns; human review of the apply path.
