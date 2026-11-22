# DEV22 pre-registration: learned families for targets with two integer inputs

Written and committed to git before any held-out attempt was run. Its SHA-256 is recorded in the DEV22 run manifest.
Anything not listed here is exploratory. Alpha 8 (= milestone 0.4.9) plan items: alpha.8.2 (compositional procedure
reuse) and alpha.8.5 (held-out transfer benchmarking). Nothing is promoted in DEV22, and no default changes.

## Question
DEV4 and DEV21 measured structural transfer through learned families, but `ProcedureCortex.induce` consults families
only when the target has one integer input. DEV22 asks: if families with the target's input schema also propose for
integer targets with 2–4 inputs, does structure learned from donors transfer to new two-input targets that today's
search misses — without false transfer, wrong answers, interference or losses on targets today's search solves?

Mechanism (the code as in this commit): `ProcedureCortex(family_scope='any_int')`, opt-in (default `'one_input'`,
unchanged). For an all-integer target with 2–4 inputs, `induce` first proposes up to 64 instantiations (parameters
−8..8, round-robin between families, DEV21's default) of the learned families with the same input schema, inside the
same budget of 512, before the exact affine solve and the generic searches; their cost counts in the reported totals.
Families come first, as on the one-input path, because three fit points almost always admit an exact integer affine
fit (development: every candidate failure with families placed after the affine solve was such a pre-emption).

## Development evidence (development structures only; `benchmarks/dev22_transfer.py --development`)
Two development structures, x·y + c and (x + c)·y, with a development unrelated set (affine 2x + y + 1 and
3x + y − 4; max(x, y + 1) and max(x, y + 5)); seed 20261122; 96 in-range attempts per cell
(`benchmarks/results/dev22/development/`):

| arm | control (`one_input`) | candidate (`any_int`) |
|---|---|---|
| relevant | 19/96 (680 evaluator calls) | **96/96** (11) |
| mixed (relevant + unrelated) | 14/96 | **96/96** (30) |
| none / one relevant / unrelated / shuffled labels | 0, 10, 0, 0 of 96 | the same |
| unrelated, evaluator calls | 885 | 841 (ratio 0.95) |

- No wrong answer in any arm or mode.
- The control's successes come from today's composer, which reuses whole donor programs and reaches constants within
  about ±6 of a donor's (its own constants are −3..3, over two layers).
- An affine development target (2x − 3y + c) with the unrelated families present: 46/48 in both modes; evaluator
  calls 59 → 120.
- In the first version the family step came after the affine solve, and the candidate reached 56 of 96 on the relevant
  arm. All 40 failures were wrong exact affine fits to the three fit points, proposed and then refuted by validation.
- One-input targets are unchanged: DEV21's two lab runs reproduce every committed attempt record (3,888 and 1,008).

## Held-out test (`benchmarks/dev22_transfer.py`)
- **Targets never run before** (one constant c each): x·(y − c), max(x, y) + c, x·x + c·y. In-range c ∈ −8..8
  except 0 (16), out-of-range |c| ∈ 9..12 (8); 3 fit seeds; seed 20261124.
- **Donors:** relevant (two donors of the target's structure, never with its constant); a new unrelated set: affine
  2x + 3y + 1 and 5x + 3y − 2 (a two-parameter family) and min(x, y) + 2, min(x, y) + 6 (a near miss of
  max(x, y) + c). All cross-pairs are incompatible, so no unintended family forms.
- **Arms:** none, one_relevant, relevant, unrelated, relevant_shuffled, mixed (relevant + unrelated). **Regression
  arm:** an affine target today's search solves, −x + 4y + c, with the unrelated families present (arms none and
  unrelated).
- **Paired modes:** every attempt runs with `family_scope='one_input'` (control: today) and `'any_int'`
  (candidate). Protocol as DEV21 on (x, y): a fresh cortex; donors through propose + held-out validation on fixed
  pairs; 3 fit examples drawn from the 10 × 10 grid; one induce (budget 512); 8 validation pairs from 10..17; success =
  6 held-out query pairs inside the fit range all answered correctly.
- **Gate G22-A** (in-range constants, pooled over the three structures, candidate unless stated):
  - **C1 gain over the control:** success(any_int, relevant) − success(one_input, relevant) ≥ 0.30, and the paired
    exact one-sided McNemar test on the relevant attempts p < 0.01.
  - **C2 transfer gain:** success(relevant) − success(none) ≥ 0.50 (DEV4's T1).
  - **C3 no interference:** success(relevant) − success(mixed) ≤ 0.10 (DEV4's T3b).
  - **C4 no false transfer:** success(unrelated) ≤ success(none) + 0.05, and success(relevant_shuffled) ≤ 0.05.
  - **C5 safety:** wrong answers per held-out query ≤ 0.02 in every arm and mode, the regression arm included.
  - **C6 no regression:** on the affine target with unrelated families, success(any_int) ≥ success(one_input) − 0.05.
  - **C7 cost:** mean evaluator calls on the unrelated arm, any_int / one_input ≤ 1.10.
  - **Passes iff C1–C7 all hold.**
- **Reported, not gated:** each structure separately; Wilson 95% intervals; out-of-range constants (predicted ≤ 0.10
  for the candidate: parameters span −8..8); the regression arm's cost, expected to roughly double because families
  are tried before the affine solve (development: about 60 → 120 evaluator calls, against a budget of 512).

## Decision rules
- **No promotion, no default change.** If G22-A passes, making `family_scope='any_int'` the default is a decision for
  the project owner, as for DEV21's round-robin.
- **R3.** Bugs found during the run are fixed with a regression test; affected runs are discarded, kept, and re-run in
  full. Nothing else changes after seeing DEV22 data.
- **R4.** Every result is reported, including unfavourable ones.
