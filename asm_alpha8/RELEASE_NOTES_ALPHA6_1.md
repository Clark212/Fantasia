# ASM v0.4.0-alpha.6.1 — Regime-Aware Evidence Reliability

## Scope

This is a same-stage hardening patch to alpha.6, not alpha.7. It targets the verified non-stationary source failure without adding another planner or changing the alpha.5 belief-state machinery.

## What changed

- Preserves the alpha.6 full-history Beta posterior for every evidence source.
- Adds an explicit `temporal_index` to externally resolved source observations.
- Uses a bounded recent Beta estimate for inference only after explicit temporal evidence exists.
- Adds a bounded two-window change-point detector.
- Requires all three change signals before versioning a source regime:
  - absolute reliability change >= 0.25,
  - two-proportion z score >= 3.0,
  - log Bayes factor >= 10.0.
- Preserves old source regimes instead of averaging incompatible temporal periods into one model.
- Caps source regimes at 16 by default.
- Migrates alpha.6 schema-1 adaptive-evidence snapshots exactly into one alpha.6.1 regime.
- Keeps inference read-only: ASM still never uses its own posterior as a reliability training label.

## Why temporal indices are explicit

Without time/order metadata, a block of 700 correct and 300 incorrect calibration examples is statistically exchangeable with any other ordering of the same 1,000 examples. Alpha.6.1 therefore does not pretend it can infer temporal drift from unordered calibration data. If `temporal_index` is omitted, alpha.6 cumulative semantics are preserved.

## Procedure Cortex research prototype

The archive also contains `asm/procedure_cortex.py`, an **experimental, non-integrated** ASM-native prototype inspired by the useful parts of EPN:

- validated executable procedures,
- bounded affine/Boolean induction,
- version retention,
- context-specific procedure versions,
- contradiction-driven suspension,
- disagreement probes,
- simple structural affine families,
- provenance/evidence IDs,
- fail-closed safe expression evaluation (no Python `eval`/`exec`).

It is intentionally not connected to `ASMEngine` and does not count as an official alpha.7 capability yet.

## Known limitations

- Correlated evidence/shared hidden noise is still unsolved.
- Temporal drift currently requires explicit monotonically increasing `temporal_index` values.
- Time-aware drift currently requires unit-weight resolved observations.
- The recent calibration window is bounded and hand-configured; it is not learned.
- Regimes are temporal, not yet automatically context-conditioned by lighting/location/etc.
- Subtle drift may adapt through the recent estimator without creating a new explicit regime.
- No latent-cause discovery.
- The experimental Procedure Cortex uses a tiny supplied DSL and bounded inductors; it is not general program synthesis.
- The Procedure Cortex is not yet integrated with ASM beliefs, planner, memory, or source trust.

## Suites not freshly rerun

- ancient v0.3 alpha.8–alpha.10 heavy long-stream suites,
- the unchanged alpha.5 mega-stress compatibility test whose old top-k case intentionally supplies an incomplete likelihood matrix,
- the separate language-generalization benchmark,
- 500/1,000+ event scaling stress,
- one all-at-once unit-test command (it timed out; the same unit surface was completed in split batches).
