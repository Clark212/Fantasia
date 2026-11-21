# DEV17 pre-registration: does ASM learn new repair procedures that work on unfamiliar problems?

Written and committed to git before the training projects' histories were mined (no example has been seen).
Its SHA-256 is recorded in every DEV17 run manifest. Anything not listed here is exploratory and labelled as such.

## What is learned, from what
- Learner: `asm/coding/induction.py` (edit extraction, anti-unification, compilation) and `asm/coding/knowledge.py`
  (lifecycle). Policy constants as in `knowledge.py` at this commit: corroboration 2 examples; validation 1 hit with
  precision >= 0.05; retirement after 20 fires with no success; at most 60 learned candidates per suspect.
- Data: REAL developer fixes from the git history of the six training projects (toolz, cachetools, inflection,
  python-semver, parse, more-itertools), mined by `benchmarks/dev17_mine_history.py` with the criteria in that file at
  this commit (fix-like message, <= 2 non-test files, exactly one function changed, <= 6 changed lines). Repository
  HEADs are recorded in the mining output. No language model and no generated data are used in DEV17.
- Split: per repository, examples ordered by commit date; the oldest 70% (rounded down, at least 1) are LEARNED from,
  the newest 30% are HELD OUT for validation.
- Evaluation problems: the BugsInPy bugs of DEV15's corpus whose developer fix changes exactly one function in one
  file (59 bugs; projects disjoint from the training projects). They are never learned from, except in Q4, where each
  is learned only AFTER it has been attempted.

## Questions and decision rules
- **Q1, transfer (primary). Gate G17-1.** Using only knowledge learned from training history (and validated on its
  held-out part), count the 59 bugs whose developer fix (AST-equal function) is produced by an ACTIVE learned
  procedure. G17-1 passes iff at least one of them is a fix that DEV15's built-in operations cannot produce
  (`patterns.in_repair_space` is False for it). Secondary: the same count including CANDIDATE procedures.
- **Q2, held-out history (descriptive).** Held-out history examples reproduced by any active procedure, beside those
  reproducible by the built-in operations; procedures by status; the procedures with held-out hits.
- **Q3, workflow on real bugs (run only if G17-1 passes).** The DEV15 real-bug harness (83 bugs, 150 s, same
  environments) with `RepairWorkflow(knowledge=<the Q1 knowledge base, frozen>)`. Every accepted patch is read by a
  person against the developer's fix. Report resolved / correct / wrong beside DEV15 (9 / 4 / 5), and which accepted
  patches came from learned procedures.
- **Q4, the learning cycle (descriptive).** The 59 bugs in order of their fix-commit date. For each: attempt with the
  current knowledge (does an active or candidate procedure produce the fix?), then record the outcome as field evidence
  for every procedure that fired, then learn from the revealed fix. Report the cumulative number reproduced with this
  online knowledge beside the static Q1 knowledge, and the procedures discovered from earlier bugs that later succeeded.
- **Promotion.** Not promoted in DEV17 whatever the results.
- **R3.** No policy constant, mining criterion or split is changed after seeing data. Bugs in ASM found during the
  runs are fixed with a regression test; affected runs are discarded, kept, and re-run in full.
- **R4.** Every result is reported, including unfavourable ones.
