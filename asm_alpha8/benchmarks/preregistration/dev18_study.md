# DEV18 pre-registration: learned fix shapes + content from the problem

Written and committed to git before the fresh evaluation projects were mined: their histories have not been looked at
(only `git ls-remote` was run, to check they are reachable). Its SHA-256 is recorded in every DEV18 run manifest.
Anything not listed here is exploratory and labelled as such.

## Disclosure (read first)
The designer (the assistant building ASM) has read many BugsInPy developer fixes during DEV15–DEV17. Some DEV18
design choices were made after that reading. In particular the EXTEND string operator was illustrated on thefuck-5,
thefuck-6 and thefuck-19, and the token-boundary ranking was tuned on those three examples. BugsInPy is therefore NOT
a fresh test of DEV18: it is reported as SECONDARY. The PRIMARY evaluation uses fix commits from eight projects nobody
working on ASM has inspected.

## What is learned, from what
- Learner: `asm/coding/shapes.py` (shapes with typed content holes, string vocabulary, lifecycle) and
  `asm/coding/content.py` (problem context, filler operators, ranking), as in this commit. It is used together with
  DEV17's `KnowledgeBase` (closed procedures).
- Knowledge: ONLY the 91 real fixes mined for DEV17 (`benchmarks/results/dev17/history.jsonl`; toolz, cachetools,
  inflection, python-semver, parse, more-itertools). All 91 are learned from; none is an evaluation problem.
- No language model, no generated data.

## Evaluation problems
- **Fresh (primary):** fix commits from click, attrs, packaging, arrow, humanize, python-tabulate, boltons and
  marshmallow, mined by `benchmarks/dev18_mine_fresh.py` with DEV17's selection criteria unchanged. Each comes with its
  problem context: the literals of the test functions the same commit added or changed (the developer's own
  specification of the fix, the analogue of "the tests that fail"), and the BEFORE module's constants, names,
  attributes and exceptions.
- **BugsInPy (secondary, see disclosure):** the 59 single-function fixes of DEV17. Context: literals of the failing
  test functions in the fixed version's test files, and the buggy module.
- Caveat fixed in advance: test literals written with a fix can contain the fixed output verbatim. That is exactly the
  information a developer's failing test gives, and the workflow uses it the same way. It is not hidden.

## Measure
A problem is REPRODUCED by a system if a candidate AST-equal to the developer's fixed function is among its first
K = 80 candidates (built-in operations and DEV17 procedures are also reported with no limit). Systems: B (DEV15
built-in operations), P17 (DEV17 closed procedures), S18 (DEV18 shapes + content), D18 (DEV18 phase 3 as the workflow
runs it: P17 then S18, 80 in total).

## Decision rules
- **G18-1 (primary gate).** On the fresh problems: the number reproduced by D18 that neither B (unlimited) nor P17
  (unlimited) reproduces. Passes iff it is at least 5 AND at least 2% of the fresh problems.
- **Q2 (descriptive).** The same measures on BugsInPy (secondary); ablations of S18 without test-derived content and
  without the learned string vocabulary, on both sets; the operators that produced each reproduction.
- **Q3 (run only if G18-1 passes).** The DEV15 real-bug harness (83 BugsInPy bugs, 150 s, same environments) with
  `RepairWorkflow(knowledge=<DEV17 procedures from the 91 fixes>, shapes=<DEV18 shapes from the 91 fixes>)`, both
  frozen. Every accepted patch is read by a person against the developer's fix. Report resolved / correct / wrong
  beside DEV15 (9 / 4 / 5). Subject to the BugsInPy disclosure.
- **Q4 (descriptive).** The learning cycle over the fresh problems in commit-date order: attempt with D18, then learn
  procedures and shapes from the revealed fix. Online beside static count.
- **Promotion.** Not promoted in DEV18 whatever the results.
- **R3.** No operator, ranking, budget, threshold or criterion is changed after seeing fresh data. Bugs in ASM found
  during the runs are fixed with a regression test; affected runs are discarded, kept, and re-run in full.
- **R4.** Every result is reported, including unfavourable ones.
