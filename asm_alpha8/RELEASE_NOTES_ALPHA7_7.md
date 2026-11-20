# ASM v0.4.0-alpha.7.7 — Bounded Covariance-Aware Procedure Routing

## Status
Official reviewed release. Alpha.7.6 remains the immutable control/reference release.

## What changed
- Added bounded inverse-covariance evidence weighting for contextual procedure routing.
- Dependency components are solved independently with `R w = 1`.
- Covariance solutions are accepted only for positive-definite components whose per-source information weights are finite and remain within `[0, 1]`.
- Singular, inconsistent, oversized (>16 sources), negative-weight, or amplifying components fall back component-wise to the certified alpha.7.6 local graph weighting.
- Added covariance-weight caching keyed by dependency-model version, source set, and pairwise dependency signature.
- Dependency-model updates invalidate the covariance cache automatically.
- Information-query planning and routed prediction now propagate the selected epistemic mode.
- `full_covariance` is the default routing mode in alpha.7.7; alpha.7.6 `full` remains available for controlled comparison.
- Added `asm_snapshot_v0_4_0_alpha_7_7` with explicit alpha.7.6 fallback. No procedure or route evidence is fabricated during migration.

## Verified results
- Synthetic positive-definite dependency benchmark: 222 covariance families / 2,040 integer support-threshold decisions.
  - alpha.7.6 local graph: 25 wrong decisions, 0 false routes.
  - alpha.7.7 covariance: 0 wrong decisions, 0 false routes.
  - mean absolute effective-support error: ~0.03511 -> ~4.0e-16.
  - max absolute effective-support error: ~0.40909 -> ~3.55e-15.
- Real learned dependency pipeline:
  - correlation-to-independence drift: abstain before -> correct left route after, with route history unchanged.
  - 16-source duplicate-majority attack: raw frequency falsely routes left; covariance mode abstains.
  - information gathering ignores duplicated `a_bad` bait and asks independently supported `z_good`.
- Repeated-route median latency in the 32-source benchmark:
  - alpha.7.6 local: ~0.552 ms.
  - alpha.7.7 covariance: ~0.648 ms.
- Full unit regression after making covariance the default: 441 collected = 440 passed + 1 inherited intentional skip.
- Alpha.7.4 benchmark: 11/11.
- Alpha.7.4 torture: 8/8.
- Alpha.7.5 routing benchmark: all checks pass; two-context accuracy 100%; random-noise false route remains false.
- Inherited alpha.5 mega-stress remains 13/14 with the pre-existing `topk_truncation_keeps_unknown_mass` failure.

## Consciousness-related phase check
9/9 architectural/behavioral checks passed. Result: no evidence of subjective consciousness or sentience. The system continues to show limited persistent computational self-model/metacognitive behavior only.

## Limits
- Only positive learned pairwise dependencies are used for redundancy correction.
- Covariance components are bounded to 16 sources; larger components deliberately fall back to alpha.7.6.
- Pairwise covariance is not a latent-cause model and cannot identify higher-order common-cause structure by itself.
- The route posterior still uses a bounded Naive-Bayes-like feature model; alpha.7.7 improves epistemic support weighting, not general world reasoning.
- Results are controlled research benchmarks and do not establish frontier-model equivalence or general intelligence.
