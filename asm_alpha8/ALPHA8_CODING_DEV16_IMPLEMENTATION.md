# ASM Alpha 8 Coding DEV16 — A Learning Engine and a Data Pipeline (implementation report)

Status: **experimental; NOT promoted; the pre-registered study has not run yet**, because it needs data from the user's
computer. Built on DEV15. ASM contains no language model and no transformer. An open-source model is used only, on the
user's computer, to write candidate training data, and ASM trusts none of it until its own sandbox has verified it.

## Headline
- **`asm.learning` now learns.** Before DEV16 it stored and ranked records with fixed weights; nothing was fitted.
  `asm/learning/engine.py` (standard library only) adds:
  - logistic regression (AdaGrad + L2, incremental) and naive Bayes;
  - smoothed isotonic calibration;
  - train/test splits that keep whole groups (projects) apart;
  - metrics always beside a no-skill baseline;
  - sealed model files (a tampered model is refused);
  - a rule that model-generated data trains nothing until verified by execution.
- **The repair workflow can learn its candidate order** (`asm/coding/learned.py`). It is opt-in: `ranker=None` is DEV15
  exactly. A ranker reorders only within a phase, so DEV14's repair space is still tried first.
- **Fix-pattern library** (`asm/coding/patterns.py`): abstract fix shapes, and whether ASM can produce a given fix at all.
  First use, on DEV15's real bugs:
  - only **4 of 59** single-function developer fixes are inside ASM's repair space;
  - the commonest fix shape, a changed string/regex literal (**11/59**), is not something ASM can do;
  - one reachable fix (tqdm-4) sat at candidate **#580**, which is why that run hit the time budget.
- **Data pipeline**, tested end to end:
  - `tools/generate_pairs.py` runs on the user's PC against a local Ollama model and never executes downloaded code;
  - `dev16_verify_pairs.py` keeps a pair only if the buggy version makes a passing test fail in the sandbox;
  - `dev16_build_training.py` labels ASM's own candidates against the known fix;
  - `dev16_train_ranker.py` evaluates with each project held out in turn.
- **Pipeline dry run with NON-LLM stand-in bugs:**
  - 632/691 pairs verified;
  - a learned ranker trained with each project held out ranks the true fix first in 81/186 cases, against 48 for the
    DEV15 order (MRR 0.59 vs 0.45; 87 improved, 52 worsened; better in all 7 held-out projects).
  - **This proves the mechanics, not usefulness:** stand-in bugs are ASM's own mutations, in-distribution by
    construction. They are never used for a decision.
- **Two pipeline bugs found by the dry run were fixed** before any real data exists:
  - function extraction and placement mangled methods whose docstrings are indented less than the code;
  - placement could alter the text inside a multi-line string.

## What was built
1. `asm/learning/engine.py`:
   - `FeatureHasher`, `LogisticModel`, `CountModel`, `IsotonicCalibrator`;
   - `group_split`, `evaluate_binary`, `evaluate_ranking`, `train_binary`, `LearnedModel` (sealed save/load);
   - `examples_from_experiences` (connects the existing `Experience` records to training).
2. `asm/coding/learned.py`: `candidate_features` and `CandidateRanker`. `faultloc.RepairWorkflow(ranker=...)` uses it,
   and the dossier notes the ranker's provenance. Every candidate now carries structured metadata; generation order and
   content are unchanged (the DEV15 tests pass unmodified).
3. `asm/coding/patterns.py`: `edit_signature`, `PatternLibrary`, `in_repair_space`.
4. Pipeline:
   - `tools/generate_pairs.py`, `tools/dev16_subjects.json` (392 test-executed functions in 7 subjects), and
     `tools/README_DEV16_DATA.md`;
   - `benchmarks/dev16_subjects.py` (training subjects + `assert_disjoint` from evaluation projects),
     `dev16_subject_manifest.py`, `dev16_verify_pairs.py`, `dev16_build_training.py`, `dev16_train_ranker.py`, and
     `dev16_standin_generator.py`.
5. Pre-registration `benchmarks/preregistration/dev16_study.md`, committed (`4237859`) before any model-generated data
   existed. Decision rule R16-1 lets the ranker become a default only if it beats the DEV15 order on held-out projects
   (MRR, fix within 80 tries, improved > worsened, at least 100 pairs). A real-bug run follows only if it passes, with
   the stated contamination caveat.

## Dry run (stand-in data; `benchmarks/results/dev16/dryrun_standin/`)
- Generated 691; verified 632. Rejected: 45 no test catches the bug, 9 timeout, 5 not runnable.
- The training set was built for 219 pairs (the build was stopped there to save time; it is a pipeline test). 186 have
  the fix inside a generated candidate list, and 199 are in the repair space.
- Leave-one-project-out, within the candidate list that contains the fix:

  | | top-1 | top-5 | MRR | mean rank |
  |---|---|---|---|---|
  | DEV15 order | 48 | 127 | 0.446 | 6.07 |
  | learned | **81** | **142** | **0.587** | **5.00** |

- Candidates tried before the fix over the whole search: median 6 vs 7, within 80: 173 vs 172.
- Per project the learned MRR is higher in all 7. For parse, though, the median total tries got worse (122 vs 102):
  reordering within a block cannot help when the fix sits behind other suspects.

## Validation
- `tests/test_alpha8_coding_dev16.py`: 21 tests, covering:
  - the models learn a real signal and show no skill on noise; incremental updates work;
  - split disjointness, calibration and metrics; seal and tamper refusal; refusal of unverified generated data;
  - fix signatures and repair-space checks;
  - ranker stability, workflow identity without a ranker, and phase protection;
  - the generator's reply checks, an end-to-end run against a fake Ollama server with resume, and placement regressions.
- Full `test_alpha8_*` on the DEV16 code (before the placement fix): 489 passed, 3 skipped, 0 failed. After the fix the
  DEV16 file was re-run (21 passed); the fix touched only the DEV16 pipeline scripts.

## Next step (user)
Run the generator on the PC (`tools/README_DEV16_DATA.md`) and send `pairs.jsonl`. Then: verify, build, train, apply
R16-1, and if it passes run the real-bug evaluation.

## Honest limits
- No result here says ASM got better at fixing real bugs; the study that could say so has not run.
- Ranking cannot reach fixes outside the repair space (55 of 59 real single-function fixes). The pattern library says
  string/regex edits are the biggest missing family.
- The planned evaluation on real bugs is contaminated as pre-registered: the generator model has likely seen BugsInPy.
  A post-cutoff real-bug corpus is DEV17 work.
- Consciousness-related architecture: not touched.
