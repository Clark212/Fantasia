# ASM v0.4.0-alpha.7.6 — Dependency-Aware Contextual Procedure Routing

Official consolidation release for the verified alpha.7.5 contextual routing work and alpha.7.6 R4 epistemic hardening.

Key additions over alpha.7.4 include contextual procedure applicability, bounded sequential information gathering, reliability-aware routing, hidden-dependency-adjusted support, temporal dependency recovery, routing-only Benjamini-Hochberg FDR control, and covariance-linear local redundancy weighting.

This release introduces snapshot key `asm_snapshot_v0_4_0_alpha_7_6` with explicit alpha.7.4 fallback. Migration is additive and does not fabricate procedure-route observations.

Known inherited issues remain documented: the alpha.5 mega-stress `topk_truncation_keeps_unknown_mass` failure and SQLite ResourceWarnings in the historical v0.4 suite.
