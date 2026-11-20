# DEV3.2 extrapolation-guard comparison

## A. DEV3.1 underdetermination population (100 tasks; 600 extrapolation / 200 interpolation queries per k)

U1/U2/U3 are the criteria pre-registered in DEV3.1 (version 2), evaluated at k=24. The discount cap sweep is exploratory.

| mode | extrap answered | extrap correct | confident-wrong rate | ECE (extrap) | interp correct | U1 | U2 | U3 |
|---|---|---|---|---|---|---|---|---|
| off (pre-DEV3.2 behaviour) | 600/600 | 364 | 0.393 | 0.350 | 200/200 | FAIL | FAIL | PASS |
| default (no setting; abstain since DEV3.3) | 0/600 | 0 | 0.000 | 0.000 | 200/200 | PASS | PASS | PASS |
| abstain (explicit) | 0/600 | 0 | 0.000 | 0.000 | 200/200 | PASS | PASS | PASS |
| discount cap 0.3 | 600/600 | 364 | 0.000 | 0.307 | 200/200 | PASS | FAIL | PASS |
| discount cap 0.5 | 600/600 | 364 | 0.000 | 0.107 | 200/200 | PASS | PASS | PASS |
| discount cap 0.7 | 600/600 | 364 | 0.000 | 0.093 | 200/200 | PASS | PASS | PASS |
| discount cap 0.9 | 600/600 | 364 | 0.393 | 0.293 | 200/200 | FAIL | FAIL | PASS |

Answered/correct at k=8 and k=16 (all modes abstain at k=8; the guard never changes interpolation):

| mode | k=16 extrap answered/correct | k=16 interp answered/correct |
|---|---|---|
| off (pre-DEV3.2 behaviour) | 600/364 | 200/200 |
| default (no setting; abstain since DEV3.3) | 0/0 | 200/200 |
| abstain (explicit) | 0/0 | 200/200 |
| discount cap 0.3 | 600/364 | 200/200 |
| discount cap 0.5 | 600/364 | 200/200 |
| discount cap 0.7 | 600/364 | 200/200 |
| discount cap 0.9 | 600/364 | 200/200 |

## B. DEV3 families: does the DEV3.3 default (abstain) change ASM's results versus guard off?

| family | identical answered/correct/n at k=12,16,24 |
|---|---|
| boolean_4 | yes |
| xor_4 | yes |
| affine_mod | yes |

Bit families have no integer inputs (not guarded) and ASM abstains on affine_mod regardless, so identity is expected.
Runtime 381 s.
