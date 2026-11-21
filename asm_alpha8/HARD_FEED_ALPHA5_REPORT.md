# ASM v0.4.0-alpha.5 Hard-Feed Review → alpha.5.1 Hardening

## Scope
This was an intentionally adversarial internal architecture feed for belief-state planning and partial observability. It is not a standardized AGI benchmark.

## Bugs found in alpha.5

### 1. Probability underflow permanently deleted hypotheses
Original alpha.5, after 200 observations favoring A at 99% reliability, represented B as zero and dropped it. After 200 equally strong observations favoring B, it incorrectly remained A=100% instead of returning to 50/50.

**alpha.5.1 fix:** `DiscreteBeliefState` now retains normalized log posterior weights internally. Public ordinary probabilities may underflow for display, but the hidden hypothesis is not deleted unless an exact zero likelihood logically eliminates it.

### 2. Malformed likelihood matrices were trusted
Original alpha.5 accepted a sensor where the returned observations summed to conditional likelihood 1.8 for the same hypothesis.

**alpha.5.1 fix:** explicit returned likelihood matrices now fail closed when any value is non-finite/out of [0,1], or when returned top-k outcomes sum to more than 1 for a hypothesis. Truncated top-k mass below 1 remains valid.

## BEFORE vs AFTER

| Probe | alpha.5 BEFORE | alpha.5.1 AFTER |
|---|---:|---:|
| 200×99%-A then 200×99%-B | stuck at A=100% | A≈50%, B≈50% |
| tiny prior B=1e-300 then strong B evidence | vulnerable to deletion | B recovers to MAP in 151 updates |
| malformed likelihood sum 1.8 | accepted; chose `sense` | rejected; invalid model counted and `sense` not selected |
| 1,000,000 sequential posterior updates vs log-space oracle | not hardened | max log error 1.137e-13 |
| 3→32-way extreme block recovery | not hardened | max uniform-return error 1.822e-13 |
| 100k belief memo keys | probability-space only | 0 material collisions >1e-12 in feed |

## Mega feed results

- Mega stress: **14/14 checks passed**.
- Extreme torture: **9/9 checks passed**.
- 50 independent 1,000-step posterior chains matched a log-space oracle.
- 200 skew-prior / varying-sensor cases remained stable.
- Anti-informative sensors at 49%, 40%, 25%, and 10% matched exact optimal Bayesian decisions.
- Known reliability drift/inversion matched exact enumeration in all tested schedules.
- Exact controlled planning scaled through 3, 5, 8, 16, and 32 hypotheses at short horizons.
- `top_k=4` on an 8-outcome sensor preserved 50% as explicit unknown mass rather than pretending omitted outcomes vanished.
- Neutral 50/50 sensing produced no fake probability gain.
- 33 hypotheses are rejected under the default max-32 bound.

## Search pressure
For an 8-hypothesis / 3-clue exact problem, the oracle goal probability was 85.7088%.

| Expansion budget | Returned goal probability |
|---:|---:|
| 128 | 7.056% |
| 256 | 8.280% |
| 512 | 18.3744% |
| 1024 | 40.1768% |
| 2048 | 85.7088% |

The result becomes exact once the search has enough budget. This is a bounded-search scaling limit, not a Bayesian arithmetic error.

## Important limitations that remain (not patched away)

### Wrong but internally valid likelihoods
If the planner is told the sensor is 90% reliable when the real sensor is 70%, it claims **99.144%** while the policy actually achieves **83.692%**.

### Correlated evidence treated as independent
With five perfectly correlated repeats from one 70% draw, the planner claims **83.692%** while actual success stays **70.000%**.

### Stale sensor model after regime flip
Assumed reliability 80%, real reliability 20%: planner claims **89.600%**, actual success **10.400%**.

These are architecture-level evidence that alpha.5 still depends on externally supplied, correct likelihood models. Fixing them requires learning/calibrating observation models and dependency structure, not just more numerical hardening.

### Astronomically rare branches
Beliefs remain recoverable in log space, but the planner intentionally prunes evidence branches with probability ≤1e-15. The torture feed exposed a branch with log probability about -919, which is preserved in the belief state but not exhaustively expanded by the planner.

## Compatibility
Executed unit tests after hardening:
- legacy: 72/72
- v0.2: 84/84
- v0.3: 77/77 (plus one inherited intentional skip)
- v0.4 including alpha.5.1: 55/55
- **Total: 288/288 executed tests passed**

Original alpha.1–alpha.5 planning benchmarks, alpha.4 stress, smoke, and trained-state counts remained green. Alpha.5 snapshot fallback → alpha.5.1 snapshot save/reload was verified with 897 episodic / 897 semantic vectors / 897 typed events / 24 current world states / 50 history entries preserved.

## Claim boundary
This demonstrates robust bounded discrete belief updating and contingent planning under supplied, valid likelihood models. It does **not** demonstrate automatic latent-hypothesis discovery, learned sensor calibration, dependency discovery, broad causal inference, AGI, or RSI.

## Next architecture trigger
The strongest next trigger is **learned/calibrated observation models**: ASM should estimate whether a sensor/evidence source is reliable, detect drift/correlation, and reduce trust when its predicted evidence statistics stop matching reality. That should be considered only after alpha.5.1 is accepted as the hardened belief-state baseline.
