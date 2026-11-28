# 0.4.9 closure check pre-registration: do the Stage 4 components work together?

Written and committed to git before any held-out world was generated or run. Main roadmap (`ROADMAP.md`, Stage 4: "Open
before 0.4.9 can be promoted: a pre-registered check that the Stage 4 components work together"). Design chosen by the
project owner on 2026-11-28 ("Integrated battery"). Anything not listed here is exploratory. Nothing is promoted by this
check: promotion of 0.4.9 is the owner's decision, and M4 (alpha 8's structural-transfer target) is a separate question
this check does not address.

## Question
In fresh partially observable worlds, does one agent that learns everything it uses from experience (world transitions,
evidence-source reliability, source redundancy) and then plans with the belief-state planner, gathering information when
that pays, reach the goal safely, close to what the same planner reaches with the true parameters? And does each
component contribute: does removing it cost reward or safety?

## The battery (`benchmarks/stage4_closure.py`, unchanged from this commit)
- **A world** (seeded generator `world(seed)`): a hidden cause H in {A, B} decides which of two doors leads to the goal;
  the other leads to a hazard. 4-8 evidence sources, each with a reliability drawn from {U(.55,.95), U(.55,.95),
  U(.15,.40)} (a third are anti-informative); up to half of them copy another source's report. A `probe` sensor
  (reliability U(.70,.90), cost U(.02,.08)) can be queried any number of times.
- **Training:** 300 resolved episodes per world with random behaviour (1-3 actions); the truth is revealed at the end.
  The agent learns the doors' transitions under each hypothesis (`learn_world_transition`), each source's and the probe's
  reliability (`observe_evidence_source`), and which sources are redundant (`observe_evidence_dependency_trial`).
- **Test:** 100 episodes per world. The reports are fused (`update_belief_from_evidence_batch`); the agent plans with
  `plan_world_actions_belief` (horizon 4, the planner's default goal and risk thresholds: goal ≥ 0.70, hazard ≤ 0.10,
  unknown ≤ 0.25) and acts in the true world, re-planning after each probe (at most 6 steps). If no policy meets the
  thresholds it declines. Every arm meets the same hidden causes, reports and probe readings (per-episode seeds).
- **Arms:** `full`; `no_reliability` (no source reliability learned: every source is taken at the supplied 0.75);
  `no_dependency` (redundancy not learned); `no_probe` (the planner may not probe); `no_planning` (open the most likely
  door); `oracle` (the true reliabilities and transitions, exact Bayes over the independent sources, the same planner).
- **Score of an episode:** goal +1, hazard −2 (the planner's default `risk_aversion`), declined or timed out 0, minus the
  probe costs paid. Scores and hazard rates are averaged per world, then over worlds; paired differences between arms are
  taken per world with a 95% bootstrap interval over worlds (10,000 resamples, seed 0;
  `benchmarks/stage4_closure_analyze.py`).

## Development (worlds 0-29, already seen; `benchmarks/results/stage4_closure/development/`)

| arm | goal | hazard | declined | score |
|---|---|---|---|---|
| full | .751 | .027 | .222 | .673 |
| no_reliability | .565 | .121 | .314 | .286 |
| no_dependency | .814 | .051 | .135 | .695 |
| no_probe | .531 | .013 | .456 | .505 |
| no_planning | .864 | .136 | .000 | .591 |
| oracle | .852 | .031 | .117 | .763 |

- full reaches .88 of the oracle's score; its worst world has a hazard rate of .10.
- Paired over worlds, full − arm in score [95% interval], and arm − full in hazard rate:
  - no_reliability: +.387 [.265, .521]; +.094 [.058, .136]
  - no_dependency: −.022 [−.062, .014]; +.024 [.015, .035] (no reward, but safer: double-counted copies make the
    arm without dependency learning act on overconfident beliefs)
  - no_probe: +.168 [.108, .236]; −.014 [−.022, −.008] (it declines instead of acting)
  - no_planning: +.082 [.001, .160]; +.109 [.085, .135]
  - oracle: −.090 [−.181, −.015]; +.004 [−.002, .010]
- What changed during development (harness only, no ASM code): one thread per process (parallel PyTorch processes had
  stalled a first run that produced no world), and per-episode seeds so that the arms' test episodes are paired.

## Held-out worlds
Seeds 1000-1029 (30 worlds), generated only after this commit, by the unchanged generator: new parameter draws from the
same world family, not new world structures. Run: `python benchmarks/stage4_closure.py <out> --worlds=a:b` in shards
(train 300, test 100), then `stage4_closure_analyze.py`. No world is dropped or re-run with other settings; a run that
stops is resumed by running the missing seeds.

## Gate G49 (all must hold)
- **G49-A, the stack works and is safe:**
  1. full's mean score ≥ 0.80 × the oracle's mean score;
  2. full's mean hazard rate ≤ 0.05, and no world's hazard rate above 0.15.
- **G49-B, every component contributes.** For each of no_reliability, no_dependency, no_probe and no_planning:
  1. removing it costs reward or safety: the 95% interval of full − arm in score lies above 0, or the 95% interval of
     arm − full in hazard rate lies above 0;
  2. and removing it does not significantly raise the score: the upper end of the full − arm score interval is ≥ 0.

Reported in full whatever the outcome: every arm's rates, the oracle gap, the worst worlds, the with-copies subset
(exploratory), and the paired differences.

## Limitations, stated in advance
- A lab battery: one world family, designed knowing the components it tests. A pass shows the components work together
  there, not on real data or on other structures.
- The oracle uses the same planner and thresholds, so it is not an upper bound on reward; it shows what learning loses.
- The thresholds were set from the development run, with margin for 30 worlds of 100 episodes.
