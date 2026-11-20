# ASM v0.4.0-alpha.7 Benchmark Report

## Primary benchmark

`benchmark_v040a7.py` — **7/7 PASS**.

Training: 500 externally resolved trials. Evaluation: 10,000 trials per main condition. Nine 70%-reliable clues per evaluation episode.

### Hidden repeated-source correlation

- BEFORE: accuracy `0.6933`, confidence `0.9995124747`, calibration gap `0.3062124747`.
- AFTER: accuracy `0.6933`, confidence `0.7000000000`, calibration gap `0.0067000000`.
- learned raw correlation: `1.0`; active bounded correlation: `0.999999999999`.

### Hidden cross-source common noise

- BEFORE: accuracy `0.6988`, confidence `0.9995124747`, calibration gap `0.3007124747`.
- AFTER: accuracy `0.6988`, confidence `0.7000000000`, calibration gap `0.0012000000`.

### Independent controls

- repeated-source independent control: BEFORE and AFTER both accuracy `0.9024`, confidence `0.9033048979`.
- cross-source independent control: BEFORE and AFTER both accuracy `0.9009`, confidence `0.9014993388`.

### Detection / false positives

- full-copy dependency became active at 64 resolved trials, matching the configured minimum.
- independent stress: 320 within-source tests + 1,120 cross-source pair tests, **0 active false dependencies**.

## Torture benchmark

`benchmark_v040a7_torture.py` — **9/9 PASS**.

- partial 25% shared-noise mixture: calibration gap `0.0727624 -> 0.0298751`, accuracy unchanged at `0.8543333`.
- partial 50% mixture: `0.1509541 -> 0.0367150`, accuracy unchanged at `0.7986667`.
- partial 75% mixture: `0.2280862 -> 0.0102088`, accuracy unchanged at `0.7465833`.
- 32 perfectly dependent sources: effective evidence count `1.00000000000193`.
- 32 independent sources: effective evidence count exactly `32.0`.
- 1,000 evidence-order permutations: maximum probability difference `1.11e-16`; no decision change.
- independent false-positive torture: 400 self-dependency tests + 3,000 cross-source pair tests, **0 false dependencies**.
- malformed schema, source capacity and trial capacity fail closed.

## Negative result: dependency drift

`probe_v040a7_dependency_drift.py` intentionally remains failing evidence rather than a release gate.

- correlated -> independent: current-tail accuracy `0.9021`, confidence `0.7358`, calibration gap `0.1663`.
- independent -> correlated: current-tail accuracy `0.6997`, confidence `0.9324`, calibration gap `0.2327`.

Interpretation: alpha.7 learns cumulative dependency. It does not yet split dependency regimes when correlation structure changes.

## Preserved benchmarks

Fresh final-tree reruns:

- `benchmark_v040a5.py`: 13/13 PASS.
- `benchmark_v040a5_stress.py`: 6/6 PASS; 80/80 random binary cases match closed-form; 200/200 random posterior sequences match direct Bayes.
- `benchmark_v040a51_torture.py`: 10/10 PASS.
- `benchmark_v040a5_extreme_torture.py`: 9/9 PASS.
- `benchmark_v040a6_torture.py`: 12/12 PASS, including 1,000,000 source updates.
- `benchmark_v040a61.py`: abrupt 90%->10% 30/30 recovery, mean recovery 22.57 observations, tail accuracy 90.42%; stationary-70 false split seeds 0/50.
- `benchmark_v040a61_stationary_torture.py`: 0 false splits across 100 stationary runs covering true reliability 10/30/50/70/90%.
- `benchmark_v040a62.py`: supplied-lineage 9-copy confidence remains 70% at 69.895% accuracy; 1,000 independent equivalence sequences exact.
- `benchmark_v040a62_torture.py`: 10/10 PASS.
- `smoke_test.py`: PASS.

## Claim boundary

These are controlled synthetic evidence-fusion experiments. They establish that this implementation can learn useful pairwise/within-source redundancy under the tested resolved-trial protocol. They do not establish general causal discovery, automatic latent-variable discovery, broad intelligence, AGI, or superiority to frontier foundation models.
