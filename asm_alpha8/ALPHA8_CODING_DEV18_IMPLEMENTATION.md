# ASM Alpha 8 Coding DEV18 — Learned Fix Shapes, Content From the Problem (implementation report)

Status: **experimental; NOT promoted (pre-registered: not promoted in DEV18 whatever the results). The pre-registered
gate G18-1 did not pass.** Built on DEV17. ASM contains no language model and no transformer; DEV18 uses no
model-generated data at all, only real developer fixes from git history.

## Headline (read this first)
- **What DEV18 adds: fix shapes with holes, and content taken from the problem.**
  - DEV17's procedures kept the exact content of the fix they came from (the string, the name), so they almost never
    applied anywhere else.
  - DEV18 abstracts one step further. A learned fix becomes a SHAPE: values the fix carried over become variables, and
    each value the fix introduced becomes a typed hole (string, number, name, attribute, exception).
  - A content solver fills the holes from the problem being solved: the failing tests' literals, the module's own
    constants and names, and character-level string edits learned from real fixes. No programmer writes the
    operation, and no model writes the content.
- **Result on 472 fresh fixes from 8 projects nobody had inspected: G18-1 not passed.**
  - D18 (DEV18 as the workflow runs it: DEV17 procedures, then shapes, 80 candidates in total) reproduced **2** fixes
    that neither the built-in operations nor DEV17 reproduces. The gate needed 10 (at least 5 and at least 2%).
  - Shapes alone (S18) reproduced 5 within 80 candidates; DEV17 procedures 0; built-in operations 13 (11 within 80).
  - As pre-registered, the real-bug workflow run (Q3) was therefore not done.
- **Why (exploratory self-check, which follows every fix to the stage where it is lost):**
  - 142 of the 472 fixes (30%) introduce more than 2 new values, beyond `MAX_HOLES` = 2, so no shape can hold them;
    5 more change more than one region.
  - For the other 325 the machinery works: a fix's own shape, given its own content, reproduces 321 of them (the 4
    misses are edits inside f-strings, a documented limit).
  - **Shape coverage is the main bottleneck:** only 56 of the 325 have a shape among the 64 learned from the 91
    history fixes, almost all of them two generic shapes ("replace a string literal", "replace a name").
  - Content is the second: the operators offer every needed value at the fix location for 133 of 325 (96 of these
    need no new value at all).
  - Both together: 8 fresh fixes. With 91 training fixes, the reachable set was about 8, below the gate of 10 before
    any ranking or budget. Shapes reached 5 of the 8 within 80 candidates; D18 reached 2, because DEV17's procedures
    come first and take part of the 80.
- **Three bugs in ASM were found and fixed** (amendment A1), each with a regression test. The first evaluation run was
  discarded and re-run in full on the fixed code: all 531 scored rows (472 fresh, 59 BugsInPy) are identical in both runs.
  - A saved shape library holding a shape with 11 or more variables failed its own integrity check on load.
  - `bytes`, `complex` and `Ellipsis` constants did not survive save and load.
  - A whole f-string could never be rewritten.

## The pieces, as built
| piece | code |
|---|---|
| shapes | `shapes._abstract`: identifiers and constants on the pattern side become variables; a value carried over reuses its variable; a value the fix introduced becomes a typed hole (`str`, `num`, `name`, `attr`, `exc`; at most `MAX_HOLES` = 2). A matched constant must have the type it had when learned. `ShapeLibrary.learn` merges equal shapes across examples (support); string edits feed a `StringVocabulary` |
| content from the problem | `content.ProblemContext`: literals of the failing tests (for mined fixes: the test functions the same commit added or changed), quoted text and exception names in failure messages; the module's constants, names, attributes and exceptions |
| content operators | strings (up to 12 values): EXTEND (grow inside a test literal to token boundaries), VOCAB (learned segment edits), TEST and MODULE (a similar literal, difflib ratio ≥ 0.6); names in scope, in the module and common builtins (top 10); attributes (top 10); exceptions; numbers |
| ranking and budget | by where the content came from (test-derived first), then the filler's rank for its match, then shape support; at most 24 fillings per match, 40 per shape, 80 in total |
| workflow | `RepairWorkflow(knowledge=..., shapes=...)`: phase 3, tried only when no built-in operation is accepted; DEV17 procedures first, then shapes, 80 in total; content from this run's failing tests (`faultloc._problem_context`). The tests, the contract and verification still decide acceptance |
| lifecycle | as DEV17: support ≥ 2 makes a shape active; 20 field fires with no success retire it; libraries are saved sealed (SHA-256) |
| fresh data | `benchmarks/dev18_mine_fresh.py`: DEV17's selection criteria unchanged, plus each fix's context |
| evaluation | `benchmarks/dev18_evaluate.py` (Q1, Q2, Q4); `benchmarks/dev18_realbugs.py` (Q3, gated) |
| self-check (exploratory) | `benchmarks/dev18_selfcheck.py`, `benchmarks/dev18_selfcheck_misses.py` |

## Pre-registered results (`benchmarks/results/dev18/`; pre-registration `8cb0c9c`, committed before the fresh projects were mined)
- **Knowledge**, learned only from the 91 DEV17 history fixes (6 projects):
  - 104 procedures (1 active);
  - 64 shapes, 3 active: `'V0' -> <str>` (support 8), `V0 -> <name>` (3), `V0 -> V0 is not None` (3);
  - 4 learned string edits.
- **Fresh data (primary):** 472 fix commits from 8 projects, mined after the pre-registration (marshmallow 149,
  click 85, boltons 63, packaging 49, tabulate 47, arrow 34, humanize 31, attrs 14). 252 have test literals in their
  context.
- **Q1 (gate G18-1): not passed.**

  | fresh (472) | reproduced, any position | within 80 |
  |---|---|---|
  | B: built-in operations (DEV15) | 13 | 11 |
  | P17: DEV17 procedures | 0 | 0 |
  | S18: DEV18 shapes + content | | 5 |
  | D18: P17, then S18 | | 2 |
  | **new by D18** (not B, not P17) | | **2** (gate: ≥ 10) |

  - The two new fixes: attrs `_Nothing.__eq__` (position 8) and marshmallow `SchemaMeta.__init__` (position 57).
    Both took a name from the function's own scope.
  - The other three shapes-only reproductions fell past 80 in D18, because DEV17's procedures come first: packaging
    `DependencyGroupResolver._validate` (41 in S18), arrow `Arrow.to` (67) and marshmallow
    `Unmarshaller.deserialize` (70).
- **Q2 (descriptive).**
  - Ablations on fresh: S18 without test-derived content still reproduces 5, and without the learned vocabulary also 5.
    None of the five used a test literal or a learned edit: three took names from scope (one also from the module),
    and two needed no new content.
  - BugsInPy (secondary: the designer has read these fixes): B 4 (2 within 80), P17 0, S18 1, D18 1; new by D18: 1, thefuck-19 (EXTEND grows a test literal; lost without test-derived content). thefuck-19 is one of the three fixes EXTEND was illustrated and tuned on before the pre-registration, so it is not independent evidence.
- **Q3:** not run (gate).
- **Q4 (learning cycle over the fresh fixes in date order: attempt with D18, then learn from the revealed fix):**
  running at the time of this commit (the learning cycle rebuilds every candidate against a growing library; see "Cheaper candidates"); its numbers are added in a follow-up commit.

## Bugs found and fixed (amendment A1; `benchmarks/preregistration/dev18_amendments.md`)
| bug | found by | effect |
|---|---|---|
| a saved shape library holding a shape with 11 or more variables failed its own seal on load: int keys were sorted as numbers when sealed and as text when loaded | the self-check could not load run 1's library | no score changed; Q3 could not have loaded the library |
| `bytes`, `complex` and `Ellipsis` constants could not be held by the saved JSON | the same save/load path (latent) | no result changed; libraries learned from 15 of the fresh fixes would have hit it |
| the f-string node itself was excluded from rewriting, not only its interior | boltons `human_readable_list` (self-check part A) | only the learning cycle could change |

- Run 1 (code `d07d6946…`) is discarded and kept in `benchmarks/results/dev18/discarded_run1/`.
- Run 2 (code `eff849ac…`) is the result; its rows so far are in `run2_partial/` (the full file, with the summary record, follows when the learning cycle ends). All 531 scored rows of run 2 equal run 1's, field by field, as A1 predicted (no fix is on the Q1/Q2 scoring path).

## Exploratory: where the fixes are lost (`benchmarks/results/dev18/selfcheck/`, not pre-registered)
Each fix is checked against its own shape (learned from that fix alone) and its own content.

| stage | fresh | BugsInPy | history |
|---|---|---|---|
| fixes | 472 | 59 | 91 |
| one changed region and ≤ 2 new values (a shape can hold the fix) | 325 | 37 | 64 |
| A: own shape + own content reproduces the fix (apply correctness) | 321 | 37 | 64 |
| B: the content operators offer every needed value at the fix location | 133 (96 need none) | 15 (10 need none) | – |
| B: own shape, real operators and budget: within 80 | 122 | 13 | – |
| C: a shape learned from the 91 history fixes reproduces it, given its content | 56 | 12 | – |
| C and B: shape known and content offered | **8** | 2 | – |
| D: the real S18 with the budget caps lifted (any position) | 8 (all 8 of C and B; 3 within 80, 5 at 134–463) | 2 | – |
| S18 within 80 (pre-registered) | 5 | 1 | – |

- New values each fresh fix introduces: 0 → 96, 1 → 158, 2 → 71, 3 → 37, 4 → 40, 5 → 20, 6 or more → 45; 5 more
  change more than one region.
- Why needed content was not offered (fresh, per hole):

  | hole | reason | holes |
  |---|---|---|
  | str | no test literals in the context | 49 |
  | str | not in the problem's context | 23 |
  | str | in the module's strings, but dissimilar or cut | 8 |
  | str | in the test literals, but dissimilar (ratio < 0.6) | 2 |
  | name | not in scope, the module or common builtins | 35 |
  | name | available, but cut by the top-10 limit (builtin 28, module 17, scope 8) | 53 |
  | attr | in the module's attributes, but cut by the top-10 limit | 20 |
  | attr | not in the module's attributes or test identifiers | 19 |
  | num / exc | not offered | 4 / 1 |
  | – | fix location inside an f-string | 4 |

## Validation
- `tests/test_alpha8_coding_dev18.py`, 17 tests:
  - content: literals come only from the named test functions; failure messages give quoted text and exception
    names; EXTEND grows to token boundaries; vocabulary edits and their contexts; similar test and module literals;
    names and exceptions;
  - shapes: carried values abstracted and introduced ones opened; the exception comes from the problem, not from the
    training fix; a string shape does not fire on numbers; problem-derived content ranks first; seal round trip,
    tamper refusal and retirement;
  - the A1 regressions (each fails on the code of run 1), and DEV17 knowledge still loading with its original seal;
  - **in the real workflow, content from the failing test completes a learned shape and fixes the bug**;
  - the fresh miner takes context only from the test functions the fix changed.
- Full `test_alpha8_*` on the final DEV18 code: **523 passed, 3 skipped, 0 failed** (DEV11–DEV18).

## What this means, and what is next
DEV18 shows that ASM can take a learned fix shape and complete it with content from the problem in front of it,
without a language model: that is how it reproduced 2 developer fixes nothing else in ASM produced. It also shows
where the limit is now. The content solver works when the shape is known (5 of the 8 reachable fixes within 80
candidates), but 91 training fixes teach too few shapes: 56 of 325 fresh fixes, almost all through two generic shapes.
- **More training fixes** (the biggest lever): shape coverage grows with examples. The DEV16 PC generator (once its
  `pairs.jsonl` exists) or more project histories would give thousands.
- **More holes:** 142 of 472 fixes introduce 3 or more new values. Raising `MAX_HOLES` multiplies the candidates, so it
  needs better ranking first.
- **Content ranking:** for 73 holes the right name or attribute was available but cut by the fixed top-10. A learned
  ranking (the DEV16 ranker) could replace the fixed order.
- **D18 ordering:** 3 shape reproductions were lost because DEV17's procedures always come first. Ordering by evidence
  instead would avoid that.
- **Cheaper candidates (a performance defect found during the runs; no result depends on it):** the caps limit what
  is kept, not what is built.
  - Every candidate is built in full (a copy of the whole function, parsed and compared several times), and only then
    are the first 40 per shape kept.
  - On one 167-line fresh function, the shapes built 6,253 candidates, 386 survived the per-shape cap, and 80 were
    used; one generic shape built 2,856 to keep 40. DEV17's procedures likewise build every candidate even where only
    80 are used.
  - Profiles: shapes take 61% of the static scoring and 49% of the learning cycle, procedure retrieval 28% and 40%.
  - Stopping each shape at its 40th valid candidate gives exactly the same 40, so the fix cannot change a result. It
    is not made now, because R3 would then require yet another full run.
  - Cost: the DEV18 evaluation took over 5 (fresh and BugsInPy alone; the learning cycle several more) hours. The largest functions took about 20 minutes each (tabulate's
    695-line `tabulate`, youtube-dl-2's 270 lines).
- **Operators:** case changes and substring shrinking for strings; edits inside f-strings.
- Each of these is a change after seeing this data, so it needs a new pre-registration (DEV19) and a new fresh set.

Consciousness-related architecture: not touched.
