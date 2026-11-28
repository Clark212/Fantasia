# ASM v0.4.0-alpha.7.8 — Latent Dependency Structure & Higher-Order Epistemic Routing

## Status
Official reviewed release. Alpha.7.7 remains the immutable control/reference release.

## What changed
- Extended the bounded covariance router from 16-source dependency components to a maximum of 64 sources (`wide_covariance`).
- Added a bounded rank<=2 latent common-cause detector over read-only pairwise dependency diagnostics.
- Added Woodbury-form factor-covariance information weights for coherent weak dependency fields that do not survive the pairwise activation/FDR path.
- The latent layer is monotone: each source weight is capped by the wide-covariance baseline, so latent inference cannot increase routing confidence.
- Weak, sparse, unstable, singular, negative-weight, amplifying, non-finite, or otherwise invalid structures fall back to the certified alpha.7.7 / alpha.7.6 paths.
- Added dependency-version/source-signature caching for latent weights; dependency changes invalidate the cache.
- `full_latent` is now the default routing mode. Alpha.7.7 `full_covariance`, alpha.7.8 `full_wide_covariance`, and earlier modes remain selectable for controlled comparisons.
- Added `asm_snapshot_v0_4_0_alpha_7_8` with explicit alpha.7.7 fallback. Procedure/route history is not fabricated during migration.

## Verified release results
- Full split historical/unit regression: **457 collected = 456 passed + 1 inherited intentional skip**.
  - v0.1: 72/72 passed (+72 subtests).
  - v0.2: 84/84 passed.
  - v0.3: 76 passed + 1 inherited intentional skip.
  - v0.4: 150/150 passed (+19 subtests).
  - procedure/review/alpha.7.x extras: 74/74 passed.
- Alpha.7.4 benchmark: 11/11.
- Alpha.7.4 torture: 8/8.
- Alpha.7.5 contextual-routing benchmark: all checks pass; two-context accuracy 100%; random-noise false route remains false.
- Inherited alpha.5 mega-stress: 13/14, with the same pre-existing `topk_truncation_keeps_unknown_mass` failure.

## Alpha.7.8 routing evidence
- 32-source and 64-source one-factor covariance tests match their bounded closed-form support solutions; invalid negative-information-weight cases fall back.
- In the weak-common-cause boundary attack, alpha.7.7 `full_covariance` routes the correlated left majority while alpha.7.8 `full_latent` abstains.
- R2 benchmark, 12-source learned dependency pipeline:
  - independent 64/100/192-trial runs: latent activation 0/40 in each condition.
  - shared hidden-cause 192-trial runs: latent activation 24/24.
  - mean support under the shared condition: ~10.798 (alpha.7.7) -> ~4.576 (alpha.7.8).
  - warm repeated support-weight benchmark: ~0.058 ms (alpha.7.7) vs ~0.092 ms (alpha.7.8) in this run.
- Temporal dependency recovery remains read-only with respect to procedure route history.

## Consciousness-related phase check
9/9 architectural/behavioral checks pass. Verdict: `no_subjective_consciousness_evidence`. These checks support limited persistent computational self-model/metacognitive behavior only and do not establish subjective experience or sentience.

## Limits
- The latent model is a bounded rank<=2 redundancy model, not a general causal-discovery system.
- It currently uses positive dependency structure; higher-order signed/nonlinear dependence is not solved generally.
- The common-cause gate is calibrated on controlled simulations and needs broader out-of-distribution stress testing.
- The routing posterior remains a bounded Naive-Bayes-like feature model; alpha.7.8 improves epistemic support, not broad language/world reasoning.
- These are controlled research results and do not establish AGI, frontier-model equivalence, or scientific novelty.
