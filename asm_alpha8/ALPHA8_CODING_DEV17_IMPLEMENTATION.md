# ASM Alpha 8 Coding DEV17 — ASM Learns Its Own Repair Procedures (implementation report)

Status: **experimental; NOT promoted. The pre-registered transfer gate G17-1 did not pass.** Built on DEV16. ASM
contains no language model and no transformer; DEV17 uses no model-generated data at all, only real developer fixes from
git history.

## Headline (read this first)
- **ASM can now construct new repair operations itself.** It works from examples of fixes:
  - it extracts what changed;
  - it generalizes several changes into one rule with variables (anti-unification);
  - it compiles the rule into an executable procedure, then tests, keeps, applies, retires or replaces it on evidence.

  No programmer writes the operation.
- **The cycle worked end to end once, on real data.**
  - From one real toolz fix (`topk`), ASM discovered the procedure `V0 -> V0 is not None`.
  - On held-out data it reproduced the developer's fix in two other projects (cachetools `Cache.__init__`,
    more-itertools `all_unique`), and that evidence made it active.
  - That is encounter → discover → construct → test → preserve → apply on unfamiliar code.
- **But it did not transfer to real bugs (G17-1 not passed).**
  - Knowledge learned from 63 real fixes in 6 projects reproduced 0 of the 59 single-function BugsInPy fixes.
  - The learning cycle over the bugs themselves (attempt, then learn from the revealed fix) also reproduced 0.
  - As pre-registered, the workflow run (Q3) was therefore not done.
- **Why (exploratory):**
  - fix SHAPES recur: 18 of 59 BugsInPy fixes have a shape that also occurs in the history (mostly "change a string
    literal"), and 13 share a shape with another BugsInPy fix;
  - fix CONTENT does not: the exact string, regex or name differs every time;
  - so a procedure that keeps the content is too specific to apply anywhere else, and one that abstracts it cannot
    say what to write. Content has to come from the problem itself (what the failing test expects, the project's own
    code), not from other projects' fixes.
- **Four bugs in ASM's rewriting were found and fixed** (amendment A1), each with a regression test. The first evaluation
  was discarded and re-run in full, with the same result. The bugs:
  - multi-line strings re-indented;
  - `elif` written back as `if`;
  - decorators duplicated;
  - lost parentheses.

  After the fix, every learned procedure reproduces the fix it was learned from: 91/91 history fixes and 59/59 BugsInPy
  fixes.

## The learning cycle, as built
| step | code |
|---|---|
| encounter an unfamiliar problem | `RepairWorkflow(knowledge=kb)`: phase 3 runs only when built-in operations (phases 1–2) accept nothing |
| search existing knowledge | `KnowledgeBase.retrieve`: active procedures first (by evidence), then candidates |
| discover a new pattern | `induction.extract_edits`: expression, statement-window and string edits, with 0–2 levels of context |
| construct a procedure | `induction.generalize` (anti-unification, shared variables) and `Procedure` (executable; edits only the match; every expression rewrite checked against the intended tree) |
| test its predictions | `KnowledgeBase.validate`: held-out examples, scoring hits, fires and cost |
| preserve | statuses `candidate`/`active`; `save`/`load` sealed with SHA-256, keeping examples, sources and history |
| apply to unfamiliar problems | `candidates_for` feeds learned candidates to the workflow; the tests, contract and verification still decide acceptance |
| improve or replace | `record_outcome` adds field evidence; `revise` retires a procedure after 20 fires with no success, and supersedes one dominated by another (same successes at lower cost, or more successes at no worse precision). Re-learning over all examples can create a new, more general procedure |

## Pre-registered results (`benchmarks/results/dev17/`; pre-registration `c504576`, before mining)
- **Data:** 91 real fix commits mined from 6 training projects (more-itertools 40, toolz 13, cachetools 13, parse 12,
  semver 10, inflection 3). Split per project by date: 63 learned from, 28 held out.
- **Q2 (held-out history):**
  - 76 procedures discovered; after validation: 1 active, 74 candidates, 1 retired;
  - 2 of 28 held-out fixes reproduced, both by `V0 -> V0 is not None`, which fired 28 times and generated 1,255 programs
    (precision 2/28).
- **Q1 (transfer, gate G17-1): not passed.** 0/59 by active procedures and 0/59 including candidates (built-in
  operations: 4/59). Learned procedures fired on every bug (median 1, maximum 6), but never produced the fix.
- **Q3:** not run (gate).
- **Q4 (learning cycle over the 59 bugs in fix-date order):** 0 reproduced online, 0 static. 149 procedures by the end;
  no procedure learned from an earlier bug later succeeded.

## Bugs found and fixed (amendment A1; `benchmarks/preregistration/dev17_amendments.md`)
| bug | found on | effect |
|---|---|---|
| multi-line strings inside a rewritten statement window were re-indented | toolz `interpose` | docstring/string content changed |
| `elif` branch written back as `if` | semver `match` | the branch left its chain, changing the program |
| decorated definition rewritten from its `def` line | semver `Version.parse` | decorator duplicated |
| expression replacing a generator expression that borrows a call's parentheses | more_itertools `run_length.decode` | invalid code |

## Validation
- `tests/test_alpha8_coding_dev17.py`, 17 tests:
  - edit kinds; anti-unification shares variables; non-executable rules are refused;
  - a procedure applies to unseen code and edits only the match; string procedure from two regex fixes;
  - round-trip; the A1 regressions;
  - lifecycle: discover, corroborate, validate, seal and tamper refusal, retire, supersede, re-generalize;
  - **a bug no built-in operation can fix is fixed by a learned procedure in the real workflow**;
  - knowledge is consulted only after built-in operations fail;
  - online: experience with one problem solves a later one;
  - the history miner keeps only small single-function fix commits.
- Full `test_alpha8_*` on the final DEV17 code: **506 passed, 3 skipped, 0 failed** (DEV11–DEV17).

## What this means, and what is next
DEV17 shows that ASM can learn procedures it was never given, and test and keep them on evidence, without a language
model. It also shows that procedures learned this way do not yet carry over to real bugs in other projects: the shape
of a fix transfers, but its content does not. The next step follows from that:
- **DEV18:** procedures whose content is filled in from the problem itself. For example, a string-edit shape whose new
  value is solved from what the failing test expects, or a name-swap shape whose replacement comes from names in scope.
  That combines the learned shape with problem-specific search.
- **More examples:** 63 training fixes is small. The DEV16 PC generator, or more projects' histories, would give
  thousands. The pre-registered rules carry over unchanged.

Consciousness-related architecture: not touched.
