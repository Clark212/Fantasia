# ASM v0.4.0-alpha.7.1 Benchmark Report

## Frozen dependency-regime benchmark

`benchmark_v040a71.py` — **8/8 PASS**.

### Correlated -> independent

The exact alpha.7 failure was reproduced first:

- BEFORE accuracy: `0.9021`
- BEFORE confidence: `0.7357873825`
- BEFORE calibration gap: `0.1663126175`

With the alpha.7.1 explicit-time path:

- AFTER accuracy: `0.9021`
- AFTER confidence: `0.9024422215`
- AFTER calibration gap: `0.0003422215`

The final recent view reports no active positive dependency while cumulative historical correlation remains `0.4972823655`, demonstrating that history was retained rather than overwritten.

### Independent -> correlated

Reproduced alpha.7 failure:

- BEFORE accuracy: `0.6997`
- BEFORE confidence: `0.9323836561`
- BEFORE calibration gap: `0.2326836561`

Alpha.7.1:

- AFTER accuracy: `0.6997`
- AFTER confidence: `0.7000000000`
- AFTER calibration gap: `0.0003000000`

### Detection speed

20/20 seeds detected both directions:

- correlated -> independent: mean `27.15` post-change observations
- independent -> correlated: mean `50.10` post-change observations

Full correlated -> independent -> correlated reversal: **20/20** runs retained exactly three regimes.

## Torture benchmark

`benchmark_v040a71_torture.py` — **9/9 PASS**.

Checks passed:

1. partial 25% <-> 75% dependency shifts detected in both directions, plus explicit 25% -> 50% -> 75% and 75% -> 50% -> 25% recent-view tracking for self and cross-source dependency
2. stationary within-source: 0 false regime splits / 100 runs
3. stationary cross-source: 0 false regime splits / 24 multi-source runs
4. 2/3/4/8/16/32 source extremes finite and behaviorally bounded
5. non-temporal shuffled data preserved alpha.7 order-invariant semantics and created 0 regimes
6. decreasing, NaN, boolean, and non-numeric temporal indices plus source/pair capacity failures were atomic/fail-closed
7. inference remained order-invariant and read-only
8. schema-1 migration created no fake temporal history
9. no NaN/inf in the stress surface

## Migration benchmark

`MIGRATION_ALPHA71.json` — PASS.

A real alpha.7 snapshot containing 300 dependency trials was reopened under alpha.7.1:

- trials: `300 -> 300`
- raw correlation: `1.0 -> 1.0` exactly
- temporal self views: `0`
- temporal pair views: `0`
- fabricated regimes: `0`

## O(1) performance profile

`benchmark_v040a71_performance.py` fresh run:

| Case | Non-temporal | Temporal | Overhead |
|---|---:|---:|---:|
| 1 source / 1,000 trials | 0.005244 s | 0.010398 s | 1.98x |
| 9 sources / 1,000 trials | 0.025840 s | 0.199804 s | 7.73x |

3,000 temporal 9-source trials completed in `0.627442 s` (`4,781.3 trials/s`).

For 10,000 current-view queries over a 192-item recent window:

- O(1) sufficient-statistics query: `0.019191 s`
- reference bounded-window rescan: `0.277816 s`
- reference rescan / O(1): `14.48x`

The reference rescan is a local emulation of the rejected algorithmic pattern, not a recovered copy of the interrupted WIP implementation.

## Preserved cognition gates

Fresh completed reruns on the recreated branch:

- alpha.5 benchmark: **13/13 PASS**
- alpha.5 hard feed: **6/6 PASS**
- alpha.5.1 torture: **10/10 PASS**
- alpha.5 extreme torture: **9/9 PASS**
- alpha.6 torture: **12/12 PASS**
- alpha.6.1 current drift: **30/30 recovered**, mean recovery `22.57`, mean tail accuracy `0.90417`
- alpha.6.1 stationary torture: **0 false splits / 100 stationary runs**
- alpha.6.2 torture: **10/10 PASS**
- alpha.7 benchmark: **7/7 PASS**
- alpha.7 torture: **9/9 PASS**

The exact old `benchmark_v040a61.py` A/B comparison was not rerun because it depends on a separate alpha.6 source tree not contained in the authoritative alpha.7 artifact. It is explicitly listed as **not rerun**, not silently counted.

## Unit regression

Final bounded batches before release documentation/package-only changes:

- v0.4/review/Procedure Cortex/alpha.7/alpha.7.1: `129/129 PASS`
- v0.3: `77 executed = 76 PASS + 1 inherited intentional SKIP`
- v0.1/v0.2: `156/156 PASS`
- total: `362 executed = 361 PASS + 1 inherited intentional SKIP`

A combined development stress command timed out and was not counted. Individual reported batches completed.

## Claim boundary

These benchmarks test synthetic evidence dependency, calibration, migration, regression, and runtime properties under the stated protocols. They do not establish AGI, general causal discovery, or superiority to GPT-5.6 Sol. A numerical model comparison would require the same standardized benchmark protocol on both systems.
