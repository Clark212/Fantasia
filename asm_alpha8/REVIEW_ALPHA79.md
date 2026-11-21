# ASM alpha.7.9 Dedicated Review / Stage-Closure Decision

## Review verdict
**PASS — freeze alpha.7.9 as the official Stage 7 closure release.**

Alpha.7.9 closes the major failure modes identified during alpha.7.6–alpha.7.8: multiple-testing artifacts, moderate covariance miscalibration, oversized covariance components, weak hidden common causes, signed/anti-correlated common causes, sparse hidden subgroups, overlapping factors, passenger leakage, and temporal migration of latent groups.

## Architecture review
The alpha.7.9 signed latent layer remains subordinate to ASM evidence authority. It sees read-only dependency diagnostics and cannot create route evidence or modify route history. Its output is monotone against alpha.7.8: each source keeps at most its alpha.7.8 weight. Any ambiguous or invalid structure falls back rather than being forced through.

The signed path first identifies bounded correlation components, recovers a balanced polarity assignment, requires coherent collective evidence, optionally removes weak bridge/passenger nodes one at a time, fits a bounded rank<=2 gauged latent factor model, and discounts only materially loaded sources. Dependency-version changes invalidate cached results.

## Regression review
Official worktree regression:
- **471 tests collected**.
- **470 passed**.
- **1 inherited intentional skip**.
- **0 new failures**.

Historical gates remain intact:
- alpha.7.4 benchmark: 11/11.
- alpha.7.4 torture: 8/8.
- alpha.7.5 contextual routing: all checks pass, 100% two-context accuracy, no random-noise false route.
- inherited alpha.5 mega-stress: 13/14 with the same `topk_truncation_keeps_unknown_mass` limitation.

## Adversarial / calibration review
- 20,000 approximate independent null correlation fields: 0 false signed-latent support reductions.
- 12 real learned independent-source runs: 0 false detections.
- 12 real learned signed hidden-cause runs: 12 detections.
- Mean signed-run support: ~7.718 under alpha.7.8 -> ~3.976 under alpha.7.9.
- 20-source overlapping two-factor support: 20.0 -> ~7.472.
- Moving latent groups are reversible: old members recover to weight 1.0; newly dependent members are discounted.
- Frustrated signed graphs fail closed to alpha.7.8.

These results justify release, but they do not prove universal calibration outside the tested families.

## Performance review
Warm cached support weighting remained close in the controlled 20-source test: ~0.191 ms for alpha.7.8 versus ~0.198 ms for alpha.7.9. The more expensive signed/factor work is version/source-signature cached.

## Consciousness-related review
9/9 checks pass. Verdict: `no_subjective_consciousness_evidence`. No anomaly requires isolation. ASM continues to show bounded computational self-model and metacognitive state only.

## Breakthrough / milestone review
**No verified scientific breakthrough claim.** The implementation combines established ideas from covariance correction, factor models, multiple-testing control, and signed-graph balance into a bounded ASM routing mechanism. The controlled results are strong engineering evidence, not proof of a new scientific principle.

Milestone remains **M3 — Adaptive Research AI**. Stage 7 hardened epistemic decision-making but did not establish broad transfer to unfamiliar problem families.

## Stage-closure decision
**Close Stage 7. Do not create alpha.7.10.**

The next work is a genuinely new capability category: learning structural abstractions from one task family and reusing/adapting them in another without a hand-designed task-specific router.

**Next version: v0.4.0-alpha.8 — Structural Transfer & Analogical Procedure Generalization.**

Alpha.8 is the first stage aimed directly at the M4 requirement: verified cross-task structural transfer/generalization.
