# ASM v0.4.0-alpha.6.1 Benchmark Report

## Alpha.6 -> alpha.6.1 non-stationary source benchmark

The benchmark uses the actual alpha.6 `AdaptiveEvidenceModel` and alpha.6.1 on identical generated streams.

### Abrupt 90% -> 10% reliability flip (30 seeds)

| Metric | alpha.6 | alpha.6.1 |
|---|---:|---:|
| Final inferred reliability | 49.90% | 14.80% |
| Last-200 decision accuracy | 13.60% | 90.42% |
| Last-200 calibration gap | 44.49% | 4.41% |
| Recovery below 50% trust | did not reliably recover | 22.57 observations mean |
| Mean explicit regimes | 1 cumulative model | 2.0 |

All 30/30 alpha.6.1 seeds crossed below 50% inferred reliability after the flip.

### Gradual 90% -> 55% drift (30 seeds)

| Metric | alpha.6 | alpha.6.1 |
|---|---:|---:|
| Final inferred reliability | 77.83% | 57.01% |
| Last-200 decision accuracy | 59.55% | 59.07% |
| Last-200 calibration gap | 20.14% | 5.18% |

This is mainly a calibration improvement; the underlying sensor remains only about 55–60% reliable near the end, so decision accuracy is not expected to jump dramatically.

### Stationary false-split tests

- 50 seeds at true 70% reliability: **0/50 false regime splits**.
- Additional long torture: 20 seeds each at 10%, 30%, 50%, 70%, and 90% reliability, 3,000 observations per seed: **0/100 false regime splits** at the final threshold.

### 90% -> 10% -> 90% return test

20/20 seeds recovered in both directions.

- mean recovery after 90% -> 10%: **22.9 observations**
- mean recovery after 10% -> 90%: **22.0 observations**
- mean explicit regime count: **3.0**
- final mean effective reliability: **89.93%**

## Existing belief/planning gates rerun on alpha.6.1

- alpha.5 benchmark: **13/13 PASS**
- alpha.5 hard feed: **6/6 PASS**
- alpha.5.1 torture: **10/10 PASS**
- alpha.5 extreme resurrection torture: **9/9 PASS**
- v0.4 unit/regression surface including alpha.6.1 + experimental Procedure Cortex: **90/90 PASS**

The seven-clue belief benchmark remains unchanged:

- goal probability: **87.3964%**
- expansions: **108**
- memo hits: **140**
- policy nodes: **77**

## Broader unit regression

Completed final-tree batches:

- legacy/review/v0.2 batch: **159/159 PASS**
- v0.3 batch: **77 executed: 76 PASS + 1 inherited intentional SKIP**
- v0.4 + new experimental tests: **90/90 PASS**

Total completed unit tests: **326 executed = 325 PASS + 1 inherited intentional SKIP**.

A combined all-at-once command exceeded the environment timeout and is not counted as a completed run; the same surface was rerun in completed split batches above.

## Experimental Procedure Cortex

Generated research benchmark:

- affine held-out generalization: **100/100**
- supported Boolean truth tables: **100/100**
- context/version retention: **50/50**
- disagreement probe selection: **100/100**

These results are intentionally narrow. The DSL and inductors are supplied and bounded. They do **not** establish general program synthesis or a production-ready Procedure Cortex.

## Migration checks

An actual alpha.6 schema-1 adaptive-evidence snapshot with 100 resolved observations migrated to alpha.6.1 with:

- identical cumulative reliability,
- identical resolved-observation count,
- one initial migrated regime,
- identical effective reliability before any temporal evidence is supplied.

The trained database still contains:

- 897 episodic events,
- 897 semantic vectors,
- 897 typed semantic-event records,
- 24 current world states,
- 50 world-state history entries.

## Remaining architectural bottleneck

Alpha.6.1 addresses temporal source reliability, but **evidence dependency remains unsolved**. Multiple observations derived from the same hidden/common source can still be overcounted as independent evidence. That remains stronger evidence for a later evidence-lineage/dependency capability than for another planning layer.
