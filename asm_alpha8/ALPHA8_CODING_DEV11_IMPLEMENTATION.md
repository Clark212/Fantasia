# ASM Alpha 8 Coding DEV11 — Semantic Fault Localization & Verified Repair (implementation report)

Status: **experimental; NOT promoted**. Built on `asm_alpha8_dev10` (DEV8.1, DEV9, DEV10 carried along). All earlier releases preserved.
Roadmap note: this replaces the roadmap's DEV11 (Contextual Repository Memory), which is deferred. It overlaps roadmap DEV13/DEV14 (debugging, adaptive repair); the evidence dossier is a first step toward repository memory.

## What it does
`CodingAgent.localize_fault(root)` and `CodingAgent.repair_failing_tests(root)` (`asm/coding/faultloc.py`):
1. **Localize** failing tests to functions from three evidence sources, each reported separately:
   *spectrum* (per-test line coverage collected by a pytest plugin inside the DEV8.1 sandbox; Ochiai, aggregated to functions), *traceback* (innermost repository frame strongest), *semantic* (DEV10 findings such as `likely_bug`/`name_behavior_mismatch` for top candidates). Fixed weights 0.5/0.35/0.15 (set before any benchmark run).
2. **Trace impact** with the DEV9 call graph (transitive callers) and the number of tests that execute each suspect.
3. **Investigate fixes** with DEV8.1: single-site template edits (operator, comparison, constant, boolean, negated condition) ordered by line suspiciousness; each verified in a sandboxed copy with stability-checked baseline, regression/vanished/skipped-test detection and confirmation re-run. Multi-fault repos are handled iteratively (partial fix, re-localize, continue).
4. **Reject plausible-but-wrong patches**: a DEV10 behavioural contract (a patch may not destroy a function that already behaved like a recognised reference, nor introduce new high-severity behavioural findings).
5. **Preserve evidence**: a `Dossier` (JSON + Markdown) with the suspect ranking and per-source scores, every rejected candidate and why (regression / vanished test / contract / duplicate / still failing), why the accepted patch was accepted, impact, a DEV10 before/after behavioural check, a behavioural verdict, **caveats**, and an explicit "what this does not establish".
6. **Never applies by itself.** `RepairWorkflow.apply_fix(root, dossier, approved=True)` needs explicit approval, refuses if the repository changed since the dossier, refuses partial/unresolved dossiers unless `allow_partial`, and writes backups.
Also: the text-preserving mutation engine (`enumerate_sites`), which doubles as the benchmark's fault injector.

## Validation actually run
- **Tests:** 42 new; `test_alpha8_*`: **335 passed** (+1 added afterwards and run alone), historical groups identical to the baseline recorded earlier (v01 72 passed; v02 13 failed; v03 3 errors; v04 6 failed; PyTorch absent here).
- **Mutation check:** 20 deliberate defects in the new logic; 17 caught first time, 3 survived because my tests were weak (an accidentally-ordered tie fixture; a regression guard masked by the behavioural contract; an inverse-property test that never reached `*`), all fixed and re-verified: **20/20 caught.**
- **Seeded-fault benchmark on real code** (`benchmarks/dev11_seeded_faults.py`; raw results in `benchmarks/results/`): faults injected one at a time into the ASM coding package, kept only if its own tests detect them. Subjects: `understanding.py`, static/matching parts of `semantics.py`, and seven DEV6/7 core modules. Seeds fixed; evidence weights fixed beforehand.

### Localization — 40 detected faults (pessimistic rank: every tied function counted ahead of the truth)
| source | top-1 | top-3 | top-5 | top-10 | notes |
|---|---|---|---|---|---|
| **combined** | 27/40 (68%) | 35/40 (88%) | 35/40 | 39/40 | 1 unlocalised (function ran only at import time) |
| spectrum alone | 18/40 | 33/40 | | | ties are the main weakness |
| traceback alone | | | | | fires on only 17/40 faults (exception raised inside repo code); rank 1 every time it fires |
| **semantic (DEV10)** | **0/40** | | | | **contributed nothing on real faults** |
The combined gain over spectrum comes from traceback evidence, not DEV10.

### Repair — 17 of those faults (subset; 90 s budget; held-out tests the repair never saw)
- **Resolved (tests pass): 11/17.** Of these: 8 exact restoration of the original program, 1 logically equivalent, **2 overfit** (one patched an unrelated function with a compensating bug; one patched the right function with different behaviour). **Both overfits also passed the held-out tests and the full original suite**, so passing held-out tests is *not* sufficient evidence of correctness here.
- So: **correct 9/17 (53%), plausible-but-wrong 2/17 (12%), not resolved 6/17 (35%)** (3 unresolved, 1 partial, 2 out of time on functions with many edit sites).
- DEV10 on real faults: **0** contract rejections and **0** `still_deviant` verdicts. Its value is demonstrated only on constructed fixtures (tie-break, rejecting a destructive `+1 -> +2` patch, showing a bug persisted after a plausible patch).
- **Caveats** (ambiguity: other edits also pass; tie: localization tied with other functions) were added *after* seeing the overfits. Post hoc on 10 repaired cases: both overfits flagged, 2 of 8 correct patches also flagged. Treat a caveat as "review this", not "wrong".

## Bugs found by my own tests during this work (all fixed, all covered)
The behavioural verdict was computed after the patch was applied (silently "unchecked"); `not`-removal deleted a parenthesis; choice among several passing candidates depended on timing noise (now evidence order); `list`-style ties made the first plausible patch win unnoticed (now a caveat); the workflow initially accepted `helper: +1 -> +2` because it passed the tests.

## Limits — read before relying on this
- **Optimistic benchmark.** Repair templates are the inverse of the injection templates, so every injected fault is repairable in principle; real bugs are rarely single-site operator edits (a fixture shows an unrepairable string bug and a two-test contradiction). Only 17 repairs: the 95% interval on 11/17 is roughly 39–85%. Subjects are one codebase, and faults were kept only if its tests detect them.
- **No baseline was run** (e.g. random function order or no localization), so this does **not** show localization improves repair over unlocalized search.
- Localization quality is limited by test coverage: with one failing and one passing test covering the same functions, suspects tie. Tracing uses `sys.settrace` (slow on heavy suites, main thread only, subprocess code untraced).
- Regression protection covers only the targets you pass. Passing tests is evidence, not proof (see the overfits).
- Python/pytest only; flaky baselines are refused; probing for DEV10 evidence executes repository code in the DEV8.1 sandbox, which is not an OS security boundary.
- No consciousness-related claim: everything is deterministic tracing, ranking, sandboxed test execution and text edits.

## Promotion gate for DEV11
(1) Real bug corpus from foreign repositories (not injected faults, not this codebase), >=100 bugs with confidence intervals; (2) baselines: random order, spectrum-only, DEV8.1-only; (3) stronger oracles for patch correctness (independent tests, mutation score of the suite) and caveat calibration; (4) a measured case where DEV10 evidence improves localization or rejects a real bad patch; (5) multi-site repair or an honest scoping of what is out of reach; (6) human review of the apply path and sandbox in a real container.
