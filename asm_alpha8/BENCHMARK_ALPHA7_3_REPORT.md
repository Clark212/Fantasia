# Benchmark Report — ASM v0.4.0-alpha.7.3

## BEFORE baseline

Exact packaged alpha.7.2 SHA-256:

`6e8fbe1dce3c8af332e3b5be3693aa664418c76d2c667d4a87450230734236de`

Fresh baseline result: 2-input affine, 2-input product, and 3-input affine autonomous induction each returned `unsupported` with 0 procedure versions.

## Primary BEFORE vs AFTER

`benchmark_v040a73.py`: **10/10 PASS**.

| check | result |
|---|---|
| exact alpha.7.2 baseline identity | PASS |
| baseline lacks multi-input induction | PASS |
| 2-input affine learned + 231/231 unseen correct | PASS |
| bounded product synthesis + 289/289 unseen correct | PASS |
| 3-input affine + 256/256 unseen correct | PASS |
| validated donor structure reuse | PASS |
| multi-input drift revision | PASS |
| full reversal revalidation | PASS |
| repeated-root guard | PASS |
| random outputs do not become active | PASS |

## Torture

`benchmark_v040a73_torture.py`: **7/7 PASS**.

- 48 random affine tasks across 2–4 inputs.
- five nonlinear/compositional primitives under hard search budget.
- four validated donor-composition cases, including `x²+y²`.
- 20 random multi-input drift/reversal runs.
- 40 random-output runs: 0 false active procedures.
- rank-deficient evidence fail-closed.
- repeated-root / low-trust guards.
- alpha.7.2 unary compatibility.

## Claim boundary

These results establish a narrow bounded capability: autonomous multi-input integer procedure fitting, shallow expression composition, held-out validation, drift revision, and audited structural reuse. They do not establish general program synthesis or broad autonomous reasoning.
