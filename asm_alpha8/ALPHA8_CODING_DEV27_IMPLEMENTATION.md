# ASM Alpha 8 DEV27 — A Family Memory Past 32 Procedures That Survives Restarts (implementation report)

Status: **experimental; NOT promoted; no default changed** (pre-registered). **The gate G27-A passed** on held-out
structures with a new background memory. Alpha 8 (= milestone 0.4.9) plan item: alpha.8.6 (persistent transfer
memory), with alpha.8.8. ASM contains no language model and no transformer.

## Headline (read this first)
- **What DEV27 tests.** `families()` reads only the first 32 active procedure versions, ordered by name, and keeps at
  most 16 families. In a larger memory, which families exist depends on names rather than on what was learned. DEV27
  keeps an index of families in the database instead (`family_memory='index'`, opt-in): every active version is
  anti-unified once with the others of the same inputs, families are stored with their parents, and all of them are
  used.
- **Result: G27-A passed.** On three three-input structures no run had used, with a new background memory of
  procedures named to sort first (288 relevant-arm attempts per cell):

  | background memory | families seen (window / index) | relevant donors, window | relevant donors, index | calls with the index (no-donor search) |
  |---|---|---|---|---|
  | none | 1 / 1 | 0.993 | 0.993, the same attempts | 33 (1,501) |
  | 48 procedures | 15 / 23 | **0.000** | **1.000** (288 vs 0 paired) | 219 (1,142) |
  | 120 procedures | 15 / 48 | **0.000** | **1.000** (288 vs 0 paired) | 345 (1,230) |

  - **After closing and reopening the database:** success is unchanged at every size.
  - **No false transfer:** without relevant donors, success is 0 at every size.
  - **No wrong answer** in 15,516 answers.
- **The price.** Each family that applies is solved and checked, so the cost grows with the memory: 33, 219 and 345
  evaluator calls, still 2%, 19% and 28% of the search the transfer replaces.
- **What it means.** Transfer no longer depends on which 32 procedures happen to sort first, and what ASM learned is
  still there after a restart. Memory size is now bounded by the cortex's own capacity (128 mechanisms) and by cost,
  not by a window.

## What DEV27 added
| piece | code |
|---|---|
| family index | `asm/procedure_cortex.py`: `ProcedureCortex(family_memory='window'|'index')`, default `'window'` (unchanged). `_indexed_families`: each active version not yet indexed is anti-unified once with every active version that has the same inputs. Families go to `procedure_families` with their parents, indexed versions to the new table `procedure_family_index`. Every distinct template whose parents are both active is returned, ordered by its parents, with no window and no cap. Templates read back from JSON are restored to tuples (`freeze`) |
| equivalence | with fewer than 32 active versions and 16 families, `'index'` returns exactly the families of `'window'` (same ids and order) |
| harness | `benchmarks/dev27_transfer.py`: DEV26's protocol on a cortex file holding a background memory (built once per size with its families indexed, copied per attempt), plus a restart arm and gate G27-A |
| lab check | `benchmarks/lab_check.py` now replaces any leftover output instead of appending to it |
| tests | `tests/test_alpha8_dev27.py` (6) |

With the default, ASM behaves exactly as before: all eight committed DEV21–DEV24 lab runs reproduce every record
(`benchmarks/results/dev27/development/lab_check_window.txt`).

## Development (development structures and memory only)
x·(y + c) + z and x·x·y − z + c with a development memory (seed 1). With 48 and 120 background procedures, relevant
donors went from 0.000 to 1.000, and after a restart too. There was no false transfer, and the cost was 2%, 14% and 28%
of the search without donors (`benchmarks/results/dev27/development/`).

Changes after looking at development results:
- **The cost check.** A smoke test showed cost growing with the families that apply (21 → 247 calls), so the draft
  bound (at most 4× the empty memory) became "cheaper than the search it replaces".
- **A harness bug.** The result record used integer memory sizes as keys, which became strings when read back, so the
  record's hash failed verification. Fixed with string keys and a regression test; the attempt records were identical.
- **A process error of mine.** An interrupted lab check left a partial output that the next run appended to; the check
  was re-run cleanly, and `lab_check.py` now replaces leftover output.

## Pre-registered held-out test — G27-A passed
`benchmarks/results/dev27/transfer.jsonl` (pre-registration `8712447`, before any held-out attempt; 5,184 attempts,
226 s; no amendment).

| check | rule | observed | |
|---|---|---|---|
| C1 scale | at 48 and 120 procedures: index − window ≥ 0.50, paired p < 0.01 | 1.000 − 0.000 at both; 288 vs 0, p = 2.0 × 10⁻⁸⁷ | ✓ |
| C2 small memory unchanged | no background: \|index − window\| ≤ 0.02 | 0.993 = 0.993 | ✓ |
| C3 restart | index: relevant_r0 − restart_r0 ≤ 0.02, every size | 0, 0, 0 | ✓ |
| C4 no false transfer | none arm ≤ 0.05, both modes, every size | 0 everywhere | ✓ |
| C5 safety | wrong per query ≤ 0.02, every cell | no wrong answer | ✓ |
| C6 cheaper than searching | index calls on relevant ≤ 0.50 × the none arm's, every size | 0.02, 0.19, 0.28 | ✓ |

- **The 2 failures per arm with no background memory** are one fit of x·y − z·(z − c) where z = 0 at every fit point.
  c is undetermined there, so no candidate is solved; enumeration proposed its first fitting value, and validation
  refuted it. This is identical in both modes. With a background memory, the index's order of candidates differed, and
  these attempts succeeded.
- **Out-of-range constants** (|c| = 9..12): 144 of 144 with the index at every size, through solving; with the window,
  144 of 144 with no background and 0 beyond.
- **Questions:** 81 index-mode attempts asked one question and 12 asked two.

## Validation
- **`tests/test_alpha8_dev27.py`, 6 tests:**
  - the default and an unknown value;
  - a small memory gives the same families in both modes;
  - past 32 active versions, only the index sees the relevant family;
  - the index survives reopening and is not rebuilt;
  - a family is used only while both its parents are active;
  - the gate's result survives the hash chain.
- **Full `test_alpha8_*`:** 599 passed, 3 skipped, 0 failed (593 before, plus 6).
- **`benchmarks/lab_check.py <dir> family_mapping=exact`** reproduces all 38,224 committed lab records on the default.

## Limitations
- **A lab:** the background memory is synthetic (five shapes, random constants), installed through the public API.
- **Linear cost.** Every applicable family is solved and checked on every target, so the cost grows with the memory.
  Larger memories would need a relevance order or screening.
- **Capacity.** The cortex holds at most 128 mechanisms, so memories larger than about 125 procedures were not tested.
- **Same inputs to form a family.** Families still form only between versions with identical inputs; renaming applies
  them to targets, but does not join donors learned over different names.
- **No re-indexing.** A version that becomes active again after being indexed is not re-indexed.

## What this means, and what is next
DEV21–DEV27 now cover the transfer stack in the lab:
- **Fair sharing** of the candidate budget between families (DEV21);
- **Several inputs** (DEV22);
- **Other names and role orders** (DEV23–DEV24);
- **Any affine constant** (DEV25);
- **A question when ambiguous** (DEV26);
- **A memory that scales and persists** (DEV27).

- **Owner's decision:** make `family_memory='index'` the default. G27-A shows no change with a small memory; the cost
  grows with the families that apply.
- **Next, DEV28 (alpha.8.7):** noise-tolerant validation, opt-in, approved by the owner for testing only.

Consciousness-related architecture: not touched.
