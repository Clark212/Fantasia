# Benchmark Report — ASM v0.4.0-alpha.7.4

## BEFORE baseline

Exact packaged alpha.7.3 SHA-256:

`421527405b0e9f9d7eb87a291e76f988e81fd4c35d01be4107cc1a9ac2b033f9`

Fresh alpha.7.3 baseline probes:

- XOR: unsupported / 0 versions;
- mixed Boolean/integer selector: unsupported / 0 versions;
- piecewise conditional: unresolved / 0 versions;
- no information-query API.

## Primary BEFORE vs AFTER

`benchmark_v040a74.py`: **11/11 PASS**.

| check | result |
|---|---|
| exact alpha.7.3 baseline identity | PASS |
| baseline lacks alpha.7.4 capabilities | PASS |
| XOR learned + validated | PASS |
| disagreement query selects missing XOR case | PASS |
| information query is read-only | PASS |
| no direct query authority | PASS |
| integer predicate learned | PASS |
| mixed Boolean/integer selector generalizes | PASS |
| piecewise affine generalizes (61/61) | PASS |
| conditional drift revision | PASS |
| conditional reversal revalidation | PASS |

## Torture

`benchmark_v040a74_torture.py`: **8/8 PASS**.

- 8 Boolean families: 8/8.
- 32 random threshold tasks: 32/32.
- 32 random piecewise-affine tasks: 32/32.
- 20 conditional drift/reversal runs: 20/20.
- 100 repeated query calls: stable.
- 100 repeated query calls: read-only / no DB mutation.
- duplicate-root query guard: PASS.
- 40 random Boolean-noise runs: 0 final active procedures.

## Claim boundary

These results establish a narrow capability: bounded typed Boolean/conditional induction, explicit ambiguity abstention, one-step disagreement-driven information requests, held-out validation, and versioned drift repair. They do not establish general active learning, autonomous experimentation, arbitrary program synthesis, or broad causal reasoning.
