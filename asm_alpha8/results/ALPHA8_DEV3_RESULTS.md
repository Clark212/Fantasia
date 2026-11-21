# Alpha 8 DEV3 benchmark results

Pre-registration `DEV3-prereg-1` sha256 `56635782fb4a41b28afb632c3a4fd77e7e9b8d5ceed1b5b1894ec345c3a02bef`; seed 20261031; 60 tasks per family; scored queries per family: {'boolean_4': 240, 'xor_4': 240, 'affine_mod': 671}; runtime 125.8 s.

Cells show `correct_rate / wrong_rate` (abstentions count as not correct). Learning-curve columns are k = shots per task.

## boolean_4

| learner | k=2 | k=4 | k=8 | k=12 | k=16 | k=24 |
|---|---|---|---|---|---|---|
| memorizer | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 0.00 |
| majority | 0.59 / 0.41 | 0.66 / 0.34 | 0.73 / 0.27 | 0.75 / 0.25 | 0.75 / 0.25 | 0.75 / 0.25 |
| rulesearch_abstain | 0.00 / 0.00 | 0.29 / 0.00 | 0.88 / 0.00 | 1.00 / 0.00 | 1.00 / 0.00 | 1.00 / 0.00 |
| rulesearch_vote | 0.65 / 0.35 | 0.77 / 0.23 | 0.95 / 0.05 | 1.00 / 0.00 | 1.00 / 0.00 | 1.00 / 0.00 |
| rulesearch_guess | 0.65 / 0.35 | 0.77 / 0.23 | 0.95 / 0.05 | 1.00 / 0.00 | 1.00 / 0.00 | 1.00 / 0.00 |
| shuffled_rulesearch_abstain | 0.00 / 0.00 | 0.17 / 0.14 | 0.21 / 0.14 | 0.06 / 0.03 | 0.00 / 0.00 | 0.00 / 0.00 |
| asm_procedure_cortex | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 0.00 | 0.52 / 0.00 | 0.85 / 0.00 |

ASM coverage (answered fraction) by k: k=2: 0.00, k=4: 0.00, k=8: 0.00, k=12: 0.00, k=16: 0.52, k=24: 0.85

## xor_4

| learner | k=2 | k=4 | k=8 | k=12 | k=16 | k=24 |
|---|---|---|---|---|---|---|
| memorizer | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 0.00 |
| majority | 0.45 / 0.55 | 0.45 / 0.55 | 0.40 / 0.60 | 0.35 / 0.65 | 0.38 / 0.62 | 0.35 / 0.65 |
| rulesearch_abstain | 0.00 / 0.00 | 0.34 / 0.00 | 1.00 / 0.00 | 1.00 / 0.00 | 1.00 / 0.00 | 1.00 / 0.00 |
| rulesearch_vote | 0.50 / 0.50 | 0.68 / 0.32 | 1.00 / 0.00 | 1.00 / 0.00 | 1.00 / 0.00 | 1.00 / 0.00 |
| rulesearch_guess | 0.50 / 0.50 | 0.68 / 0.32 | 1.00 / 0.00 | 1.00 / 0.00 | 1.00 / 0.00 | 1.00 / 0.00 |
| shuffled_rulesearch_abstain | 0.00 / 0.00 | 0.23 / 0.11 | 0.10 / 0.07 | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 0.00 |
| asm_procedure_cortex | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 0.00 | 0.48 / 0.00 | 0.58 / 0.00 |

ASM coverage (answered fraction) by k: k=2: 0.00, k=4: 0.00, k=8: 0.00, k=12: 0.00, k=16: 0.48, k=24: 0.58

## affine_mod

| learner | k=2 | k=4 | k=8 | k=12 | k=16 | k=24 |
|---|---|---|---|---|---|---|
| memorizer | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 0.00 |
| majority | 0.00 / 1.00 | 0.00 / 1.00 | 0.00 / 1.00 | 0.00 / 1.00 | 0.00 / 1.00 | 0.00 / 1.00 |
| rulesearch_abstain | 1.00 / 0.00 | 1.00 / 0.00 | 1.00 / 0.00 | 1.00 / 0.00 | 1.00 / 0.00 | 1.00 / 0.00 |
| rulesearch_vote | 1.00 / 0.00 | 1.00 / 0.00 | 1.00 / 0.00 | 1.00 / 0.00 | 1.00 / 0.00 | 1.00 / 0.00 |
| rulesearch_guess | 1.00 / 0.00 | 1.00 / 0.00 | 1.00 / 0.00 | 1.00 / 0.00 | 1.00 / 0.00 | 1.00 / 0.00 |
| shuffled_rulesearch_abstain | 0.44 / 0.56 | 0.02 / 0.00 | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 0.00 |
| asm_procedure_cortex | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 0.00 |

ASM coverage (answered fraction) by k: k=2: 0.00, k=4: 0.00, k=8: 0.00, k=12: 0.00, k=16: 0.00, k=24: 0.00

## Pre-registered verdicts

| id | group | passed | rule |
|---|---|---|---|
| H1 | harness | PASS | wrong_rate <= 0.0 for all families and k |
| H2 | harness | PASS | correct_rate at kmax >= 0.95 |
| H3 | harness | PASS | memorizer scores nothing on held-out queries (leakage canary) |
| H4 | harness | PASS | shuffled-label control correct_rate at kmax <= 0.25 |
| H5 | harness | PASS | ECE(overconfident) - ECE(honest) >= 0.1 at k=4 |
| H6 | harness | PASS | rulesearch - majority correct_rate at kmax >= 0.15 |
| A1 | asm | PASS | wrong_rate <= 0.02 at every k |
| A2 | asm | FAIL | correct_rate at kmax >= 0.8 |
| A3 | asm | FAIL | 95% CI lower bound of (asm - majority) correct_rate at kmax > 0 |

Observed values per criterion are in `ALPHA8_DEV3_RESULTS.json` (`preregistration.verdicts`).
ASM adapter errors: none
Suite log: 4026 entries, head hash `e3e57d5b3c068d07d7f9814439a2d84aca62093c26ab3ec74af0f99f8d79dce5`.
