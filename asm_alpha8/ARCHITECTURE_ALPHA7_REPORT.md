# ASM v0.4.0-alpha.7 Architecture Report

## Capability

Alpha.7 adds an evidence-dependency learner beside alpha.6.x adaptive reliability and alpha.6.2 explicit lineage.

Three different questions are now separated:

1. **How reliable is a source?** — `AdaptiveEvidenceModel`.
2. **Is this observation a known copy/derivation?** — `EvidenceLineageGraph`.
3. **Do observations behave as statistically redundant even when no ancestry was supplied?** — `EvidenceDependencyModel`.

## Learning protocol

Dependency learning only consumes externally resolved trial groups:

```python
engine.observe_evidence_dependency_trial(
    "trial-184",
    resolved_hypothesis="A",
    observations={
        "camera-A": ["A", "A", "A"],
        "camera-B": ["A"],
    },
)
```

Within-source correlation is estimated from symmetric correctness-pair sufficient statistics. Cross-source correlation is estimated from one aggregate correctness value per source per trial. Significance is gated by:

- minimum resolved trials: 64
- minimum positive correlation: 0.25
- Fisher-z gate: 4.0

Only positive dependency reduces evidence mass in alpha.7.

## Inference

Hidden dependency is fused symmetrically:

```python
belief = engine.update_belief_from_evidence_batch(
    {"A": 0.5, "B": 0.5},
    evidence=[
        {"source_id": "camera-A", "observation": "A", "supplied_reliability": 0.7},
        {"source_id": "camera-B", "observation": "A", "supplied_reliability": 0.7},
    ],
)
```

For a batch with source correlation matrix `R`, alpha.7 estimates shared redundancy using positive `r²` terms. It computes an effective evidence count of the form:

`n_eff = n² / correlation_denominator`

and a common evidence scale:

`scale = n_eff / n`

Every likelihood contribution in the batch receives the same scale. This makes the correction invariant to evidence ordering and avoids the rejected early-clue dominance bug from sequential marginal weighting.

## Complexity / bounds

- max learned sources: 256
- max source pairs: 32,768
- max resolved trial IDs: 131,072
- max readings per source in one training trial: 4,096
- max hidden-dependency inference batch items: 4,096
- within-source sufficient-statistic update: O(readings)
- cross-source trial update: O(unique_sources²), bounded by the source cap
- effective-batch calculation: O(unique_sources²)

All capacity overflows fail closed.

## Persistence

Snapshot key: `asm_snapshot_v0_4_0_alpha_7`.

Alpha.6.2 is an explicit fallback. Older source reliability and lineage state migrate unchanged; dependency learning starts empty because retroactively inventing correlations from historical data without resolved trial grouping would be unsound.

## Preserved authority boundary

Language models and external backends remain proposal-only. Evidence dependency learning does not let an external model directly mutate beliefs. The learning label is externally resolved truth, and the result only changes how future evidence mass is weighted.

The EPN-inspired Procedure Cortex remains experimental and separate from the stable engine.

## Known architectural gaps

- no dependency regime/change-point detection
- no negative-correlation exploitation
- no automatic trial-boundary discovery
- no causal direction or latent common-cause identification
- batch-only hidden-dependency correction
- belief planner does not yet use learned dependency when simulating future sensing sequences
- correctness correlation is a coarse reduction for multi-class error structure
