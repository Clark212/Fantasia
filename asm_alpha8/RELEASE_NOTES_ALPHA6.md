# ASM v0.4.0-alpha.6 — Release Notes

**Release capability:** Adaptive Evidence Reliability.

Alpha.6 is a genuine new capability stage after alpha.5.x hardening: ASM can learn how trustworthy a named evidence source is from resolved outcomes and feed that learned reliability back into belief-state inference/planning.

## Added

- `asm/adaptive_evidence.py` with bounded persistent Beta reliability models.
- Engine APIs: `observe_evidence_source`, `evidence_source_status`, `adaptive_evidence_likelihoods`, `update_belief_from_source`.
- `plan_world_actions_belief` supports `evidence_source_id` and `supplied_reliability`. Learned categorical sensor likelihoods may override a valid but wrong supplied sensor model; unrelated explicit action likelihoods are preserved.
- No self-training from ASM's own posterior. Calibration updates require externally resolved truth.
- Anti-informative sources below 50% reliability are supported rather than clamped to chance.
- Default 1024-source capacity bound.
- Snapshot key `asm_snapshot_v0_4_0_alpha_6` with alpha.5.2 fallback.
- New benchmark and torture feed.

## Main measured result

On stationary model mismatch, calibration improves sharply without changing the underlying decision evidence:

- true 70% / supplied 90% calibration gap: **8.38% → 0.95%**
- true 90% / supplied 70% calibration gap: **0.85% → 0.02%**
- true 20% adversarial / supplied 90% accuracy: **1.87% → 98.13%** after learning that the source should be inverted

## What alpha.6 intentionally does not solve

- abrupt reliability drift or source flips
- correlated/copied evidence
- hidden common-noise sources
- arbitrary confusion matrices / observation alphabets
- latent-cause discovery
- language generalization
- remaining long-stream scaling

See `BENCHMARK_ALPHA6_REPORT.md` and `BEFORE_AFTER_ALPHA6.json` for exact numbers and research boundaries.
