# ASM v0.4.0-alpha.7.9 — Adversarial Latent-Structure Hardening & Stage-Closure

## Status
Official reviewed stage-closure release. Alpha.7.8 remains the immutable control/reference release.

## What changed
- Added a bounded component-wise **signed latent redundancy guard** above the certified alpha.7.8 `full_latent` router.
- Detects coherent anti-correlated / signed common causes by inferring a balanced polarity gauge before factor fitting.
- Detects sparse hidden dependency groups embedded among unrelated sources instead of requiring one global latent field.
- Supports bounded rank<=2 overlapping latent factors inside components up to 32 sources.
- Adds conservative bridge/passenger pruning only when a mixed connected component fails the collective evidence gate.
- Applies latent discounts only to materially loaded sources, reducing stale/passenger leakage.
- Latent discounts are monotone: alpha.7.9 can only reduce the alpha.7.8 weight for a source, never increase confidence.
- Frustrated/inconsistent sign structure, weak evidence, insufficient trials, oversized components, numerical failure, or invalid fits fall back locally to alpha.7.8.
- Dependency-version/source-signature caching invalidates automatically when the dependency state changes.
- `full_signed_latent` is now the default routing mode. Alpha.7.8 `full_latent`, alpha.7.7 `full_covariance`, and earlier modes remain selectable controls.
- Added `asm_snapshot_v0_4_0_alpha_7_9` with explicit alpha.7.8 fallback; migration does not fabricate procedure-route evidence.

## Verified release results
- Full split historical/unit regression: **471 collected = 470 passed + 1 inherited intentional skip**.
  - v0.1: 72/72 passed (+72 subtests).
  - v0.2: 84/84 passed.
  - v0.3: 76 passed + 1 inherited intentional skip.
  - v0.4: 150/150 passed (+19 subtests).
  - procedure/review/alpha.7.x extras: 88/88 passed.
- Alpha.7.4 benchmark: **11/11**.
- Alpha.7.4 torture: **8/8**.
- Alpha.7.5 contextual-routing benchmark: all checks pass; two-context accuracy **100%**; random-noise false route remains false.
- Inherited alpha.5 mega-stress remains **13/14**, with the same pre-existing `topk_truncation_keeps_unknown_mass` failure.

## Alpha.7.9 benchmark evidence
- Approximate adversarial 8-source null correlation fields: **0/20,000 false support reductions**.
- Real learned independent-source runs: **0/12 false detections**.
- Real learned signed hidden-cause runs: **12/12 detections**.
- Mean support in the signed learned runs: alpha.7.8 **~7.718** -> alpha.7.9 **~3.976**.
- 20-source overlapping two-factor structure: alpha.7.8 support **20.0** -> alpha.7.9 **~7.472**.
- Moving-group test: sources from the old hidden group recover to weight **1.0**, while the new hidden group is discounted after the dependency version changes.
- Warm support-weight median in the controlled 20-source benchmark: alpha.7.8 **~0.191 ms** vs alpha.7.9 **~0.198 ms** in this run.

## Consciousness-related phase check
9/9 architectural/behavioral checks pass. Verdict: `no_subjective_consciousness_evidence`. These checks demonstrate only bounded computational self-model/metacognitive behavior and do not establish subjective experience or sentience.

## Limits
- The signed model assumes a sufficiently coherent balanceable sign structure; frustrated graphs fail closed to alpha.7.8.
- The signed latent component is bounded to 32 sources and rank<=2.
- The 20,000 null-field calibration is a controlled approximation, not a proof of a universal false-positive rate.
- The model is not general causal discovery and does not capture arbitrary nonlinear/high-order dependence.
- The routing posterior remains a bounded feature model; alpha.7.9 improves epistemic support, not broad world knowledge or language intelligence.
- No AGI, frontier-model-equivalence, consciousness, or scientific-novelty claim is made.

## Stage decision
Alpha.7.9 closes the current **Stage 7 epistemic/procedure-routing hardening cycle**. The next work should begin a new capability category rather than continue with alpha.7.10.

**Next: v0.4.0-alpha.8 — Structural Transfer & Analogical Procedure Generalization.**
