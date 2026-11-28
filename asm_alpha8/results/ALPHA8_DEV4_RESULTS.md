# Alpha 8 DEV4 results

Pre-registration `DEV4-prereg-1` sha256 `2a308eca150df8928740af5ebd336e4612e96264f7455dcab1af28ac138486f6`; seed 20261102; runtime 235.4 s.

## Part A: structural discovery map (ASM default configuration)

Cells: `correct_rate / wrong_rate` on held-out interior determined queries (abstention counts as not correct). ASM coverage = answered fraction.

### affine  (120 queries)

| learner | k=8 | k=16 | k=24 |
|---|---|---|---|
| memorizer | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 0.00 |
| majority | 0.00 / 1.00 | 0.00 / 1.00 | 0.00 / 1.00 |
| grid_reference | 1.00 / 0.00 | 1.00 / 0.00 | 1.00 / 0.00 |
| shuffled_grid_reference | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 0.00 |
| asm_struct | 0.00 / 0.00 | 1.00 / 0.00 | 1.00 / 0.00 |
| shuffled_asm_struct | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 0.00 |

ASM coverage: k=8: 0.00, k=16: 1.00, k=24: 1.00

### quad  (120 queries)

| learner | k=8 | k=16 | k=24 |
|---|---|---|---|
| memorizer | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 0.00 |
| majority | 0.00 / 1.00 | 0.00 / 1.00 | 0.00 / 1.00 |
| grid_reference | 1.00 / 0.00 | 1.00 / 0.00 | 1.00 / 0.00 |
| shuffled_grid_reference | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 0.00 |
| asm_struct | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 0.00 |
| shuffled_asm_struct | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 0.00 |

ASM coverage: k=8: 0.00, k=16: 0.00, k=24: 0.00

### clamp  (120 queries)

| learner | k=8 | k=16 | k=24 |
|---|---|---|---|
| memorizer | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 0.00 |
| majority | 0.47 / 0.53 | 0.53 / 0.47 | 0.55 / 0.45 |
| grid_reference | 0.97 / 0.00 | 1.00 / 0.00 | 1.00 / 0.00 |
| shuffled_grid_reference | 0.03 / 0.00 | 0.00 / 0.00 | 0.00 / 0.00 |
| asm_struct | 0.00 / 0.00 | 0.25 / 0.00 | 0.55 / 0.00 |
| shuffled_asm_struct | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 0.00 |

ASM coverage: k=8: 0.00, k=16: 0.25, k=24: 0.55

### threshold  (103 queries)

| learner | k=8 | k=16 | k=24 |
|---|---|---|---|
| memorizer | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 0.00 |
| majority | 0.54 / 0.46 | 0.59 / 0.41 | 0.57 / 0.43 |
| grid_reference | 0.95 / 0.00 | 1.00 / 0.00 | 1.00 / 0.00 |
| shuffled_grid_reference | 0.03 / 0.02 | 0.00 / 0.00 | 0.00 / 0.00 |
| asm_struct | 0.00 / 0.00 | 0.17 / 0.00 | 0.61 / 0.00 |
| shuffled_asm_struct | 0.00 / 0.00 | 0.00 / 0.00 | 0.02 / 0.01 |

ASM coverage: k=8: 0.00, k=16: 0.17, k=24: 0.61

### linear2  (240 queries)

| learner | k=8 | k=16 | k=24 |
|---|---|---|---|
| memorizer | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 0.00 |
| majority | 0.05 / 0.95 | 0.06 / 0.94 | 0.04 / 0.96 |
| grid_reference | 1.00 / 0.00 | 1.00 / 0.00 | 1.00 / 0.00 |
| shuffled_grid_reference | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 0.00 |
| asm_struct | 0.00 / 0.00 | 1.00 / 0.00 | 1.00 / 0.00 |
| shuffled_asm_struct | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 0.00 |

ASM coverage: k=8: 0.00, k=16: 1.00, k=24: 1.00

### product2  (240 queries)

| learner | k=8 | k=16 | k=24 |
|---|---|---|---|
| memorizer | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 0.00 |
| majority | 0.00 / 1.00 | 0.00 / 1.00 | 0.00 / 1.00 |
| grid_reference | 1.00 / 0.00 | 1.00 / 0.00 | 1.00 / 0.00 |
| shuffled_grid_reference | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 0.00 |
| asm_struct | 0.00 / 0.00 | 0.10 / 0.00 | 0.10 / 0.00 |
| shuffled_asm_struct | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 0.00 |

ASM coverage: k=8: 0.00, k=16: 0.10, k=24: 0.10

## Part B: structural transfer (target y = x*x + c; donors validated through the public lifecycle)

| group | arm | success | mean evaluator calls | family-origin rate | wrong per query |
|---|---|---|---|---|---|
| in_range | none | 0.00 | 304 | 0.00 | 0.000 |
| in_range | one_relevant | 0.00 | 304 | 0.00 | 0.000 |
| in_range | relevant | 1.00 | 13 | 1.00 | 0.000 |
| in_range | unrelated | 0.00 | 304 | 0.00 | 0.000 |
| in_range | mixed | 0.00 | 304 | 0.00 | 0.000 |
| in_range | relevant_shuffled | 0.00 | 311 | 0.00 | 0.000 |
| out_of_range | none | 0.00 | 296 | 0.00 | 0.000 |
| out_of_range | one_relevant | 0.00 | 296 | 0.00 | 0.000 |
| out_of_range | relevant | 0.00 | 313 | 0.00 | 0.000 |
| out_of_range | unrelated | 0.00 | 296 | 0.00 | 0.000 |
| out_of_range | mixed | 0.00 | 296 | 0.00 | 0.000 |
| out_of_range | relevant_shuffled | 0.00 | 312 | 0.00 | 0.000 |

## Pre-registered verdicts

| id | group | passed | rule |
|---|---|---|---|
| A-H1 | harness | PASS | grid reference never wrong at any k |
| A-H2 | harness | PASS | grid reference correct_rate at kmax >= 0.95 |
| A-H3 | harness | PASS | memorizer scores nothing (leakage canary) |
| A-H4 | harness | PASS | shuffled-label reference correct_rate at kmax <= 0.25 |
| A-H5 | harness | PASS | reference - majority correct_rate at kmax >= 0.15 |
| A1 | asm | PASS | ASM wrong_rate <= 0.02 at every k, every family |
| A2 | asm | PASS | ASM trained on shuffled labels: wrong_rate <= 0.02 |
| A3 | asm | FAIL | >= 3 families with correct_rate >= 0.8 at k=24 |
| B-V1 | harness | PASS | no donor ever uses the target constant |
| B-V2 | harness | PASS | relevant_shuffled success <= 0.05 (success cannot occur without signal) |
| T1 | asm | PASS | success(relevant) - success(none) >= 0.5 (in-range targets) |
| T2 | asm | PASS | success(one_relevant) - success(none) <= 0.1 |
| T3 | asm | PASS | unrelated donors: success drop <= 0.05 and cost ratio <= 1.1 |
| T3b | asm | FAIL | mixed donors: success within 0.1 of relevant |
| T4 | asm | PASS | wrong answers per held-out query <= 0.02 in every arm |
| T5 | asm | PASS | relevant donors cannot reach constants outside +-8: success <= 0.1 (predicted range limit) |

ASM adapter errors (Part A): none
Observed values per criterion: `ALPHA8_DEV4_RESULTS.json` (`preregistration.verdicts`).
