# ASM Alpha 8 Coding DEV15 — Repair Beyond Single Sites (implementation report)

Status: **experimental; NOT promoted** (fixed in advance: the corpus has 83 real bugs, below the external bar of 100).
DEV11–DEV14 remain unpromoted. Built on `asm_alpha8_dev14` (verified 42/42 against its manifest before use).
Scope: DEV14's four suggestions, in full: multi-site and insertion repairs, verification of import-time code, oracle
inputs mined from every version, and a second pre-registered label-rule study.
Final `asm.coding` hash: `62e7e2e3564f5a32b7c2073a84af75befb4e802cdd8ba0fc971ef1b423bfd5ad` (the same hash in every
published run manifest). Environment: CPython 3.13.18, pytest 9.1.1, Linux, 4 CPUs; real bugs under Python 3.8.20.

## Headline (read this first)
- **Real bugs: 9 of 83 patched, 4 correct.** DEV14 accepted 2 patches on the same 83 bugs and 0 were correct.
  - Correct: thefuck-9 and youtube-dl-28 are identical to the developer's fix; youtube-dl-29 and thefuck-22 are
    behaviourally equivalent. **All four come from the new families** (try/except ×2, statement guard ×2).
  - Wrong: thefuck-15, thefuck-21, tqdm-6, tqdm-8, youtube-dl-11. Every patch was read against the developer's diff,
    with probes where needed (`benchmarks/results/dev15/REALBUGS_REVIEW.md`).
- **Labels still do not work.** 6 real-bug patches were labelled high; 3 of them are wrong.
  - Pre-registered L15 label rule: **not confirmed** on fresh decoys (high 40%, medium 0%, low 92% WRONG).
  - The DEV14 rule (still shipped) does not order risk on the same data either (42% / 64% / 19%).
  - 57 of the 103 WRONG decoys carry no warning flag at all.
- **Safety gate passed.** On 24 fresh injected faults with realistic tests, 0/18 accepted patches were wrong with DEV15
  families, and 0/18 with DEV14's repair space.
  - With failing-tests-only suites: 3/17 vs 1/15. Both extra wrong patches use the new families (a variable swap and a
    statement guard).
- **The DEV15 oracle still errs on real bugs.** It called tqdm-8 and youtube-dl-11 `equivalent`; probes show both are
  wrong. It now catches thefuck-15 (DEV14's miss).
- **One ASM safety bug was found during the pre-registered runs, fixed, and every run was restarted.** A `try/except`
  around a context manager's `yield` swallowed the *test's own* exception (cookiecutter-4, labelled high).
- **Cost.** Real-bug runs now average 118 s (DEV14: 56 s), and 34 bugs hit the 150 s budget (DEV14: 10). The second
  phase spends the remaining budget where DEV14 gave up early.

## What was built
1. **Repair families** (`asm/coding/repair_ops.py`). The shapes were chosen from the 60 developer fixes of ≤3 lines in
   the DEV14 corpus:
   - `name`: a local/parameter read replaced by another one bound strictly earlier. Similar names are ranked first,
     with up to 3 options.
   - `drop_clause`: one operand removed from an `and`/`or`.
   - `getattr`: `obj.attr` read becomes `getattr(obj, 'attr', None)`; never applied to a method being called.
   - `guard_return`: `if p is None: return D` at function entry. D is None, `[]`, or a literal the function already
     returns. Never added to generator functions.
   - `guard_stmt`: a simple statement on an executed line wrapped in `if N:` / `if N is not None:`.
   - `try_except`: the same wrapping with `try/except E: pass`. E is a builtin exception named in a failing traceback,
     never AssertionError.
   - `pair`: two non-overlapping site edits in one function, from the most suspicious lines (≤36 pairs).
   - Deliberately excluded: statement deletion (the classic test-overfitting edit), string/regex edits, new calls.
   - No wrapper or guard is placed around `yield` / `yield from` / `await` (amendment A1).
2. **Two-phase search** (`faultloc.RepairWorkflow`, `extended_ops=True` by default).
   - Phase 1 is exactly DEV14's repair space over every suspect.
   - Phase 2, the new families, runs only if phase 1 accepts nothing. Wherever DEV14 repairs a fault, DEV15 makes the
     same patch (tested).
   - Found on a smoke run before freezing: mixing the families into one ordering pushed a correct DEV14 fix past the
     per-suspect cap.
3. **Alternatives as evidence.**
   - Alternatives are also drawn from the new families, even when a DEV14 template was accepted. This is how
     thefuck-15's `not in` patch now gets `alternatives_disagree` (label medium, DEV14: high).
   - **Minimal-repair rule:** a pair is never an alternative to an accepted single edit. "Fix + extra edit" is a decoy,
     and counting it made every fix look underdetermined (found by the DEV12/13 confidence tests).
4. **Import-time verification** (`verification.verify_import_state`). A module-level function called while its module
   is imported (statically detected) has no recorded calls. It is now judged by:
   - the module's state right after import;
   - replays of the recorded calls of the other functions in the module.

   `re.Pattern` objects are encoded by pattern text and flags; DEV14 encoded every Pattern as an identical empty object.
   On inflection's `_irregular` (DEV14's 96 unknown decoys), an equivalent edit shows footprint 0 and a wrong one is
   caught on `pluralize('salesperson')`.
5. **Inputs mined from every version** (`generation.py`, `verification.generation_plan`).
   - Constants come from the target function in the original and in every compared version, found by qualified name so
     inserted lines do not break the lookup.
   - Strings up to 80 characters (was 20).
   - Mined strings are joined in pairs and appended to recorded values.
   - Mined values come before generic ones. With several arguments, DEV14's round-robin budget never reached them.
   - All three changes were needed before thefuck-15's distinguishing input (stderr containing both messages) appeared.
6. **Benchmarks.**
   - `dev15_oracle.py`: the DEV14 oracle plus the import-time mode (state-only differences are `unknown`) and
     all-version mining.
   - `dev15_realbugs.py`: evaluate stage; stores both diffs.
   - `dev15_calibration.py`: paired DEV15/DEV14 runs on the same faults.
   - `dev15_decoys.py`: the DEV14 protocol on the fresh subjects.
   - `dev15_subjects.py`, `dev15_summaries.py` (L1/G1 exactly as written), `dev15_publish.py`,
     `dev15_verify_results.py`.

## Pre-registration and integrity
- `benchmarks/preregistration/dev15_study.md` was committed (`8e93d03`) and pushed before any study data existed.
  - Its sha256 `0fb331f3…66e7` is cited in every run manifest.
  - The push initially failed (no GitHub access) and succeeded later, so the git commit time is the timestamp.
- **Amendment A1** (`dev15_amendments.md`): the cookiecutter-4 bug, fixed under the pre-registered bug clause.
  - First-launch records are published in `results/dev15/discarded_run1/`.
  - A seconds-long launch before that wrote only manifests, which were deleted.
- `python benchmarks/dev15_verify_results.py` → 4/4 entries reproduced: intact chains, the shipped pre-registration
  cited, one code hash across all runs, summaries recomputed.

## Fresh pre-registered study (seed 89; semver 3.0.4, parse 1.20.2, more-itertools 10.5.0; never used before)
**Calibration**, 24 faults, each run twice (DEV15 / DEV14 repair space, 150 s):

| | realistic: DEV15 | realistic: DEV14 | weak: DEV15 | weak: DEV14 |
|---|---|---|---|---|
| resolved | 19 | 19 | 17 | 15 |
| accepted WRONG / judged | **0/18** | **0/18** | 3/17 | 1/15 |
| unresolved / time budget | 0 / 5 | 3 / 2 | 0 / 3 (+4 partial) | 3 / 2 (+4 partial) |
| families of accepted patches | single_site 19 | single_site 19 | single_site 15, name 1, guard_stmt 1 | single_site 15 |

- **G1 passed:** the families stay on by default.
- Realistic suite: the families never produced an accepted patch, because these faults are single-site by construction.
  Their only effect was spending the remaining budget (3 DEV14 "unresolved" became DEV15 "time_budget").
- Weak suite: 2 of the 3 DEV15 wrong patches are new-family patches on faults DEV14 left unresolved. For
  `if kwargs:` and `match_expr -> version`, a correct-looking test pass hides wrong behaviour.

**Decoys:** 30 faults, 324 rows; 103 WRONG decoys, 116 correct controls.

| flag | on WRONG decoys | on correct controls |
|---|---|---|
| `alternatives_disagree` | 46/103 (45%) | 4/116 (3%) — LR+ ≈ 13, again the only strong flag |
| `tied_localization` | 35/103 | 50/116 |
| `behaviour_changed_where_tests_passed` | 3/103 | 8/116 |
| `behaviour_unverified` | **0/103** | 25/116 |
| `underdetermined` | **0/103** | 13/116 |
| none of the counted flags | **57/103** | |

- **L1:** L15 gives high 57/144, medium 0/25, low 46/50, so the ordering is **not confirmed** and the DEV14 rule stays.
  - Medium (unverified / underdetermined) fired only on correct controls here.
  - The DEV14 rule gives 42% / 64% / 19%, also not ordered.
  - Conclusion across DEV14 and DEV15: `alternatives_disagree` is a strong warning; no three-level label built from these
    flags has ordered risk on fresh data.
- Clustering: 6 faults contribute 75 of the 103 WRONG decoys; confidence intervals treat rows as independent.
- `behaviour_unverified` fell from 31% of DEV14's wrong decoys to 0%. Import-time code is the main reason
  (16 unknown decoys remain).

## Real historical bugs (BugsInPy; same 83 valid bugs as DEV14, re-validated from scratch)

| | DEV14 | DEV15 |
|---|---|---|
| developer's function ranked 1st / top-3 / top-5 | 41 / 65 / 68 | 41 / 65 / 68 (localization unchanged) |
| resolved / unresolved / partial / time budget | 2 / 71 / 0 / 10 | **9** / 39 / 1 / 34 |
| accepted patches correct (person-read) | 0/2 | **4/9** |
| accepted families | single_site 2 | try_except 4, guard_stmt 2, single_site 2, name 1 |
| developer's fixed tests pass on the patch | 2/2 | 9/9 |

Per-patch verdicts with probes are in `benchmarks/results/dev15/REALBUGS_REVIEW.md`:
- tqdm-8 is a half fix: one of the two renames.
- youtube-dl-11: `str_to_int(5.5)` returns 5.
- thefuck-21 returns None instead of False.
- tqdm-6: same wrong negation as DEV14.
- thefuck-15: same wrong patch, now labelled medium and classed wrong by the oracle.

25 of the 34 time-budget bugs are youtube-dl, where test runs are slowest.

## Bugs in ASM found by DEV15 (all fixed, each with a regression test that fails when the fix is reverted)
| # | bug | found by | effect before the fix |
|---|---|---|---|
| 1 | try/except or guard placed around `yield` | pre-registered real-bug run (cookiecutter-4) | **the test's own exception was swallowed**; patch accepted with label high. All runs restarted |
| 2 | one mixed candidate ordering | fresh-subject smoke run (parse) | lost a repair DEV14 makes |
| 3 | pairs counted as alternatives | DEV12/DEV13 confidence tests | nearly every fix flagged `alternatives_disagree` |
| 4 | name swap allowed a name bound on the same line | mutation check M8 | `x = f(y)` could become `x = f(x)` |
| 5 | strings >20 chars never mined, generic values first, no combined strings | thefuck-15 re-judged | the oracle and verification could not find the distinguishing input |
| 6 | `re.Pattern` encoded as an empty object | import-time tests | every compiled-regex state looked identical |

## Validation actually run
- `tests/test_alpha8_coding_dev15.py`: 27 tests. They cover:
  - DEV14 equivalence of the default generation, relative order, singles before pairs, test-file protection;
  - each family, with end-to-end repairs for name / insertion / pair;
  - phase identity with DEV14, the thefuck-15 shape, the minimal-repair rule;
  - mining, qualname lookup, import-time detection and verification, Pattern encoding;
  - both oracle modes, and the yield regression.
- **Mutation checks:** 11/11 deliberate defects caught (10 before freezing, plus the A1 fix). M8 was missed at first
  and exposed bug #4.
- **Full `test_alpha8_*`:** 467 passed, 3 skipped before freezing; **469 passed, 3 skipped, 0 failed** on the final code (617 s).
- **Unchanged:** the historical groups (v01–v04) and the DEV14 benchmark scripts; DEV14's results verifier is untouched.

## Audit
- **Security:**
  - New families never edit test files (the DEV14 protection applies to every candidate).
  - No wrapper is placed around suspension points.
  - Project code runs only inside the DEV8.1 sandbox, which is still not an OS security boundary.
  - Fresh sdists' test suites were run only through the sandboxed runner.
- **Latency:** phase 2 roughly doubles real-bug time (mean 118 s, median 141 s, max 207 s; budget 150 s).
- **Memory:** unchanged caps (1 GB replay, 4 GB tests).
- **Consciousness-related architecture:** not touched. Nothing here bears on subjective experience.

## Promotion verdict
**Do not promote** (pre-committed).
- First real correct repairs: 4/83 real bugs.
- Labels are not trustworthy: half the high-labelled real-bug patches are wrong, and no rule ordered risk on fresh data.
- The oracle's `equivalent` needs a person on real bugs.

Suggested DEV16:
- Make `alternatives_disagree` the primary warning and stop presenting a three-level label. Pre-register a two-level
  "warning / no warning" claim instead.
- Search for disagreeing alternatives more widely on high-labelled patches; 57/103 wrong decoys had no flag.
- Make the phase-2 budget separate and bounded, so DEV15 is not slower where it adds nothing.
- Grow the real-bug corpus past 100 (more BugsInPy projects need older interpreters or Docker).
- Add to the oracle a check that runs the developer's tests from other files on the patch (untested whether it would
  have caught tqdm-8 or youtube-dl-11).
