# ASM Alpha 8 DEV33 — The Project's Own Test Suite as an Acceptance Check, on Fresh Real Bugs (implementation report)

Status: **experimental; NOT promoted; no default changed** (pre-registered; design chosen by the assistant at the project
owner's request). **G33-A passed; G33-B did not.** On 48 real bugs no ASM run had touched, the opt-in check halved the
learned arm's wrong patches and lost no correct repair. With it, learned knowledge repaired 1 bug that the checked
workflow without it does not; 2 were needed, and one run overran the clock. Alpha 8 (= milestone 0.4.9) plan items:
alpha.8.4 (negative transfer protection) and alpha.8.1/8.2 on real data, with alpha.8.5. ASM contains no language model
and no transformer.

## Headline (read this first)
- **What DEV33 tests.** In DEV32, 12 of the 14 bugs ASM resolved got a wrong patch, because only the bug's own test files
  decide acceptance. DEV33 adds an opt-in check, `RepairWorkflow(regression_suite=[...])`. A patch must also keep
  passing every test of the project's own suite that passes on the buggy version, or it is rejected and the search
  goes on.
- **Development (DEV32's bugs, seen):** on 30 bugs the check cut wrong patches from 10 to 2 (learned) and from 8 to 1
  (control) and kept every correct one. It would reject 1 of 134 developer fixes.
- **Fresh data:** 61 bugs mined from 16 new projects (fewer than DEV32's 172: these projects have few small test-backed
  fixes), 48 valid. Every accepted patch was read against the developer's fix, with probes
  (`benchmarks/results/dev33/REALBUGS_REVIEW.md`):

  | | control | learned | checked | checked_learned |
  |---|---|---|---|---|
  | accepted patches | 5 | 6 | 3 | 4 |
  | correct | 1 | 2 | 1 | 2 |
  | wrong | 4 | 4 | **2** | **2** |

- **G33-A passed (the check):**
  - **A1:** checked_learned had 2 wrong patches against learned's 4: half, and 2 fewer. Met, exactly at the threshold.
  - **A2:** both correct learned repairs were kept.
  - **A3:** 1 of 48 developer fixes (2.1%) would be rejected, within 5%.
- **G33-B not passed (learned knowledge with the check):**
  - **B1:** 1 bug repaired correctly only with learned knowledge, mistletoe-5 (identical to the developer's fix, and
    not repaired by the checked control even at 300 s); 2 needed.
  - **B4:** one checked_learned run took 478 s, over the 360 s limit.
  - B2 (no loss) and B3 (safety: 2 wrong against 2 + 1) held.
- **What it means.**
  - The project's own tests are a much better acceptance check than the bug's tests alone. Over DEV32's seen bugs and
    DEV33's fresh ones, the learned arm's wrong patches fell from 14 to 4, and the check rejected no correct one.
  - It cannot stop a wrong patch whose behaviour no test covers: markdownify-4, autoflake-2, markdown-it-py-1 and
    dataclasses-json-4's second patch.
  - Learned knowledge still repairs few fresh bugs: 1 here, 2 in DEV32.

## What DEV33 changed
| piece | code |
|---|---|
| the check | `RepairWorkflow(regression_suite=None\|[paths])`, opt-in, default off (`asm/coding/faultloc.py`, ≈ 25 lines). The suite runs once on the original working copy. A candidate that passes the bug's tests and DEV10's contract runs the suite on a copy; if a test that passed there no longer passes, it is rejected (`rejected_regression_suite`, the broken tests in the dossier) and the search goes on. Test modules that cannot be imported do not stop the run (`--continue-on-collection-errors`) |
| the suite | `benchmarks/dev33_development.py: project_suite`: the project's `tests/` or `test/` directory, else its top-level test modules |
| harness | `benchmarks/dev33_realbugs.py` (arms, shards, `--resume`, time control); DEV29's per-bug evaluation resolves per-bug options (a callable of the buggy tree) and records the suite; `benchmarks/dev33_probes.py` |
| tests | `tests/test_alpha8_dev33.py` (4: off by default; a patch that breaks the suite is rejected and the search finds the right one; only the wrong patch leaves nothing accepted; an unimportable module does not stop the suite) |

## Development (data already seen; `benchmarks/results/dev33/development/`)
- **The whole suite on DEV32's 14 accepted patches:** it breaks tests in 8 of the 10 wrong ones and none of the 4 correct
  ones. A first run stopped at sqlglot's collection errors and is kept; the re-run continues past them.
- **On DEV32's 143 developer fixes:** 134 have a suite, and the check would reject 1 (sqlglot-6). 9 have none (pypika
  keeps its tests in the package).
- **The checked arms on 30 of DEV32's bugs:**

  | | wrong patches |
  |---|---|
  | learned | 10 |
  | checked_learned | 2 |
  | control | 8 |
  | checked | 1 |

  Every correct patch was kept. The longest checked_learned run took 325 s.

## Fresh bugs
- **Projects:** markdown-it-py, mdit-py-plugins, mistletoe, uncertainties, bitstring, ftfy, add-trailing-comma, autopep8,
  pycodestyle, freezegun, feedparser, reorder-python-imports, tokenize-rt, idna, construct and dataclasses-json
  (`benchmarks/preregistration/dev33_projects.json`, heads in `results/dev33/environment/repos_heads.txt`).
- **Mined:** 61 bugs from 62 candidate commits.
  - bitstring 20, mistletoe 14, dataclasses-json 9, construct 4; tokenize-rt and idna 3 each; markdown-it-py and
    mdit-py-plugins 2 each; add-trailing-comma, autopep8, freezegun and feedparser 1 each.
  - uncertainties, ftfy, pycodestyle and reorder-python-imports gave none.
  - The set was fixed before mining, so no project was added for the low yield.
- **Valid:** 48 of 61. The rest: the tests do not fail on the buggy version 10, not runnable 2, the buggy version does
  not import 1.
- **Localization:** every bug had a spectrum. The developer-changed function ranked first in 25, in the top 5 in 39,
  and was not a suspect in 4.

## Pre-registered evaluation (`benchmarks/preregistration/dev33_study.md`, committed in `fc7adbe` before mining)
| criterion | needed | reached | |
|---|---|---|---|
| A1 checked_learned wrong vs learned | ≤ half and ≥ 2 fewer | 2 vs 4 | ✔ |
| A2 learned-correct bugs lost | ≤ 1 | 0 | ✔ |
| A3 developer fixes rejected by the check | ≤ 5% | 1 of 48 (2.1%) | ✔ |
| B1 correct only with learned knowledge (vs checked and checked_long) | ≥ 2 | 1 (mistletoe-5) | ✘ |
| B2 checked-correct bugs lost | ≤ 1 | 0 | ✔ |
| B3 checked_learned wrong | ≤ checked's 2 + 1 | 2 | ✔ |
| B4 longest checked_learned run | ≤ 360 s | 478 s | ✘ |

Raw records: `results/dev33/dev33_control_learned_checked_checked_learned_*of3.jsonl`, `dev33_time_control.jsonl`
(hash-chained); probes `probes.jsonl`; the check's cost `whole_suite_on_developer_fixes_*of3.jsonl`; verdicts
`REALBUGS_REVIEW.md`. The run was not interrupted (a background task kept the session alive throughout).

### Reported, not gated
- **The check's rejections:** 10 candidates in the checked arm and 13 in checked_learned, in 4 bugs. The wrong patches
  of dataclasses-json-5 and -8 were stopped with nothing accepted instead. In dataclasses-json-4 the search went on to
  another wrong patch, a `try/except` that no test covers.
- **Time:**
  - medians: control 137 s, learned 280 s, checked 146 s, checked_learned 289 s.
  - longest: checked 330 s and checked_learned 478 s, both on markdown-it-py-2.
  - On markdown-it-py-2 the bug's test is a fuzzer test, a candidate test run timed out, and the suite ran after each
    of 4 rejections.
- **The suites** take a median of 1.7 s on these projects' buggy versions (at most 7.6 s).

## Two defects found in the check (reported; not fixed after seeing data)
- **Its suite runs are not bounded by the remaining budget**, only by the test runner's timeout. That is why the clock
  failed (B4). The fix is to pass the remaining time as the timeout of each suite run.
- **Test IDs that change from run to run count as broken tests.**
  - feedparser's parametrized IDs contain memory addresses (`<function <lambda> at 0x…>`), so its developer fix looked
    like 18 regressions: the one rejection in A3.
  - No accepted patch was affected: no feedparser candidate passed the bug's tests.
  - The fix is to normalise such IDs before comparing.
- **R3 decision:** neither defect changed any accepted patch. The pre-registered check is reported as run.

## Validation
- `python3 -m pytest -q tests/test_alpha8_*.py`: **631 passed, 3 skipped** (627 + 4 new). The 57 PyTorch failures elsewhere
  in `tests/` are unchanged.
- With `regression_suite=None` (the default) the workflow is unchanged: `tests/test_alpha8_dev33.py` checks it, and the
  DEV29, DEV31 and DEV32 tests pass unchanged.

## Limitations
- **Small sample.** 48 valid bugs and 6 with an accepted patch; A1 passed exactly at its threshold (4 → 2).
- **The check only knows what the tests know.** 4 wrong patches over DEV32 and DEV33 broke no test.
- **One run per arm**, and the two defects above.

## What this means, and what is next
- **Owner decisions:**
  - whether to keep `regression_suite` (opt-in), and whether to make it the default for real-bug repair;
  - whether G33-A counts as alpha.8.4 evidence on real data. `alpha8_plan.validated` was not changed.
- **Recommended next DEV:**
  - bound the check's suite runs by the remaining time and normalise unstable test IDs, both small fixes with a
    regression test;
  - then repeat G33-B on more fresh bugs with the check on.
  - The check now makes accepted patches trustworthy enough to make more learned repairs worth seeking.
