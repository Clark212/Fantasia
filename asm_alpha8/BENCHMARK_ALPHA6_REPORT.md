# ASM v0.4.0-alpha.6 — Adaptive Evidence Reliability

## Scope

Alpha.6 adds one new capability: ASM can learn the reliability of a named evidence source from externally resolved outcomes and use that learned reliability during belief updates and belief-state planning. It does **not** add another planner, latent-cause invention, drift detection, or correlation learning.

The learner is a bounded persistent Beta posterior per source. Inference never trains the source model from ASM's own current guess; only an explicit resolved hypothesis may update it. This prevents a self-confirmation loop.

## Architecture

- `EvidenceSourceReliability`: persistent alpha/beta state, learned reliability, posterior uncertainty, support, and supplied-vs-learned mismatch delta.
- `AdaptiveEvidenceModel`: bounded registry (default 1024 sources), fail-closed validation, symmetric categorical likelihood generation for 2–32+ hypotheses, export/import state.
- `ASMEngine.observe_evidence_source(...)`: supervised reliability update after external resolution.
- `ASMEngine.update_belief_from_source(...)`: belief update using learned source reliability without mutating the source model.
- `ASMEngine.plan_world_actions_belief(..., evidence_source_id=..., supplied_reliability=...)`: planner may override a structurally valid but factually wrong sensor likelihood with the learned source model for categorical sensor observations that name hypotheses. Other action likelihoods remain unchanged. Simulated branches never train calibration.
- Snapshot key: `asm_snapshot_v0_4_0_alpha_6`, with explicit alpha.5.2 fallback.

## BEFORE vs AFTER — controlled online calibration

Protocol: 6000 sequential episodes, 9 clues/episode, tail metrics over the final 1500 episodes, fixed random seed 4060. Ground truth is revealed only after each episode, then used to train the source reliability.

| Scenario | Supplied | Learned final | BEFORE accuracy | BEFORE confidence | BEFORE calib gap | AFTER accuracy | AFTER confidence | AFTER calib gap |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| matched70 | 70.00% | 69.97% | 90.20% | 90.34% | 0.14% | 90.20% | 90.31% | 0.11% |
| true70_model90 | 90.00% | 69.96% | 89.13% | 97.51% | 8.38% | 89.13% | 90.08% | 0.95% |
| true90_model70 | 70.00% | 90.03% | 99.87% | 99.02% | 0.85% | 99.87% | 99.88% | 0.02% |
| antiinformative20_model90 | 90.00% | 19.96% | 1.87% | 99.18% | 97.32% | 98.13% | 98.12% | 0.01% |
| drift90_to60_model90 | 90.00% | 74.89% | 72.80% | 95.76% | 22.96% | 72.80% | 89.52% | 16.72% |
| flip90_to10_model90 | 90.00% | 49.99% | 0.00% | 99.94% | 99.94% | 0.00% | 79.75% | 79.75% |
| correlated70_model70 | 70.00% | 70.35% | 71.33% | 99.95% | 28.62% | 71.33% | 99.95% | 28.62% |

### What improved

- True 70% / supplied 90%: tail calibration gap fell from **8.38% to 0.95%** while decision accuracy stayed 89.13%.
- True 90% / supplied 70%: tail calibration gap fell from **0.85% to 0.02%**.
- Anti-informative true 20% / supplied 90%: ASM learned reliability below 50%, correctly inverted the evidence, and tail accuracy changed from **1.87% to 98.13%**; calibration gap fell from 97.32% to 0.01%.
- Matched 70% source remained effectively unchanged, avoiding a regression when the supplied model was already right.

### Failures deliberately preserved

- **Drift:** 90%→60% source ended at a historical average around 74.89%; tail calibration gap remained 16.72%. Alpha.6 has no forgetting/windowing/change-point mechanism.
- **Sudden adversarial flip:** 90%→10% produced a historical mean near 50%; final-window accuracy remained 0% and calibration gap 79.75%. This is strong evidence for a future drift/change-point capability.
- **Correlated evidence:** repeated copies of one 70%-reliable clue still produced ~99.95% confidence with ~71.33% accuracy. Marginal source reliability learning cannot discover dependence/common noise.

These are not patched with hard-coded corrections.

## Torture feed

`benchmark_v040a6_torture.py`: **12/12 PASS**. It actually ran:

- 1,000,000 resolved reliability updates with finite state and convergence to 70%.
- recovery from exact supplied priors 1.0 and 0.0.
- 32 simultaneous evidence sources with bounded source capacity.
- exact export/import round-trip.
- 250 randomized Beta-posterior sequences against a direct oracle (max error 1.11e-16).
- normalized symmetric likelihood matrices from 2 through 32 hypotheses, including extreme reliabilities.
- 100,000 inference calls verifying inference does not self-train the source.
- malformed snapshot rejection.
- tiny weighted updates remaining finite.

## Preserved belief/planning behavior

Fresh final-tree runs:

- migrated alpha.5 controlled benchmark: **13/13 PASS**. The only migrated assertion is the current release version string; Bayesian targets and behavioral checks are unchanged.
- alpha.5 hard feed: **6/6 PASS**.
- alpha.5.1 torture: **10/10 PASS**.
- alpha.5.1 extreme torture: **9/9 PASS**.
- seven-clue hidden-state result remains **87.3964%**, with 108 expansions, 140 memo hits, and 77 policy nodes.
- old alpha.5 mega-feed was freshly rerun and remains **13/14**: its legacy top-k truncation check expects incomplete likelihood mass to be accepted; current fail-closed probability contracts intentionally reject that interpretation. This incompatibility remains visible.

## Unit regression

Final source tree, split into completed batches to avoid timeout ambiguity:

- v0.1/v0.2 legacy surface: **156/156 PASS**.
- v0.3 surface: **76 PASS + 1 inherited skip** (`test_v030a3` skips when the alpha.2 source artifact is unavailable).
- v0.4 surface including alpha.6: **74/74 PASS**.
- review-patch surface: **3/3 PASS**.
- total executed unit tests: **310 = 309 PASS + 1 SKIP**.

## Migration

Opening the supplied trained database through alpha.6 preserved:

- 897 episodic events
- 897 semantic vectors
- 897 typed semantic event records
- 24 current world states
- 50 world-state history entries

The migrated database starts with zero adaptive source models, as expected; alpha.6 does not fabricate reliability history for old data.

## Performance

Alpha.6 does not claim to solve the remaining long-stream scaling issue. A fresh 160-event run measured:

- first-10 mean: **6.63 ms/event**
- last-10 mean: **30.96 ms/event**
- total: **3222.90 ms**

This remains an engineering bottleneck independent of the new evidence-learning capability.

## Known limitations / next bottleneck

1. Requires externally resolved truth to learn reliability; no self-supervised reliability discovery yet.
2. Stationary Beta model has no forgetting, recency weighting, drift detection, or change-point detection.
3. Learns marginal source correctness only; it cannot detect correlated sensors, copied evidence, or hidden common noise.
4. Initial likelihood model is symmetric categorical: the observation must name one hypothesis. It does not yet learn arbitrary observation vocabularies or a full confusion matrix.
5. Does not propose new latent hypotheses or hidden causes.
6. Language generalization was not improved in alpha.6.
7. Long-stream semantic/relation scaling remains non-constant.
8. Ancient alpha.8–alpha.10 heavyweight long-stream benchmark programs were **not freshly rerun** for this release; their unit surfaces were rerun.

The next capability should be earned from the preserved failures above. The strongest evidence now points to **non-stationarity/dependency learning** (drift/change-points and evidence correlation), not another planning layer.
