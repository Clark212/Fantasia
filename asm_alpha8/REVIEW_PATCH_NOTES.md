# ASM v0.4.0-alpha.5.1 — review patch

This is a **review patch of the existing alpha.5.1 branch**, not a new planning stage and not alpha.6.

## Why this patch exists

An external review identified two concrete engineering defects:

1. ASM claimed PyTorch was optional, but `asm.transition_mechanism` still defined `_RecurrentTransitionNet(nn.Module)` when `nn` was `None`, so importing the core could fail on a machine without PyTorch.
2. Long-running text ingestion became dominated by repeated `OnlineSemanticMap.similar()` work. The same unchanged semantic state was recomputed many times during one event across the encoder, perception, and relation-discovery layers.

## Changes

### 1. Import-safe PyTorch boundary

`asm/transition_mechanism.py` now defines the neural transition network only when `torch.nn` is available. Without PyTorch, ASM core import and ordinary non-neural processing remain available. Constructing a recurrent transition mechanism still raises an explicit `RuntimeError`.

This patch **does not pretend PyTorch-dependent learned features work without PyTorch**. The GRU reader/writer and recurrent transition mechanisms still require it when used.

### 2. Semantic similarity cache

`asm/semantic.py` now caches:

- bounded semantic views for a term; and
- final `similar(term)` results

while the semantic map is unchanged. Any call to `observe(...)` or `import_state(...)` invalidates these caches. This is intentionally conservative: it trades some remaining recomputation for exact behavior preservation.

## BEFORE vs AFTER performance

Controlled replay used `PYTHONHASHSEED=0`, 60 deterministic dense random-text events, vocabulary size 72, 8 tokens/event, training mode, and identical inputs on both builds.

| Metric | BEFORE | AFTER |
|---|---:|---:|
| Full decisions identical | — | **60/60** |
| Total runtime | 23,164.73 ms | 1,688.51 ms |
| Last-10 mean | 807.83 ms/event | 48.80 ms/event |
| Total speedup | — | **13.72×** |
| Last-10 speedup | — | **16.55×** |

The patch therefore fixes a large amount of redundant work without changing the measured decisions in that replay.

## Important: the speed problem is not fully solved

A separate 160-event patched stress run still grew from about **6.66 ms/event** over the first 10 events to **131.80 ms/event** over the last 10.

A 120-event profile shows the remaining dominant path is:

`relation_discovery.observe_text` → `observe_episode` → `_maybe_merge` → `_relation_similarity` → `semantic.similar` / cosine comparisons.

So the next performance bottleneck is relation-prototype merge/search scaling. This patch should not be described as constant-time or as a complete performance fix.

## PyTorch-absent verification actually run

With imports of `torch` blocked in a fresh subprocess:

- import ASM: **PASS**
- construct `ASMEngine`: **PASS**
- process one ordinary training event: **PASS**
- instantiate a PyTorch-only recurrent transition mechanism: **explicit failure as intended**

The entire test suite was **not** rerun in a PyTorch-absent environment, so this patch does not claim every test is PyTorch-independent.

## Regression checks actually run

- v0.4 alpha1-alpha5 unit surface: **49/49 PASS**
- alpha.5.1 focused tests: **10/10 PASS**
- selected semantic/relation tests: **28/28 PASS**
- review-patch tests: **3/3 PASS**
- alpha.5 belief-state benchmark: **13/13 PASS**
- alpha.5 hard feed: **6/6 PASS**
- alpha.5.1 torture feed: **10/10 PASS**

A full `python -m unittest discover -s tests` run was attempted but exceeded the environment's 120-second execution cap after a long stream of passing tests. It is therefore **not claimed as complete**.

## What this patch does not do

It does not:

- add a constrained RWKV-7 structured extractor;
- claim RWKV extraction quality without local weights;
- add a same-language-core vector-memory-vs-ASM A/B benchmark;
- advance planning capability;
- fix the remaining relation-discovery scaling bottleneck.

Those should be evaluated separately rather than mixed into this portability/performance patch.
