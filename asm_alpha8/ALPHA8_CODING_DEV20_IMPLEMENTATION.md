# ASM Alpha 8 Coding DEV20 — Learned Edit Steps That Combine (implementation report)

Status: **experimental; NOT promoted (pre-registered: not promoted in DEV20 whatever the results). The pre-registered
gate G20-1 did not pass.** Built on DEV19. ASM contains no language model and no transformer; DEV20 uses no
model-generated data at all, only real developer fixes from git history.

## Headline (read this first)
- **What DEV20 tests: is the representation the limit?**
  - DEV19 found that whole-fix shapes rarely recur (680 of 730 were seen once), and that 12.6× more data added nothing.
  - DEV20 learns each minimal change of a fix as a STEP, and builds candidates from steps:
    - a single step at one place;
    - the same step at every matching place (multi-site, e.g. a consistent rename);
    - two steps learned together (a pair).
  - DEV20 also adds a content fix: a name introduced as a raised exception becomes an exception hole.
- **Result on 483 fresh fixes from 12 projects nobody had inspected: G20-1 not passed.**
  - S20 reproduced 4 fixes within 80 candidates.
  - **1** of them is reproduced by none of the built-in operations, DEV17's procedures or DEV18's shapes. The gate
    needed 10.

  | system | within 80 | any position |
  |---|---|---|
  | B: built-in operations (DEV15) | 4 | 5 |
  | P17: DEV17 procedures | 6 | 10 |
  | S18: DEV18 shapes | 8 | – |
  | **S20: DEV20 steps** | **4** (single 3, multi-site 1, pair 0) | – |
  | D20: the workflow's order (P17 ≤ 30, then S18 ≤ 20, then S20 to 80) | 7 | – |

- **Both additions beyond single steps cost more than they gained (Q2).**
  - S20 with single steps only reproduces **7**; S20 without exception holes also reproduces **7**.
  - The multi-site and pair shares took 30 of the 80 candidates in nearly every function. They displaced 4
    single-step fixes and added 1 multi-site fix; pairs added none.
  - One learned step, "replace any name with an exception name", matches every name in a function. The exception
    list is never empty and ranks high, so in one function this step alone took 40 of the 50 single slots.
- **Why S20 misses (Q3).**
  - 370 of the 483 fixes cannot be built from what was learned:
    - 214 contain a step that never occurred in the 1,254 training fixes;
    - 142 have a step with more than 2 new values;
    - 14 have a composition DEV20 does not build.
  - Of the 113 it could build, the developer's new value (mostly a new name or string) is not offered for 57, and 17
    are produced but ranked beyond 80.
- **What it means.**
  - Steps do recur more often than whole-fix shapes (304 vs 240 of 1,254, leave-one-project-out).
  - But recurring steps are generic, and a generic step matches many places in a function. Without knowing where
    the bug is, the right place competes with every other place.
  - On fresh projects, S20 (4, or 7 at best) did not beat S18 (8).

## What DEV20 added
| piece | code |
|---|---|
| learned steps | `asm/coding/steps.py`: every minimal change of a fix, lifted to its nearest expression or statement, is a step; the same change at several places is one multi-site step; docstring changes are not learned; abstraction as DEV18 shapes, plus the step's context (parent node and field) |
| candidates | `StepLibrary.candidates_for`: SINGLE (one step at one place; places in a context the step was seen in rank first among equal fillings), MULTI-SITE (the same filled step at every place with the same match), PAIR (two steps learned together in ≥ 2 fixes, closer places first); shares of K = 80: 50 / 15 / 15, unused shares passed on; programs built lazily in rank order |
| content fix | a name introduced as the exception of a `raise` is an `exc` hole, filled with the exceptions the problem's tests name, then common builtin exceptions (DEV19: such names were never offered) |
| workflow | `RepairWorkflow(steps=...)`: phase 3 tries procedures (≤ 30), then shapes (≤ 20), then steps to 80; without steps, unchanged |
| fresh data | `benchmarks/dev20_mine.py`: 12 projects never inspected; DEV18's selection criteria and problem context |
| evaluation | `benchmarks/dev20_evaluate.py` (G20-1, Q2), `benchmarks/dev20_gap.py` (Q3) |
| development | `benchmarks/dev20_dev_coverage.py`, `dev20_dev_eval.py`, `dev20_selfcheck.py`, `dev20_selfcheck_classify.py`, `dev20_dev_limits.py`, `dev20_dev_caporder.py`; outputs in `benchmarks/results/dev20/development/` |
| exploratory | `benchmarks/dev20_explore_why.py`, `benchmarks/dev20_explore_ablation.py`; outputs in `benchmarks/results/dev20/exploratory/` |

Nothing else in ASM changed: B, P17 and S18 are as in DEV19, and the content operators and caps are DEV18's.

## Development, before the pre-registration (data already inspected; `benchmarks/results/dev20/development/`)
- **Steps recur more than shapes.** Leave-one-project-out over the 1,254 DEV17–DEV19 fixes:
  - every step of the fix also occurs in another project for 304 fixes; a whole-fix shape does for 240;
  - fixes with several different changes: 34 of 192 by steps, 0 by shapes;
  - the same change at several places: 16 of 50 by steps.
- **The machinery is correct.** With each hole filled by the fix's own value, 744 of the 847 fixes of 1–2 steps are
  reproduced. Every one of the 103 failures is a stated limit, none a bug:

  | limit | fixes |
  |---|---|
  | the per-step caps (+1 timed out with them lifted) | 38 |
  | a pair with a statement step | 24 |
  | inside an f-string | 17 |
  | a rename that changed only some places | 13 |
  | a pair with a multi-site element | 7 |
  | a whole `else`/`elif` block deleted | 2 |
  | a statement step at several places | 1 |
- **The limits cost little.** Of the 304 step-covered fixes, 255 have a composition DEV20 builds. Widening pairs to
  multi-site steps could add at most 5 of 1,254, so the design was not widened.
- **Realised coverage is far below that.**
  - In DEV19's setting, 24 of 103 test fixes are eligible (every step learned, a composition DEV20 builds), and S20
    reproduces 2.
  - In DEV18's setting, 70 of 472 are eligible, and S20 reproduces 2.
  - For most eligible misses, the developer's own value is not among the values the content operators offer.
- **The cap's order.**
  - Keeping each step's best candidates by its ranking key changed nothing.
  - Putting places in a context the step was seen in first gained 3 fixes and lost 1, none of them new. The order
    was left as it was.
- **Expectation, pre-registered:** G20-1 not expected to pass.
- **One harness issue was found and fixed before the pre-registration.**
  - DEV18's timeout is an `Exception`, so ASM's own `except Exception` handlers (a failed text build) swallowed it.
  - A slow fix then ran on without a limit. No result changed; runs only took longer.
  - The DEV20 scripts use a `BaseException` timeout (`HarnessTests`).

## Pre-registered results (`benchmarks/results/dev20/`; pre-registration `2c48e8e`, committed before any DEV20 project was cloned)
- **Knowledge:** all 1,254 DEV17–DEV19 fixes, in per-project batches:
  - 1,471 procedures (48 active);
  - 798 shapes (55 active);
  - 747 steps (63 active, 684 seen once), 44 of them multi-site;
  - 297 pairs, 14 of them learned from ≥ 2 fixes.
- **Fresh problems:** 483 fixes from the 12 pre-registered projects; all 12 were cloned. Per project: lark 110,
  markdown 89, babel 64, mistune 52, deepdiff 46, pyjwt 32, glom 31, tenacity 17, voluptuous 15, python-dotenv 13,
  natsort 11, bidict 3.
- **Code:** the run used the pre-registered commit's ASM code (code hash `b88d5dad…`, unchanged since). The
  manifest records the pre-registration's SHA-256 (`d36f7bb8…`).
- **G20-1 (primary): 1 fix reproduced by S20 and by none of B, P17, S18. Not passed** (needed ≥ 10 and ≥ 2%).
  - The fix is `markdown` `SmartyExtension.__init__`: an option string renamed at both places it occurs
    (`'smart_substitutions'` → `'substitutions'`).
  - It was reproduced by a multi-site step, with the new string taken from the tests.
- **Q2 (descriptive).**
  - S20 by kind: single 3, multi-site 1, pair 0.
  - Ablations: single steps only 7; without exception holes 7.
  - D20 (the workflow's order): 7.

| project | fixes | B any / 80 | P17 any / 80 | S18 | S20 | D20 | new by S20 |
|---|---|---|---|---|---|---|---|
| lark | 110 | 1 / 0 | 2 / 2 | 1 | 1 | 2 | 0 |
| markdown | 89 | 1 / 1 | 3 / 2 | 3 | 2 | 3 | 1 |
| babel | 64 | 1 / 1 | 3 / 1 | 1 | 0 | 1 | 0 |
| mistune | 52 | 1 / 1 | 0 / 0 | 1 | 0 | 0 | 0 |
| deepdiff | 46 | 0 / 0 | 2 / 1 | 1 | 1 | 1 | 0 |
| pyjwt | 32 | 0 / 0 | 0 / 0 | 1 | 0 | 0 | 0 |
| glom | 31 | 1 / 1 | 0 / 0 | 0 | 0 | 0 | 0 |
| tenacity, voluptuous, python-dotenv, natsort, bidict | 59 | 0 / 0 | 0 / 0 | 0 | 0 | 0 | 0 |
| **all** | **483** | **5 / 4** | **10 / 6** | **8** | **4** | **7** | **1** |

- **Q3 (descriptive): why S20 misses** (`dev20_gap.py`, same knowledge).

  | class | fresh fixes |
  |---|---|
  | a step never learned | 214 |
  | a step with more than 2 new values | 142 |
  | a composition DEV20 does not build (a pair not learned together twice 7, 3+ steps 4, a pair with a multi-site element 3) | 14 |
  | **eligible** (single 93, pair 14, multi-site 6) | **113** |
  | — reproduced within 80 | 4 |
  | — a hole whose own value the content operators do not offer (holes: names 30, strings 26, attributes 7, exceptions 2) | 57 |
  | — produced, ranked beyond 80 (at 56, 59, 62, 70, 85, 119, … 4,673) | 17 |
  | — every value offered, but cut by the per-step caps | 9 |
  | — the unlimited-budget check timed out (90 s) | 8 |
  | — pairs and multi-site steps not produced (content not checked) | 17 |
  | — the place is not a site (inside an f-string or a bare string) | 1 |

## Bugs found and fixed during the runs
None. The runs used the pre-registered code throughout; nothing was re-run.

The exception-hole flooding below is a design flaw, not a bug: the pre-registered design does not restrict where a
step with an exception hole applies.

## Exploratory: why the ablations beat S20 (`benchmarks/results/dev20/exploratory/`, not pre-registered)
`dev20_explore_why.py` traces the 4 fixes that single steps only, or no exception holes, reproduce and S20 misses. The
4 are lost in two ways.

| fix | S20 | single steps only | without exception holes |
|---|---|---|---|
| babel `PluralRule.__init__` (`sorted(list(rules))` → `sorted(rules)`; no other system) | not within 80 (56th single) | 56 | 16 |
| babel `ExtractMessages.finalize_options` | not within 80 (70th single) | 70 | 30 |
| markdown `CodeHiliteExtension.extendMarkdown` | not within 80 (62nd single) | 62 | 38 |
| mistune `DirectiveToc.__init__` | not within 80 (59th single) | 59 | not within 80 |

- **The multi-site and pair shares.**
  - S20 filled all 80 candidates in 480 of the 483 functions. Unless a function had too few multi-site or pair
    candidates, those two shares took 30 of the 80 slots (in these 4 fixes: 30, 30, 30 and 21).
  - So singles ranked past the 50th were cut. That cost these 4 fixes (56th to 70th among the singles) and gained 1
    (the multi-site fix above).
- **The exception hole.**
  - The step `V0 -> V900` (a name replaced by a new name) was learned from 3 fixes in `raise` positions. There, the
    new name is an exception hole.
  - The step matches every name in a function, and the exception list (the tests' exceptions, then common builtin
    ones) is never empty and ranks among the highest.
  - Steps with an exception hole took 40, 46 and 24 of the 50 single slots in the first three fixes; in the second,
    40 of the 46 came from this one step.
  - Without exception holes, the same change is an ordinary name hole and ranks lower.
- **Both removed** (`dev20_explore_ablation.py`): 7 reproduced, 1 new (babel `PluralRule.__init__`). Without
  exception holes alone, 2 are new (that fix and the multi-site one). That is the best of any DEV20 variant, and still
  far below 10.

## Validation
- `tests/test_alpha8_coding_dev20.py`, 17 tests:
  - extraction (6):
    - a rename is one multi-site step;
    - different changes are separate steps with their places;
    - a docstring change is not a step;
    - a change inside a changed region belongs to it;
    - an inserted statement is anchored on its neighbour;
    - a name introduced as a raised exception is an exception hole;
  - candidates (9):
    - multi-site rewrites every occurrence;
    - a pair learned from 2 fixes reproduces a two-change fix;
    - a pair can join two statements, closer places first;
    - docstrings are not rewritten;
    - a pair seen once is not used;
    - the raised exception comes from the problem;
    - text outside the rewritten places is kept exactly;
    - budget limits and a full budget;
    - the sealed library round-trips and refuses a tampered file;
  - workflow (1): a learned multi-site rename fixes a bug through `RepairWorkflow`;
  - harness (1): the diagnostic timeout is not swallowed by ASM's `except Exception` handlers (fails with DEV18's).
- Full `test_alpha8_*` on the final DEV20 code: **549 passed, 3 skipped, 0 failed** (DEV11–DEV20).

## What this means, and what is next
DEV17–DEV20 tried four ways for ASM to learn from real developer fixes:
- exact procedures (DEV17);
- open shapes with content operators (DEV18);
- 12.6× more data (DEV19);
- smaller steps that combine (DEV20).

On fresh projects, none reproduces more than 2 fixes that the built-in operations and exact procedures do not. On the
DEV20 set, shapes and steps together add 3 of 483.

DEV20 adds a specific lesson. Steps recur because they are small, and small means generic: a recurring step such as
"drop a wrapping call" or "replace a name" matches dozens of places in a function. Choosing the step is not enough
without choosing the place. In these evaluations each system gets the whole function; nothing tells it where the bug
is.

- **Where, not only what (the recommended next step).**
  - ASM's repair workflow has fault localization (the lines the failing tests execute), and phase 3 runs inside it.
  - A pre-registered workflow run on real bugs (DEV18's Q3, never reached) would measure two things at once:
    - whether localization makes generic steps usable;
    - what a user actually gets: a repair the tests and contract checks accept, not only the developer's exact text.
  - It needs the fresh bugs' tests to run in ASM's sandbox, as DEV15's real-bug corpus did.
- **Ranking by generality.**
  - Rank a step's candidates by how specific its pattern is and whether the place's context was seen.
  - Apply exception holes only at `raise` positions.
  - On this data, that could recover the 4 fixes above and some of the 17 ranked beyond 80.
- **Content and knowledge are still the largest losses.**
  - 214 of the 483 fixes contain a step never seen in 1,254 fixes.
  - 57 of the 113 eligible fixes need a new name or string that no operator offers.
- Each of these is a change made after seeing DEV20 data, so it needs its own pre-registration and a new fresh set.
  The DEV20 fresh fixes become training data.

Consciousness-related architecture: not touched.
