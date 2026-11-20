# ASM v0.4.0-alpha.7.6 Experimental R2

## Status
Experimental research branch. Not an official release and not a novelty claim.

## Change from R1
R1 used one global dependency scale for every routing-evidence row. R2 attributes the dependency model's batch effective count with leave-one-out marginal effective support, then normalizes to the exact batch N_eff. This preserves full weight for independent sources while assigning the discount to members of a correlated cluster.

## Controlled result
For sources s1,s2 hidden-correlated and s3,s4 independent, R2 weights were approximately s1=.3333, s2=.3333, s3=1.0, s4=1.0 under near-perfect s1/s2 dependence; total effective support ~=2.6667.

Partial-correlation stress, 8 seeds each, 80 resolved dependency trials per seed:
- 0% shared: mean N_eff 4.0000; default-threshold full router 8/8 routed
- 25% shared: mean N_eff 3.9386; 8/8 routed
- 50% shared: mean N_eff 3.6874; 8/8 routed
- 75% shared: mean N_eff 3.1530; 8/8 routed
- 100% shared: mean N_eff 2.6667; 0/8 routed

The strict diagnostic min_support=4 intentionally exposed threshold brittleness for fractional support; it is not the normal ASM route threshold. Normal ROUTE_MIN_SUPPORT is 3.

## Regression
Focused procedure stack: 45/45 PASS (test_alpha75_parallel, v040a72, v040a73, v040a74).
Self-model regression phase gate: test_v0117 10/10 PASS.

## Consciousness-related phase interpretation
No new anomaly. R2 modifies routing-evidence weighting only. Existing computational self-model behavior remains functional; these tests provide no evidence of subjective experience.

## Remaining falsification work
False-positive learned dependencies, stale dependency after regime change, adversarial misleading correlated sources, randomized calibration/false-route tradeoffs, temporal dependency adaptation, full historical regression, performance, migration, and exact-package recertification remain outstanding.
