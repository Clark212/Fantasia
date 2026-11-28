# ASM alpha.7.5 Parallel WIP1 — Contextual Applicability Router

This is an **independent research branch**, not an official release and not a replacement for `ASM v0.4.0-alpha.7.4`.

## Authoritative base

- Base artifact: `ASM_v0.4.0-alpha.7.4.zip`
- Expected SHA-256: `6f6a5ae1bd2c0fe57f3d758d7cb3663e621cbe955fceecb61180f7c9ec02d992`
- The code-level `__version__` intentionally remains `0.4.0-alpha.7.4` because this is a parallel WIP branch, not a promoted alpha.7.5.

## New experimental mechanism

The branch adds a bounded contextual applicability layer **separate from procedure correctness**.

New APIs:

- `observe_procedure_route(...)`
- `route_procedure_context(...)`
- `predict_routed_procedure(...)`
- `plan_procedure_route_queries(...)`
- `procedure_route_evidence_status(...)`

### Routing model

- only routes among **active/validated** procedure contexts;
- applicability evidence must be externally resolved;
- routing evidence is gated by ASM source reliability;
- repeated ancestry roots cannot multiply routing support;
- source reliability regime changes invalidate stale routing evidence;
- the fallback router is a small auditable categorical Naive-Bayes model with Laplace smoothing;
- a unique empirically supported context signature may route directly;
- uncertainty returns `needs_information` or `abstain`, never an arbitrary procedure;
- query selection maximizes bounded expected entropy reduction;
- query recommendation and query-tree planning are read-only;
- hypothetical query branches never become evidence.

### Sequential information gathering

`plan_procedure_route_queries(...)` creates a bounded hypothetical tree (max depth 4, max 8 branches per query, hard 128-node cap). It simulates possible observations only to choose useful questions. It never records a hypothetical answer.

### Temporal applicability drift

Temporal behavior activates **only** when the caller supplies a finite, strictly increasing `temporal_index`.

- Untimed/historical route evidence keeps cumulative semantics.
- Timed evidence can form a recent persistent signature run.
- A persistent recent run can route to a new applicable procedure without deleting older route evidence.
- Decreasing/malformed temporal indices fail before mutation.

This WIP does **not** yet claim a complete contextual-regime model or planner action integration.

## Fresh results

### New routing tests

`tests/test_alpha75_parallel.py`

- 13/13 PASS
- two-context routing and routed prediction
- read-only missing-context query
- bounded two-step four-context query tree
- duplicate-root suppression
- target must have an active procedure
- low-trust routing evidence blocked
- source-regime invalidation
- random/no-pattern routing abstains
- persistence across DB reopen
- feature contract fail-closed
- temporal A→B→A routing drift with history preserved
- malformed/decreasing temporal indices fail atomically

### v0.4 regression

- 150/150 PASS (`test_v040*.py`)
- inherited SQLite `ResourceWarning`s remain visible; no new failure was observed.

### Additional procedure/graft regression

- 18/18 non-v0.4 procedure/graft tests PASS
- alpha.7.2/7.3/7.4 tests were also included in the v0.4 150/150 batch.

### Existing alpha.7.4 gates

- alpha.7.4 BEFORE/AFTER benchmark: 11/11 PASS
- alpha.7.4 torture: 8/8 PASS

### Parallel benchmark

Fresh `ALPHA75_PARALLEL_BENCHMARK.json`:

- two-context routing accuracy: 100% on 200 benchmark decisions
- ambiguous context: `needs_information`
- four-context bounded query tree: all four leaves resolved
- temporal routing: A → B → A recovered, 14 historical routing records preserved
- random/no-pattern mapping: abstained, 0 false route in the benchmark case
- median route latency: ~0.263 ms in this environment
- median two-level query-plan latency: ~0.761 ms in this environment

These are local internal measurements, not standardized frontier-model benchmarks.

## Exact alpha.7.4 migration probe

A DB created by the untouched alpha.7.4 artifact was reopened under this branch:

- existing A procedure versions preserved: 1
- existing B procedure versions preserved: 1
- A prediction preserved: 6 for x=5
- B prediction preserved: 4 for x=5
- fabricated routing evidence: **0**

See `MIGRATION_ALPHA75_PARALLEL.json`.

## Known gaps before promotion

This is intentionally WIP. Major remaining work:

1. contextual routing with noisy/continuous signals beyond bounded categorical features;
2. explicit routing-regime objects instead of only preserved evidence + recent temporal runs;
3. correlated context observations across multiple inference-time sources;
4. integration with belief-state planner information actions;
5. 2/4/8/16/32-procedure torture matrix;
6. random/no-pattern false-route stress across many seeds;
7. full v0.1-v0.3 historical regression;
8. full package recertification and official version/snapshot bump only after comparison with the other alpha.7.5 branch.

## Research discipline

This branch is kept separate so it can be compared fairly with the independently produced Sonnet/Claude alpha.7.5. The stronger mechanisms can then be selected by evidence rather than merged wholesale.
