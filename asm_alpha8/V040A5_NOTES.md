# ASM v0.4.0-alpha.5 — Belief-State Planning & Partial Observability

## Why this release exists

Alpha.4 could build observation-conditioned policy trees, but it had no compact internal state for hidden causes. In the partial-observability hard feed, a 70%-reliable clue helped once, then repeated clues stayed stuck at 70% unless the full observation history was supplied externally. Contradictory evidence was also overconfident, and the raw-history control grew to 765 expansions / 431 policy nodes at seven clues.

Alpha.5 adds a bounded discrete latent belief state to the planner. It is a sufficient statistic over hidden hypotheses, not a raw observation transcript.

## Architecture changes

- `DiscreteBeliefState`
  - normalized bounded distribution over latent hypotheses
  - immutable branch-local state
  - Bayesian evidence update
  - entropy and stable memoization key
- `BeliefStateInternalPlanner`
  - carries posterior belief through simulated branches
  - computes observation probability from `P(observation | hypothesis)` when available
  - fuses repeated evidence
  - corrects contradictory evidence
  - supports outcome-specific simulation context per sibling branch
  - memoizes equivalent `(visible state, posterior, branch context, depth)` states
  - emits a compact policy DAG using node references instead of duplicating raw-history subtrees
- `ASMEngine.plan_world_actions_belief(...)`
  - read-only planning API
  - accepts an initial latent belief and optional likelihood provider
- new alpha.5 snapshot key with explicit alpha.4 fallback

Normal alpha.1-alpha.4 planners and transition learning behavior are preserved.

## BEFORE vs AFTER

| Controlled task | Alpha.4 | Alpha.5 |
|---|---:|---:|
| 1 noisy 70% clue | 70.000% | 70.000% |
| 3 clues | 70.000% last-observation compression | 78.400% |
| 5 clues | 70.000% last-observation compression | 83.692% |
| 7 clues | 70.000% last-observation compression | 87.3964% |
| A then B contradictory clues | acted like latest clue = 70% | posterior returns to 50/50 |
| 7-clue full-history control | 765 expansions / 431 policy nodes | 108 expansions / 77 graph nodes |

The 78.4%, 83.692%, and 87.3964% figures are the expected accuracy of the optimal decision policy after 3, 5, and 7 independent 70%-reliable binary clues. They are not posterior confidence for one fixed clue sequence.

## Hard feed

- 80 randomized binary-sensor cases matched the closed-form Bayesian target with maximum absolute error `3.33e-16`.
- All 80 exercised belief-state merging and stayed inside the 256-expansion bound.
- 200 randomized posterior-update sequences matched direct Bayes.
- A 3-hypothesis / 3-clue world matched exact enumeration: `81.55%` expected correct decision, absolute error `1.11e-16`.
- Outcome-specific branch-context probe reached 100% with branch-specific actions.

## Compatibility evidence

Split unit runs after the final alpha.5 code changes:

- legacy-a: 37/37
- legacy-b: 35/35
- v0.2-a: 29/29
- v0.2-b: 55/55
- v0.3-a: 37/37 (one intentional skip in the inherited suite)
- v0.3-b: 40/40
- v0.4 alpha.1-alpha.5: 49/49

Total executed unit tests: **282/282**, with one inherited intentional skip.

Additional checks:

- alpha.1 preservation benchmark: PASS
- alpha.2 benchmark: PASS
- alpha.3 benchmark: PASS
- alpha.4 benchmark: PASS
- alpha.4 randomized stress: 300/300 contingent cases + 200/200 useless-sensing controls PASS
- alpha.5 benchmark: 13/13 PASS
- alpha.5 stress: 6/6 PASS
- smoke test: PASS
- world-state benchmark: 19/19; 10,000-update scaling probe and 200/200 filtered queries PASS
- trained DB migration: 897 episodic / 897 semantic vectors / 897 typed semantic events preserved; world state 24 current / 50 history preserved

## Claim boundary

This release demonstrates **controlled bounded planning with an explicitly supplied discrete latent hypothesis space and observation likelihoods**. It does not demonstrate automatic discovery of hidden variables, broad Bayesian reasoning, general causal inference, AGI, RSI, or human-like understanding.

The very heavy inherited alpha.8-alpha.10 long-stream suites were not rerun to completion after the final alpha.5 patch in this environment. Use `python run_release_checks.py --full` on a machine where those long gates can finish before making a fresh full-stack certification claim.
