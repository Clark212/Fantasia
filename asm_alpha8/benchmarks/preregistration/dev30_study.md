# DEV30 pre-registration: an M4-candidate battery of the whole structure-transfer stack

Written and committed to git before any held-out attempt was run. Its SHA-256 is recorded in the DEV30 run manifest.
Anything not listed here is exploratory. Alpha 8 (= milestone 0.4.9) plan item: alpha.8.9 (M4 stage-closure
candidate), with alpha.8.5. Nothing is promoted in DEV30 and no default changes. Whether any of this supports a
promotion is the project owner's decision.

## Question
DEV21–DEV28 each tested one mechanism of structure transfer, in one condition, against the configuration of the time.
DEV30 asks whether the whole stack, every opt-in mechanism together, transfers learned structure under every one of
those conditions at once. The test uses fresh two- and three-input structures and checks for false transfer, wrong
answers, and losses or cost against today's defaults. No ASM code changes in DEV30.

## Configurations (paired on every attempt)
- **defaults:** today's `ProcedureCortex`: `family_sharing='round_robin'`, `family_scope='any_int'` and
  `family_mapping='rename'` (all three owner-approved), with `'enumerate'`, `'first'`, `'window'` and `'strict'`.
- **stack:** the same, plus `family_parameters='solve'` (DEV25), `family_ambiguity='ask'` (DEV26),
  `family_memory='index'` (DEV27) and `contradiction_policy='tolerant'` (DEV28).

## Conditions (`benchmarks/dev30_battery.py`)
Relevant donors are two donors of the target's structure over (u, v[, w]), in a role order drawn per attempt from all
n! orders.
- **relevant:** the basic transfer.
- **far:** constants beyond −8..8 (|c| = 9..12, 20, 50).
- **ambiguous:** the 5 fit points drawn from {0,1,2}^n.
- **memory:** 60 background procedures (DEV27's generator, a new memory seed), named to sort first.
- **restart:** as memory, then the cortex closed and reopened after the donors are installed and the families read.
- **noisy:** each label of the target and of the donors wrong with probability 0.05.
- **combined:** memory, noisy and far together.
- **Controls:** none, unrelated (four unrelated donors that form two families), shuffled target labels.

Protocol for every target and donor:
- 5 fit labels, 10 validation labels, one `induce` (budget 512);
- the oracle answers at most 2 questions, clean;
- success = 6 queries inside the evidence range all answered correctly.

In-range constants are −8..8 except 0 (16; far and combined use their 12), with 3 fit seeds and seed 20261201.

## Development evidence (development data only)
Development structures: x·(y + c) + y (two inputs), x·(y + c) + z and x·x·y − z + c (three inputs). A development
unrelated set and DEV27's development memory (seed 1), seed 30001.
Files: `benchmarks/dev30_battery.py --development`, `benchmarks/results/dev30/development/battery_dev.jsonl`.

| condition (144 attempts; far and combined 108) | defaults | stack |
|---|---|---|
| relevant | 1.000 (48 evaluator calls) | 1.000 (50) |
| far | 0.000 | **1.000** |
| ambiguous | 0.924 | **0.993** (0.50 questions per attempt) |
| memory | 0.000 | **1.000** |
| restart | 0.000 | **1.000** |
| noisy | 0.076 | **0.632** |
| combined | 0.000 | **0.537** |
| all transfer conditions (936) | 0.308 | **0.889** (545 vs 1 paired, p = 2.4 × 10⁻¹⁶²) |
| none / unrelated / shuffled | 0 / 0 / 0 | 0 / 0 / 0 |

- **No wrong answer in any cell.**
- **The one attempt the stack loses** is a degenerate fit where x = 0 at four of five points. The right mapping's
  parameter is undetermined, so it has no solved candidate, and a wrong one fit (DEV26's known limit).
- **Changes after looking at development results:**
  - **B5 (cost) was added.**
  - **A design fix in the static checks.** The held-out unrelated sets first formed only one family each, because the
    affine pairs differed in shape, not only in constants. The development run had also used that same set. The set
    that was run is now the development set, and a new held-out set forms two families per arity.
- **Static checks on the held-out material** (no attempt run):
  - each held-out structure forms one one-parameter family in every role order;
  - the held-out unrelated sets form two families each (one and two parameters);
  - every donor and target is valid for every constant.
- Tests: `tests/test_alpha8_dev30.py` (3).

## Held-out test
- **Structures never run before:**
  - two inputs: x·y·y − c·x, (y − c)·x + y, x·x + y·(x + c);
  - three inputs: x·(y + z + c), y·y − x·(z + c), (z − c)·(x + 2y).
- **Inputs to the run:** a new memory (seed 91) and the held-out unrelated sets.
- **Gate G30-A** (pooled over the six structures):
  - **B1 transfer everywhere:** with the stack, success ≥ 0.90 on each of relevant, far, ambiguous, memory and restart,
    and ≥ 0.40 on noisy and on combined.
  - **B2 gain over the defaults:** success(stack) − success(defaults) ≥ 0.30 over all transfer conditions, and the
    paired exact one-sided McNemar test p < 0.01.
  - **B3 no false transfer:** success ≤ 0.05 on none, unrelated and shuffled, in both configurations.
  - **B4 safety:** wrong answers per query ≤ 0.02 in every cell, and with the stack at most 0.005 above the defaults in
    every condition.
  - **B5 cost:** mean evaluator calls on relevant, stack / defaults ≤ 1.5.
  - **Passes iff B1–B5 all hold.**
- **Reported, not gated:**
  - each condition by arity and structure;
  - questions asked;
  - evaluator calls per condition;
  - every attempt the stack loses and why.

## What a pass would and would not mean
A pass shows that the lab's structure-transfer stack works as a whole, on fresh structures, under every condition
measured so far, with no wrong answers. It does not show transfer on real data: DEV29 measures that separately, and M4
("verified cross-task structural transfer") needs both. Nothing is promoted by this DEV.

## Decision rules
- **No promotion, no default change.** Making any stack option the default, and promoting 0.4.9 or M4, are the project
  owner's decisions.
- **R3.** Bugs found during the run are fixed with a regression test; affected runs are discarded, kept, and re-run in
  full. Nothing else changes after seeing DEV30 data.
- **R4.** Every result is reported, including unfavourable ones.
