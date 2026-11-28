# Alpha 8 DEV3.1 underdetermination results

Pre-registration `DEV3.1-ud-prereg-2` sha256 `8bbd7c90cfbcc725bc9de1aa81e4b19c88b21f0b2c4f3ed321c180375c7999f5`; seed 20261101; 100 tasks (50 plain affine, 50 hidden modulus); runtime 5.0 s.

Extrapolation = x in 12..17 (wraps under the hidden modulus). Interpolation = x in {3, 7}. Cells: `answered / n`, correct, confident-wrong rate (wrong with confidence >= 0.8, over all queries), ECE on answered.

## extrap

| learner | k=8 | k=16 | k=24 |
|---|---|---|---|
| memorizer | 0/600, ok 0, cw 0.000, ece 0.00 | 0/600, ok 0, cw 0.000, ece 0.00 | 0/600, ok 0, cw 0.000, ece 0.00 |
| naive_affine_extrapolator | 600/600, ok 364, cw 0.393, ece 0.39 | 600/600, ok 364, cw 0.393, ece 0.39 | 600/600, ok 364, cw 0.393, ece 0.39 |
| hidden_mod_bayes_vote | 600/600, ok 364, cw 0.012, ece 0.02 | 600/600, ok 364, cw 0.012, ece 0.02 | 600/600, ok 364, cw 0.012, ece 0.02 |
| hidden_mod_bayes_abstain | 0/600, ok 0, cw 0.000, ece 0.00 | 0/600, ok 0, cw 0.000, ece 0.00 | 0/600, ok 0, cw 0.000, ece 0.00 |
| asm_procedure_cortex | 0/600, ok 0, cw 0.000, ece 0.00 | 600/600, ok 364, cw 0.393, ece 0.33 | 600/600, ok 364, cw 0.393, ece 0.35 |
| support_guarded_asm | 0/600, ok 0, cw 0.000, ece 0.00 | 0/600, ok 0, cw 0.000, ece 0.00 | 0/600, ok 0, cw 0.000, ece 0.00 |

## interp

| learner | k=8 | k=16 | k=24 |
|---|---|---|---|
| memorizer | 0/200, ok 0, cw 0.000, ece 0.00 | 0/200, ok 0, cw 0.000, ece 0.00 | 0/200, ok 0, cw 0.000, ece 0.00 |
| naive_affine_extrapolator | 200/200, ok 200, cw 0.000, ece 0.00 | 200/200, ok 200, cw 0.000, ece 0.00 | 200/200, ok 200, cw 0.000, ece 0.00 |
| hidden_mod_bayes_vote | 200/200, ok 200, cw 0.000, ece 0.00 | 200/200, ok 200, cw 0.000, ece 0.00 | 200/200, ok 200, cw 0.000, ece 0.00 |
| hidden_mod_bayes_abstain | 200/200, ok 200, cw 0.000, ece 0.00 | 200/200, ok 200, cw 0.000, ece 0.00 | 200/200, ok 200, cw 0.000, ece 0.00 |
| asm_procedure_cortex | 0/200, ok 0, cw 0.000, ece 0.00 | 200/200, ok 200, cw 0.000, ece 0.07 | 200/200, ok 200, cw 0.000, ece 0.04 |
| support_guarded_asm | 0/200, ok 0, cw 0.000, ece 0.00 | 200/200, ok 200, cw 0.000, ece 0.07 | 200/200, ok 200, cw 0.000, ece 0.04 |

## Pre-registered verdicts

| id | group | passed | rule |
|---|---|---|---|
| V1 | validity | PASS | reference ECE on extrapolation at k=24 <= 0.1 |
| V2 | validity | PASS | naive extrapolator is flagged (confident_wrong_rate and ECE above floors) |
| V3 | validity | PASS | abstaining reference is never wrong at any k |
| V4 | validity | PASS | memorizer scores nothing (leakage canary) |
| V6 | validity | PASS | a calibrated, answering learner meets the U1/U2 bars, so the bars are attainable |
| V5 | validity | PASS | interpolation correct_rate at k=24 >= 0.95 |
| U1 | asm | FAIL | share of extrapolation queries answered wrongly with confidence >= 0.8 at k=24 <= 0.02 |
| U2 | asm | FAIL | ECE on answered extrapolation queries at k=24 <= 0.15; abstaining on all is honest (vacuous) and its coverage is reported |
| U3 | asm | PASS | interpolation correct_rate at k=24 >= 0.8 |

ASM adapter errors: none
Observed values per criterion: `ALPHA8_DEV3_1_RESULTS.json` (`preregistration.verdicts`).
