# ASM Alpha 8 DEV23 — Learned Families over Other Input Names (implementation report)

Status: **experimental; NOT promoted; no default changed** (pre-registered). **The gate G23-A passed** on held-out
two-input transfer tasks. Alpha 8 (= milestone 0.4.9) plan items: alpha.8.3 (uncertain analogy mapping) and alpha.8.5.
Built on DEV22 (`family_scope='any_int'`). ASM contains no language model and no transformer.

## Headline (read this first)
- **What DEV23 tests.** After DEV22, a learned family applied only to targets with its own input names: a family
  learned over (a, b) could not help a task over (x, y). Which target input plays which role is unknown, so DEV23 lets
  ASM try every type-preserving mapping of the family's inputs onto the target's and lets the evidence decide
  (`family_mapping='rename'`, opt-in).
- **Result: G23-A passed.** On three two-input structures no run had used (144 in-range attempts per cell), with
  donors over (a, b):

  | arm | control (DEV22's families) | with renaming |
  |---|---|---|
  | relevant donors, aligned roles (a plays x) | 0.021 (1,186 evaluator calls) | **1.000** (20) |
  | relevant donors, swapped roles (a plays y) | 0.021 | **0.979** (21) |
  | relevant + unrelated donors, aligned / swapped | 0.021 / 0.021 | **0.993** / **0.979** (56, 57) |
  | none / one relevant / unrelated | 0.021 each | 0.021 each |
  | shuffled labels | 0.000 | 0.000 |
  | donors with the target's own names (DEV22's case) | 1.000 (12) | 1.000, every attempt identical |
  | affine target + unrelated families (regression) | 1.000 (3) | 1.000 (73) |
  | wrong answers, any cell | 0 | 0 |

  Paired over both role orders: 279 attempts succeed only with renaming, none only with the control (exact one-sided
  p = 1.0 × 10⁻⁸⁴).
- **Where it fails.** All 7 failures are x·x·y + c at fit points where x·x·y and y·y·x agree (each point has x = 0,
  y = 0 or x = y). In 5, both mappings fit and the positional one, tried first, is the wrong one. In 2, an unrelated
  family also fits a fit with x = 0 throughout and comes first. Each time validation refutes the proposal and no answer
  is given; none is a wrong answer.
- **The price.** On an affine target that the exact solve gets in one step, the renamed unrelated families tried first
  add 68 candidates (of the 512-candidate budget) and about 70 evaluator calls (3 → 73), with no loss of success.
- **What it means.** In a noise-free lab, structure learned from donors now transfers across input names, whichever
  way the roles are assigned. Equal names are still assumed to mean equal roles, and only targets with as many inputs as
  the family are covered.

## What DEV23 added
| piece | code |
|---|---|
| input mapping | `asm/procedure_cortex.py`: `ProcedureCortex(family_mapping='exact'|'rename')`, default `'exact'` (unchanged). `_renamings(family inputs, target inputs)`: the identity when the names are equal; with `'rename'`, every type-preserving bijection, the positional (sorted-name) order first (two integer inputs: two mappings) |
| budget | `_family_candidates`: each (family, mapping) is one round-robin source. With `'rename'` the family budget is 17 proposals (one parameter range) per source, never below the old 64, up to 256 on multi-input targets and 221 on one-input targets (the 289 affine grammar programs after the families are never cut). Their cost counts in every total |
| leaf-only renaming | `_rename_inputs`: an input may share an operator's name (e.g. `min`), which `substitute` would also rename into an invalid program; found in development by a test |
| origin | the mapping is recorded, e.g. `family:<id>@a=y,b=x` |
| harness | `benchmarks/dev23_transfer.py`: DEV22's protocol with donors over other names, two role orders, paired modes, regression arms, gate G23-A |
| lab check | `benchmarks/dev23_lab_check.py exact|rename`: re-runs DEV21's and DEV22's committed labs with a mapping forced and compares every attempt record |
| tests | `tests/test_alpha8_dev23.py` (8) |

With the default, ASM behaves exactly as before: DEV21's and DEV22's four lab runs reproduce every committed attempt
record (3,888; 1,008; 2,880; 2,592).

## Development (development structures only)
x·(y + c) + y and max(x + c, 2y), donors over (a, b), DEV22's development unrelated set renamed to (p, q), 96 in-range
attempts per cell (`benchmarks/results/dev23/development/`):
- **Relevant donors:** 21/96 → 92/96 in both role orders. Mixed: 21/96 → 90/96 in both.
- **Unchanged:** none, one relevant and unrelated stay at 21/96, and shuffled labels at 0. Exact-name donors: 92/96,
  every attempt identical. An affine target with the unrelated families: 47/48 in both modes (35 → 101 calls).
- **Wrong answers:** 5 in each arm, in both modes, the arm without donors included (4 with renamed unrelated
  families, 0 with shuffled labels and on the affine target). All come from max(x + c, 2y),
  where 2y dominates at the fit and validation points, so c is not identified until a query. The control's affine fit
  is wrong at the same queries. That property of the structure is why the held-out structures are polynomial: there a
  wrong constant cannot pass validation.
- **Renaming forced on the earlier labs** (their donors share the target's names): three of the four reproduce every
  record. In DEV21's held-out lab 18 of 3,888 attempts gain and none lose, all in the four-family arm at c = 8: 64
  proposals over four families give each 16 of its 17 values, and the per-source budget gives 17.

## Pre-registered held-out test — G23-A passed
`benchmarks/results/dev23/transfer.jsonl` (pre-registration `c22a026`, before any held-out attempt; 4,176 attempts,
54 s; no amendment).

| check | rule | observed | |
|---|---|---|---|
| C1 gain over the control | rename − exact on relevant ≥ 0.30, paired p < 0.01 | 0.990 − 0.021 = 0.969; 279 vs 0, p = 1.0 × 10⁻⁸⁴ | ✓ |
| C2 no role-order penalty | aligned − swapped ≤ 0.10 | 1.000 − 0.979 = 0.021 | ✓ |
| C3 transfer gain | relevant − none ≥ 0.50 | 0.990 − 0.021 = 0.969 | ✓ |
| C4 no interference | relevant − mixed ≤ 0.10, each role order | aligned 0.007; swapped 0.000 | ✓ |
| C5 no false transfer | unrelated ≤ none + 0.05; shuffled ≤ 0.05 | 0.021 = 0.021; 0.000 | ✓ |
| C6 safety | wrong per query ≤ 0.02, every cell (in and out of range, regression included) | 0 wrong of 7,098 answers | ✓ |
| C7 no regression | exact-name donors and the affine target: not below control − 0.05 | 1.000 = 1.000; 1.000 = 1.000 | ✓ |
| C8 cost | unrelated arm calls, rename / exact ≤ 1.10 | 1,088.8 / 1,186.3 = 0.92 | ✓ |

- **Per structure** (relevant donors, both role orders, control → renaming): x·x·y + c 0.000 → 0.969;
  (x + c)·(y − 1) 0.000 → 1.000; x − c·y·y 0.063 → 1.000. Wilson 95%: 0.990 (0.970–0.996) vs 0.021 (0.010–0.045).
- **The 7 failures** (x·x·y + c only):
  - 3 with swapped roles: fits (0,5), (0,8), (7,7); (0,9), (1,0), (6,6); and (0,0), (0,3), (0,5). At such points both
    mappings fit, and the positional one is tried first and refuted.
  - The same 3 in the mixed swapped arm (one of them now taken by an unrelated family, max(x + 8, y), at x = 0).
  - 1 in the mixed aligned arm: that unrelated family at the all-x = 0 fit.
- **Elsewhere** the unrelated and shuffled arms each had one renamed family proposed and refuted at that fit (no
  answer; neither arm gains).
- **Positional mapping winning with swapped roles:** 3 attempts, all (x − 1)(y − 1), which is symmetric, so both
  mappings are right.
- **The control's successes** (6 of 288 relevant attempts, and the same 3 of 144 without donors) are x ± y·y, which
  its composer builds directly. With donors over other names the control has nothing to reuse: its composer remaps only
  exact-name or one-input donors.
- **Out-of-range constants** (|c| = 9..12): 0.000 in both modes with relevant donors over other names, as predicted
  (parameters span −8..8). With exact-name donors: 0.083 in both modes, from today's composer combining a whole donor
  with a constant or with y·y.
- **one_relevant = none** (0.021), as predicted: one donor forms no family.
- **Prediction that failed:** the regression target's cost was expected to roughly triple (development: 35 → 101). It
  went from 3.0 to 72.7 evaluator calls (24×): every held-out fit was solved by the exact affine solve in one step, so
  the 68 renamed family proposals before it dominate. In absolute terms that is 68 of the 512 candidates and about 70
  evaluator calls, with no change in success (48 of 48 in both modes).

## Bugs found and fixed
| | bug | found by | effect |
|---|---|---|---|
| D1 (development) | renaming with `substitute` also renames operator names, so a family over an input called `min` became an invalid program, and `Program` raised inside `induce` | a development unit test (`test_an_input_named_like_an_operator_is_renamed_as_an_input_only`) | fixed before the pre-registration by `_rename_inputs` (leaves only); the `'exact'` path does not reach it |

No bug was found during the held-out run; there is no amendment.

## Validation
- `tests/test_alpha8_dev23.py`, 8 tests:
  - the default and an unknown mapping;
  - the renamings (identity for equal names, both orders, types kept, arity);
  - transfer in both role orders where the control fails;
  - exact-name donors give the same attempt;
  - the budget (17 per source, never below 64);
  - an input named like an operator;
  - one-input families over another name apply only when renaming;
  - DEV4's one-input lab unchanged.
- Full `test_alpha8_*` on the final DEV23 code: **575 passed, 3 skipped, 0 failed** (567 before, plus 8).
- Full `tests/` except the 3 modules that cannot import without `torch`: 971 passed, 4 skipped, 57 failed. The 57
  failing test IDs are identical on the DEV22 commit (`b5407bd`): the pre-existing PyTorch failures, none new.
- `benchmarks/dev23_lab_check.py exact` reproduces all 10,368 committed attempt records of DEV21's and DEV22's labs.

## Limitations
- **A noise-free integer lab:** two inputs, one constant per structure, one seed, donors installed through the public
  API, and three fit points per target.
- **Equal names keep their roles:** when donor and target share input names, only the identity mapping is tried.
- **Same arity only:** a family applies only to targets with as many inputs of the same types. A family over two
  inputs cannot help a three-input target, and one-input donors are left to the composer.
- **No choice between mappings:** when several mappings fit the three fit points, the first is proposed, and if
  validation refutes it the attempt fails (all 7 held-out failures). ASM does not yet ask for a disambiguating example
  there. Its conditional search can, through `needs_information`.
- **Budget:** with n inputs there are up to n! mappings per family. The per-source budget then grows with them, up to
  256 proposals; three- and four-input targets were not tested.
- **Parameters span −8..8.**

## What this means, and what is next
DEV21 made learned families share their budget fairly, DEV22 made them reach tasks with several inputs, and DEV23 lets
them cross input names under an unknown role assignment. All three passed pre-registered held-out gates, in a lab. For
M4 (verified cross-task structural transfer), the open limits are noise, scale, and mappings the evidence cannot
settle.

- **Owner decisions:** make `family_scope='any_int'` (DEV22) and `family_mapping='rename'` (DEV23) the defaults. Both
  gates show no loss. The cost is about 60–70 extra evaluator calls on affine targets when unrelated families exist.
- **Recommended DEV24 (alpha.8.7, then alpha.8.4):** take the same mechanism out of the noise-free lab. Donors and
  targets would carry wrong labels at a pre-registered rate, and three-input targets would be added (six mappings per
  family). That measures whether transfer, the safety record and the budget survive realistic conditions.
- **Smaller follow-up (alpha.8.3):** when several family mappings fit and disagree, ask for one disambiguating
  example, through the cortex's existing information-query path, instead of proposing the first.
- Each of these is a change made after seeing DEV23 data, so it needs its own pre-registration and held-out tasks.

Consciousness-related architecture: not touched.
