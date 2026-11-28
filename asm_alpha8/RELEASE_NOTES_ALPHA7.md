# ASM v0.4.0-alpha.7 — Evidence Dependency Learning

Alpha.7 is a new capability stage: ASM can learn hidden positive redundancy between evidence observations from externally resolved trial groups, rather than requiring explicit lineage to be supplied.

## What changed

- Added `EvidenceDependencyModel`.
- Learns **within-source intratrial correlation** (repeated readings from one sensor).
- Learns **cross-source trial-level correlation** (different sensors that repeatedly succeed/fail together).
- Learning requires external resolved truth and an explicit trial boundary; ASM never uses its own posterior as the training label.
- Uses conservative Fisher-gated positive correlation and `r²` shared-variance redundancy.
- Added symmetric `update_belief_from_evidence_batch(...)` fusion.
- Batch fusion computes a bounded effective evidence count and applies one common evidence scale, avoiding order-dependent sequential discounting.
- Explicit alpha.6.2 lineage remains unchanged and is still the correct path when provenance is known.
- Dependency state is persistent under the new snapshot key `asm_snapshot_v0_4_0_alpha_7`, with explicit alpha.6.2 fallback.
- Added hard bounds for sources, pairs, trials, readings per source/trial, and inference batch size.
- EPN-derived Procedure Cortex remains experimental and is not integrated into `ASMEngine`.

## BEFORE vs AFTER

Controlled 9-clue, 70%-reliable hidden-copy task, 10,000 evaluation trials:

- repeated readings from one source:
  - BEFORE: 69.33% accuracy, 99.951% confidence, 30.621% calibration gap.
  - AFTER: 69.33% accuracy, 70.000% confidence, 0.670% calibration gap.
- nine cross-source observations sharing the same hidden noise:
  - BEFORE: 69.88% accuracy, 99.951% confidence, 30.071% calibration gap.
  - AFTER: 69.88% accuracy, 70.000% confidence, 0.120% calibration gap.
- genuinely independent repeated-source clues remained numerically unchanged: 90.24% accuracy, 90.330% confidence.
- genuinely independent cross-source clues remained numerically unchanged: 90.09% accuracy, 90.150% confidence.

Perfect-copy dependency becomes active at the configured minimum of 64 resolved trials in the deterministic detection benchmark.

## Partial dependency torture

For 9 clues with a hidden shared-noise mixture:

- 25% shared mode: calibration gap 7.276% -> 2.988%, decisions unchanged.
- 50% shared mode: 15.095% -> 3.671%, decisions unchanged.
- 75% shared mode: 22.809% -> 1.021%, decisions unchanged.

A 32-source perfect common-noise batch collapses to ~1.0 effective clue. A 32-source independent batch remains exactly 32 effective clues.

## What failed during development

The first integration used sequential marginal effective-sample-size weights. It was rejected because partial correlation made inference order-dependent and could lower decision accuracy by overweighting early clues.

The final architecture performs dependency correction only in symmetric batches. The existing `update_belief_from_source(...)` sequential API intentionally preserves alpha.6.2 behavior.

Raw correlation also over-discounted weak partial dependency in early torture. The final release uses `r²` as a conservative shared-variance redundancy measure.

## Known limitations

- Dependency is cumulative, not regime-aware. If sources change from correlated to independent or vice versa, alpha.7 can lag badly.
- Negative correlation is reported but not exploited for evidence fusion.
- Trial boundaries must be supplied; alpha.7 does not discover episode segmentation.
- Hidden-dependency correction currently requires `update_belief_from_evidence_batch(...)`; the internal belief planner does not yet automatically model correlated future observations.
- Pairwise correctness correlation is not a complete causal or latent-variable model.
- Multi-class dependency is reduced to correctness-vs-resolved-truth statistics in this stage.
- No unrestricted latent-cause invention was added.

## Regression

Completed unit-test batches on the final tree:

- v0.4/review/Procedure Cortex/new alpha.7 batch: 118/118 PASS.
- v0.3 batch: 77 executed = 76 PASS + 1 inherited intentional SKIP (`alpha.2 source unavailable`).
- v0.1/v0.2 batch: 156/156 PASS.
- total: 351 executed = 350 PASS + 1 inherited intentional SKIP.

Preserved release gates freshly rerun on the final tree:

- alpha.5 benchmark: 13/13 PASS.
- alpha.5 hard feed: 6/6 PASS.
- alpha.5.1 torture: 10/10 PASS.
- alpha.5 extreme resurrection torture: 9/9 PASS.
- alpha.6 torture: 12/12 PASS.
- alpha.6.1 abrupt 90%->10% drift: 30/30 recovered; mean below-0.5 recovery 22.57 observations; tail accuracy 90.42%.
- alpha.6.1 stationary torture: 0 false splits across 100 runs.
- alpha.6.2 lineage torture: 10/10 PASS.
- alpha.7 benchmark: 7/7 PASS.
- alpha.7 torture: 9/9 PASS.
- smoke test: PASS.

A combined all-batches wrapper exceeded the environment timeout after the first two batches; it is not counted. Each unit batch was run separately to completion.

## Migration

An alpha.6.2 snapshot with 100 resolved source observations and two lineage nodes migrated with the source state and lineage intact; alpha.7 dependency state starts empty rather than fabricating historical correlations.

The historical trained DB still loads with:

- 897 episodic events
- 897 semantic vectors
- 897 typed semantic-event records
- 24 current world states
- 50 world-state history entries

## Next evidence-backed bottleneck

Dependency drift is now the clearest same-stage hardening target. In a 1000-correlated -> 1000-independent probe, cumulative alpha.7 became underconfident by ~16.63 percentage points; in the reverse sequence it remained overconfident by ~23.27 points. A later alpha.7.x patch should investigate regime-aware dependency learning without weakening the stationary false-positive gates.
