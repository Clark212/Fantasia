# ASM v0.4.0-alpha.7.9 — Adversarial Latent-Structure Hardening & Stage-Closure

ASM is an experimental persistent cognitive architecture focused on continual learning, explicit memory/belief state, bounded planning, executable procedures, epistemic calibration, and auditable self-model state. It is not a transformer/LLM architecture and external models do not become cognitive authority.

## Current release
Alpha.7.9 closes the Stage 7 epistemic/procedure-routing hardening cycle. The default `full_signed_latent` router preserves alpha.7.8 latent routing and adds conservative signed/component-wise hidden-dependency correction for sparse, anti-correlated, overlapping, and moving latent source groups.

Safety/epistemic invariant: the alpha.7.9 layer may **reduce** alpha.7.8 evidence weight but cannot create extra confidence. Invalid or weak structures fall back to the certified alpha.7.8 path.

## Verification summary
- 471 collected unit/regression tests: 470 PASS + 1 inherited intentional SKIP.
- Alpha.7.4 benchmark 11/11; torture 8/8.
- Alpha.7.5 contextual-routing benchmark clean with 100% two-context accuracy.
- Alpha.7.9: 0/20,000 approximate-null false activations, 0/12 real-independent false detections, 12/12 real signed-hidden-cause detections.
- Consciousness-related check 9/9 with verdict `no_subjective_consciousness_evidence`.
- Inherited alpha.5 mega-stress remains 13/14 on `topk_truncation_keeps_unknown_mass`.

## Milestone
**M3 — Adaptive Research AI.**

## Next stage
**v0.4.0-alpha.8 — Structural Transfer & Analogical Procedure Generalization**, targeting the first verified cross-task structural transfer toward M4.

See `RELEASE_NOTES_ALPHA7_9.md` and `REVIEW_ALPHA79.md` for the full claim boundary and evidence.
