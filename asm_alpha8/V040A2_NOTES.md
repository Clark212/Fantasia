# v0.4.0-alpha.3 notes

Milestone: **Robust Branching Simulation & Search**.

Key implementation changes:
- `LocalRecurrentTransitionMechanism.predict_simulated()` — read-only prediction with branch-local recurrent hidden/trace context.
- `TransitionMechanismBank.predict_simulated()` — bank-level planning API.
- abstraction/consolidation query telemetry can be disabled for hypothetical inference.
- `StateGoal.distance()` / `proximity()` — generic search guidance without weakening exact goal satisfaction.
- planner global state+context dominance pruning.
- adaptive bounded beam widening on stall/uncertainty.
- state-diversity slots in narrow beams.
- bounded deferred-branch best-first rescue using only remaining expansions.
- explicit planner failure statuses/reasons.
- snapshot compatibility extended for v0.4 alpha.1/alpha.2.

New gates:
- `tests/test_v040a2.py`
- `benchmark_v040a2.py`
- `results/planning_v040a2_alpha1_ab.json`

Known next problems:
- stochastic/multi-outcome futures are represented only as the mechanism's selected prediction, not a probability tree.
- proximity is hand-generic, not learned from experience.
- plans do not yet model action costs/resources beyond step/risk penalties.
- natural-language goals remain intentionally ungrounded.
