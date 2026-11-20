# DEV16 pre-registration: learning from language-model-generated bugs

Written and committed to git before any language-model-generated data exists (the generator has not been run).
Its SHA-256 is recorded in every DEV16 run manifest. Anything not listed here is exploratory and labelled as such.

## Principle
ASM contains no language model and no transformer. An open-source model (planned: `qwen2.5-coder:7b` via Ollama, on
the user's computer) is only a source of candidate DATA. Nothing it produces is trusted: a pair is used only after
ASM's sandbox has shown that the buggy version makes a test fail that passes on the original.

## Data
- Generator: `tools/generate_pairs.py`, prompt version `dev16-bug-v1`, seed 16, temperature 0.7, 6 bug kinds per
  function. Model name and digest are recorded per pair; if a different model is used, it is reported, and the rules
  below apply unchanged.
- Training subjects (`benchmarks/dev16_subjects.py`, manifest `tools/dev16_subjects.json`): toolz 1.2.0, cachetools
  8.0.0, inflection 0.5.1, semver 3.0.4, parse 1.20.2, more-itertools 10.5.0 (recipes, and more as a separate subject).
  None is a project of an evaluation corpus (`assert_disjoint`).
- Verification: `benchmarks/dev16_verify_pairs.py` (criterion above; new risky constructs are rejected unrun).
- Training rows: `benchmarks/dev16_build_training.py` (labels: candidate AST-equal to the original).
- Stand-in data (`generator == "standin_mutation"`) is for pipeline testing only and is never used for a decision below.

## Questions and decision rules (fixed in advance)
- **Q1, data quality (descriptive).** Report the fraction of generated pairs accepted locally, verified, and rejected per
  reason; verified pairs by bug kind and subject.
- **Q2, coverage (descriptive).** Fraction of verified pairs whose fix is in ASM's repair space (`in_repair_space`),
  and the most common signatures of the unreachable ones. This ranks candidate repair families for DEV17; no claim
  that adding a family will help.
- **Q3, learned ranking. Decision rule R16-1.** Leave-one-project-out over the training subjects, logistic ranker,
  pairs whose fix appears in a generated candidate list. Let L and G be the learned and given (DEV15) orders.
  - The ranker may be offered as a RepairWorkflow default only if ALL hold on the pooled held-out pairs:
    (a) MRR(L) > MRR(G); (b) pairs with the fix within the first 80 candidates tried: L > G; (c) improved > worsened;
    (d) at least 100 held-out pairs with a reachable fix. Otherwise "not adopted" and `ranker=None` stays the default.
  - Folds are reported individually; a project where L is worse than G is reported as such.
- **Q4, real bugs (run only if R16-1 passes).** The DEV15 real-bug evaluation (83 BugsInPy bugs, same harness and budget)
  with the trained ranker. Every accepted patch is read by a person against the developer's fix, as in DEV15. Report
  resolved, correct and wrong counts beside DEV15 (9 resolved, 4 correct).
  - Caveat fixed in advance: the generator model was trained on public GitHub code, which likely includes BugsInPy's
    projects and fixes. The ranker never sees BugsInPy code (training subjects are disjoint), but the bug SHAPES it learns
    from could reflect memorized fixes. A real-bug corpus fixed after the model's training cutoff is DEV17 work, and only
    such a corpus can give an uncontaminated real-bug number.
- **Promotion.** Not promoted in DEV16 whatever the results (real-bug corpus < 100, and Q4 is contaminated as stated).
- **R3.** No feature, model setting, threshold or rule is changed after seeing generated data, except through R16-1.
  Bugs found in ASM are fixed with a regression test; affected runs are discarded, kept, and re-run in full.
- **R4.** Every result is reported, including unfavourable ones.
