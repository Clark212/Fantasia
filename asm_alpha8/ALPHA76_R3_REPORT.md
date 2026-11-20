# ASM v0.4.0-alpha.7.6 Experimental R3 Research Report

## Status

**Experimental research branch. Not promoted as the official alpha.7.6 release.**

Authoritative base: `ASM_v0.4.0-alpha.7.6-experimental-R2.zip`  
Base SHA-256: `326cd0bfd1b6ef4b1fd38ad7d9e914cbaeafcf071d61341a6a338bca82061608`

R3 keeps ASM as cognitive authority. No external model is granted direct belief, procedure, policy, or action authority.

## Research target

R3 attacks the alpha.7.6 hypothesis more strictly: whether procedure applicability routing improves when source reliability and hidden evidence dependence are corrected **locally**, while preserving continual evidence accumulation, drift recovery, active information gathering, and fail-closed behavior.

## Architectural changes from R2

1. **Reliability is now a real routing weight.** R2 only enforced a trust floor/version check; `frequency` and `reliability` were therefore too similar. R3 stores current learned reliability on effective routing rows and continuously weights support.
2. **Dependency correction is local to source identity.** R2 used a global effective-batch correction. R3 uses bounded source-graph weights `1 / (1 + sum(rho_ij^2))` over active pairwise hidden-dependency estimates. A perfectly duplicated pair contributes one effective stream; a perfect k-source duplicate clique contributes one stream; disconnected independent sources remain weight 1.
3. **Continual history no longer collapses as one giant simultaneous batch.** Source dependency weight is applied per externally resolved routing observation, so genuinely new observations across time can accumulate.
4. **Full routing composes reliability × dependency weight.** The ablations are now identifiable: frequency-only, reliability-only, dependency-only, and full.
5. **Information-value queries use the same epistemic weights.** Duplicated sources can no longer dominate which missing context feature ASM chooses to ask about.
6. **Temporal regime persistence uses effective support.** Reliability/dependency penalties can delay a switch when recent rows are epistemically weak, while four admitted high-trust observations remain sufficient under the trust-floor contract.
7. **Dependency diagnostics are cached by dependency-model version + source set.** Any learned dependency update changes the version and invalidates the cache automatically.
8. Fixed a canonical pair-key bug (`dup2` vs `dup10`) that caused some large-set correlations to be missed.

## Adversarial benchmark results

### Partial hidden correlation (12 seeds each)

| Shared-noise setting | Mean learned active correlation | Frequency routes | Reliability routes | Dependency routes | Full routes | Mean full support |
|---:|---:|---:|---:|---:|---:|---:|
| 0.0 | 0.0000 | 12/12 | 12/12 | 12/12 | 12/12 | 3.9048 |
| 0.25 | 0.0374 | 12/12 | 12/12 | 12/12 | 12/12 | 3.8775 |
| 0.5 | 0.4715 | 12/12 | 12/12 | 12/12 | 12/12 | 3.5481 |
| 0.75 | 0.7272 | 12/12 | 12/12 | 12/12 | 12/12 | 3.2313 |
| 1.0 | 1.0000 | 12/12 | 12/12 | 12/12 | 0/12 | 2.9286 |


Full ASM preserves routing through moderate/strong-but-incomplete dependence in this test, but at effectively complete duplication its reliability × dependency support falls below the default evidence threshold and it abstains.

### Reliability ablation

Six barely admitted sources (learned reliability `0.8039`) vote for one context while one near-perfect source (`0.9902`) disagrees.

- Frequency: **routed left**, confidence `0.8212`.
- Reliability-only: **abstain**, confidence `0.7896`.
- Full: **abstain**, confidence `0.7896`.

This verifies that reliability is no longer an alias for frequency counting.

### Large duplicate clique locality

16 perfectly redundant sources collapse to effective support **1.000000**, while three unrelated sources retain weights `[1.0, 1.0, 1.0]`. Total corrected support is **4.000000**.

### Continual repeated evidence

80 routing rows = 20 rounds × four sources, with one perfectly duplicated pair and two independent sources.

- R3 local dependency support: **60.0000**
- R3 full reliability×dependency support: **58.5714**
- Old giant-batch N_eff diagnostic on the same historical source list: **7.2727**
- R3 route: **routed → left**

This is the main architectural correction from R2: source redundancy lowers each source's per-observation vote but does not erase independent evidence accumulated over time.

### Dependency drift recovery

Across `8` seeds:

- routed before correlation disappeared: **0/8**
- routed after recent evidence became independent: **8/8**
- mean full support: **2.9286 → 3.7770**
- mean remaining active correlation after drift: **0.2312**

Routing history was not rewritten; inference changed because the existing temporal dependency model changed its current view.

### Adversarial correlated majority

When a duplicated cluster supports the wrong context and three independent sources support the alternative:

- 16-source duplicate cluster: frequency **routes the duplicated side**, full ASM **abstains**.
- 32-source duplicate cluster: frequency **routes the duplicated side**, full ASM **abstains**.
- Full support at 16 duplicates: wrong side `0.9762`, independent side `2.9286`.

R3 does not automatically route the minority side because its confidence threshold remains conservative; the verified gain is preventing a false confident route.

### Information-query weighting

Frequency-only query selection chooses `a_bad` because duplicated rows dominate raw counts. Full ASM chooses `z_good` after dependency correction. Repeated query evaluation caused **0 persistent-state mutations**.

### Performance

Fresh completed microbenchmark medians in this environment:

- full route decision: **0.611 ms**
- ambiguous route/query decision: **0.218 ms**

These are microbenchmarks, not hardware-independent claims.

## Regression / compatibility

Final bounded unit regression after the R3 code changes:

- v0.1 + v0.2: **156/156 PASS**
- v0.3: **77 executed = 76 PASS + 1 inherited intentional SKIP**
- v0.4: **150/150 PASS**
- review/graft/procedure/alpha.7.5/R3: **41/41 PASS**
- total: **424 executed = 423 PASS + 1 inherited intentional SKIP**

Recent historical gates rerun individually:

- alpha.7.4 benchmark: **11/11**
- alpha.7.4 torture: **8/8**
- alpha.7.5 benchmark all checks: **true**
- alpha.7.5 two-context accuracy: **100.0%**
- alpha.7.5 random-noise false routed: **false**
- inherited alpha.5 mega-stress: **13/14**, same failure: `topk_truncation_keeps_unknown_mass`

Known inherited SQLite `ResourceWarning`s remain visible in the v0.4 regression. They were already present before R3 and are not counted as new cognition failures.

## Consciousness-related phase check

R3 evaluation: **9/9 PASS**.

Checks include internal-state intervention sensitivity, outcome-grounded capability estimates, unknown-self-belief fail-closed behavior, contradictory self-belief revision, self/other belief separation, a negative subjective-claim control, persistence, fresh-model ablation, and inspection of directly measured internal state variables.

**Verdict: `no_subjective_consciousness_evidence`.** These tests demonstrate computational self-model/metacognitive capacities only. They do not establish subjective experience, sentience, or consciousness.

## Development failures that changed the design

- R2's `reliability` ablation was not genuinely continuous; fixed rather than hiding it.
- Global batch dependency scaling over-penalized long histories; replaced with source-local redundancy correction.
- Global heterogeneous N_eff could suppress independent sources beside a large duplicate clique; fixed with additive local source weights.
- Pair keys were not canonical for lexicographically awkward source IDs; fixed after the 16-source clique test failed.
- Query selection originally used raw counts even when routing used corrected support; fixed.
- Several aggregate regression/benchmark commands exceeded the execution limit. Their partial outputs were discarded and the gates were rerun in bounded individual batches.

## What R3 does NOT prove

- It does not prove the routing mechanism is novel in the research-literature sense.
- It does not prove the mechanism dominates all Bayesian, ensemble, active-learning, or expert-routing baselines.
- It does not show GPT-5.6-level general intelligence or AGI.
- It does not establish consciousness.

## Next bottleneck

The next useful experiment is **calibration under wrong dependency beliefs**: quantify false-abstention cost while the dependency model is stale, measure recovery delay under gradual/abrupt correlation changes, and compare the local source-graph weighting against stronger formal baselines (cluster-aware Bayesian fusion / covariance-aware weighting) on the exact same tasks.
