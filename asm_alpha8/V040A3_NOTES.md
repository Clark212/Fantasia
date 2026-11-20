# v0.4.0-alpha.3 notes

## Milestone

Probabilistic Futures & Simulation Trust.

## Core additions

1. Bounded `conditional_outcome_support` table per local transition mechanism.
2. `predict_distribution_simulated()` with bounded top-k observed outcomes and residual unknown probability.
3. Neural fallback is explicitly `neural_uncalibrated`; it cannot silently claim its softmax confidence is a calibrated transition probability.
4. `ProbabilisticInternalPlanner` evaluates goal probability, hazard probability, residual unknown mass, action cost, and multi-step probability propagation.
5. `ASMEngine.plan_world_actions_probabilistic()` exposes the new planner while preserving the alpha.2 deterministic API.
6. Alpha.2 snapshot compatibility retained; alpha.3 conditional counts persist in mechanism blobs.

## Claim boundary

The planner is bounded and open-loop. It does not yet produce a contingent policy tree. Empirical transition frequencies are local to retained structured input signatures and should not be described as globally calibrated probabilities under distribution shift.
