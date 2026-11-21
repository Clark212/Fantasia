# DEV18 amendments

## A1: three ASM bugs found by an exploratory self-check; run 1 discarded and re-run in full (R3)

**When and how found.** The first pre-registered evaluation run (run 1; ASM code SHA-256 `d07d6946cd21…`, commit
`84c8ed5`) had scored 216 of the 472 fresh problems when an exploratory self-check (`benchmarks/dev18_selfcheck.py`,
not pre-registered) was started to find bugs before any result was reported. It asks, for every fix, whether the
shape learned from that fix alone reproduces the fix when handed its own content. Nothing in the gate, the measures,
the operators, the ranking or the budgets was changed.

**Bug 1 — a saved shape library refused to load (found first: the self-check could not load run 1's library).**
`Shape.var_types` is keyed by int. `ShapeLibrary.save` sealed the body with int keys sorted as numbers; JSON turns
them into strings, which `load` re-sorted as text ("10" < "2"), so any library holding a shape with 11 or more
variables failed its own integrity check. 11 of the 64 shapes learned from the 91 history fixes have 11 or more, so
run 1's `shapes_dev18.json` cannot be loaded. Effect on run 1's scores: none (the evaluation scores the library it
holds in memory; the file is only written). Effect: Q3 loads this file and could not have run.
Fix: keys are written as strings, and the seal is computed over exactly the JSON that `load` reads back.

**Bug 2 — constants JSON cannot hold (same save/load path; latent).** Procedures and shapes are saved as JSON terms.
A `bytes` constant came back from a saved knowledge base as a tuple of ints (so the procedure no longer matched or
wrote the right value), and `complex`/`Ellipsis` constants made saving fail; the shape library failed to save any of
the three. Effect on DEV17/DEV18 results: none (no saved library used by any run holds such a constant; DEV17's
`knowledge_history.json` loads unchanged with its original seal). 15 of the 472 fresh fixes contain such constants,
so a library learned from them (the learning cycle, Q3 after it) would have hit it. Fix: tagged JSON objects
(`term_to_json` / `term_from_json`); files without such constants serialize byte-for-byte as before.

**Bug 3 — a whole f-string could not be rewritten.** `Procedure.apply_detailed` skips nodes inside an f-string,
because their source positions are not reliable; the documented rule. The exclusion set also contained the f-string
node itself, whose position is reliable, so a learned edit whose pattern is an f-string (boltons
`human_readable_list`: `f'{delimiter.strip()} '` -> `delimiter and delimiter.strip() + ' '`) never applied, even to
its own fix. Effect: the fix only makes a top-level f-string eligible as the ROOT of an expression match, which only an
expression pattern rooted at an f-string or at a bare variable can match. None of the 48 expression procedures and
37 expression shapes learned from the history has such a root (wording corrected after the runs: 4 statement
patterns contain an f-string inside them, and statement matching is unchanged), so the static results (Q1, Q2)
cannot change; the learning cycle (Q4) can, through that one fresh fix. Confirmed: all 531 scored rows of run 2
equal run 1's.
Fix: only nodes strictly inside an f-string are skipped.

**Not changed (limits, reported as such).** Edits inside an f-string (a literal part or a `{...}` field; 4 fresh
fixes: attrs `_MinLengthValidator.__call__`, packaging `_process_description_content_type`, `Requirement._iter_parts`,
`release`) stay unsupported, as the DEV17 code documented before the pre-registration. Supporting them would extend an
operator after seeing fresh data, which R3 forbids. The same holds for edits with more than `MAX_HOLES` = 2 holes.

**Regression tests** (`tests/test_alpha8_coding_dev18.py::SerializationTests`, each fails on the code of run 1):
`test_a_shape_with_eleven_or_more_variables_survives_save_and_load`,
`test_bytes_and_ellipsis_constants_survive_save_and_load`, `test_a_whole_f_string_can_be_rewritten_but_not_its_parts`;
`test_knowledge_saved_by_dev17_still_loads_with_its_seal` guards backward compatibility.

**Self-check after the fixes (exploratory).** Own shape + own content, no caps: history 64/64, BugsInPy 37/37, fresh
321/325 (the 4 f-string interiors above) of the fixes whose edit can be abstracted at all (history 64/91, BugsInPy
37/59, fresh 325/472; the rest have more than 2 content holes or no single changed region).

**Action (R3).** Run 1 is discarded and kept (`benchmarks/results/dev18/discarded_run1/`). The evaluation is re-run in
full, unchanged, on the fixed code (run 2). Run 1 is allowed to finish only as a consistency check: none of the three
fixes is on the scoring path of Q1/Q2, so run 2's Q1/Q2 rows are expected to equal run 1's. Any difference will be
reported.
