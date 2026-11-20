# ASM v0.4.0-alpha.7.2 — Autonomous Procedure Induction

## Status

Alpha.7.2 promotes the audited Procedure Cortex integration only after a fair same-core BEFORE vs AFTER benchmark and a fresh regression recertification. The alpha.7.1 evidence-dependency architecture remains intact and authoritative.

This is **not** a claim of AGI, RSI, general program synthesis, or arbitrary autonomous skill learning.

## What changed

Alpha.7.2 adds bounded experience-triggered procedure induction on top of the alpha.7.1 + Astra-donor procedure/evidence graft:

- `observe_procedural_experience(...)` records externally resolved experience and enables autonomous induction.
- The lower-level `observe_procedure(..., auto_induce=True)` path exposes the same mechanism explicitly.
- A candidate is considered only after at least **3 independent evidence roots** from sources whose current reliability is at least `0.8` and whose stored source-regime version is still current.
- Autonomous proposals are **not trusted immediately**. The existing held-out gate still requires **8 independent validation observations** for unary-integer procedures before activation.
- The first mismatch of an active procedure starts a fresh procedure-regime window. Repeated failures of the already-suspicious version do not keep moving the window forward.
- After rule drift, ASM can induce a new version from fresh trusted evidence.
- If an older stored program matches the new regime, ASM creates a **new auditable revalidation version** instead of silently resurrecting old trust.
- Auto-induction state is persisted in SQLite and survives restart.
- Repeated descendants of one evidence root do not create fake support.
- Low-trust/stale sources cannot trigger autonomous induction.
- Capacity failures return `blocked` while preserving the valid observation and all existing version history.
- Procedure prediction remains read-only with respect to evidence-dependency learning and autonomous-induction state.
- The old manual `observe_procedure` + `induce_procedure` path remains backward compatible.

## BEFORE vs AFTER benchmark

`benchmark_v040a72.py` uses the same alpha.7.2 code, source trust, examples, validation rules, and procedure grammar. The only capability switch under test is autonomous induction.

- **BEFORE:** `auto_induce=False`; no manual discovery/repair call is supplied on tasks whose purpose is to test autonomy.
- **AFTER:** `auto_induce=True`; held-out validation remains unchanged.

Result: **8/8 PASS**.

Key observations:

| Case | BEFORE | AFTER |
|---|---|---|
| Initial rule discovery | abstains without an explicit induction call | discovers `2x+3`, validates it, predicts `201` for `x=99` |
| Trust immediately after 3 fit roots | n/a | still abstains; held-out validation required |
| Rule drift `2x+3 -> -3x+7` | old procedure suspends; no automatic repair | version 2 induced from 3 fresh roots, validated, predicts `-113` for `x=40` |
| Full reversal back to `2x+3` | no automatic recovery | version 3 created by auditable old-structure revalidation, predicts `123` for `x=60` |
| One repeated root | no autonomous behavior | 32 descendants remain 1 independent root; 0 versions |
| Low-trust source | no autonomous behavior | 32 observations produce 0 versions |
| Validated unseen accuracy | manual path: 201/201 | autonomous path: 201/201 |

Full raw evidence: `ALPHA72_BEFORE_AFTER.json`.

## Torture

`benchmark_v040a72_torture.py`: **8/8 PASS**.

- 32 distinct bounded affine rules: **32/32** learned, validated, and predicted correctly.
- Drift + full reversal: **20/20** runs passed.
- Random-output false-activation torture: **0 false active procedures across 50 runs**.
- One-root descendant flood: 0 autonomous versions.
- Low-trust flood: 0 autonomous versions.
- Single outlier: conservative temporary abstention followed by fresh-version revalidation and recovery.
- Restart during held-out validation: state preserved; no duplicate induction attempt.
- Version-capacity exhaustion: fail closed; history retained.
- Manual API compatibility: PASS.

Raw evidence: `ALPHA72_TORTURE.json`.

## Performance

Fresh `benchmark_v040a72_performance.py` measurements in this environment:

- Manual initial discovery median over 20 runs: `0.00364163 s`.
- Autonomous initial discovery median over 20 runs: `0.00389487 s`.
- Discovery ratio: `1.06954x` (~6.95% overhead).
- 500 steady active observations, manual median: `0.0297468 s`.
- 500 steady active observations, auto median: `0.0316951 s`.
- Steady ratio: `1.06550x` (~6.55% overhead).
- Median DB size after the steady profile: `147456` bytes for both paths.

These timings are environment-specific and are not general hardware claims.

## Migration

A real alpha.7.1 database was created using the packaged alpha.7.1 release, then reopened under alpha.7.2.

- adaptive source reliability state preserved exactly;
- evidence-dependency state preserved exactly;
- arbitrary persisted probe data preserved;
- **0 fabricated procedure versions**;
- alpha.7.2 then saved under its new snapshot key.

Evidence: `MIGRATION_ALPHA72.json`.

## Regression recertification

Final bounded unit batches after the alpha.7.2 version/migration changes:

- v0.1 tests: **72/72 PASS**
- v0.2 tests: **84/84 PASS**
- v0.3 tests: **77 executed = 76 PASS + 1 inherited intentional SKIP**
- v0.4 a1-a4: **37/37 PASS**
- v0.4 a5-a6.2: **57/57 PASS**
- v0.4 a7-a7.2 + graft tests: **44/44 PASS**
- review + legacy experimental Procedure Cortex tests: **11/11 PASS**

Total: **382 executed = 381 PASS + 1 inherited intentional SKIP**.

Behavior gates freshly completed:

- alpha.5 frozen benchmark: **13/13 PASS**
- alpha.5.1 torture: **10/10 PASS**
- alpha.5.1 extreme torture: **9/9 PASS**
- alpha.6 torture: **12/12 PASS**
- alpha.6.1 abrupt drift: **30/30 recovered**
- alpha.6.1 stationary torture: **0 false splits across 100 stationary seeds**
- alpha.6.2 lineage torture: **10/10 PASS**
- alpha.7 frozen benchmark: **7/7 PASS**
- alpha.7 torture: **9/9 PASS**
- alpha.7.1 frozen benchmark: **8/8 PASS**
- alpha.7.1 torture: **9/9 PASS**
- alpha.7.2 BEFORE/AFTER: **8/8 PASS**
- alpha.7.2 torture: **8/8 PASS**

Aggregate commands that timed out were **not counted**. Their completed sub-batches were rerun separately where needed.

## Current limitations / next bottleneck

The built-in autonomous synthesizer is intentionally narrow. It currently autonomously searches unary integer identity/square/affine hypotheses (with family reuse). The typed DSL can represent more than that, and external systems may propose other typed programs, but alpha.7.2 does **not** autonomously discover arbitrary Boolean, multi-input, conditional, or composed procedures.

The next bottlenecks are:

1. compositional procedure induction without combinatorial search explosion;
2. stronger integration between procedure evidence and alpha.7/7.1 learned cross-source dependency, beyond root deduplication + source reliability regime binding;
3. disagreement-driven active experiment selection wired into the experience loop;
4. procedure-selection benchmarks when many valid/competing procedures coexist.
