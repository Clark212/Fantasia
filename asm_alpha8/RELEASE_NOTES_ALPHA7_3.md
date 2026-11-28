# ASM v0.4.0-alpha.7.3 — Multi-Input Compositional Procedure Induction

## Status

Alpha.7.3 extends the certified alpha.7.2 autonomous Procedure Cortex while preserving alpha.7.1 evidence-dependency learning and all older cognitive/planning layers.

This release is a **same-stage capability extension**, not a new architecture reset. It does not claim AGI, RSI, general code synthesis, or arbitrary autonomous skill learning.

## What changed

Alpha.7.3 adds bounded autonomous synthesis for integer procedures over **2–4 named integer inputs**.

The built-in synthesis path is layered:

1. **Exact bounded affine solve** for `sum(ai*xi)+b` using rational Gaussian elimination.
   - the fit must be full-rank;
   - underdetermined fits are rejected rather than assigned arbitrary coefficients;
   - integer coefficients/bias are bounded to `[-32, 32]`.
2. **Validated procedure structure reuse**.
   - only currently active donor procedures whose source-regime dependencies remain valid may donate structure;
   - unary donors can be remapped onto each integer input;
   - donor authority is never inherited: the new procedure must earn its own fit and held-out evidence.
3. **Cheap nonlinear seeds**, including per-input squares.
4. **Shallow signature-deduplicated composition** using `add`, `sub`, `mul`, `min`, and `max`.
5. **Hard search budget: 512 candidate programs**.

The unary alpha.7.2 grammar remains unchanged.

## Evidence gates

To reduce spurious multi-input fits, autonomous proposal now requires:

- unary: **3** independent trusted roots (unchanged from alpha.7.2);
- 2 inputs: **4** roots;
- 3 inputs: **5** roots;
- 4 inputs: **6** roots.

All candidates still require **8 distinct held-out validation inputs** before activation.

Repeated descendants of one root still count once. Low-trust or stale-source observations still cannot trigger autonomous induction.

## BEFORE vs AFTER — exact alpha.7.2 artifact

The BEFORE baseline is the exact packaged `ASM_v0.4.0-alpha.7.2.zip` with SHA-256:

`6e8fbe1dce3c8af332e3b5be3693aa664418c76d2c667d4a87450230734236de`

Fresh baseline probes confirmed that alpha.7.2 returned `unsupported` and created **0 procedure versions** for:

- 2-input affine induction;
- 2-input product induction;
- 3-input affine induction.

Alpha.7.3 BEFORE/AFTER benchmark: **10/10 PASS**.

Key AFTER results:

- 2-input affine `2x + 3y + 5`: autonomously proposed, validated, and **231/231** unseen grid predictions correct.
- `x*y`: found within the hard budget and **289/289** unseen grid predictions correct.
- 3-input affine: **256/256** random unseen predictions correct.
- validated donor structure reuse: composed procedure activated only after its own held-out evidence.
- multi-input rule drift: new version induced and validated.
- full reversal: old structure returned only as a **new auditable revalidation version**.
- repeated-root guard preserved.
- random-output safety case produced 0 active false procedure.

Raw evidence: `BASELINE_ALPHA72_MULTIINPUT.json` and `ALPHA73_BEFORE_AFTER.json`.

## Torture

`benchmark_v040a73_torture.py`: **7/7 PASS**.

- **48 random affine rules** across 2, 3, and 4 inputs: all learned, validated, and predicted correctly on unseen data.
- bounded nonlinear primitives: `x*y`, `min(x,y)`, `max(x,y)`, `x²+y`, and `x*y+x`: PASS.
- validated donor compositions, including `x²+y²`: PASS.
- **20/20** multi-input drift + full-reversal runs: PASS.
- **40** random-output runs: **0 false active procedures**.
- rank-deficient affine evidence: unresolved/fail-closed at the 512-candidate cap with 0 versions.
- repeated-root and low-trust guards: PASS.
- unary alpha.7.2 compatibility: PASS.

An early torture run exposed two useful issues and was **not counted** as a pass:

1. a duplicate held-out input meant only 7 distinct validation inputs; ASM correctly refused activation. The benchmark generator was fixed rather than weakening ASM's validation rule;
2. three multi-input fit roots allowed a spurious nonlinear fit. The architecture was hardened to require one extra independent multi-input root and the same torture was rerun cleanly.

Raw evidence: `ALPHA73_TORTURE.json`.

## Performance

Fresh `benchmark_v040a73_performance.py` results in this environment:

| operation | median | p90 / detail |
|---|---:|---:|
| 2-input affine synthesis | 0.000859 s | p90 0.001092 s; 1 candidate / 4 evaluator calls median |
| `x*y` synthesis | 0.001424 s | p90 0.001566 s; 18 candidates / 72 evaluator calls median |
| `x²+y` synthesis | 0.003601 s | p90 0.004021 s; 71 candidates / 284 evaluator calls median |
| active procedure prediction | 20,000 in 0.14224 s | ~140,605 predictions/s |

The exact alpha.7.2 vs current unary compatibility microbenchmark showed nearly identical initial autonomous discovery latency in one run (`0.004187 s` vs `0.004143 s`). The steady 500-observation run was ~`1.169x` slower in that measurement, so this is recorded as a performance item to watch rather than ignored. Median SQLite size remained `147456` bytes in both profiles.

These numbers are environment-specific microbenchmarks, not general hardware claims.

## Migration

A real alpha.7.2 SQLite database was created using the exact packaged alpha.7.2 code, containing an active validated autonomous unary procedure and saved alpha.7.2 cognitive snapshot. The same DB was then opened under alpha.7.3.

Verified:

- procedure version/program/state preserved;
- 8 validation supports preserved;
- source dependency preserved;
- autonomy attempt state/signature preserved;
- prediction remained correct (`62` for `x=20`);
- **0 fabricated multi-input procedure versions**;
- alpha.7.2 snapshot was recognized;
- alpha.7.3 saved a new snapshot key and reopened with the same procedure behavior.

Raw evidence: `MIGRATION_ALPHA73.json`.

## Regression recertification

Fresh bounded unit batches after final capability/version changes:

- v0.1: **72/72 PASS**
- v0.2: **84/84 PASS**
- v0.3: **77 executed = 76 PASS + 1 inherited intentional SKIP**
- v0.4 including alpha.7.3: **138/138 PASS**
- review / Procedure Cortex / Astra-graft tests: **21/21 PASS**

Total: **392 executed = 391 PASS + 1 inherited intentional SKIP**.

Fresh behavior gates:

- alpha.5 frozen benchmark: **13/13 PASS**
- alpha.5.1 torture: **10/10 PASS**
- alpha.5.1 extreme torture: **9/9 PASS**
- alpha.6 torture: **12/12 PASS**
- alpha.6.1 abrupt drift: **30/30 recovered**
- alpha.6.1 stationary: **0 false splits across 100 runs**
- alpha.6.2 lineage torture: **10/10 PASS**
- alpha.7 benchmark/torture: **7/7 + 9/9 PASS**
- alpha.7.1 benchmark/torture: **8/8 + 9/9 PASS**
- alpha.7.2 benchmark/torture: **8/8 + 8/8 PASS**
- alpha.7.3 benchmark/torture: **10/10 + 7/7 PASS**

### Preserved inherited failure

`benchmark_v040a5_mega_stress.py` is **13/14**, failing only `topk_truncation_keeps_unknown_mass`.

The exact untouched alpha.7.2 artifact produces the **same 13/14 result and same failed check**, so this is an inherited benchmark/architecture limitation, not an alpha.7.3 regression. It remains preserved as evidence and was not redefined away.

One aggregate old-gate command timed out and **none of its partial output was counted**. Alpha.7/7.1/7.2 gates were rerun separately to completion.

## Current limitations / next bottleneck

Alpha.7.3 still does not autonomously synthesize arbitrary programs. Current built-in autonomous synthesis is limited to bounded integer expressions over 1–4 inputs, with shallow composition and a small operation set.

Important remaining bottlenecks:

1. autonomous **Boolean/conditional** procedure induction;
2. deeper composition without combinatorial explosion;
3. procedure selection when many procedures match different contexts;
4. wiring disagreement-driven experiment selection into the normal experience loop;
5. tighter use of alpha.7/7.1 learned cross-source dependency inside procedural evidence accounting;
6. reduce or explain the observed steady unary observation overhead;
7. inherited top-k belief-planning unknown-mass failure remains open.

## Inherited runtime warning note

The clean-extraction v0.4 unittest batch emitted **25 `ResourceWarning: unclosed database` warnings** while still passing. The exact untouched alpha.7.2 artifact emits the same **25 warnings** on its v0.4 suite (128/128 PASS), so this warning set is inherited rather than introduced by alpha.7.3. It remains an open cleanup item.
