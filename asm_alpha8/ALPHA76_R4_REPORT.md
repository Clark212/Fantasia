# ASM v0.4.0-alpha.7.6 Experimental R4 Research Report

## Status

**Experimental research branch. Not promoted as the official alpha.7.6 release.**

Authoritative base: `ASM_v0.4.0-alpha.7.6-experimental-R3.zip`  
Base SHA-256: `45febf6d41128632a5019f76ca9acb84eb493bb9943d5c8fd21851c369ff0946`

ASM remains the cognitive authority. R4 does not grant an external model direct belief, procedure, policy, memory, or action authority.

## Research target

R4 attacks the main weakness left by R3: **what happens when the dependency model itself is wrong?**

The phase tests:

- false-positive dependency learning at larger source counts,
- the cost of a wrong dependency belief,
- temporal recovery after fresh independent evidence,
- whether R3's local `rho^2` redundancy correction matches covariance theory,
- whether a routing-only multiple-comparison guard can reduce scale false discoveries without erasing real strong dependence.

## Architectural changes from R3

### 1. Routing-only false-discovery guard

The historical `EvidenceDependencyModel` is intentionally unchanged.

When Procedure Cortex asks the engine for a source-dependency graph, R4 now applies a **Benjamini-Hochberg FDR guard (`q = 0.01`)** across the pairwise dependency hypotheses for the current source set.

This is read-only and routing-specific. It does not rewrite dependency history, regimes, or alpha.7/alpha.7.1 persistence semantics.

The provider now exposes diagnostics:

- tested pair count,
- base active pair count,
- accepted pair count,
- suppressed pair count.

### 2. Covariance-linear local redundancy weighting

R3 used:

`source_weight = 1 / (1 + sum(rho_ij^2))`

R4 uses:

`source_weight = 1 / (1 + sum(rho_ij))`

for positive routing dependencies accepted by the FDR guard.

For an equicorrelated `k`-source cluster this gives:

`N_eff = k / (1 + (k - 1) * rho)`

which is the standard variance/design-effect effective-sample-size relationship.

Perfect duplicate cliques still collapse to one effective stream. Disconnected independent sources retain weight 1.

## Findings

### Scale false-discovery stress

All trials used completely independent 70%-reliable sources with 100 externally resolved dependency trials.

| Sources | Runs | Base runs with any active false pair | FDR-accepted runs | Base active pairs | Accepted pairs |
|---:|---:|---:|---:|---:|---:|
| 16 | 300 | 1 (0.33%) | 1 (0.33%) | 1 | 1 |
| 32 | 200 | 13 (6.5%) | 4 (2.0%) | 13 | 4 |
| 64 | 80 | 11 (13.75%) | 0 (0%) | 11 | 0 |

The original per-pair gate is conservative, but the probability of at least one chance activation rises with `O(n^2)` pair tests. The routing FDR layer substantially reduces that scale effect.

### True-dependency sensitivity

One genuinely dependent pair was embedded among 30 independent sources, with 100 resolved trials per run.

| Shared-noise probability | Runs | Base pair active | R4 FDR accepted |
|---:|---:|---:|---:|
| 0.50 | 24 | 20 | 18 |
| 0.75 | 24 | 24 | 24 |
| 1.00 | 24 | 24 | 24 |

The guard therefore has a measurable cost at moderate dependence: two of the 20 base-active 50%-shared cases were suppressed. R4 does **not** hide this tradeoff.

### Wrong-belief recovery

Four deterministic 32-source seeds produced rare FDR-surviving false dependency pairs despite the world being independent.

Dependency-only procedure routing initially abstained because the false pair reduced the effective support of a three-source exact context signature below the three-root threshold.

Fresh externally resolved independent observations were then supplied with explicit temporal indices.

Recovery delays:

- seed 73: **7 trials**
- seed 139: **21 trials**
- seed 159: **6 trials**
- seed 164: **46 trials**

Mean: **20 trials**  
Maximum: **46 trials**  
Recovered: **4/4**  
Route-history mutations during recovery: **0**

This is an important negative-result boundary: R4 can temporarily over-abstain when the dependency learner is wrong. The temporal dependency view can correct that mistake without rewriting externally resolved procedure-route history.

### Covariance/design-effect comparison

Across equicorrelated synthetic blocks with sizes `2, 4, 8, 16, 32` and correlations `0.1, 0.25, 0.5, 0.75, 1.0`:

- R3 `rho^2` mean absolute effective-support error versus covariance design effect: **2.0340**
- R3 maximum absolute error: **16.6226**
- R4 covariance-linear mean absolute error: **0.0** for this benchmark family

The zero is not a universal claim about arbitrary covariance graphs; the benchmark is deliberately the equicorrelated/block family for which the closed-form design effect is known.

### R3 adversarial gates under R4

All **7/7** R3 adversarial tests remain PASS.

The original partial hidden-correlation benchmark remains conservative and functional:

- 0% shared noise: 12/12 routes
- 25%: 12/12
- 50%: 12/12
- 75%: 12/12
- effectively complete duplication: 0/12 full routes

Dependency drift still recovers 8/8 in the R3 gate.

### Performance

Completed R4 microbenchmark, 32-source route graph:

- median full route decision: **0.576 ms**
- p95 full route decision: **0.693 ms**

These are environment-specific microbenchmarks, not hardware-independent performance claims.

## Regression

Completed bounded unit regression after R4 changes:

- v0.1 + v0.2: **156/156 PASS**
- v0.3: **77 executed = 76 PASS + 1 inherited intentional SKIP**
- v0.4: **150/150 PASS**
- review/graft/procedure/alpha.7.5/R3/R4: **45/45 PASS**
- total: **428 executed = 427 PASS + 1 inherited intentional SKIP**

Additional historical gates rerun:

- alpha.7.4 benchmark: **11/11 PASS**
- alpha.7.4 torture: **8/8 PASS**
- alpha.7.5 parallel benchmark: **all checks pass**, two-context accuracy 100%, random-noise false routed = false
- inherited alpha.5 mega stress: **13/14**, same inherited failure `topk_truncation_keeps_unknown_mass`

Known inherited SQLite `ResourceWarning`s remain visible in the v0.4 unit batch and were not introduced by R4.

## Consciousness-related phase check

R4 phase check: **9/9 specific checks PASS**.

Verdict: **`no_subjective_consciousness_evidence`**.

The checks continue to support persistent computational self-modeling and limited metacognitive behavior, including self/other belief separation and state-grounded interventions. They do not establish subjective experience, sentience, or consciousness. No new anomaly was observed in R4.

## Development failures / rejected changes

- An inspection output initially appeared to show route support being summed twice. Numbered source inspection proved this was a display concatenation artifact; **no code patch was made for a nonexistent bug**.
- A proposed reliability-aware lowering of `min_support` made an old R3 dependency-drift adversarial case route too early. The patch was **rejected and reverted**. R4's false-dependency recovery test was changed to dependency-only mode so it measures the intended mechanism without weakening historical routing gates.
- A large initial sensitivity sweep timed out. Its partial result was discarded; smaller bounded runs were used instead.

## Breakthrough / milestone assessment

**Verified human-unknown breakthrough: NO.**

FDR correction and covariance/design-effect weighting are established statistical ideas. The research value here is applying and testing them inside ASM's persistent executable-procedure applicability system with hidden-dependency learning and temporal correction.

**ASM milestone remains: Adaptive Research AI.**

R4 is a reliability hardening phase, not a new general-capability tier.

## Next bottleneck

R4 still uses a local pairwise approximation for arbitrary dependency graphs. The next serious research question is whether a bounded **covariance-matrix / cluster-latent routing model** can improve calibration on heterogeneous graphs without:

- negative/unstable weights,
- expensive matrix inversion,
- over-abstention,
- loss of continual online updates,
- corruption from wrong dependency estimates.

A fair R5 should compare R4 against regularized generalized-least-squares / cluster-aware Bayesian baselines on the exact same source graphs and route tasks.
