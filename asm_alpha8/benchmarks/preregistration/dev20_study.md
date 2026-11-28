# DEV20 pre-registration: do learned edit steps that combine reproduce fixes the existing systems do not?

Written and committed to git before any DEV20 fresh project was cloned or mined; none of their histories has been
looked at. Its SHA-256 is recorded in every DEV20 run manifest. Anything not listed here is exploratory.

## Question
DEV19 found that whole-fix shapes rarely recur (680 of 730 seen once) and that 12.6× more data barely raised coverage.
DEV20 tests the alternative DEV19 recommended: learn each minimal change of a fix as a STEP
(`asm/coding/steps.py`, as in this commit), and build candidates from steps:
- SINGLE: one step at one place;
- MULTI-SITE: the same filled step at every place with the same match (a consistent rename);
- PAIR: two steps learned together in at least 2 fixes, at two places of the function, closer places first (same
  statement, then one statement inside the other, then elsewhere);
- a name introduced as the exception of a `raise` is an exception hole (DEV19: such names were never offered).
- steps are not applied to docstrings or other bare string statements (they learn no changes to those).

Ranking and budget: each kind's best up to its share of K = 80 (single 50, multi-site 15, pair 15), unused shares
passed on. Content operators and caps are DEV18's. Nothing else in ASM changes; B, P17 and S18 are as in DEV19.

## Development evidence (on data already inspected; reported before the fresh data exists)
All outputs are in `benchmarks/results/dev20/development/`.
- **Steps recur more than shapes.** Leave-one-project-out over the 1,254 DEV17–DEV19 fixes (32 projects;
  `benchmarks/dev20_dev_coverage.py`):
  - every step of the fix also occurs in another project: 304 fixes; a whole-fix shape of it does: 240;
  - fixes with several different changes (192): 34 by steps, 0 by shapes;
  - the same change at several places (50): 16 by steps; a shape rewrites one place only.
- **The machinery is correct.** Self-check (`benchmarks/dev20_selfcheck.py`): a library learned from one fix alone,
  each hole filled with the fix's own value in place of the content operators. Of the 847 fixes with 1–2 steps of at
  most 2 new values each, 744 are reproduced (single 674 of 722, multi-site 24 of 41, pair 46 of 84; 12 of them apart
  from a docstring change, which steps do not learn). All 103 failures were traced to a stated limit, none to a bug
  (`benchmarks/dev20_selfcheck_classify.py`): the per-step caps 38 (reproduced once they are lifted) and 1 more that
  timed out (300 s) with them lifted; a pair with a statement step (pairs join expression steps) 24; inside an
  f-string 17; a rename that changed only some of the matching places 13; a pair with a multi-site element 7; a whole
  `else`/`elif` block deleted (DEV17's statement splice cannot remove its header line) 2; a statement step at several
  places 1. (The self-check's 120 s limit could be swallowed by ASM's own `except Exception` handlers, so every fix
  ran to completion; the later scripts use a limit that cannot be, tested in `HarnessTests`.)
- **What the limits cost** (`benchmarks/dev20_dev_limits.py`): of the 304 step-covered fixes, 255 have a composition
  DEV20 builds. The other 49: a rename that changed only some places 15, three or more steps 12, a single step inside
  an f-string 9, a pair not learned together in 2 fixes of other projects 8, a pair with a multi-site element 5. The
  one limit with an obvious generalisation (pairs of multi-site steps) costs at most 5 of 1,254 fixes, so the design
  is not widened.
- **S20 against the baselines** (`benchmarks/dev20_dev_eval.py`). DEV19's setting (knowledge from 1,151 fixes, tested
  on DEV19's 103 fresh fixes): S20 reproduces 2 within 80, both new (reproduced by none of B, P17, S18): one
  multi-site, one through an exception hole (1.9%). DEV18's setting (91 fixes → 472): S20 reproduces 2, neither new.
- **Why S20 misses** (`benchmarks/dev20_gap.py`). A fix is *eligible* when every step was learned and DEV20 builds
  its composition.
  - DEV19's setting: 24 of the 103 test fixes are eligible; the rest have a step never learned (51), a step with more
    than 2 new values (27), or a pair not learned together twice (1). S20 reproduces 2 of the 24. The other 22: a hole
    whose own value the content operators do not offer 12; every value offered, but the right candidate cut by the
    per-step caps 3 (the place 1, a later filling 2); produced, ranked 83rd 1; the unlimited-budget check timed out
    (90 s) 5; a multi-site step (content not checked) 1.
  - DEV18's setting: 70 of the 472 are eligible (never learned 251, more than 2 new values 143). S20 reproduces 2. The
    other 68: a value not offered 55; the place is not a site (inside an f-string or a bare string) 3; every value
    offered, but cut by the caps 3 or the fix also changed a docstring 1; produced, ranked beyond 80 4; multi-site,
    not checked 2.
  - The values not offered are new names and strings (holes: DEV19's setting names 7, strings 6, attributes 2;
    DEV18's: strings 39, names 16, attributes 1).
  - So S20 is limited first by knowledge (most fixes have a step never learned, or one with too many new values),
    then by content; how steps combine or rank costs little.
- **The per-step cap's order** (`benchmarks/dev20_dev_caporder.py`). A generic step (e.g. `V0 -> V0 is not None`)
  matches almost every expression, and the cap (40 single-site candidates per step) keeps the places that come first
  in the function. Keeping instead each step's best candidates by its ranking key changes nothing (S20 2 and 2 in the
  two settings, the same fixes). Putting places in a context the step was seen in first reproduces 4 and 2 (6
  instead of 4): it gains 3 fixes, none of them new, and loses 1. The cap's order is left as it is (no gain on the
  primary measure).
- **Expectation.** On this evidence G20-1 is not expected to pass: it needs a larger effect than development showed,
  and S20 is limited by knowledge and content, which DEV20 does not change. DEV20 is run to measure steps on projects
  nobody has inspected, not to promote.

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
S20 to 80). Run: `benchmarks/dev20_evaluate.py`.

## Decision rules
- **G20-1 (primary).** The number of fresh fixes reproduced by S20 within 80 that neither B (any position), P17 (any
  position) nor S18 (within 80) reproduces. Passes iff ≥ 10 AND ≥ 2% of the fresh problems.
- **Q2 (descriptive).** S20 by kind (single, multi-site, pair); ablations: S20 with single steps only, and S20 without
  exception holes; D20 (the workflow's order).
- **Q3 (descriptive).** Why S20 misses on the fresh set: `benchmarks/dev20_gap.py` with the same knowledge (the share
  of fresh fixes whose steps were all learned in a composition DEV20 builds, and for those, content vs ranking).
- **No learning cycle** (DEV19's added nothing).
- **Promotion.** Not promoted in DEV20 whatever the results (a stage closure needs its own pre-registered gate).
- **R3.** Bugs in ASM found during the runs are fixed with a regression test; affected runs are discarded, kept, and
  re-run in full. Nothing else changes after seeing DEV20 data.
- **R4.** Every result is reported, including unfavourable ones.
