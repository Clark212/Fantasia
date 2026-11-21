# Benchmark Report — ASM v0.4.0-alpha.7.2

## Fair comparison

The primary BEFORE vs AFTER test holds code, data, source trust, validation thresholds, and grammar constant.

- BEFORE: autonomous induction disabled; no manual discovery/repair call on autonomy tasks.
- AFTER: autonomous induction enabled.

### Result: 8/8 PASS

| Check | Result |
|---|---|
| autonomous initial discovery | PASS |
| held-out gate preserved | PASS |
| autonomous drift revision | PASS |
| full reversal revalidation | PASS |
| repeated-root guard | PASS |
| low-trust guard | PASS |
| manual accuracy preserved | PASS |
| unseen coverage preserved | PASS |

After validation, both the manual and autonomous paths produced **201/201 correct predictions** on the bounded unseen integer sweep used by the benchmark.

## Torture: 8/8 PASS

- 32/32 distinct affine rules learned correctly.
- 20/20 drift + reversal runs passed.
- 0/50 random-output runs produced a false active procedure.
- root/trust guards passed.
- single-outlier recovery passed.
- restart-mid-validation passed.
- capacity fail-closed passed.
- manual compatibility passed.

See `ALPHA72_BEFORE_AFTER.json` and `ALPHA72_TORTURE.json` for raw structured results.

## Claim boundary

These tests establish a narrow capability: bounded autonomous induction, validation, revision and revalidation for the supported procedure family. They do not establish general program synthesis, broad autonomous skill learning, AGI, or RSI.
