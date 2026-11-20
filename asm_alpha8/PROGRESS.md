# ASM Progress

## Current experimental release: v0.4.0-alpha.7.4

Capability stage: **Planning, Belief-State Reasoning, Adaptive Evidence & Bounded Procedure Learning**

Completed progression in v0.4:

- alpha.1 — bounded internal rollouts
- alpha.2 — robust branching simulation/search and branch-local context
- alpha.3 — probabilistic futures, explicit unknown mass, tail-risk propagation
- alpha.4 — active information gathering and contingent policy trees
- alpha.5 — compact belief-state planning under partial observability
- alpha.5.1 — log-space belief hardening and fail-closed likelihood contracts
- alpha.5.2 — indexed cognition/performance hardening and language proposal firewall
- alpha.6 — online evidence-source reliability learning from externally resolved truth
- alpha.6.1 — bounded temporal calibration and versioned source regimes
- alpha.6.2 — explicit evidence lineage and dependency-aware fusion for known copies/derivations
- alpha.7 — learned hidden positive evidence dependency with symmetric batch fusion
- alpha.7.1 — explicit-time dependency adaptation, bounded recent view, and preserved dependency regimes
- alpha.7.2 — autonomous unary procedure induction, held-out validation, revision, and reversal revalidation
- alpha.7.3 — bounded 2–4 input integer procedure induction with affine solving and shallow compositional structure reuse
- alpha.7.4 — bounded Boolean/conditional induction with ambiguity abstention and read-only disagreement-driven information queries

### Current result

Alpha.7.4 keeps alpha.7.1 as the evidence/dependency authority and extends alpha.7.3 with typed Boolean/conditional procedure induction plus read-only information queries. The exact alpha.7.3 baseline lacks these capabilities. Alpha.7.4's BEFORE/AFTER suite is **11/11 PASS**, torture is **8/8 PASS**, migration is **9/9 PASS**, and full unit recertification is **404 executed = 403 PASS + 1 inherited intentional SKIP**.

The query layer can ask which unobserved input best separates competing bounded hypotheses, but cannot invent the answer, mutate evidence, or train from simulation.

### Experimental next-stage research

The next procedure bottlenecks are contextual procedure routing, deeper hierarchical composition without search explosion, and persistent multi-step information-gathering policies rather than single-query selection. Evidence research still includes negative-correlation exploitation and richer latent/common-cause structure. The inherited alpha.5 top-k unknown-mass stress failure remains open and preserved.

## v0.4.0-alpha.7.9 — Adversarial Latent-Structure Hardening & Stage-Closure
- Added monotone component-wise signed latent redundancy correction above alpha.7.8.
- Verified sparse subgroup, anti-correlated hidden-factor, overlapping two-factor, migration/recovery, frustrated fallback, and null-calibration behavior.
- Full split regression: 471 collected = 470 PASS + 1 inherited intentional SKIP.
- Stage 7 review: PASS / close stage. Next capability stage: alpha.8 structural transfer and analogical procedure generalization.
