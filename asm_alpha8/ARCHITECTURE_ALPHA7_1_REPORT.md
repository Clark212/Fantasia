# ASM v0.4.0-alpha.7.1 Architecture Report

## Capability boundary

Alpha.7.1 does not replace alpha.7. It adds an explicitly time-aware layer around the existing cumulative dependency model.

ASM now keeps four distinct evidence concepts separate:

1. **Source reliability** — `AdaptiveEvidenceModel`.
2. **Known provenance/copies** — `EvidenceLineageGraph`.
3. **Hidden statistical redundancy** — cumulative `EvidenceDependencyModel` from alpha.7.
4. **Current dependency regime** — optional temporal recent-view/regime state from alpha.7.1.

Only externally resolved evidence trials can train dependency. Inference and ASM's own current belief cannot supply the training label.

## Explicit temporal contract

Temporal adaptation is opt-in:

```python
engine.observe_evidence_dependency_trial(
    "trial-1001",
    resolved_hypothesis="A",
    observations={"sensor-A": ["A", "A"], "sensor-B": ["A"]},
    temporal_index=1001,
)
```

The temporal index must be finite and strictly greater than the last accepted temporal index. Calls without a temporal index preserve alpha.7 cumulative behavior and do not create fake temporal history or regimes.

## Two views of dependency

### Cumulative view

The alpha.7 sufficient statistics remain the complete historical record. They are never discarded merely because the current regime changes.

### Recent/current view

For explicitly temporal data, a bounded recent window (default 192 accepted temporal trial contributions) drives current dependency lookup. This lets present inference adapt when dependency structure changes without rewriting historical evidence.

## O(1) rolling sufficient statistics

Each recent/change window stores aggregate Pearson-correlation sufficient statistics:

- sample count
- `sum_x`, `sum_y`
- `sum_x²`, `sum_y²`
- `sum_xy`

Each accepted trial contributes one compact statistics object. Adding a new trial adds those statistics; evicting the oldest trial subtracts them exactly. Therefore rolling-window update and correlation lookup do not rescan all stored observations.

Cross-source trial construction is still bounded by the number of participating sources, and symmetric evidence-batch fusion still has pairwise work. Alpha.7.1's O(1) claim applies specifically to maintaining/querying each temporal dependency window, not to the entire multi-source training operation.

## Change detection and regimes

Two temporal detectors are used:

- within-source: change window 64, delta gate 0.35, z gate 4.5, persistence 3
- cross-source: change window 96, delta gate 0.45, z gate 6.0, persistence 5

The stricter cross-source gate is intentional: pairwise source correlation was noisier in stationary torture and an earlier shared-gate design produced false cross-source change points.

Strong persistent changes close the prior `_DependencyRegime` and open a new version. The bounded recent estimator can still adapt current inference to moderate changes that do not justify a hard regime split.

## Inference semantics

Alpha.7's symmetric batch fusion is preserved. Current temporal correlation changes the effective evidence mass only when a temporal recent view exists. Non-temporal models use cumulative correlation exactly as before.

Inference is read-only with respect to dependency training state. The torture benchmark recorded identical dependency state version before and after inference and zero posterior difference across evidence ordering in the tested contract.

## Persistence

Current snapshot key: `asm_snapshot_v0_4_0_alpha_7_1`.

The loader explicitly falls back to `asm_snapshot_v0_4_0_alpha_7`. A schema-1 alpha.7 dependency snapshot restores cumulative statistics while leaving temporal windows and regimes empty. Schema 2 persists temporal windows, change detector state, and regimes.

This prevents a migration from inventing chronology that was never supplied.

## Atomic failure behavior

Validation and capacity checks are performed before committing the accepted trial. Tested rejected cases include decreasing, non-finite, boolean, and non-numeric temporal indices plus source-capacity and pair-capacity failures. These paths leave dependency state unchanged.

## Authority boundary

External language models, neural backends, EPN prototypes, or code generators do not become the cognitive authority. Procedure Cortex remains experimental and is not integrated into `ASMEngine`. Alpha.7.1 changes how externally resolved evidence dependency is represented; it does not grant external modules direct belief/memory authority.

## Remaining architecture gaps

- no negative-correlation exploitation in evidence mass
- no latent common-cause or causal-direction discovery
- no automatic trial-boundary or chronology inference
- multi-class errors are still reduced to correctness statistics for dependency estimation
- planner does not yet model correlated future observations
- multi-source temporal training retains O(source-pair) work even though each rolling dependency view is O(1) to update/query
