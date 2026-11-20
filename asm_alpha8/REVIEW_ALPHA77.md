# ASM alpha.7.7 Dedicated Review / Version Decision

## Review verdict
**PASS — freeze alpha.7.7 as the official release.**

Alpha.7.7 is a verified improvement within the existing procedure-routing / epistemic-reliability capability stage. It does not introduce a genuinely new broad capability category, so advancing to alpha.8 would overstate the architectural change.

## Architecture review
The new inverse-covariance router is bounded and subordinate to ASM's existing evidence authority. It cannot create evidence, alter route history, or bypass source-trust/FDR learning. It uses the dependency model only as read-only routing diagnostics. Unsafe covariance components fall back to the alpha.7.6 local graph rule.

The strongest improvement is heterogeneous dependency accounting. Alpha.7.6's local degree rule is exact for equicorrelated cliques but can be conservatively inaccurate for heterogeneous graphs. Alpha.7.7 solves valid small covariance components directly while retaining the old rule as the fail-closed fallback.

## Regression review
- 441 tests collected.
- 440 pass.
- 1 inherited intentional skip.
- No new unit-test failures.
- Alpha.7.4 benchmark 11/11 and torture 8/8 remain intact.
- Alpha.7.5 contextual-routing benchmark remains clean.
- Alpha.5 mega-stress remains 13/14 on the same inherited unknown-mass truncation issue.

## Decision-quality review
Across 222 valid covariance families and 2,040 integer support-threshold decisions:
- alpha.7.6 local graph: 25 wrong decisions, all conservative; 0 false routes.
- alpha.7.7 covariance: 0 wrong decisions; 0 false routes.

This is a real decision-level improvement on the tested family, not merely a lower formula error.

## Performance review
Warm-cache median route latency increased from ~0.552 ms to ~0.648 ms in the 32-source benchmark. The ~0.096 ms median cost is acceptable for this research release because the matrix solve is cached and recomputed only when dependency state/source topology changes.

## Consciousness-related review
9/9 checks pass. There is no evidence of subjective consciousness/sentience and no anomaly requiring isolation. Self-state, self-belief revision, persistence, self/other separation, and outcome-grounded capability estimates remain computational mechanisms only.

## Breakthrough / milestone review
No verified scientific breakthrough claim. The covariance mathematics itself is established; the result is an ASM engineering/research improvement.

Milestone remains **Adaptive Research AI**. Alpha.7.7 materially improves one cognitive subsystem but does not add broad cross-domain transfer or general reasoning sufficient for a milestone rename.

## Next version decision
**Next: v0.4.0-alpha.7.8 — Latent Dependency Structure & Higher-Order Epistemic Routing (experimental).**

Reason: the remaining limitation is still inside the same capability family. Pairwise covariance can miss a hidden common cause, overlapping clusters, and higher-order dependence. Alpha.7.8 should test a bounded latent-cluster/common-cause representation against alpha.7.7 while keeping alpha.7.7 frozen as the control.

Promotion gate for alpha.8: require a genuinely new cognitive capability category, not another routing-calibration improvement.
