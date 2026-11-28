# ASM Alpha 8 DEV34 — Project Adaptation (development) and the M4 Real-Data Gate with the Fixed Check (implementation report)

Status: **experimental; NOT promoted; no default changed** (pre-registered; design chosen by the assistant, the project
owner: "I trust you"). **G34-A not passed.** On 59 real bugs no ASM run had touched, learned knowledge repaired none that
the checked workflow without it does not; 2 were needed. With its two DEV33 defects fixed, the check kept every run
within the clock and rejected no developer fix. In development, project adaptation (learning a project's own earlier
fixes) added nothing and was not run on fresh data. Alpha 8 (= milestone 0.4.9) plan items: alpha.8.1/8.2 on real data,
with alpha.8.4 and alpha.8.5. ASM contains no language model and no transformer.

## Headline (read this first)
- **The planned mechanism, project adaptation, failed in development and was dropped before the fresh run.**
  - **The idea:** before repairing a bug, learn the project's own fix examples (DEV17's criteria) from the commits
    before the buggy one into DEV20's libraries.
  - **The measure:** on DEV32's and DEV33's 191 seen bugs (149 measurable), whether phase 3's learned candidates
    contain the developer's fix (AST-equal):

    | libraries | developer fixes reproduced |
    |---|---|
    | DEV20 alone | 2 |
    | DEV20 + the project's own past | 2 (the same) |
    | the project's own past alone, up to 2,000 candidates per function | 1 |
    | + the bug's own fix leaked in, as a diagnosis (80 candidates) | 3 |
    | the same, uncapped (16 measurable bugs before the 2-hour limit) | 11 of 16 (DEV20 alone: 1) |

  - **What it shows:** the learned layers can represent most of these fixes once they have seen one. But a project's
    earlier fixes almost never contain one that recurs in its later bugs. Adaptation would add nothing measurable.
- **The fresh experiment: the M4 real-data gate again** (DEV33's G33-B as G34-A), with the check fixed. 103 bugs were
  mined from 16 new projects, 59 valid. Every accepted patch was read against the developer's fix, with a probe
  (`benchmarks/results/dev34/REALBUGS_REVIEW.md`):

  | | checked (150 s) | checked_learned (+ phase 3's own 150 s) |
  |---|---|---|
  | accepted patches | 1 (pycparser-5) | 1 (the same patch) |
  | correct | 0 | 0 |
  | wrong | 1 (minor: another `ParseError` message) | 1 |
  | resolved only with learned knowledge | — | **0** |

  - A1 (≥ 2 learned-only correct repairs) failed with 0.
  - A2 (no loss) held.
  - A3 (safety: 1 wrong against 1 + 1) held.
  - A4 (the clock: longest learned run 304 s, limit 360; DEV33: 478 s) held.
- **The two fixes to the check worked:**
  - no run passed 360 s;
  - the check rejected none of the 59 developer fixes (DEV33: 1 of 48, from unstable test ids).
- **What it means.** Five attempts at the M4 real-data question are now on record:

  | DEV | learned-only correct repairs | needed |
  |---|---|---|
  | DEV29 | 1 | 2 |
  | DEV31 | 0 | 2 |
  | DEV32 | 2 (with too many wrong patches) | 2 |
  | DEV33 | 1 | 2 |
  | DEV34 | 0 | 2 |

  The learned knowledge from other projects rarely meets a fix it has seen, and a project's own history does not
  supply one either. More of the same knowledge will not pass this gate.

## What DEV34 changed
| piece | code |
|---|---|
| the check, fixed | `asm/coding/faultloc.py`: each regression-suite run gets at most the workflow's remaining time; test ids are compared without memory addresses (`_stable_id`). `tests/test_alpha8_dev34.py`: both tests fail on the DEV33 code and pass now |
| the history miner | `benchmarks/dev17_mine_history.py`: the example loop is `examples(repo, name, rev=...)`, a generator over the commits reachable from a revision; re-mining inflection reproduces DEV17's committed records exactly |
| development | `benchmarks/dev34_development.py` (offline reproduction with DEV20, adapted, own-only, leaked and uncapped libraries) |
| harness, probes | `benchmarks/dev34_realbugs.py` (DEV33's checked arms), `benchmarks/dev34_probes.py` (on `dev33_probes.main`, which now takes probes and a records pattern) |

## Fresh bugs
- **Projects:** bleach, dateparser, faker, falcon, folium, furl, mimesis, oauthlib, parsedatetime, peewee, pycparser,
  pygments, python-benedict, email-validator, python-multipart and tzlocal (`benchmarks/preregistration/dev34_projects.json`).
- **Mined:** 103 bugs. faker 20, python-benedict 13, pycparser 12, dateparser 10, pygments 9, folium and oauthlib 8
  each, mimesis 7, bleach 6, email-validator 5, falcon 4, python-multipart 1. furl, parsedatetime, peewee and tzlocal
  gave none.
- **Valid:** 59 of 103. The rest:

  | reason | bugs |
  |---|---|
  | the fixed version's tests fail | 21 (faker 18: a test dependency is likely missing from the pre-registered list) |
  | not runnable | 12 (dateparser 9) |
  | the tests do not fail on the buggy version | 11 |

  No project was added and no dependency changed after mining.
- **Localization:**
  - 6 bugs had no spectrum: 5 traced runs timed out, and in 1 every failing test changes under tracing.
  - 3 runs ended `unstable_baseline` (pygments-5 in both arms, faker-12 in one).
  - Of 52 ranked bugs, the developer-changed function was first in 23, in the top 5 in 36, and not a suspect in 5.

## Pre-registered evaluation (`benchmarks/preregistration/dev34_study.md`, committed in `be4c51f` before mining)
| criterion | needed | reached | |
|---|---|---|---|
| A1 correct only with learned knowledge (vs checked and checked_long) | ≥ 2 | 0 | ✘ |
| A2 checked-correct bugs lost | ≤ 1 | 0 | ✔ |
| A3 checked_learned wrong | ≤ checked's 1 + 1 | 1 | ✔ |
| A4 longest checked_learned run | ≤ 360 s | 304 s | ✔ |

Raw records: `results/dev34/dev34_*of3.jsonl` (hash-chained); probe `probes.jsonl`; the check's cost
`whole_suite_on_developer_fixes_*of3.jsonl`; verdicts `REALBUGS_REVIEW.md`. The run was not interrupted.

### Reported, not gated
- **Phase 3** was reached in 46 bugs and tested a median of 153 extra candidates there (DEV31: 89). It accepted none:
  40 ran out of time, 4 unresolved, 1 partial, 1 unstable.
- **The check's rejections:** 4 candidates in 2 bugs in each arm.
- **The check's cost:** it rejected 0 of the 59 developer fixes. Suites take a median of 4.3 s; one oauthlib bug's takes
  441 s, longer than the repair budget, so the check cannot finish it.
- **Partial patches** (ASM fixed some failing tests): python-benedict-11, folium-5, folium-8 and mimesis-5 in both arms,
  oauthlib-2 in checked_learned only.
- **Time:** checked median 148 s (max 155), checked_learned median 295 s (max 304).

## Validation
- `python3 -m pytest -q tests/test_alpha8_*.py`: **634 passed, 3 skipped** (631 + 3 new). The 57 PyTorch failures elsewhere
  in `tests/` are unchanged.
- The development run of the fixed check on three of DEV33's seen bugs:
  - markdown-it-py-2 went from 478 s to 303 s, with the same rejections;
  - mistletoe-5 is still repaired by learned knowledge only;
  - dataclasses-json-4 gets DEV33's patch.

## Limitations
- **Project adaptation** was measured offline, against AST-equal developer fixes only. A correct but different patch
  (like DEV32's sqlglot-14) would not count, and the uncapped leaked run covers 16 bugs.
- **59 valid bugs and one accepted patch:** the fresh run says little about the check itself.
- **faker** lost 18 of 20 bugs to its environment, under the pre-registered dependency list.

## What this means, and what is next
- **M4's real-data gate has now failed five times.** The evidence points at the knowledge itself: what ASM learns from
  fixes rarely recurs in new bugs, in other projects or in the same one.
- **Recommended next DEV**, toward the roadmap's DEV34–DEV35 topics: a different source of repair knowledge than
  recurring fix patterns, for example causal reasoning over the failing test.
  - **The idea:** derive what the code should do from the test's expected value and the traced values that lead to it,
    then edit the code that produces the difference.
  - **First step:** test this in development on the seen bugs whose fixes ASM can represent but never meets (the leaked
    diagnosis).
- **Owner decisions:**
  - whether to keep repeating the M4 gate or redesign it;
  - whether `regression_suite` (fixed in DEV34) should become the default for real-bug repair.
