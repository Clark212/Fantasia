# DEV15 pre-registered outcomes (rules in ../../preregistration/dev15_study.md, amendment A1 in dev15_amendments.md)
Every number is recomputed from the raw chains by `python benchmarks/dev15_verify_results.py` (4/4 entries).

- **L1, label rule L15: NOT CONFIRMED -> the DEV14 rule stays shipped.**
  103 WRONG decoys (>= 10), 116 correct controls. P(WRONG | label) under L15: high 57/144 = 0.396, medium 0/25 = 0.000,
  low 46/50 = 0.920. Medium is below high, so the ordering fails. Sensitivity (`wrong` only): same conclusion.
  DEV14 rule on the same data (replication of DEV14's R2): high 0.419, medium 0.642, low 0.188, also **not ordered**.
- **G1, repair families gate: PASSED -> `extended_ops` stays on by default.**
  Realistic suite, 24 fresh faults: W15/A15 = 0/18, W14 = 0/18. W15 <= 0.10 * A15 and W15 <= W14 + 1.
  (Weak suite, reported not gated: DEV15 3/17 WRONG, DEV14 1/15.)
- **G2, real bugs:** 9/83 resolved; read by a person: 4 correct (2 identical to the developer's fix), 5 wrong
  (`REALBUGS_REVIEW.md`).
- **Promotion:** not promoted (83 < 100 real bugs, as fixed in advance).
- **R3:** nothing else changed after seeing data. The one code change during the runs (A1) was a bug fix under the
  pre-registered bug clause; all runs were restarted on the fixed code and the discarded ones are published.
- **R4:** all results, including unfavourable ones, are in ALPHA8_CODING_DEV15_IMPLEMENTATION.md.
