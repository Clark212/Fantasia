# ASM Alpha 8 DEV25 — Solving Family Parameters from the Fit Examples (implementation report)

Status: **experimental; NOT promoted; no default changed** (pre-registered). **The gate G25-A passed** on held-out
three-input structures. Alpha 8 (= milestone 0.4.9) plan item: alpha.8.8 (transfer scaling & efficiency), with
alpha.8.5. ASM contains no language model and no transformer.

## Headline (read this first)
- **What DEV25 tests.** A learned family has proposed its parameters by enumerating −8..8, shared round robin between
  sources. DEV24 measured the two costs of that: constants outside −8..8 are never reached, and when 18 sources share
  256 proposals, each reaches only −8..5. DEV25 lets each source first propose the parameters solved exactly from the
  fit examples (`family_parameters='solve'`, opt-in).
- **Result: G25-A passed.** On four three-input structures no run had used (role orders 0 and 5 together):

  | cell | enumerate (the default) | solve |
  |---|---|---|
  | relevant donors, c in −8..8 | 1.000 (55.6 evaluator calls) | 1.000 (26.2) |
  | relevant donors, c beyond the grid (±9..12, ±20, ±50) | 0.000 | **0.982** (212 vs 0 paired) |
  | relevant + unrelated, c = 6, 7, 8 (beyond the budget's reach) | 0.000 | **1.000** (54 vs 0 paired) |
  | relevant + unrelated, c in −8..8 overall | 0.812 (303) | **1.000** (66) |
  | structure not affine in its parameter (fallback), c in range | 1.000 / 0.812 | 1.000 / 0.812 |
  | none / unrelated / shuffled labels | 0 | 0 |
  | wrong answers (10,176 answers given) | 0 | 0 |

- **What made it safe** came from development, before the pre-registration:
  - **Two checks.** A solution must leave two fit examples to check it, so with three fit points only one-parameter
    families are solved. A two-parameter family solved from two of three points overfit.
  - **Identified.** A solution is proposed only if no neighbouring value also fits the fit points. A piecewise family
    such as max(x + c, 2y) can fit a range of values, and choosing one raised wrong answers.
  - **Extra proposals.** Solved candidates are added to the budget, so enumeration keeps its reach.
- **Where it fails:** 8 attempts (2%) beyond the grid, all role order 5 at degenerate fits (e.g. y = z at every fit
  point), where an earlier, wrong mapping also solves to a fitting value. Each was proposed, refuted by validation, and
  gave no answer: DEV23's and DEV24's mapping ambiguity, which DEV26 addresses.
- **What it means.** Learned families now reach any integer constant their template is affine in, at about half the
  evaluator calls, and the budget's reach no longer shrinks with the number of sources for such families.

## What DEV25 added
| piece | code |
|---|---|
| parameter solving | `asm/procedure_cortex.py`: `ProcedureCortex(family_parameters='enumerate'|'solve')`, default `'enumerate'` (unchanged). `_solve_parameters`: the template read as affine in its parameters, evaluated at the zero and unit vectors on the fit examples one at a time and solved exactly (rationally) from the first that determine it. The solution must be integral, within the literal bound, leave two checking examples, and be identified (no neighbour fits). Every template evaluation is an evaluator call |
| proposal order | `_family_candidates`: with `'solve'`, each source's solved parameters first (source order, tagged `#solved`), as extra proposals up to the family budget's ceiling; enumeration follows without repeating them. Both the one-input and the 2–4-input paths |
| harness | `benchmarks/dev25_transfer.py`: DEV24's protocol with constants beyond the grid, a non-affine structure, gate G25-A |
| lab check | `benchmarks/lab_check.py <dir> option=value …`: re-runs all eight committed DEV21–DEV24 lab runs with the options (the harnesses' own options win) and compares every record |
| tests | `tests/test_alpha8_dev25.py` (6) |

With the default, ASM behaves exactly as before: all eight committed lab runs reproduce every attempt record (38,224;
`benchmarks/results/dev25/development/lab_check_enumerate.txt`).

## Development
Development structures x·(y + c) + z, x·x·y − z + c and the non-affine (x − c)·(y − c) + z, with DEV24's development
unrelated set (`benchmarks/results/dev25/development/`). The final version passed every check: beyond the grid 0/144 →
144/144, beyond the budget's reach 0/36 → 36/36, no loss in range, and fewer evaluator calls.

Three changes were made after looking at development results, all before the pre-registration:
1. **Two checks.** The first version also solved two-parameter families. Mixed arms within reach fell from 0.994 to
   0.942 and the non-affine mixed arm from 1.000 to 0.923. 22 of the 25 wrong proposals came from the unrelated
   two-parameter affine family: solved from two of three points, it is checked by one and passes by coincidence.
2. **Identified.** With solving forced on the eight committed lab runs, DEV23's development run gained 178 attempts,
   lost 20, and its wrong answers rose from 79 to 99, all on max(x + c, 2y). There the evidence lets many values of c
   fit, and the affine reading picked one that validation could not refute. With the neighbour check the same run has
   75 wrong answers, fewer than committed.
3. **Extra proposals.** Two remaining losses there were solved candidates displacing enumeration's last values.

**Solving forced on all eight committed lab runs, final code** (inspected data;
`benchmarks/results/dev25/development/lab_check_solve.txt`): 3,360 attempts gained, 13 lost, fewer evaluator calls in
every run.
- **Gains:**
  - DEV21: 1,026 (held-out) + 192 (development);
  - DEV22: 138 + 95;
  - DEV23: 421 + 178;
  - DEV24: 781 + 529.
- **Losses:** 12 are DEV24's (x − z)·(y + c) mapping ambiguity, now resolved in another order, and 1 is a piecewise
  family in DEV22.
- **Wrong answers:** 75 against 79 committed (DEV23 development); 0 elsewhere.

Provenance note: the development run's header records the hash of an earlier draft of the pre-registration, which
existed while development was still running. The committed pre-registration (`1fdda93`) is the final one, and the
held-out run records its hash.

## Pre-registered held-out test — G25-A passed
`benchmarks/results/dev25/transfer.jsonl` (pre-registration `1fdda93`, before any held-out attempt; 4,032 attempts,
67 s; no amendment).

| check | rule | observed | |
|---|---|---|---|
| C1 reach | mixed, c = 6..8: solve − enumerate ≥ 0.50, paired p < 0.01 | 1.000 − 0.000; 54 vs 0, p = 5.6 × 10⁻¹⁷ | ✓ |
| C2 range | relevant, beyond the grid: solve − enumerate ≥ 0.50, p < 0.01 | 0.982 − 0.000; 212 vs 0, p = 1.5 × 10⁻⁶⁴ | ✓ |
| C3 no loss | relevant in range, mixed within reach: ≥ enumerate − 0.05 | 1.000 = 1.000; 1.000 = 1.000 | ✓ |
| C4 fallback | non-affine structure: ≥ enumerate − 0.05 | 1.000 = 1.000; 1.000 = 1.000 | ✓ |
| C5 no false transfer | unrelated ≤ none + 0.05; shuffled ≤ 0.05 | 0 = 0; 0 | ✓ |
| C6 safety | wrong per query ≤ 0.02, every cell | no wrong answer | ✓ |
| C7 cost | calls solve / enumerate ≤ 1.10 (relevant; unrelated) | 26.2 / 55.6 = 0.47; 1,149.7 / 1,126.0 = 1.02 | ✓ |

- **Per structure** (relevant donors, all constants, enumerate → solve): x + y·(z + c) 0.571 → 1.000;
  x·(y − c) − z·z 0.571 → 0.994; (x + y + c)·z − x 0.571 → 0.982.
- **The 8 failures** come from 4 fits, each in relevant_r5 and mixed_r5:
  - x·(y − c) − z·z at c = 11, fit (1,9,9), (4,3,3), (9,0,0): y = z at every point;
  - (x + y + c)·z − x at c = −11 and c = −9, fits where x = y at every point;
  - (x + y + c)·z − x at c = −20, one more degenerate fit.

  In each, an earlier, wrong mapping solved to a value fitting the three points; validation refuted it and gave no
  answer.
- **The non-affine structure** behaves identically in both modes: the solve finds no integral, identified value, and
  enumeration does the work (beyond the grid, 0 in both modes, as predicted).
- **Solving does the work:** 1,006 of the 1,087 successes in solve mode came from a solved candidate.

## Validation
- **`tests/test_alpha8_dev25.py`, 6 tests:**
  - the default and an unknown value;
  - `_solve_parameters`: solved, non-integral, undetermined, piecewise and not identified, and two parameters with
    three points (nothing spent);
  - constants beyond the grid transfer only when solved;
  - beyond the budget's reach;
  - the non-affine fallback;
  - the one-input path.
- **Full `test_alpha8_*`:** 588 passed, 3 skipped, 0 failed (582 before, plus 6).
- **`benchmarks/lab_check.py <dir> family_mapping=exact`** reproduces all 38,224 committed lab records on the default.

## Limitations
- **A lab:** integer targets, three fit points, one seed, donors installed through the public API.
- **One-parameter families only** with three fit points: two-parameter families need four or more fit examples to be
  solved, and are enumerated as before.
- **Affine in the parameter.** A family not affine in its parameter (quadratic, or piecewise where the evidence fits a
  range) falls back to enumeration, with its −8..8 grid and reach.
- **Mapping ambiguity remains.** Solving changes which fitting mapping comes first: DEV24's held-out lab under solving
  gains 781 attempts and loses 12 to it.

## What this means, and what is next
DEV21–DEV25: learned families share their budget fairly, reach tasks with several inputs, cross input names and role
orders, and now reach any constant their template is affine in, at lower cost. The failures left in these labs are
almost all one kind: several (family, mapping, value) candidates fit three points, and the first is proposed.
- **Owner's decision:** make `family_parameters='solve'` the default. G25-A shows no loss; with it forced on all eight
  earlier lab runs, 3,360 attempts are gained and 13 lost, with fewer wrong answers and fewer evaluator calls.
- **Next, DEV26 (alpha.8.3):** ask for one disambiguating example when fitting candidates disagree.

Consciousness-related architecture: not touched.
