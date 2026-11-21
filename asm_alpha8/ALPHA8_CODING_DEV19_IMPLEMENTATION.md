# ASM Alpha 8 Coding DEV19 — More Training Data, Same System (implementation report)

Status: **experimental; NOT promoted (pre-registered: not promoted in DEV19 whatever the results). The pre-registered
gate G19-1 did not pass.** Built on DEV18 (with its amendment A2). ASM contains no language model and no transformer;
DEV19 uses no model-generated data at all, only real developer fixes from git history.

## Headline (read this first)
- **What DEV19 tests: was DEV18's gap a data problem?**
  - DEV18 found that its 91 training fixes teach too few fix shapes.
  - DEV19 changes only the amount of knowledge: 91 → 563 → 1,151 real developer fixes (12.6×, from 16 projects).
  - The system is unchanged: no operator, ranking, budget or threshold.
- **Result on 103 fresh fixes from 8 projects nobody had inspected: G19-1 not passed.**
  - With all 1,151 fixes, D18 reproduced **0** fixes that neither the built-in operations nor DEV17's procedures
    reproduce. The gate needed 10.
- **The learning curve (Q2): 12.6× the knowledge, the same result.**

  | knowledge | B: built-in (any / within 80) | P17: procedures (any / within 80) | S18: shapes, within 80 | D18, within 80 | new by D18 |
  |---|---|---|---|---|---|
  | L91: 91 fixes | 3 / 2 | 1 / 1 | 2 | 2 | 1 |
  | L563: 563 fixes | 3 / 2 | 3 / 2 | 2 | 2 | 0 |
  | **LALL: 1,151 fixes** | 3 / 2 | 5 / 2 | 2 | 2 | **0** (gate: ≥ 10) |

  - Shapes reproduce the same 2 fixes at every level.
  - Exact procedures find more with more data (1 → 5 at any position), but only 2 within 80: the other 3 are ranked
    past 80.
  - "New" falls to 0 because, with more data, the procedures also find the one fix only shapes found with 91.
- **Why (exploratory diagnostic, which follows each fix to where it is lost):**
  - **Coverage grows slowly.** A learned shape that reproduces the fix, given the fix's own content, exists for 10,
    17 and 19 of the 103 fresh fixes at the three levels: 12.6× the data for about twice the coverage. 27 of the 103
    cannot be held by any shape (more than 2 new values).
  - **Content is offered for only 7 of those 19.** 9 need a value the operators cannot see: developer-written messages
    (5), `ValueError` and `AttributeError` (missing from the builtin list), and a name and an attribute from outside the
    problem. 3 need a value that was available but cut by the top-10 limit.
  - **Ranking cannot close the gap.**
    - With the budget caps lifted, the shapes produce 6 of the 7 at any position (1 timed out): positions 48 to
      7,278, in lists of 15,000–126,000 candidates.
    - 4 of the 7 are also DEV17-procedure fixes, so even perfect ranking would add at most 3 new fixes. The gate
      needed 10.
  - **The larger library crowds the budget anyway.** Every problem fills all 80 shape candidates at every level, and
    the two fixes the shapes reproduce sink from positions 32 and 9 to 75 and 48.
  - **The new knowledge is mostly a long tail.** 680 of the 730 shapes learned from 1,151 fixes were seen once. Both
    fixes the shapes reproduce come from generic shapes already in the 91-fix library: `V0 -> V0 is not None` (active
    there, support 3) and `V0.V1 -> V1` (seen once there, 5 times with all 1,151).
- **Learning cycle (Q3): 2 online against 2 static.** Learning each revealed fresh fix before the next one added
  nothing on this set.
- **A bug in ASM was found and fixed (amendment A2), with regression tests; the evaluation was re-run in full.**
  - When DEV17's procedures alone filled the 80 candidates, the shape library still returned 1, so 81 were tried.
  - No scored row could change: no hit is at position 80, in DEV19 or in DEV18. The re-run confirms it: all 309
    scored rows equal the first run's, field by field, and the learned knowledge is identical.
  - **It did change one DEV18 result:** DEV18's learning cycle found 4 fixes within 80, not the reported 5. The fifth
    came from the 81st candidate. The DEV18 report is corrected.
  - ASM's own repair workflow could not reach it: procedures there give at most 60 candidates.
- **A miner bug was fixed before any data was used (A1):** one non-UTF-8 file made the miner lose a whole project
  (dateutil). Both mining runs were re-run in full, and the fresh records mined before the fix are identical after it.

## What DEV19 added
| piece | code |
|---|---|
| training data | `benchmarks/dev19_mine.py train`: 10 more projects (dateutil, pyparsing, itsdangerous, markupsafe, jsonschema, pathspec, tomlkit, sqlparse, pyflakes, isort), DEV18's selection criteria and problem context unchanged |
| fresh data | `benchmarks/dev19_mine.py fresh`: 8 projects never inspected (pluggy, wcwidth, xmltodict, python-slugify, cerberus, schema, jmespath, parsimonious) |
| evaluation | `benchmarks/dev19_evaluate.py`: three knowledge levels, each learned in per-project batches and scored with DEV18's `score` (B, P17, S18, D18, K = 80); the learning cycle from LALL |
| A1 (miners) | `dev17_mine_history.decode_output`: valid UTF-8 decoded exactly as before; else the source's declared encoding; else replacement characters |
| A2 (ASM) | `ShapeLibrary.candidates_for`, `KnowledgeBase.candidates_for`: no candidates when the budget is already full |
| exploratory | `benchmarks/dev19_diag_coverage.py`, `benchmarks/dev19_diag_ceiling.py`, `benchmarks/dev19_diag_content.py`, `benchmarks/dev19_cycle_check.py` |

No ASM mechanism was added: DEV19 is a data experiment on the DEV18 system.

## Pre-registered results (`benchmarks/results/dev19/`; pre-registration `5e1a796`, committed before any DEV19 project was cloned)
- **Data**, mined after the pre-registration with DEV18's criteria:
  - training: 588 fixes from 10 projects (isort 268, pyparsing 65, tomlkit 58, jsonschema 53, sqlparse 53, dateutil 38,
    pyflakes 27, pathspec 11, itsdangerous 10, markupsafe 5);
  - fresh: 103 fixes from 8 projects (cerberus 29, pluggy 27, schema 18, xmltodict 9, jmespath 8, parsimonious 6,
    wcwidth 5, python-slugify 1), 52 with test literals in their context.
- **Knowledge per level:**

  | level | fixes | procedures (active) | shapes (active) | string edits |
  |---|---|---|---|---|
  | L91: DEV17 history | 91 | 104 (1) | 64 (3) | 4 |
  | L563: + DEV18 fresh | 563 | 676 (11) | 365 (25) | 29 |
  | LALL: + DEV19 training | 1,151 | 1,354 (44) | 730 (50) | 55 |

- **Q1 (gate G19-1, LALL): not passed.** 0 fixes reproduced by D18 that neither B nor P17 reproduces (gate: ≥ 10 and
  ≥ 2%).
  - D18's 2 reproductions at LALL are both DEV17 procedures: pluggy `_HookCaller._add_hookimpl` (position 8) and
    cerberus `Validator._validate` (33). Shapes reproduce the same two, at 75 and 48.
  - Built-in operations: wcwidth `wcswidth` and xmltodict `_DictSAXHandler.startElement` (position 0), and schema
    `Schema.validate` at position 308.
- **Q2 (learning curve):** the table above. Per fix:
  - pluggy `_HookCaller._add_hookimpl`: S18 at 32 → 65 → 75; P17 from L563 on (8 at LALL). The only "new" fix at L91.
  - cerberus `Validator._validate`: S18 at 9 → 23 → 48; P17 at every level (33 at LALL).
  - schema `Regex.__init__` (from L563), and two schema `Schema.validate` fixes (from LALL): P17 only, past 80
    (positions 334, 2,499 and 4,384, in lists of 943 to 15,211 programs).
  - Neither shape reproduction used test-derived content or a learned string edit (the DEV18 ablations change nothing).
- **Q3 (learning cycle from LALL over the fresh fixes in date order: attempt with D18, then learn the revealed fix):**
  **2 reproduced online within 80 candidates, against 2 static.** Learning from each revealed fix before the next one
  added nothing here. DEV18's cycle, from 91 fixes over 472, gave 4 against 2. By the end the knowledge held 1,254
  fixes.

## Bugs found and fixed (`benchmarks/preregistration/dev19_amendments.md`)
| | bug | found by | effect |
|---|---|---|---|
| A1 | the miners decoded git output as strict UTF-8, and one ISO-8859-1 source file made the whole dateutil history an error | mining dateutil | no DEV19 data was used before the fix; DEV17 and DEV18 data are unaffected (all their output was valid UTF-8, and decodes identically) |
| A2 | `ShapeLibrary.candidates_for` returned one candidate for `limit=0`, so a full budget became 81 | the stack of the running learning cycle (`s18_programs` called with limit 0) | no scored row (no hit at position 80 anywhere); DEV18's cycle 5 → 4; DEV19's cycle unchanged (2 with and without it) |

- Mining: both first runs are discarded and kept (`discarded_mining1/`). The records of the 4 fresh projects mined in
  full before the fix are identical after it, and cerberus's 19 records from the interrupted first run are the first
  19 of the re-run.
- Evaluation run 1 (code `f4f9029f…`) is discarded and kept (`discarded_eval1/`).
- **Run 2 (code `8e32f966…`) is the result** (`dev19_eval.jsonl`).
  - All 309 scored rows equal run 1's, field by field, as A2 predicted.
  - The learned libraries are identical: the shapes byte for byte, the procedures apart from wall-clock timestamps.
  - Its learning cycle gives 2 online, as run 1's did with the defect: in DEV19 the defect changed nothing.
  - Run 2 took 1 h 46 min (run 1: 2 h 19 min). Its cycle took 8 minutes instead of 22, because a full budget no
    longer searches the shape library.

## Exploratory: where the fixes are lost (`benchmarks/results/dev19/diagnostic/`, not pre-registered)
Each fresh fix is followed to the stage where it is lost (`dev19_diag_coverage.py`, `dev19_diag_ceiling.py`,
`dev19_diag_content.py`; DEV18's checks, applied to DEV19's knowledge).

| stage | fresh fixes |
|---|---|
| fixes | 103 |
| one changed region and ≤ 2 new values (a shape can hold the fix) | 76 |
| C: a learned shape reproduces the fix, given its content (L91 / L563 / LALL) | 10 / 17 / 19 |
| B (LALL): the content operators offer every needed value | 7 of the 19 (4 need none) |
| B (LALL): the fix's own shape alone, real operators and budget: within 80 | 6 |
| D (LALL): the real S18 with the budget caps lifted, any position | 6 of the 7 (48, 93, 366, 1,805, 2,633, 7,278); the 7th timed out |
| of these, reproduced by neither B nor P17 (the most that could count as new) | 3 (1,805, 2,633, 7,278) |
| S18 within 80 (pre-registered) | 2 |

- 16 of the 19 are known through an active shape (support ≥ 2). For six, the best-supported such shape is the generic
  "replace a string literal" (support 97). No fix known at L91 is lost at LALL.
- The 27 fixes no shape can hold all introduce more than 2 new values (with unlimited holes, all 27 would be held).
- P17 at LALL (unlimited) reproduces 5: positions 8, 33, 334, 2,499 and 4,384. Its lists hold 943 to 15,211 programs.
- Why the needed content was not offered (LALL, the 12 known-shape fixes not covered; one fix has two reasons):

  | hole | reason | fixes |
  |---|---|---|
  | name | not in scope, the module or the common builtins (`ValueError`, `AttributeError`, `Number`) | 3 |
  | str | no test literals in the context (developer-written messages) | 3 |
  | str | not in the problem's context | 2 |
  | name | a common builtin, cut by the top-10 limit (`bool`, `int`) | 2 |
  | name | in scope, cut by the top-10 limit (`self`) | 1 |
  | attr | in the module's attributes, cut by the top-10 limit (`__class__`) | 1 |
  | attr | not in the module's attributes or test identifiers (`has_plugin`) | 1 |

- The long tail: 680 of the 730 LALL shapes have support 1; the most supported are `'V0' -> <str>` (97),
  `V0 -> <name>` (32), `'V0'.V1 -> <str>.V1` (16), `V0.V1 -> V0.<attr>` (11) and `V0 -> <name>(V0)` (10). Hole counts:
  0 → 254 shapes, 1 → 287, 2 → 189.

## Validation
- `tests/test_alpha8_coding_dev19.py`, 7 tests:
  - A1: valid UTF-8 git output decodes exactly as before; a Latin-1 source with its declaration is decoded, not lost;
    undeclared bad bytes become replacement characters; `git show` of a Latin-1 file works end to end;
  - A2: a full budget gets no shape candidates and no procedure candidates; every other limit gives exactly the first
    candidates. The limit-0 tests fail on the code of run 1.
- Full `test_alpha8_*` on the final DEV19 code: **532 passed, 3 skipped, 0 failed** (DEV11–DEV19).

## What this means, and what is next
DEV19 answers the question DEV18 left open. With this design, more real data is not the lever. 12.6× the training
fixes about doubled shape coverage (10 → 19 of 103) and added no reproduced fix:
- the shapes reproduce the same 2 fixes at every level;
- DEV17's procedures find 3 more, but only hundreds to thousands of candidates down;
- even perfect ranking could add at most 3 fixes that only shapes find.

The fixes that recur (a handful of generic shapes) were already learned from 91 examples. Most of the rest of the
knowledge is a long tail of shapes seen once, which mainly competes for the budget.
- **Representation (the largest loss; the recommended DEV20).**
  - 57 of the 76 fixes a shape could hold have no learned shape, and 27 more need more than 2 new values.
  - Whole-edit shapes rarely recur. Smaller edit steps that combine (insert a guard, add an argument, replace a
    callee) may recur far more often, and could hold multi-value fixes.
  - DEV20 would test that hypothesis, on a new fresh set.
- **Content.** 12 of the 19 known-shape fixes lack a value.
  - 3 were cut by the fixed top-10, and a learned ranking (the DEV16 ranker) could keep them.
  - 9 are not visible to the operators. Builtin exception names are missing from the builtin list (a small fix), and
    developer-written messages have no source in the problem.
- **Ranking.** Worth it only after the above: here it could add at most 3 new fixes.
- **Measure.** The gate counts a fix only if it is AST-equal to the developer's within 80 candidates. ASM's workflow
  accepts any candidate that the tests and contract checks accept. A pre-registered workflow run on real bugs
  (DEV18's Q3, never reached) would measure what a user gets.
- Each of these is a change made after seeing DEV19 data, so it needs its own pre-registration and a new fresh set.
  The DEV19 fresh fixes become training data.

Consciousness-related architecture: not touched.
