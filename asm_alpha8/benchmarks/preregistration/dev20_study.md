# DEV20 pre-registration: do learned edit steps that combine reproduce fixes the existing systems do not?

Written and committed to git before any DEV20 fresh project was cloned or mined; none of their histories has been
looked at. Its SHA-256 is recorded in every DEV20 run manifest. Anything not listed here is exploratory.

## Question
DEV19 found that whole-fix shapes rarely recur (680 of 730 seen once) and that 12.6× more data barely raised coverage.
DEV20 tests the alternative DEV19 recommended: learn each minimal change of a fix as a STEP
(`asm/coding/steps.py`, as in this commit), and build candidates from steps:
- SINGLE: one step at one place;
- MULTI-SITE: the same filled step at every place with the same match (a consistent rename);
- PAIR: two steps learned together in at least 2 fixes, at two places in the same statement;
- a name introduced as the exception of a `raise` is an exception hole (DEV19: such names were never offered).

Ranking and budget: each kind's best up to its share of K = 80 (single 50, multi-site 15, pair 15), unused shares
passed on. Content operators and caps are DEV18's. Nothing else in ASM changes; B, P17 and S18 are as in DEV19.

## Development evidence (on data already inspected; reported before the fresh data exists)
- Leave-one-project-out over the 1,254 DEV17–DEV19 fixes (32 projects; `benchmarks/dev20_dev_coverage.py`):
  - every step of the fix also occurs in another project: 304 fixes; a whole-fix shape of it does: 240;
  - fixes with several different changes (192): 34 by steps, 0 by shapes;
  - the same change at several places (50): 16 by steps; a shape rewrites one place only.
- `benchmarks/dev20_dev_eval.py`, in DEV19's setting (knowledge from 1,151 fixes, tested on DEV19's 103 fresh fixes):
  S20 reproduces 2 within 80, both new (reproduced by none of B, P17, S18): one multi-site, one through an exception
  hole (1.9%). In DEV18's setting (91 fixes → 472): S20 reproduces 2, neither new.
- So the gate below needs a larger effect than development showed, or a larger fresh set at the same rate.

## Knowledge (real developer fixes only; no language model, no generated data)
All 1,254 fixes of DEV17–DEV19, in this order and per-project batches, for every learned system (P17, S18, S20):
DEV17 history (91), DEV18 fresh (472), DEV19 training (588), DEV19 fresh (103).

## Evaluation problems
Fix commits from 12 projects nobody working on ASM has inspected (`benchmarks/dev20_mine.py` FRESH: lark, tenacity,
python-dotenv, natsort, deepdiff, voluptuous, Python-Markdown, glom, PyJWT, mistune, bidict, Babel), with DEV18's
selection criteria and problem context. A project that cannot be cloned is reported and left out; no project is added
or swapped after mining.

## Measure
As DEV18/DEV19: reproduced = a candidate AST-equal to the developer's fix, within K = 80 (B and P17 also at any
position). Per fresh fix: B, P17, S18, S20, and D20 (the workflow's order with steps: P17 ≤ 30, then S18 ≤ 20, then
S20 to 80).

## Decision rules
- **G20-1 (primary).** The number of fresh fixes reproduced by S20 within 80 that neither B (any position), P17 (any
  position) nor S18 (within 80) reproduces. Passes iff ≥ 10 AND ≥ 2% of the fresh problems.
- **Q2 (descriptive).** S20 by kind (single, multi-site, pair); ablations: S20 with single steps only, and S20 without
  exception holes; D20 (the workflow's order).
- **No learning cycle** (DEV19's added nothing).
- **Promotion.** Not promoted in DEV20 whatever the results (a stage closure needs its own pre-registered gate).
- **R3.** Bugs in ASM found during the runs are fixed with a regression test; affected runs are discarded, kept, and
  re-run in full. Nothing else changes after seeing DEV20 data.
- **R4.** Every result is reported, including unfavourable ones.
