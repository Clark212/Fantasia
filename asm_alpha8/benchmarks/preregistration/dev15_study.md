# DEV15 pre-registration: repair families, label rule L15, real bugs

Written and committed to git before any DEV15 benchmark run (calibration, decoys, real-bug evaluation) produced data.
The commit that adds this file is the timestamp. Its SHA-256 is recorded in every DEV15 run manifest. Anything not
listed here is exploratory and is labelled as such in the report.

## Code
- The DEV15 tree at the commit that adds this file. Each run manifest records the `asm.coding` hash; it must be the same
  for every run that a decision below uses.
- If a bug in ASM is found while the runs are in progress, it is fixed with a regression test, every affected run is
  discarded and re-run in full on the fixed code, and both the discarded and the final runs are reported.

## Data
1. **Fresh injected-fault subjects** (never used by DEV11-DEV14), PyPI sdists:
   - semver 3.0.4 (`semver/version.py`; its `.pytest.ini` replaced by a minimal one: import path and warning filter only)
     sha256 `afc7d8c584a5ed0a11033af086e8af226a9c0b206f313e0301f8dd7b6b589602`
   - parse 1.20.2 (`parse.py`) sha256 `b41d604d16503c79d81af5165155c0b20f6c8d6c559efa66b4b695c3e5a0a0ce`
   - more-itertools 10.5.0 (`more_itertools/recipes.py`, tests `tests/test_recipes.py`)
     sha256 `5482bfef7849c25dc3c6dd53a6173ae4795da2a41a80faea6700d9f5846c5da6`
   - Seed **89** (DEV13 used 31, DEV14 53). Fault model: DEV14's single-site faults detected by the full suite.
2. **Calibration** (`benchmarks/dev15_calibration.py`): 8 faults per subject. For each fault and each suite strength
   (half = failing + random half of passing; weak = failing only), the shipped workflow runs twice on the same fault:
   DEV15 repair space (`extended_ops=True`) and DEV14 repair space (`extended_ops=False`), 150 s budget each.
3. **Decoys** (`benchmarks/dev15_decoys.py`): DEV14's decoy protocol unchanged, 10 faults per subject, up to 8 decoys
   per fault, DEV15 oracle and DEV15 verification.
4. **Real bugs** (`benchmarks/dev15_realbugs.py`): the 83 BugsInPy bugs that DEV14's validation criterion accepts (re-run
   from scratch for DEV15: the same 83), DEV15 repair space, 150 s budget, judged against the developer's fixed program.

## Oracle (fixed before the runs)
`benchmarks/dev15_oracle.py`: DEV14 classes and settings (200 generated inputs, seed 7919), plus constants mined from
the reference, patched and (real bugs) buggy versions, and import-time functions judged by module state and the
replayed calls of the other functions in that module (state-only differences are `unknown`).

## Outcome definitions (as DEV14)
- WRONG (primary): `wrong`, or `wrong_generated` with `original_ok`. Sensitivity: `wrong` only.
- CORRECT: `restored` or `equivalent`. `unknown` excluded from rates, reported separately.

## Decision rules (fixed in advance)
- **L1, label rule L15.** L15: `low` if `alternatives_disagree`; else `medium` if any of `underdetermined`,
  `behaviour_unverified`, `competing_patches_in_other_functions`, `behavioural_deviation_persists`; else `high`.
  `tied_localization` and `behaviour_changed_where_tests_passed` are informational.
  - On the fresh decoys (WRONG decoys vs CORRECT controls, as DEV14): if fewer than 10 WRONG decoys, "insufficient
    evidence" and the shipped rule stays DEV14's (R1 rule).
  - Else ship L15 iff P(WRONG | high) < P(WRONG | medium) < P(WRONG | low) under L15 (point estimates) **and** every
    label has at least 5 rows. Otherwise keep the DEV14 rule.
  - The DEV14 rule's ordering on the same fresh data is reported (a replication of DEV14's R2).
  - Provenance, stated so it is not mistaken for evidence: L15 was chosen after looking at DEV14's seed-53 decoys, where
    it gives 6/92, 13/56, 23/27. That data cannot confirm it; only the fresh data can.
- **G1, repair families gate.** On the fresh calibration, realistic (half) suite: W15/A15 = WRONG accepted patches /
  judged (WRONG or CORRECT) accepted patches with DEV15 families; W14 the same with the DEV14 repair space.
  `extended_ops` stays on by default iff W15/A15 <= 0.10 **and** W15 <= W14 + 1. Otherwise the default becomes off
  (opt-in) and the report says so. The weak suite is reported, not gated (it is under-specified by construction).
- **G2, real bugs (descriptive).** Report resolved / unresolved / time budget, the edit family and oracle class of every
  accepted patch, and whether the developer's fixed test files pass on it. Every accepted patch's diff is read by a
  person against the developer's diff, with a written verdict per patch (`benchmarks/results/dev15/REALBUGS_REVIEW.md`).
  No rate claim beyond counts.
- **Promotion.** The external review's bar is at least 100 real bugs with credible repair rates. The corpus here has 83,
  so DEV15 is **not promoted** whatever the results.
- **R3.** No flag, label rule, weight, threshold, operator or budget is changed after seeing fresh data, except through
  L1 and G1 as written.
- **R4.** Every result is reported, including those unfavourable to DEV15.
