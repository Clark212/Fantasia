# DEV19 pre-registration: does more training data close the shape gap?

Written and committed to git before any DEV19 project (training or fresh) was cloned or mined; none of their histories
has been looked at. Its SHA-256 is recorded in every DEV19 run manifest. Anything not listed here is exploratory.

## Question
DEV18 found that its gate failed mainly because 91 training fixes teach too few fix shapes (8 of 472 fresh fixes were
reachable at all). DEV19 changes ONLY the amount of knowledge: the system is DEV18's with amendment A2 (performance
only), as in this commit. No operator, ranking, budget or threshold is changed.

## Knowledge (real developer fixes only; no language model, no generated data)
- L91: the 91 DEV17 history fixes. L563: + the 472 DEV18 fresh fixes (inspected in DEV18, so training data now).
- LALL: + fixes from 10 new training projects (`benchmarks/dev19_mine.py` TRAIN: dateutil, pyparsing, itsdangerous,
  markupsafe, jsonschema, pathspec, tomlkit, sqlparse, pyflakes, isort), DEV18 selection criteria unchanged.

## Evaluation problems
Fix commits from 8 projects nobody working on ASM has inspected (`dev19_mine.py` FRESH: pluggy, wcwidth, xmltodict,
python-slugify, cerberus, schema, jmespath, parsimonious), with DEV18's problem context. A project that cannot be
cloned is reported and left out; no project is added or swapped after mining.

## Measure
As DEV18: reproduced = a candidate AST-equal to the developer's fix within K = 80 (B and P17 also unlimited).

## Decision rules
- **G19-1 (primary).** With LALL: the number of fresh fixes reproduced by D18 that neither B nor P17 reproduces.
  Passes iff ≥ 10 AND ≥ 2% of the fresh problems.
- **Q2 (descriptive).** The same counts at L91 and L563 (the learning curve), B and P17 beside them.
- **Q3 (descriptive).** Learning cycle from LALL over the fresh problems in date order: online beside static.
- **Promotion.** Not promoted in DEV19 whatever the results (a stage closure needs its own pre-registered gate).
- **R3.** Bugs in ASM found during the runs are fixed with a regression test; affected runs are discarded, kept, and
  re-run in full. Nothing else changes after seeing DEV19 data.
- **R4.** Every result is reported, including unfavourable ones.
