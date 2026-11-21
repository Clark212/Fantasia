# DEV14 pre-registered outcomes (fresh seed-53 set; rules in ../../preregistration/dev14_fresh_calibration.md)
Recomputed from the raw chains by `python benchmarks/dev14_verify_results.py` (entry `fresh_decoys_seed53`).
- R1 tied_localization: 42 WRONG decoys (>= 10). TPR 7/42 = 0.167, FPR 27/133 = 0.203, LR+ 0.82 -> DEMOTE (informational).
- R2 label ordering under the R1 rule: P(WRONG|high) 6/82 = 0.073, P(WRONG|medium) 23/56 = 0.411, P(WRONG|low) 13/37 = 0.351
  -> ORDERING NOT CONFIRMED.
- R3 no other flag, label rule, weight or threshold was changed.
- R4 all results, including unfavourable ones, are in ALPHA8_CODING_DEV14_IMPLEMENTATION.md.
