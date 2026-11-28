# ASM v0.4.0-alpha.5.2 — Release Notes

**Release class:** same-stage architecture hardening. This is **not** alpha.6 and does not add a new planning capability stage.

## Why this release exists

External review of alpha.5.1 found three concrete engineering problems:

1. Core import was not truly PyTorch-optional.
2. Long-stream event processing spent most of its time in repeated semantic/relation comparisons.
3. The swappable language core had too weak a trust boundary and too little cognitive context.

Alpha.5.2 fixes those architecture problems while preserving alpha.5 belief-state planning behavior.

## Architecture changes

### Indexed relation cognition

`SelfDiscoveredRelationSystem` now maintains derived runtime indexes over connector and scoring features. Candidate retrieval narrows join/merge comparisons before invoking the existing scoring equations. Relation prototypes are cached and role usage is maintained incrementally.

Merge maintenance is scheduled at creation/promotion, support 2/powers of two, and bounded support milestones rather than paying a broad merge scan after every event. This schedule was changed after a legacy separation/consolidation regression was discovered during development; the final targeted regression surface is green.

### Dependency-aware semantic similarity

`OnlineSemanticMap` no longer discards every cached semantic view after every observation. It tracks affected terms, invalidates only dependent views, maintains normalized reverse postings, and accumulates exact cosine dot products through sparse inverted postings.

A regression test compares the sparse accumulator against direct cosine scoring.

### Language proposal firewall

Language backends do not directly become ASM cognition. `validate_language_proposal(...)` rejects malformed proposals before persistence, including non-finite confidence/priority values, bad schemas, unsupported proposal kinds, and malformed nested paths.

The RWKV-7 adapter now has a constrained JSON proposal extraction path. Parsed proposals still pass through the ASM contract and acceptance gates.

### Bounded cognitive context for generation

The generation context may now contain bounded subsets of:

- self state and workspace
- active goals
- agent beliefs
- current world state
- relevant semantic event memories

This gives a language backend useful ASM state without transferring decision authority to it.

### PyTorch optionality

Core ASM import and normal event processing were verified with all `torch` imports deliberately blocked. Torch-dependent learned modules remain optional capabilities and are no longer a mandatory `requirements.txt` dependency.

### Snapshot migration

The current snapshot key is `asm_snapshot_v0_4_0_alpha_5_2`. Alpha.5.2 explicitly falls back to the alpha.5.1 snapshot key before older alpha.5/alpha.4 keys. A migration smoke test preserved event count, relation count, and semantic term count from an alpha.5.1-created database.

## Controlled performance result

Using the same deterministic dense-text stress generator and `PYTHONHASHSEED=0`:

| Comparison | Before | Alpha.5.2 | Speedup | Decision signature |
|---|---:|---:|---:|---|
| 20 events: pre-review alpha.5.1 → alpha.5.2 | 2038.27 ms | 172.81 ms | **11.79x** | identical 20/20 |
| last-10 mean on same run | 182.03 ms/event | 10.66 ms/event | **17.08x** | identical |
| p50 on same run | 69.18 ms | 8.60 ms | **8.05x** | identical |
| 160 events: alpha.5.1 review patch → alpha.5.2 | 8615.13 ms | 3249.12 ms | **2.65x** | identical 160/160 |
| last-10 mean on same run | 75.00 ms/event | 29.81 ms/event | **2.52x** | identical |
| p50 on same run | 61.80 ms | 19.12 ms | **3.23x** | identical |

The requested 10x target is therefore met **for cumulative controlled event-processing throughput versus the pre-review alpha.5.1 candidate**, not as a claim of 10x intelligence. Long-stream per-event time still grows, so scaling is improved, not solved.

## Controlled same-core A/B

`benchmark_same_core_ab.py` freezes the same default language embedding core and compares plain cosine vector retrieval with ASM structured event/belief memory on 12 synthetic belief-memory queries.

- plain vector memory: **1/12 (8.33%)**
- ASM structured memory: **12/12 (100%)**

This is deliberately narrow. The test strongly favors preserving agent/object/slot structure and the frozen embeddings are weak; it does **not** establish a general intelligence or general memory advantage.

## Belief-state preservation

Fresh final-branch runs:

- `benchmark_v040a5.py`: **13/13 PASS**
- `benchmark_v040a5_stress.py`: **6/6 PASS**
- `benchmark_v040a51_torture.py`: **10/10 PASS**
- `benchmark_v040a5_extreme_torture.py`: **9/9 PASS**
- unchanged `benchmark_v040a5_mega_stress.py`: **13/14**

The unchanged mega-feed failure is the known top-k case that supplies an incomplete likelihood matrix. Alpha.5.2 inherits alpha.5.1's fail-closed probability contract and rejects that old input assumption rather than silently accepting it.

Seven-clue belief planning remains **87.3964%**, with **108 expansions, 140 memo hits, and 77 policy nodes**.

## Tests actually completed

- targeted architecture/legacy regression group: **76/76 PASS**
- v0.4 planning/belief regression group including alpha.5.2 tests: **64/64 PASS**
- alpha.5.2-specific tests: included in those runs; **5 tests** cover sparse semantic equivalence, proposal validation, constrained extractor parsing/context, and persistence firewall behavior
- smoke test: PASS
- no-Torch import + one-event processing smoke: PASS
- alpha.5.1 → alpha.5.2 snapshot migration smoke: PASS

A full `python -m unittest discover -s tests -q` was attempted during development but exceeded the execution environment's 120-second command cap. It is **not** reported as a full-suite pass.

The ancient alpha.8-alpha.10 mega long-stream suites were **not freshly rerun** for this release.

## Known limitations

1. A structurally valid but factually wrong/stale/correlated likelihood model can still make ASM confidently wrong. Alpha.5.2 does not learn its likelihood model.
2. The constrained RWKV extractor has contract/parser tests, but no bundled RWKV weights were available for an honest unseen-language quality benchmark.
3. Long-stream runtime still increases as learned semantic/relation state grows; indexing reduces the slope but does not make cognition constant-time.
4. Evidence branches at the planner's extremely small probability cutoff can still be pruned from search even though log-space belief preserves the underlying hypothesis.
5. The same-core A/B result is task-specific and should not be generalized beyond structured belief-memory retrieval.

## Next research bottlenecks

Before adding another planning stage, the strongest remaining evidence points to:

- real unseen-sentence language extraction evaluation with an actual language backend
- further long-horizon semantic/relation scaling
- model calibration / likelihood learning / drift and correlation detection as a possible future capability stage, if the failure evidence continues to support it

## Final release-gate note

A sequential `run_release_checks.py --planning-only` attempt completed the 64-test v0.4 unit group and planning alpha.1, alpha.2, alpha.3, alpha.4, alpha.4 stress, alpha.5, alpha.5 stress, and alpha.5 mega jobs before the outer 120-second environment command cap stopped the runner. The remaining alpha.5 extreme and smoke checks had already been run separately and passed. The trained historical database was also loaded separately with 897 episodic events, 897 semantic vectors, 897 semantic events, 24 current world states, and 50 history entries preserved.
