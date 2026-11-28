# ASM v0.4.0-alpha.6.2 Benchmark Report

## New lineage benchmark
`benchmark_v040a62.py`, deterministic seed, 20,000 trials per main condition.

- Shared clue repeated 9x, BEFORE: accuracy 0.69895, confidence 0.9995124747, calibration gap 0.3005624747.
- Shared clue repeated 9x, AFTER with explicit lineage: accuracy 0.69895, confidence 0.7000000000, calibration gap 0.00105.
- Nine independent clues: BEFORE and AFTER identical: accuracy 0.8977, confidence 0.9006742015, calibration gap 0.0029742015.
- 1,000 randomized 20-observation independent sequences: max probability error `0.0`; 1000/1000 decision ranks identical.
- Three independent roots repeated 3x each: BEFORE confidence 0.9536364349 vs AFTER 0.7833416216 at identical 0.7847 accuracy.

## New torture
`benchmark_v040a62_torture.py`: **10/10 PASS**.

Included:
- 10,000-deep copy chain remains exactly one effective 70% clue.
- 1,000 randomized 32-update independent sequences exactly match ordinary Bayes.
- 32-hypothesis duplicate evidence stays finite and does not inflate confidence.
- 1,000 partial-overlap updates remain finite.
- graph, item-root, and per-belief capacity fail closed.
- malformed/missing/cyclic ancestry snapshots fail closed.
- 100 independent roots each copied 10x exactly equal 100 independent Bayesian updates.

## Preserved gates freshly rerun
- alpha.5 benchmark: **13/13 PASS**.
- alpha.5 hard feed: **6/6 PASS**.
- alpha.5 extreme resurrection torture: **9/9 PASS**.
- alpha.6 torture: **12/12 PASS**.
- alpha.6.1 abrupt drift: 30/30 recovered; mean below-0.5 recovery 22.57 observations; tail accuracy 90.42%.
- alpha.6.1 stationary torture: **0 false splits / 100 stationary runs**.
- v0.4 unit surface: **94/94 PASS**.
- complete unit modules run in three bounded batches: **338 executed = 337 PASS + 1 inherited intentional SKIP**.
- smoke test: PASS.

A monolithic `unittest discover` command exceeded the environment timeout. The same test modules were therefore run in three completed batches; no unfinished monolithic run is counted as a pass.

## Migration
An alpha.6.1 snapshot with 100 resolved temporal source observations migrated with identical cumulative/effective reliability and one regime. Alpha.6.2 correctly initialized an empty lineage graph. The historical trained DB still loads with 897 episodic events, 897 semantic vectors, 897 semantic-event records, 24 current world states, and 50 world-state history entries.

## Important negative result
The existing alpha.6 `correlated70_model70` benchmark still shows ~99.95% confidence at ~71% accuracy when **no provenance is supplied**. Alpha.6.2 does not pretend to discover hidden dependencies. That remaining failure is evidence for a later dependency-learning capability.
