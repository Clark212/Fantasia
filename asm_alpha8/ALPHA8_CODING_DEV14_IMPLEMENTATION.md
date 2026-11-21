# ASM Alpha 8 Coding DEV14 — Verification Integrity & Generalization (implementation report)

Status: **experimental; NOT promoted. DEV11, DEV12 and DEV13 remain unpromoted.** Built on `asm_alpha8_dev13`
(verified 24/24 against its manifest before use). Earlier releases preserved.
Scope chosen by the user: inputs beyond the tests, real historical bugs, a fresh pre-registered calibration set, and
evidence-chain integrity.
Final `asm.coding` hash: `1dd1abba112418db72163be7fc60c42c6db994b0be7bdb748076291be0bf19b7`. Environment: CPython 3.13.18,
pytest 9.1.1, Linux, 2 CPUs. Real bugs ran under Python 3.8.20 virtualenvs (below).

## Headline (read this first)
- **Real historical bugs (BugsInPy, 83 reproducible).** ASM localizes the function the developer changed reasonably often:
  **41/83 uniquely first, 65/83 within the top 3** (ties counted against ASM). **Repair essentially fails:** the workflow
  accepted a patch for **2/83**, and **both behave differently from the developer's fix**. The tests and the oracle did not
  catch this; I found it reading the two diffs, and an executable probe confirms it. One was labelled **high**.
- **Fresh pre-registered calibration (seed 53, toolz / cachetools / inflection).** With realistic tests, **0/23 accepted
  patches were wrong**. With deliberately weak tests, **5/23 were wrong**, and none of the 5 was labelled high.
- **Pre-registered rules.** R1 demoted `tied_localization`. It fired on 7/42 WRONG decoys and on 27/133 correct
  controls (LR+ 0.82). Under R2, **label ordering is not confirmed**: P(WRONG) is 7% at high, 41% at medium, 35% at low.
- **Inputs beyond the tests** exposed **0 of 79** DEV13 blind-spot decoys, with 0 false alarms. Most of them are
  masked or equivalent edits, not oracle misses.
- **Integrity.** Dossiers are sealed and tamper-evident, and `apply_fix` refuses a tampered or swapped one. Every
  published number is recomputed from hash-chained raw records by `benchmarks/dev14_verify_results.py`, which passes
  5/5 entries here.
- **Six real bugs in ASM were found by this work and fixed, each with a regression test (below).** Two of them
  matter for safety or correctness on real code:
  - ASM **edited a test file** to make a real tqdm bug's test pass.
  - On Python < 3.11, ASM's call recorder **silently recorded nothing**.

## What was built
1. **Evidence-chain integrity** (`asm/coding/integrity.py`).
   - Dossiers are sealed with SHA-256 over canonical JSON (body and provenance) plus a per-step hash chain.
   - `apply_fix` checks, in this order: approval, then the seal, then the binding to the sealed patch hashes, then the
     status and tree fingerprint. It raises an error on a tampered, unsealed or swapped-patch dossier.
   - Benchmark output is written as a hash-chained JSONL with a run manifest on line 0. The manifest records Python,
     pytest, platform, code hash, subject file hashes and the pre-registration hash. A writer refuses to append to a
     broken chain.
   - `dev14_publish.py` writes `results/dev14/summary.json` with the file hashes.
   - `dev14_verify_results.py` checks that each chain is intact, that file hashes match, and that the cited
     pre-registration hash matches the shipped file. It then recomputes every summary.
   - Tested: one changed summary number fails the check, and so does one edited record.
2. **Inputs beyond the test suite** (`asm/coding/generation.py`, `verification.py`).
   - Values are mined from the function's own constants (c-1, c, c+1, and its strings), plus typed boundary values.
     Generation uses single changes and pairs.
   - Crossover takes argument k from one recorded call and puts it into another, so object-heavy code is reached with
     real values.
   - Every input is tagged recorded, perturbed or generated, and results are reported per origin. Inputs identical to
     one already replayed are dropped (DEV14 fix: a re-run of DEV14's own test found duplicates).
   - The DEV14 oracle uses 200 generated inputs, with WRONG on generated inputs only counted if the original program
     ran normally on them.
3. **Project interpreter** (`sandbox.check_python`, `interpreter()`, `SafeTestRunner(python=…)`,
   `run_python_worker(python=…)`).
   - Tests, replay workers and semantic probes run under the project's own Python; ASM itself stays on 3.13.
   - `FaultLocalizer.localize` and `RepairWorkflow.run` apply the runner's interpreter to everything they start.
   - Tested with an interpreter identity only an alternative path has, and on real Python 3.8 with pytest 3.2, 3.10,
     5.4 and 6.2.
4. **Real-bug harness** (`benchmarks/dev14_realbugs.py`). It runs in four stages:
   - **prepare:** partial clones of the projects.
   - **envs:** a Python 3.8 virtualenv per distinct requirement set, with the corpus' *pinned* 2020 requirements.
   - **validate:** the BugsInPy criterion. Buggy source plus the fixed version's test files must fail, and the fixed
     version must pass.
   - **evaluate:** localization rank of the developer-changed functions, then the shipped workflow (150 s budget). An
     accepted patch is compared against the developer's fixed program with the DEV14 oracle, and the fixed test files
     are run on it.

   `dev14_realbugs_audit.py` runs fixed, written probes against the fixed and patched trees.
5. **Fresh calibration**: pre-registered in `benchmarks/preregistration/dev14_fresh_calibration.md` (sha256
   `7d75611f…22bb`, sent to you before the runs), cited in every fresh manifest, applied exactly.
6. **R1 outcome shipped.**
   - `faultloc.INFORMATIONAL_FLAGS = {"tied_localization"}`. The flag and its caveat are still shown, marked
     `[informational]`, but only `confidence_counted` flags set the label. No other rule, weight or threshold changed
     (R3).

## Bugs in ASM found by DEV14 (all fixed, all with regression tests and mutation checks)
| # | bug | how it was found | effect before the fix |
|---|---|---|---|
| 1 | Tests inside the package (`tqdm/tests/tests_tqdm.py`) were not recognised as tests | real bug tqdm-5: the workflow "repaired" it by **editing the test** | test code could be patched. Now: test directories at any depth, `test_*`/`tests_*`/`*_test(s)` modules, conftest, **and every file pytest collected tests from** |
| 2 | Tracing plugin used `code.co_qualname` (Python 3.11+) | first run on Python 3.8 | **no calls recorded at all** on older Pythons, so no behavioural verification. Fallback derives qualnames from source; matches `co_qualname` exactly on 3.13 |
| 3 | pytest < 4 node ids (`f.py::C::()::t`) differ from JUnit's | 5 thefuck bugs refused as "plugin and pytest disagree" | class-based tests could not be localized on old pytest |
| 4 | Exit code 1 with no test run was reported as "tests failed" | a broken conftest in boltons | startup failures looked like real failures (DEV8 test assertion updated accordingly) |
| 5 | Generated inputs could repeat an existing call | re-running DEV14's own test | wasted budget, no wrong result |
| 6 | DEV12 footprint test assumed no generated inputs | full regression | test now checks the DEV12 prediction on DEV12 inputs only |

## Fresh pre-registered calibration (30 detected faults, seed 53; code `14d6f9fd…`, frozen during the runs)
Calibration (each fault repaired under a realistic suite, failing + half the passing tests, and a weak one, failing only):

| | realistic | weak |
|---|---|---|
| plausible single-site patches | 35 judged: 25 restored, 10 equivalent, **0 wrong** (+1 unknown) | 53 judged: **17 wrong** (32%) (+1 unknown) |
| verification available | 27/36 | 42/54 |
| workflow resolved | 24/30 | 24/30 |
| accepted patch WRONG | **0/23** (95% CI 0–14%) | **5/23** (22%, CI 10–42%) |
| labels of the wrong ones (shipped DEV13 rule → R1 rule) | — | low, medium×4 → **medium×5** |
| localization top-1 / top-3 | 20 / 25 | 14 / 22 |

Decoys (true fix + one extra edit, kept only if they pass the repair suite):

| | |
|---|---|
| decoys | 174 rows (87 distinct programs; most kept under both suites) |
| decoy classes | 42 WRONG, 36 equivalent, **96 unknown** |
| controls | 133 correct (110 restored + 23 equivalent) |

- **The 96 unknown decoys** all come from 5 inflection faults in `_irregular`. That function runs only at import
  time, so no call is recorded and nothing can be replayed. Code that runs only at import is a verification blind
  spot.
- **The WRONG decoys are clustered:** 3 faults in `inflection.ordinal` give 23 of the 42. The confidence intervals
  treat rows as independent and therefore understate uncertainty.

| flag (exploratory except R1) | on WRONG decoys | on correct controls |
|---|---|---|
| `alternatives_disagree` | 23/42 (55%) | 4/133 (3%) |
| `underdetermined` | 13/42 | 24/133 |
| `behaviour_unverified` | 13/42 | 43/133 |
| `tied_localization` (R1) | 7/42 (17%) | 27/133 (20%) → **LR+ 0.82, demoted** |
| `behaviour_changed_where_tests_passed` | **0/42** | 10/133 — fires only on correct patches here |
| any flag | 36/42 | 74/133 |

- **R2:** P(WRONG | label) under the R1 rule is 6/82 (7%) at high, 23/56 (41%) at medium, and 13/37 (35%) at low.
  That is **"ordering not confirmed"**. No calibrated-probability claim is made.
- **Sensitivity analysis** (WRONG means `wrong` only): identical. No decoy was classed `wrong_generated`.
- **R1 consequences, unfavourable included.**
  - The one wrong weak-suite patch that was `low` (competing + tied) becomes `medium`.
  - The real-bug thefuck-15 patch becomes **high** (it would have been medium).
  - Several correct patches move up to high.
  - These follow the pre-registered rule; R3 forbids adjusting it after seeing them.
- **Interruption:** the container restarted during the inflection calibration (7/10 done). It was resumed with the
  same code and seed from the next pool position (`--skip=11`); both chains are published.
- **Machine load:** the fresh runs shared the 2-CPU machine with other DEV14 jobs. Workflow time budgets make outcomes
  sensitive to load.

## Inputs beyond the tests: DEV13 decoys re-judged
- 113 distinct programs were re-judged.
- **0 of 79** blind-spot decoys were exposed (one literal-only exposure disappeared once crossover was added and the
  run repeated). The 8 known-wrong decoys were still found. **0 correct patches were turned into false "wrong".**
- 76 of the 79 blind edits are executed by the tests, so they are mostly masked or equivalent mutants, not oracle
  misses.
- **Correction to DEV13:** 10 DEV13 decoy records have ambiguous descriptions (two identical sites on one line). They
  cannot be reconstructed and are reported, not judged. Site descriptions now carry a column when ambiguous, and
  patches are identified by content hash.

## Real historical bugs (BugsInPy: PySnooper, thefuck, tqdm, cookiecutter, httpie, youtube-dl)
- **Corpus:** 96 bugs, of which **83 are valid** (they fail on buggy and pass on fixed under Python 3.8 with pinned
  requirements). The rest:
  - 5 where the bug's test cannot import against the buggy API (not localizable by spectrum)
  - 3 where the fixed version still fails
  - 3 not runnable (cookiecutter's `tox` invocation)
  - 1 that does not fail on buggy
  - 1 with no parsable test command
- **Environment deviations (recorded):**
  - Only Python 3.8 was obtainable; the corpus wants 3.6–3.8.
  - `setuptools<60` was added where unpinned, because modern setuptools breaks old pytest at startup.
  - Two failing pins fell back to unpinned versions.
  - An earlier validation pass installed undeclared test-only imports (`python_toolbox`, `six`, `future`) into shared
    virtualenvs.

| | result (83 bugs) |
|---|---|
| spectrum complete (after node-id fix) | 83/83 |
| developer-changed function ranked 1st (ties pessimistic) / top-3 / top-5 | **41 / 65 / 68** |
| developer's change outside any function / never ranked | 3 / 8 |
| by project, top-3 | thefuck 28/32, youtube-dl 31/38, tqdm 5/9, PySnooper 1/1, httpie 0/2, cookiecutter 0/1 |
| workflow: resolved / unresolved / time budget | **2** / 71 / 10 |
| accepted patches that match the developer's behaviour | **0/2** |

Developer fixes average 3.2 changed lines, and 21 of the 83 touch more than one function. ASM's repair space is a
single-site template edit, which explains most of the 71 unresolved.

The two accepted patches:
- **thefuck-15** (label **high**, oracle "equivalent").
  - ASM changed `B in stderr` to `B not in stderr`. The developer removed condition B.
  - On stderr containing both messages, the developer's `match` returns True and ASM's returns False.
  - No test or recorded input contains both strings, and the oracle mines constants from the *fixed* function,
    which no longer contains B.
- **tqdm-6** (label medium, `behaviour_unverified`, oracle "unknown").
  - ASM negated a `hasattr(…, "__len__")` test.
  - `len(tqdm([1,2,3], total=10, disable=True))` gives 3 in the developer's version; ASM's raises AttributeError.

Before the test-protection fix, a third "accepted patch" (tqdm-5) edited the test file. Those runs were discarded and
all 83 were re-run on the final code.

## Validation actually run
- **New tests:** `tests/test_alpha8_coding_dev14.py` has 41 tests: integrity, apply refusals, provenance, chains,
  generation, crossover, startup error, patch identity, interpreter selection, the qualname fallback, old-pytest node
  ids, test protection and R1.
  - Old-Python tests run when `ASM_TEST_OLD_PYTHON` is set; all pass on pytest 3.2.1, 3.10.1, 5.4.3 and 6.2.5 under
    Python 3.8.
- **Full `test_alpha8_*`:** 442 passed, 1 failed, 2 skipped (378 s).
  - The failure was the DEV8 exit-code assertion contradicting bug fix #4. I updated it and re-ran it: it passes.
  - The test-protection fix (#1) came after that full run. The DEV14 file (41 passed) and DEV11–13 were re-run on it,
    but the whole suite was not re-run after that change.
- **Earlier assertions updated, with reasons in the files:**
  - DEV12 footprint (#6)
  - DEV13 compensating-patch label: R1 makes it medium
  - DEV8 exit code (#4)
- **Historical groups**, identical to the DEV13 baseline: v01 72 passed; v02 13 failed; v03 3 errors; v04 6 failed.
- **Mutation checks:**
  - First pass (integrity, generation, crossover): 17/17 deliberate defects caught.
  - Later checks: interpreter (4), qualname (1), dedupe (1), node id (1), test protection (2) and R1 (2) — all caught.
- **Results verifier:** `python benchmarks/dev14_verify_results.py` gives 5/5 entries reproduced from raw chains.

## Audit
- **Security:**
  - Test code is now protected wherever it lives, including any file pytest collected tests from.
  - The project-interpreter path is validated (an existing executable file). Project code still runs under the DEV8.1
    sandbox: scrubbed environment, rlimits, network namespace, process-group kill.
  - The sandbox is still not an OS security boundary.
  - The real-bug harness clones public repositories and installs their pinned dependencies with uv into throwaway
    virtualenvs; that code runs only inside the sandbox.
- **Latency:**
  - Generation adds up to 100 replayed inputs per verified patch. Its time cost was not benchmarked separately.
  - Real bugs took 56 s mean / 34 s median to localize and repair (150 s workflow budget; maximum 197 s). The fresh calibration took about 8 min per fault.
- **Memory:** replay workers are capped at 1 GB and test runs at 4 GB. Record caps are unchanged from DEV13.
- **Consciousness-related architecture:** not touched by DEV14. Nothing here bears on subjective experience.

## Promotion verdict
**Do not promote.** The bar from the external review (at least 100 real bugs with credible repair rates) is not met:
- Real-bug repair is 2/83, and both accepted patches are wrong.
- Label ordering is not confirmed.
- An oracle "equivalent" verdict was wrong on a real bug.

What DEV14 does establish: localization on real bugs (65/83 in the top 3), evidence that cannot be quietly edited, a
working old-interpreter path, and six fixed defects.

Suggested DEV15:
- multi-site and insertion repairs, sized to real fixes (3 lines across 1–2 functions)
- verification for code that runs only at import time
- oracle inputs mined from the buggy and fixed functions together
- a second pre-registered study of whether any label rule can order risk
