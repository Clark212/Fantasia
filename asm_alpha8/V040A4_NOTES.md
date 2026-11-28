# ASM v0.4.0-alpha.4 — Active Information Gathering & Contingent Planning

Alpha.4 preserves alpha.3 stochastic probability/risk planning and adds bounded observation-conditioned policy trees.

## New capability
- AND/OR contingent search: different observed outcome branches may choose different future actions.
- Information is not hard-coded by action name; sensing is useful only when observation changes the best continuation.
- Explicit value-of-contingency reference against the preserved alpha.3 open-loop planner.
- Bounded horizon, predictor-call budget, top-k outcomes, unknown mass, hazard probability, and action/resource costs remain explicit.
- Nested contingent decisions are detected below shared intermediate actions.

## Claim boundary
This is controlled local planning over learned/explicit transition distributions. It is not broad reasoning, causal discovery, language-grounded goal generation, or AGI.
