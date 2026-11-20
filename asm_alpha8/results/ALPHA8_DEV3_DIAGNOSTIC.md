# DEV3 exploratory diagnostics (not pre-registered)

Purpose: separate an adapter problem from a capability gap for ASM's ProcedureCortex on integer rules.

| case | shots k | answered | correct | wrong | adapter errors |
|---|---|---|---|---|---|
| plain affine y=a*x+b (held-out x beyond training range) | 24 | 120/120 | 120 | 0 | 0 |
| plain affine y=a*x+b | 8 | 0/120 | 0 | 0 | 0 |
| affine mod 29, small a,b, wrap not always visible in shots | 24 | 54/120 | 45 | 9 | 0 |

Reading: plain integer affine is learned and extrapolated at k=24 but not at k=8; ASM's grammar has no modulus operation,
so the benchmark's affine_mod family is outside what it can represent. In the third case the shots can fit a plain affine rule
that is wrong for held-out inputs where the modulus wraps, and ASM answers some of those with confidence (see 'wrong').
