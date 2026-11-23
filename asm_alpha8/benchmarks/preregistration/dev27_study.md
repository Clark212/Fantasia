# DEV27 pre-registration: a family memory that scales past 32 procedures and survives restarts

Written and committed to git before any held-out attempt was run. Its SHA-256 is recorded in the DEV27 run manifest.
Anything not listed here is exploratory. Alpha 8 (= milestone 0.4.9) plan item: alpha.8.6 (persistent transfer memory),
with alpha.8.8. Nothing is promoted in DEV27, and no default changes.

## Question
`families()` reads only the first 32 active procedure versions (ordered by name) and keeps at most 16 families. In a
memory holding more procedures, which families exist therefore depends on names, not on what was learned: a relevant
family whose donors sort late is invisible. DEV27 asks: with a family index kept in the database, does transfer work
whatever the memory's size and after reopening the database, without false transfer, wrong answers, or a cost that
outgrows the search it replaces?

Mechanism (the code as in this commit): `ProcedureCortex(family_memory='index')`, opt-in (default `'window'`,
unchanged).
- **The index.** `_indexed_families` anti-unifies each active version not yet indexed, once, with every active version
  that has the same inputs, as `families()` does. It stores each family found with its parents (tables
  `procedure_families` and `procedure_family_index`).
- **Reading it.** Every distinct template whose two parents are still active is returned, ordered by its parents, with
  no window and no cap.
- **Persistence.** The index survives reopening and is not rebuilt.
- **Equivalence.** With fewer than 32 active versions and 16 families it returns exactly the families of `'window'`,
  with the same ids and order.

## Development evidence (development data only)
DEV24's development structures x·(y + c) + z and x·x·y − z + c; relevant donors over (u, v, w) in role order 0 or 5.
A background memory of N = 0, 48 or 120 procedures named to sort first (alternating over (a, b, c) and (a, b), shapes
a·x + b·c + k, (a + k)·b − c, max(a, b) + k·c, a·x + b·y + k and max(a, b + k), with random constants; memory seed 1).
It is built once into a database file per size, with its families indexed, and copied for each attempt. Arms: none,
relevant_r0, relevant_r5, restart_r0, where the cortex is closed and reopened after the relevant donors are installed
and the families read. c = −12..12 except 0; 3 fit seeds; seed 27001. Both modes use `family_parameters='solve'` and
`family_ambiguity='ask'` (DEV25–DEV26; the oracle answers at most 2 questions)
(`benchmarks/dev27_transfer.py --development`, `benchmarks/results/dev27/development/transfer_dev.jsonl`):

| memory | families seen (window / index) | relevant donors, window | relevant donors, index | evaluator calls, index (none arm) |
|---|---|---|---|---|
| 0 | 1 / 1 | 1.000 | 1.000 (same attempts) | 34.9 (1,520) |
| 48 | 13 / 22 | **0.000** | **1.000** | 153.2 (1,107) |
| 120 | 13 / 42 | **0.000** | **1.000** | 347.9 (1,256) |

- **Paired, relevant arms (in range):** 192 attempts succeed only with the index at both 48 and 120, none only with the
  window.
- **After reopening the database:** the index's success is unchanged at every size (1.000).
- **No donors:** 0 in both modes. No wrong answer in any cell.
- **Cost** grows with the number of families that apply, since each is solved and checked. It stays at 2%, 14% and 28%
  of a search without donors at the same memory size.
- **Changes after looking at development results:**
  - The cost check. The draft bounded growth at 4× the empty memory's cost; a smoke test showed growth with the number
    of families (21 → 247 calls), so the check now compares with the search the transfer replaces.
  - A harness bug. The result record used integer memory sizes as keys, which became strings when read back, so its
    hash failed verification. Fixed with string keys and a regression test; the attempt records were identical.
- **Defaults unchanged.** With `'window'`, all eight committed DEV21–DEV24 lab runs reproduce every attempt record
  (`benchmarks/lab_check.py <dir> family_mapping=exact`).
- **Static checks on the held-out material** (no attempt run):
  - each held-out structure forms one one-parameter family in every role order;
  - the held-out memory forms 7 three-input families at 48 procedures and 11 at 120.
- Tests: `tests/test_alpha8_dev27.py` (6).

## Held-out test (`benchmarks/dev27_transfer.py`)
- **Targets never run before:** (z − c)·y + x, x·y − z·(z − c), (x + 2y + c)·z. c = −12..12 except 0 (24);
  3 fit seeds; seed 20261129.
- **A new background memory** (the same generator, memory seed 77) of 0, 48 and 120 procedures.
- **Arms:** none, relevant_r0, relevant_r5, restart_r0.
- **Paired modes:** `family_memory='window'` (control: the default) and `'index'`. Both use `family_parameters='solve'`,
  `family_ambiguity='ask'`, `family_scope='any_int'` and `family_mapping='rename'`. Protocol as DEV26.
- **Gate G27-A** (constants in range, pooled over the three structures; relevant = role orders 0 and 5):
  - **C1 scale:** at memory sizes 48 and 120, success(index) − success(window) ≥ 0.50 on relevant arms, and the paired
    exact one-sided McNemar test p < 0.01.
  - **C2 small memory unchanged:** with no background memory, |success(index) − success(window)| ≤ 0.02 on relevant
    arms.
  - **C3 restart:** with the index, success(relevant_r0) − success(restart_r0) ≤ 0.02 at every size.
  - **C4 no false transfer:** success(none) ≤ 0.05 in both modes at every size.
  - **C5 safety:** wrong answers per query ≤ 0.02 in every cell.
  - **C6 cheaper than searching:** with the index, mean evaluator calls on relevant arms ≤ 0.50 × those of the arm
    without donors, at every size.
  - **Passes iff C1–C6 all hold.**
- **Reported, not gated:**
  - families seen;
  - evaluator calls by size, i.e. the cost of a larger memory;
  - each structure;
  - questions asked;
  - out-of-range constants.

## Decision rules
- **No promotion, no default change.** If G27-A passes, making `family_memory='index'` the default is a decision for the
  project owner.
- **R3.** Bugs found during the run are fixed with a regression test; affected runs are discarded, kept, and re-run in
  full. Nothing else changes after seeing DEV27 data.
- **R4.** Every result is reported, including unfavourable ones.
