# ASM v0.4.0-alpha.7.1 — Dependency Regime Learning

Alpha.7.1 is a same-stage hardening patch for alpha.7. It fixes a verified failure: evidence dependency itself can change over time, while alpha.7 only retained a cumulative dependency estimate.

Authoritative base artifact: `ASM_v0.4.0-alpha.7.zip`, verified SHA-256 `8465354b0261424123e7dc58b1a1d5cd15997f22d7402fb9d69658247511b6f6`.

## What changed

- Added an **explicit temporal path** to `observe_evidence_dependency_trial(..., temporal_index=...)`.
- Temporal adaptation activates only when the caller supplies a finite, strictly increasing `temporal_index`; insertion order is never silently treated as chronology.
- Preserved the full alpha.7 cumulative dependency statistics alongside a bounded **recent/current dependency view** used for current inference.
- Added versioned dependency regimes so durable change points are retained rather than erasing old dependency structure.
- Added O(1) rolling sufficient statistics with exact contribution removal; current dependency lookup does not rescan the bounded history window.
- Uses separate change detectors for within-source and cross-source dependency. Cross-source changes use stricter gates because pairwise estimates are noisier.
- Added `ASMEngine.evidence_dependency_regimes(...)`.
- Snapshot schema 2 persists temporal windows and regimes. Schema-1 alpha.7 snapshots migrate without inventing temporal history.
- Procedure Cortex remains experimental and separate from the stable engine.

## BEFORE vs AFTER — reproduced alpha.7 failures

The alpha.7 baseline failures were reproduced before applying the temporal fix.

| Regime change | Metric | alpha.7 BEFORE | alpha.7.1 AFTER |
|---|---:|---:|---:|
| correlated -> independent | accuracy | 90.21% | 90.21% |
| correlated -> independent | confidence | 73.5787% | 90.2442% |
| correlated -> independent | calibration gap | 16.6313% | 0.0342% |
| independent -> correlated | accuracy | 69.97% | 69.97% |
| independent -> correlated | confidence | 93.2384% | 70.0000% |
| independent -> correlated | calibration gap | 23.2684% | 0.0300% |

Decision accuracy was preserved in both frozen drift cases.

Across 20 seeds, the new detector found correlated -> independent changes in all 20 runs after **27.15 observations on average**, and independent -> correlated changes in all 20 after **50.10 observations on average**. A correlated -> independent -> correlated reversal retained three regimes in **20/20** runs.

## Stationary and partial-dependency hardening

`benchmark_v040a71_torture.py` finished **9/9 PASS**.

- 0 false within-source dependency regime splits across 100 stationary runs.
- 0 false cross-source dependency regime splits across 24 stationary multi-source runs.
- Material 25% <-> 75% partial-dependency shifts were detected in both directions for within-source and cross-source dependency. Explicit 25% -> 50% -> 75% and 75% -> 50% -> 25% sequences also tracked the changing recent correlation in the correct direction for both dependency types; moderate steps are allowed to adapt without forcing a hard regime split.
- 2, 3, 4, 8, 16, and 32 source extremes remained finite and respected independent/common-noise behavior.
- Non-temporal shuffled training retained alpha.7 order-invariant cumulative semantics and created no temporal regimes.
- decreasing, NaN, boolean, and non-numeric temporal indices failed closed; source-capacity and pair-capacity rejection also left state unmodified.
- inference remained order-invariant and did not train dependency state.

## Persistence / migration

A real alpha.7 snapshot DB containing 300 dependency trials was reopened under alpha.7.1:

- 300/300 dependency trials preserved.
- raw correlation preserved exactly (`1.0 -> 1.0`).
- 0 fabricated temporal self views.
- 0 fabricated temporal pair views.
- 0 fabricated dependency regimes.

The historical trained DB is byte-for-byte preserved with SHA-256 `da20ca225c9dc7a98a62819cc7d6fc9cb521c63f86db0b8a576ae2d32f1801e4` and still contains 897 episodic events, 897 semantic vectors, 897 typed semantic events, 24 current world states, and 50 world-state history entries.

## Performance profile

Fresh measurements from this recreated branch:

- 1-source, 1,000 trials: temporal path median `0.01040 s` vs non-temporal `0.00524 s` — **1.98x** overhead.
- 9-source, 1,000 trials: temporal path median `0.19980 s` vs non-temporal `0.02584 s` — **7.73x** overhead.
- 3,000 resolved 9-source temporal trials: `0.62744 s` (**4,781 trials/s**) in this environment.
- 10,000 current-dependency queries: O(1) path `0.01919 s`; a reference 192-item rescan `0.27782 s`, or **14.48x slower**. The rescan is a reference emulation of the rejected design, not the original interrupted implementation.

## Regression recertification

Fresh bounded unit batches on the recreated final core:

- v0.4/review/Procedure Cortex/alpha.7/alpha.7.1: **129/129 PASS**.
- v0.3: **77 executed = 76 PASS + 1 inherited intentional SKIP**.
- v0.1/v0.2: **156/156 PASS**.
- total: **362 executed = 361 PASS + 1 inherited intentional SKIP**.

Preserved cognition gates rerun:

- alpha.5 benchmark: 13/13 PASS.
- alpha.5 hard feed: 6/6 PASS.
- alpha.5.1 torture: 10/10 PASS.
- alpha.5 extreme torture: 9/9 PASS.
- alpha.6 torture: 12/12 PASS.
- alpha.6.1 current abrupt-drift gate: 30/30 recovered, mean 22.57 observations, mean tail accuracy 90.42%.
- alpha.6.1 stationary torture: 0 false splits / 100 runs.
- alpha.6.2 lineage torture: 10/10 PASS.
- alpha.7 benchmark: 7/7 PASS.
- alpha.7 torture: 9/9 PASS.
- alpha.7.1 benchmark: 8/8 PASS.
- alpha.7.1 torture: 9/9 PASS.

The exact historical `benchmark_v040a61.py` A/B runner was **not rerun** because it imports a sibling `ASM_v0.4.0-alpha.6` source tree that is not present in the supplied authoritative alpha.7 artifact. This is recorded as not rerun rather than counted as pass. The self-contained current alpha.6.1 drift gate and stationary torture were rerun instead.

One combined development stress command timed out and was **not counted**. All reported unit batches above completed independently. Inherited non-fatal `ResourceWarning` messages from some SQLite test paths were observed and are not hidden as benchmark failures.

## Known limitations / next bottleneck

- Temporal adaptation depends on explicit chronological indices; ASM does not infer chronology or trial segmentation.
- Only positive dependency reduces evidence mass; negative correlation is not exploited.
- Dependency remains pairwise correctness correlation rather than a general latent-cause model.
- Learned dependency is not yet used by the belief planner to simulate correlated future sensing sequences.
- Cross-source temporal training is materially more expensive than the non-temporal path even after O(1) query hardening.

This release does **not** claim AGI, general causal discovery, or numerical superiority to GPT-5.6 Sol or any frontier model. No cross-model numerical comparison is valid without the same standardized protocol.
