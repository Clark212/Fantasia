# DEV25 pre-registration: solving family parameters from the fit examples

Written and committed to git before any held-out attempt was run. Its SHA-256 is recorded in the DEV25 run manifest.
Anything not listed here is exploratory. Alpha 8 (= milestone 0.4.9) plan item: alpha.8.8 (transfer scaling &
efficiency), with alpha.8.5. Nothing is promoted in DEV25, and no default changes.

## Question
A learned family proposes instantiations of its parameters −8..8, shared round robin between sources (a family under
one mapping). DEV24 measured two limits:
- **The grid:** constants outside −8..8 are never reached.
- **The budget's reach:** when 18 sources share 256 proposals, each reaches 14 of its 17 values, and constants 6, 7, 8
  are lost (0 of 54).

DEV25 asks: if each source first proposes the parameters solved exactly from the fit examples, do both limits
disappear, without losses, wrong answers, or extra cost?

Mechanism (the code as in this commit): `ProcedureCortex(family_parameters='solve')`, opt-in (default
`'enumerate'`, unchanged).
- **The solve.** For each source, `_solve_parameters` reads the template as affine in its parameters. It evaluates the
  template at the zero vector and each unit vector on the fit examples, one example at a time, and solves exactly
  (rationally) from the first examples that determine the parameters. The solution must be integral and within the
  literal bound.
- **Order and cost.** The solved candidates come first, in source order, tagged `#solved`, as extra proposals up to the
  family budget's ceiling, so the enumeration after them keeps its reach. Enumeration follows as before, without
  repeating them. Every template evaluation of the solve counts as an evaluator call. `induce` still checks each
  candidate on every fit example, so a template that is not affine costs only the solving evaluations.
- **Two checks.** A solution must leave at least two fit examples to check it, so with three fit points only
  one-parameter families are solved.
- **Identified.** A solution is proposed only if no neighbouring value (each parameter ± 1) also fits the fit examples.
  An affine template never fails this; a piecewise one that fits a range of values does, and is left to enumeration.
- **Paths.** Both the one-input path and the 2–4-input path.

## Development evidence (development data only)
DEV24's development structures x·(y + c) + z and x·x·y − z + c, plus a structure not affine in its parameter,
(x − c)·(y − c) + z (anti-unification ties the two constants into one parameter). DEV24's development unrelated set;
seed 20261124. In-range c = −8..8 except 0, out of range |c| = 9..12, far |c| = 20, 50; 3 fit seeds; paired modes
(`benchmarks/dev25_transfer.py --development`, `benchmarks/results/dev25/development/transfer_dev.jsonl`):

| cell (role orders 0 and 5 together) | enumerate (control) | solve |
|---|---|---|
| relevant donors, c in range | 0.995 (56.5 evaluator calls) | 0.995 (29.6) |
| relevant donors, c beyond the grid (out of range and far) | 0.000 | **1.000** (144 vs 0 paired) |
| relevant + unrelated, c within enumeration's reach (−8..5) | 0.994 (141) | 0.981 (69) |
| relevant + unrelated, c = 6, 7, 8 | 0.000 | **1.000** (36 vs 0 paired) |
| relevant + unrelated, c beyond the grid | 0.000 | **1.000** |
| not affine in its parameter: relevant / mixed, c in range | 1.000 / 0.812 | 1.000 / 0.812 (calls 52 → 67) |
| none / unrelated / shuffled labels | 0 / 0 / 0 | 0 / 0 / 0 (unrelated calls 1,125 → 1,145) |

- **No wrong answer in any cell.**
- **First version** (also solving two-parameter families from two of three points):
  - mixed arms within reach fell from 0.994 to 0.942, and the non-affine mixed arm from 1.000 to 0.923;
  - 22 of the 25 wrong proposals came from the unrelated two-parameter affine family. Solved exactly, it is checked by
    only one remaining point and passes by coincidence; enumeration reaches only 17 of its 289 value pairs.
  - Hence the two-check rule above, the first of three changes made after looking at development results.
- **The remaining within-reach loss (0.013)** is one fit (c = −3, fit seed 1, both role orders): the unrelated max
  family, a piecewise family, solved to a value that fits all three points and was refuted by validation (no answer).
- **Defaults unchanged.** With `'enumerate'`, all eight committed lab runs of DEV21–DEV24 reproduce every attempt record
  (`benchmarks/lab_check.py <dir> family_mapping=exact`; DEV21's held-out lab needs the mapping since 2026-11-23).
- **Solving forced on those eight runs** (inspected data: development evidence;
  `benchmarks/lab_check.py <dir> family_mapping=exact family_parameters=solve`):
  - **Second change.** In the version with only the two-check rule, DEV23's development run gained 178 attempts, lost
    20, and its wrong answers rose from 79 to 99. Every one came from max(x + c, 2y): there the fit and validation
    points let many values of c fit, the affine reading picked one at an example where x = 2y, and queries where
    x > 2y exposed it. Hence the identification rule: the same run then had 75 wrong answers, fewer than committed.
  - **Third change.** Two losses in that run were solved candidates displacing enumeration's last values in a six-source
    arm. Hence solved candidates as extra proposals up to the ceiling.
  - The final code's numbers on all eight runs are in the DEV25 report.
- **Static design checks on the held-out material** (no attempt run, no outcome measured):
  - each held-out structure forms one one-parameter family in every role order;
  - the held-out unrelated donors form exactly two families (one and two parameters), so the mixed arms again have 18
    sources and enumeration reaches −8..5;
  - every donor and target is a valid program for every constant.
- Tests: `tests/test_alpha8_dev25.py` (6).

## Held-out test (`benchmarks/dev25_transfer.py`)
- **Targets never run before:**
  - affine in c: x + y·(z + c), x·(y − c) − z·z, (x + y + c)·z − x;
  - not affine in its parameter: (x + c)·(y + c) − z.
- **Constants:** in range −8..8 except 0 (16), out of range |c| = 9..12 (8), far |c| = 20, 50 (4); 3 fit seeds;
  seed 20261127.
- **Donors:**
  - **Relevant:** two donors of the target's structure (constants from `donor_constants`, always in range), over
    (u, v, w), in role order 0 or 5 (the right mapping first or last of six).
  - **Unrelated** (new set over (p, q, r)): 3p − 2q + r + 4 and 3p + q + r − 2 (two parameters), max(p, q − 3) − r and
    max(p, q − 7) − r (one parameter).
- **Arms:** none, unrelated, relevant_r0, relevant_r5, relevant_shuffled, mixed_r0, mixed_r5 (relevant + unrelated).
  The non-affine structure runs none, relevant_r0 and mixed_r0.
- **Paired modes:** `family_parameters='enumerate'` (control: the default) and `'solve'`, both with
  `family_scope='any_int'` and `family_mapping='rename'`. Protocol as DEV24 (three-input, budget 512, 3 fit points,
  8 validation points, success = 6 queries answered correctly).
- **Gate G25-A** (pooled over the three affine structures unless stated; relevant = role orders 0 and 5, mixed =
  mixed_r0 and mixed_r5):
  - **C1 reach:** mixed, c = 6, 7, 8: success(solve) − success(enumerate) ≥ 0.50, paired exact one-sided McNemar
    p < 0.01.
  - **C2 range:** relevant, |c| = 9..12, 20, 50: success(solve) − success(enumerate) ≥ 0.50, paired p < 0.01.
  - **C3 no loss:** success(solve) ≥ success(enumerate) − 0.05 on relevant with c in range, and on mixed with
    c = −8..5 (within enumeration's reach).
  - **C4 fallback:** on the non-affine structure, success(solve) ≥ success(enumerate) − 0.05 on relevant_r0 with c in
    range, and on mixed_r0 with c = −8..5.
  - **C5 no false transfer:** solve: success(unrelated) ≤ success(none) + 0.05, and success(relevant_shuffled) ≤ 0.05
    (c in range).
  - **C6 safety:** wrong answers per query ≤ 0.02 in every cell (each arm, mode and constant group).
  - **C7 cost:** mean evaluator calls, solve / enumerate ≤ 1.10, on relevant with c in range and on unrelated with c
    in range.
  - **Passes iff C1–C7 all hold.**
- **Reported, not gated:** each structure and constant group separately; the non-affine structure beyond the grid
  (predicted about 0 in both modes); Wilson 95% intervals; the origins of failures.

## Decision rules
- **No promotion, no default change.** If G25-A passes, making `family_parameters='solve'` the default is a decision
  for the project owner.
- **R3.** Bugs found during the run are fixed with a regression test; affected runs are discarded, kept, and re-run in
  full. Nothing else changes after seeing DEV25 data.
- **R4.** Every result is reported, including unfavourable ones.
