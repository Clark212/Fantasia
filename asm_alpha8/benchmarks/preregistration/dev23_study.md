# DEV23 pre-registration: learned families over other input names (uncertain input mapping)

Written and committed to git before any held-out attempt was run. Its SHA-256 is recorded in the DEV23 run manifest.
Anything not listed here is exploratory. Alpha 8 (= milestone 0.4.9) plan items: alpha.8.3 (uncertain analogy mapping)
and alpha.8.5 (held-out transfer benchmarking). Nothing is promoted in DEV23, and no default changes.

## Question
DEV22 made learned families propose for integer targets with 2–4 inputs, but a family applies only to targets with its
own input names: a family learned over (a, b) cannot help a task over (x, y), even when the task has the same structure.
Which input of the target plays which role in the family is unknown. DEV23 asks: if ASM tries every type-preserving
mapping of the family's inputs onto the target's and lets the evidence decide, does structure transfer across input
names, whichever way the roles are assigned, without false transfer, wrong answers, interference or losses on targets
that work today?

Mechanism (the code as in this commit): `ProcedureCortex(family_mapping='rename')`, opt-in (default `'exact'`,
unchanged).
- `_renamings(family inputs, target inputs)`: the identity when the names are equal (equal names keep their roles);
  otherwise, with `'rename'`, every bijection between the two input sets that keeps each input's type, the positional
  (sorted-name) order first. Two integer inputs give two mappings.
- `_family_candidates`: each (family, mapping) is one source in DEV21's round-robin. With `'rename'` the family budget
  grows to 17 proposals (one range of a parameter, −8..8) per source, up to a ceiling: half the search budget (256 of
  512) on multi-input targets, and 221 on one-input targets, where the 289 affine grammar programs after the families
  are never cut. It never falls below the old 64. Their cost counts in every reported total, as in DEV22.
- Renaming touches input leaves only (`_rename_inputs`): an input may share an operator's name (e.g. `min`), which
  `substitute` would also rename. Found in development by a test; with `'exact'` this code is not reached.
- An origin records the mapping, e.g. `family:<id>@a=y,b=x`.

## Development evidence (development data only)
Development structures x·(y + c) + y and max(x + c, 2y); an affine development target 2x + 5y + c; DEV22's
development unrelated set renamed to (p, q): affine 2p + q + 1 and 3p + q − 4, max(p, q + 1) and max(p, q + 5);
seed 20261122; 96 in-range attempts per cell, paired (`benchmarks/dev23_transfer.py --development`,
`benchmarks/results/dev23/development/transfer_dev.jsonl`):

| arm | control (`exact`) | candidate (`rename`) |
|---|---|---|
| relevant donors over (a, b), aligned roles | 21/96 (808 evaluator calls) | **92/96** (20) |
| relevant donors over (a, b), swapped roles | 21/96 | **92/96** (21) |
| mixed (relevant + unrelated), aligned / swapped | 21/96, 21/96 | **90/96**, **90/96** (52, 53) |
| none / one relevant / unrelated | 21/96 each | 21/96 each |
| shuffled labels | 0/96 | 0/96 |
| relevant donors over (x, y) (exact names) | 92/96 (13) | 92/96, every attempt identical |
| affine target with the unrelated families present | 47/48 (35) | 47/48 (101) |
| unrelated arm, evaluator calls | 807.5 | 765.8 (ratio 0.95) |

- Paired, relevant arms: 142 attempts succeed only with renaming, none only with the control (exact one-sided p =
  1.8 × 10⁻⁴³).
- **Wrong answers** (both modes): 5 in each arm of the two development structures, the arm without donors included (4
  in the renamed-unrelated arm, 0 with shuffled labels), and none on the affine target. All come from max(x + c, 2y):
  at these fit points 2y dominates, so neither the fit nor the validation pairs (10..17, where 2y also dominates)
  identify c, and a held-out query does. The control's affine fit 2y is wrong at the same queries. That is 5 of 576
  queries per cell (0.009): this structure is uninformative under the protocol; it is not a renaming effect. In each
  held-out structure below, every point with y ∉ {0, 1} identifies c and every validation point has y ≥ 10, so a wrong
  constant cannot pass validation.
- **The candidate's 8 failures on relevant arms** are this structure's wrong constants (4 per role order).
- **Interference:** the two extra failures per mixed arm (c = 5 and 7, fit seed 2) are a renamed unrelated family,
  max(y, x + k) with k = c, which equals the target wherever x + c dominates, as it does at those three fit points. It
  comes first in the round robin (unrelated donors are listed first), is proposed, and is refuted by validation (no
  answer, not a wrong answer). Renaming adds the families that can propose, and so the chances of a coincidental fit
  to three points.
- **Out-of-range constants** (|c| = 9..12): 12/48 in both modes and both role orders (parameters span −8..8).
- **Defaults unchanged:** with `family_mapping='exact'`, DEV21's and DEV22's four lab runs reproduce every committed
  attempt record (3,888; 1,008; 2,880; 2,592; `benchmarks/dev23_lab_check.py exact`).
- **The same four labs with `'rename'` forced** (`benchmarks/dev23_lab_check.py rename`; all their donors share the
  target's names, so only the budget rule can matter): DEV21 development (DEV4's lab), DEV22 held-out and DEV22 development reproduce every record. DEV21's
  held-out lab differs in 162 of 3,888 attempts. 18 gain success and none lose. All 18 are the four-family arm
  (`mixed4`, round robin) at c = 8: there, 64 proposals over four families give each 16 of its 17 values, and the
  per-source rule gives 17. The other 144 differ only in candidate and evaluator counts. No wrong answer.
- Tests: `tests/test_alpha8_dev23.py` (8).

## Held-out test (`benchmarks/dev23_transfer.py`)
- **Targets never run before** (one constant c each): x·x·y + c, (x + c)·(y − 1), x − c·y·y. In-range c ∈ −8..8
  except 0 (16), out-of-range |c| ∈ 9..12 (8); 3 fit seeds; seed 20261125.
- **Donors:** relevant: two donors of the target's structure, never with its constant (DEV4's `donor_constants`),
  over inputs (a, b), named to sort after the unrelated donors (the worst listing order, as in DEV22). In the
  **aligned** role order a plays x and b plays y, so the positional mapping is right. In the **swapped** order a plays y
  and b plays x, so only the second mapping is right. A new unrelated set over (p, q): affine 4p − q + 3 and
  4p + 2q − 5 (a two-parameter family), max(p − 2, q) and max(p − 6, q). Cross-pairs are incompatible, so no
  unintended family forms.
- **Arms:** none, one_relevant, relevant_aligned, relevant_swapped, unrelated, relevant_shuffled (aligned donors,
  shuffled target labels), mixed_aligned, mixed_swapped (relevant + unrelated), exact_names (relevant donors over
  (x, y): DEV22's case, a regression arm). **Regression target:** an affine target today's search solves,
  3x − 2y + c, with the unrelated families present (arms none and unrelated).
- **Paired modes:** every attempt runs with `family_mapping='exact'` (control: DEV22's families) and `'rename'`
  (candidate), both with `family_scope='any_int'`. Protocol as DEV22: a fresh cortex; donors through propose +
  held-out validation on fixed pairs; 3 fit examples from the 10 × 10 grid; one induce (budget 512); 8 validation
  pairs from 10..17; success = 6 held-out query pairs (DEV22's `queries_for`, amendment A1 included) all answered
  correctly.
- **Gate G23-A** (in-range constants, pooled over the three structures, candidate mode unless stated; relevant =
  relevant_aligned and relevant_swapped together):
  - **C1 gain over the control:** success(rename, relevant) − success(exact, relevant) ≥ 0.30, and the paired exact
    one-sided McNemar test on the relevant attempts p < 0.01.
  - **C2 no role-order penalty:** success(relevant_aligned) − success(relevant_swapped) ≤ 0.10.
  - **C3 transfer gain:** success(relevant) − success(none) ≥ 0.50 (DEV4's T1).
  - **C4 no interference:** success(relevant_o) − success(mixed_o) ≤ 0.10 for both role orders o.
  - **C5 no false transfer:** success(unrelated) ≤ success(none) + 0.05, and success(relevant_shuffled) ≤ 0.05.
  - **C6 safety:** wrong answers per held-out query ≤ 0.02 in every cell: each arm and mode, in-range and
    out-of-range constants, the regression target included.
  - **C7 no regression:** success(rename) ≥ success(exact) − 0.05 on exact_names, and on the regression target with
    the unrelated families.
  - **C8 cost:** mean evaluator calls on the unrelated arm, rename / exact ≤ 1.10.
  - **Passes iff C1–C8 all hold.**
- **Reported, not gated:** each structure and role order separately; Wilson 95% intervals; out-of-range constants
  (predicted about equal in both modes: parameters span −8..8); one_relevant (predicted equal to none: one donor forms
  no family, and the composer reuses only exact-name multi-input donors); the regression target's cost, expected to
  roughly triple because renamed unrelated families are tried before the affine solve (development: 35 → 101 evaluator
  calls, of a budget of 512).

## Decision rules
- **No promotion, no default change.** If G23-A passes, making `family_mapping='rename'` the default is a decision for
  the project owner. A pass is evidence for alpha.8.3 from one mechanism in a noise-free lab. It does not mark the
  alpha.8.3 target validated in the plan, as for DEV21 (alpha.8.4) and DEV22.
- **R3.** Bugs found during the run are fixed with a regression test; affected runs are discarded, kept, and re-run in
  full. Nothing else changes after seeing DEV23 data.
- **R4.** Every result is reported, including unfavourable ones.
