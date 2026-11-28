# Benchmark report — ASM v0.1.1.4

Executed locally with Python 3.12.14. All measured results below come from script output. No GPT-5.6 Sol score was measured.

| Test | Old, 5 training seeds | New, 5 training seeds | Unique queries |
|---|---:|---:|---:|
| original | 40/40 | 40/40 | 8 |
| familiar | 80/80 | 80/80 | 16 |
| audit_paraphrases | 0/80 | 80/80 | 16 |
| passive | 20/40 | 40/40 | 8 |
| exploratory_language | 10/80 | 45/80 | 16 |
| negation_isolation | 0/60 | 60/60 | 12 |

The shipped database and its migrated copy produced the same per-category percentages. Training-order repetitions are not independent test questions.

## Remaining exploratory failures

- `repeated computation drives up processor temperature`: expected THRESHOLD; result unsupported.
- `repeated compression ramps up tank pressure`: expected THRESHOLD; result unsupported.
- `practice enhances skill`: expected ENABLE; result unsupported.
- `study improves knowledge`: expected ENABLE; result unsupported.
- `electrical input pushes voltage upward`: expected TRIGGER; result unsupported.
- `current sends circuit voltage higher`: expected TRIGGER; result unsupported.
- `air pressure gets the membrane moving`: expected TRIGGER; result unsupported.

## Scope and scoring

Fixed synthetic training set; same test cases across versions; no test-query training. Repeated seeds are not independent questions. Audit cases are regression tests. Exploratory cases were added after implementation, but are not an independent evaluation. Scores reflect expected learned continuations, not physical certainty.

The old API was scored using its first RELATION hypothesis; the new API uses its explicit prediction field, including abstention. This measures observable behavior, not an isolated learner comparison. Old passive phrasing can accidentally obtain the right continuation with the wrong subject/object direction. Unit tests separately verify direction in the new parser.

Negation isolation requires both the correct negative structural representation and no affirmative continuation. It is not an evaluation of every form of negation. The model is trained on positive CORE observations for this benchmark; separate tests train negative continuations and competing outcomes.

The original eight-question benchmark includes an exact training prefix. All results are small, synthetic diagnostics. Audit examples are known regressions, not a blind holdout. Exploratory queries were frozen after code implementation and their failures retained.

Graph links and cue transfers are not scored as logically valid answers. Prediction scores are not calibrated probabilities. Host timings exclude database loading and are illustrative, not speed comparisons to GPT.

## Migration provenance

Bundled migrated database integrity check: ok. All 797 original events remain. The stricter grammar retains 92 structural observations; no event rows were deleted.

## Release verification

23 unittest methods passed, plus the original smoke test. First-run demo copying, reopening saved state, EOF shutdown, and an empty start passed. Source database bytes were unchanged; every original event row was preserved. Detailed logs are in results/.
