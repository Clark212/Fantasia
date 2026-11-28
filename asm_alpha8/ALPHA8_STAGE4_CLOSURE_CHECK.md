# The 0.4.9 closure check: do the Stage 4 components work together? (main roadmap, 2026-11-28)

**Gate G49 passed** on 30 held-out worlds. Nothing is promoted: whether this check, with the frozen baseline's
reproduction (`benchmarks/results/mainroute/BASELINE_REPRODUCTION.md`), supports promoting 0.4.9 is the project owner's
decision. M4 (alpha 8's structural-transfer target) is a separate question this check does not address.

## Objective
`ROADMAP.md`, Stage 4: "Open before 0.4.9 can be promoted: a pre-registered check that the Stage 4 components work
together." The owner chose an integrated battery (2026-11-28). In it, one agent:
- learns world transitions, evidence-source reliability and source redundancy from experience;
- plans with the belief-state planner, gathering information when that pays;
- is compared with ablations that each remove one component, and with an oracle.

## Design (pre-registered: `benchmarks/preregistration/stage4_closure_study.md`, commit 2949c37)
- **Battery:** `benchmarks/stage4_closure.py`; analysis: `benchmarks/stage4_closure_analyze.py`.
- **A world:**
  - a hidden cause decides which of two doors leads to the goal; the other leads to a hazard;
  - 4-8 evidence sources, a third of them anti-informative, up to half copying another source;
  - a costly probe sensor with reliability 0.70-0.90.
- **Per world:**
  - 300 resolved training episodes;
  - 100 test episodes, the same for every arm;
  - the planner's default thresholds: goal ≥ 0.70, hazard ≤ 0.10, unknown ≤ 0.25.
- **Score of an episode:** goal +1, hazard −2 (the planner's default risk aversion), declining 0, minus the probe costs.
- **The Stage 4 components exercised:**

  | stages | component | API |
  |---|---|---|
  | 0.4.0-0.4.1 | learned transitions, simulated | `learn_world_transition`, `predict_distribution_simulated` |
  | 0.4.2-0.4.5 | contingent, probabilistic, information-gathering belief-state planning | `plan_world_actions_belief` |
  | 0.4.6 | evidence reliability | `observe_evidence_source`, `adaptive_evidence_likelihoods` |
  | 0.4.7-0.4.8 | evidence dependency and batch routing | `observe_evidence_dependency_trial`, `update_belief_from_evidence_batch` |

## Results: held-out worlds (seeds 1000-1029, generated after the pre-registration)
Raw records: `benchmarks/results/stage4_closure/heldout/` (with `environment.txt` and `analysis.json`).

| arm | goal | hazard | declined | probes per episode | score | worst world's hazard |
|---|---|---|---|---|---|---|
| **full** | .839 | **.028** | .133 | .41 | **.761** | .09 |
| no_reliability | .657 | .108 | .235 | .88 | .393 | .32 |
| no_dependency | .856 | .048 | .095 | .28 | .744 | .20 |
| no_probe | .645 | .019 | .336 | 0 | .608 | .07 |
| no_planning | .879 | .121 | 0 | 0 | .636 | .39 |
| oracle | .885 | .026 | .089 | .41 | .812 | .10 |

Paired over the 30 worlds (95% bootstrap interval):

| removed | full − arm, score | arm − full, hazard rate | contributes through |
|---|---|---|---|
| reliability learning | +.368 [.270, .476] (29 worlds better, 0 worse) | +.079 [.047, .115] | reward and safety |
| dependency learning | +.016 [−.011, .049] (11 / 13) | +.020 [.010, .032] (17 safer, 0 less safe) | safety |
| probing | +.153 [.081, .240] (23 / 3) | −.010 [−.015, −.005] | reward (without it, the agent declines) |
| planning | +.125 [.066, .190] (24 / 5) | +.093 [.068, .122] (29 safer, 0 less safe) | reward and safety |
| (oracle) | −.051 [−.091, −.008] (6 / 24) | −.002 [−.012, .009] | — |

### Gate G49: every criterion holds
- **G49-A1:** full's score is ≥ 0.80 of the oracle's: .761 vs .812, **0.937**.
- **G49-A2:** full's mean hazard rate is ≤ .05 (**.028**), and no world exceeds .15 (worst **.09**).
- **G49-B, each component contributes:**
  - removing it costs reward or safety (one of the two intervals lies above 0);
  - removing it does not significantly raise the score (the upper end of the score interval is ≥ 0);
  - this holds for all four: reliability, dependency, probing and planning.

## What the results show, and what they do not
- **The components work together.** The full agent learns everything it uses from 300 episodes, and its hazard rate
  (.028) is the oracle's (.026; the paired difference's interval contains 0).
- **Each component has a measurable role:**
  - Reliability learning matters most. Without it, anti-informative sources are trusted, and the hazard rate quadruples.
  - Dependency learning buys safety, not reward. Without it, copies are double-counted and beliefs become
    overconfident, so that arm acts more often: slightly more goals, 1.7 times the hazards, and a worst world of .20.
  - Probing turns uncertain episodes into goals instead of declines.
  - Planning avoids the hazards that acting on the most likely door incurs.
- **Learning still costs something.** The full agent scores .051 below the oracle and is worse in 24 of 30 worlds. It
  mostly declines more (.133 vs .089), because its learned likelihoods are less certain than the true ones.
- **Development vs held-out.** Worlds 0-29, seen before the pre-registration, gave the same ordering: full .673, oracle
  .763 (0.88), and full's hazard rate .027. Dependency again contributed through safety only.

## Limitations
- **A lab battery.** One world family, designed knowing the components it tests. The held-out worlds are new parameter
  draws, not new structures. A pass shows the components work together here, not on real data or on other worlds.
- **The oracle is not an upper bound on reward.** It uses the same planner and thresholds, and the planner's state
  predictions still come from the learned pooled transition model. Its true likelihoods and exact prior make the
  branch probabilities exact, but the model's small unknown-outcome residual remains in both arms.
- **The thresholds were set from the development run**, with margin for 30 worlds of 100 episodes. With one
  pre-registered run, the result has no replication.
- **What changed during development,** before the pre-registration and only in the harness:
  - one thread per process (parallel PyTorch processes stalled a first run, which produced no world);
  - per-episode seeds, so that the arms' test episodes are paired.

## Verification
- **Runs:** development (worlds 0-29, four shards) and held-out (worlds 1000-1029, four shards). Both used the
  committed harness (commit 2949c37, harness SHA-256 `5a55ca67…`). Analysis: `stage4_closure_analyze.py`. The gate
  was recomputed from `analysis.json` in code.
- **No ASM code changed** in this check. The test state is the main route's: 470 passed and 1 skipped with PyTorch, and
  the refreshed release gate passes 56 of 56.

## Next
- **The owner's decision:** whether 0.4.9 is promoted. What the decision rests on:
  - the baseline reproduces;
  - the release gate is refreshed and passes;
  - G49 passed in this lab battery;
  - M4 is not met.
- **Then:** the roadmap's remaining Stage 4 / alpha 8 work, or, if 0.4.9 is promoted, the start of Stage 5 as the
  roadmap defines it.
