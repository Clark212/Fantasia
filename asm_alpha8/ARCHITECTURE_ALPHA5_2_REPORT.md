# ASM alpha.5.2 Architecture Report

## Goal

Improve the existing alpha.5.1 architecture by roughly an order of magnitude where the profiler showed genuine waste, without changing the alpha.5 belief/planning claim or hiding failures.

## BEFORE → AFTER

### Event-processing performance

Controlled generator: 72-token synthetic vocabulary, two relation-like clauses per event, deterministic random seed 1337, `PYTHONHASHSEED=0`, training enabled, snapshots effectively disabled during the timing loop.

#### Pre-review alpha.5.1 vs alpha.5.2 — 20 events

| Metric | Pre-review alpha.5.1 | Alpha.5.2 | Ratio |
|---|---:|---:|---:|
| total | 2038.2727 ms | 172.8124 ms | **11.7947x** |
| first-10 mean | 21.7982 ms | 6.6247 ms | 3.2904x |
| last-10 mean | 182.0291 ms | 10.6565 ms | **17.0815x** |
| p50 | 69.1766 ms | 8.5961 ms | 8.0475x |

The complete 20-event decision/relation signature matched.

#### Review-patched alpha.5.1 vs alpha.5.2 — 160 events

| Metric | Review patch | Alpha.5.2 | Ratio |
|---|---:|---:|---:|
| total | 8615.1307 ms | 3249.1226 ms | **2.6515x** |
| first-10 mean | 6.1746 ms | 6.7297 ms | 0.9175x |
| last-10 mean | 75.0048 ms | 29.8103 ms | **2.5161x** |
| p50 | 61.7974 ms | 19.1183 ms | **3.2324x** |

The complete 160-event decision/relation signature matched.

The first few events are not faster than the review patch because the new indexes have setup/maintenance cost. The gain appears as state grows, which is the behavior the change was designed to improve.

### What was removed from the hot path

Before:

- frequent broad relation scans
- repeated relation prototype construction
- repeated role-usage aggregation
- whole-map semantic cache invalidation after small updates
- repeated nested Python loops for candidate cosine scoring

After:

- feature/connector candidate indexes
- cached prototypes and maintained role mass
- bounded merge-maintenance schedule
- dependency-aware semantic invalidation
- normalized inverted postings for sparse dot-product accumulation

## Language architecture

The language core is still swappable, but alpha.5.2 makes the boundary explicit:

`backend text/extraction -> LanguageProposal -> fail-closed contract validation -> ASM acceptance gates -> persistent cognition`

A backend cannot persist an arbitrary dictionary as a belief just because it generated it.

RWKV constrained extraction accepts only JSON-shaped proposals from the allowed proposal vocabulary. This is a structural safety/correctness improvement; it is **not yet a measured language-understanding improvement**.

Generation receives bounded cognitive context rather than only a focus string/confidence number.

## Same-core A/B

A narrow 12-case structured-belief retrieval benchmark used the same frozen language embedding core on both sides.

| Memory system | Correct |
|---|---:|
| plain cosine vector memory | 1/12 |
| ASM structured belief/event memory | 12/12 |

This demonstrates that, on this task, ASM's structured state contributes something beyond swapping in a different language core. It does not prove superiority for general retrieval.

## Portability

With Python import interception forcing every `torch` import to raise `ImportError`, alpha.5.2 successfully:

- imported `asm`
- constructed `ASMEngine`
- processed one training event

Torch-only learned mechanisms remain optional and can still report that Torch is required when specifically selected.

## Snapshot migration check

An alpha.5.1 engine created a database with:

- 4 events
- 4 discovered relations
- 19 semantic terms

Alpha.5.2 loaded the same database with exactly:

- 4 events
- 4 discovered relations
- 19 semantic terms

It then processed a fifth event and saved under `asm_snapshot_v0_4_0_alpha_5_2`.

## Preserved belief/planning measurements

The 70%-reliable binary clue benchmark remains:

- 1 clue: 70.000%
- 3 clues: 78.400%
- 5 clues: 83.692%
- 7 clues: 87.3964%

Seven-clue search: 108 expansions, 140 memo hits, 77 policy nodes.

## Remaining bottlenecks

Alpha.5.2 is faster, but 160-event cost still rises from roughly 6.73 ms/event in the first 10 to 29.81 ms/event in the last 10 on this stress stream. Index maintenance, semantic state growth, relation discovery, and downstream learning systems still grow with accumulated state.

The bigger cognitive limitation is unchanged: supplied probability models can be internally legal yet wrong. Detecting/calibrating that mismatch belongs to a later capability if supported by further experiments.
