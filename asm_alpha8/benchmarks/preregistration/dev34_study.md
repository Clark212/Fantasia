# DEV34 pre-registration: the M4 real-data gate again, with the acceptance check fixed, on freshly mined real bugs

Written and committed to git before any fresh bug was mined. Its SHA-256 is recorded in the DEV34 run manifests. Anything
not listed here is exploratory. Alpha 8 (= milestone 0.4.9) plan items: alpha.8.1/8.2 on real data (the M4 real-data
question), with alpha.8.4 and alpha.8.5. Nothing is promoted in DEV34 and no default changes. Design chosen by the
assistant (the project owner: "I trust you", 2026-11-27).

## Question
Does learned knowledge (DEV20's sealed libraries, in phase 3 with DEV31's own clock) repair fresh real bugs that the
workflow without it does not, without extra wrong patches, when every accepted patch must also keep the project's own
test suite passing (DEV33's check, with its two defects fixed)? This is DEV33's G33-B, unchanged, on new bugs.

Earlier attempts at this question, all reported: DEV29 (1 of 2 needed, seen bugs), DEV31 (0 of 2), DEV32 (2 of 2, failed
on safety), DEV33 (1 of 2, failed on the clock). The question is repeated, not changed; a pass here is one pass in five
attempts and is reported as such.

## What changed before this commit (development only)
- **The check's two DEV33 defects** (`asm/coding/faultloc.py`, `tests/test_alpha8_dev34.py`; each test fails on the
  DEV33 code and passes now):
  - a suite run gets at most the workflow's remaining time (DEV33's markdown-it-py-2 ran 478 s);
  - test ids are compared without memory addresses (`<function <lambda> at 0x…>` in DEV33 feedparser-1's ids).
- **The harness** `benchmarks/dev34_realbugs.py` (DEV33's arms and per-bug evaluation).
- **`benchmarks/dev17_mine_history.py`**: the example loop is a generator over the commits reachable from a revision
  (re-mining inflection reproduces DEV17's committed records exactly). Used only by the development study below.

## Development (data already seen; `benchmarks/results/dev34/development/`)
- **Project adaptation, the mechanism first planned for DEV34, is not run on fresh data.** On DEV32's and DEV33's 191
  seen bugs (149 measurable), each project's fix examples (DEV17's criteria) from the commits before the buggy one were
  learned into DEV20's libraries:

  | libraries, phase 3's candidates | developer fixes reproduced (AST-equal) |
  |---|---|
  | DEV20 alone | 2 (astroid-4, mistletoe-5) |
  | DEV20 + the project's own past | 2 (the same) |
  | the project's own past alone, up to 2,000 candidates per function | 1 (mistletoe-5) |
  | DEV20 + own past + the bug's own fix (leaked, a diagnosis), phase 3's 80 | 3 |
  | the same, uncapped (34 of 191 bugs before the 2-hour limit; 16 measurable) | 11 of 16 (DEV20 alone: 1) |

  The learned layers can represent most of these fixes once they have seen them, but a project's earlier fixes almost
  never contain one that recurs in its later bugs. Adaptation would add nothing measurable, so it is left out.
- **The fixed check on three of DEV33's seen bugs** (`fixed_check_on_dev33_bugs.jsonl`): markdown-it-py-2's checked_learned
  run takes 303 s (DEV33: 478 s) and checked 155 s (330 s), with the same rejections; mistletoe-5 is still repaired
  by checked_learned only, and dataclasses-json-4 gets the same patch as in DEV33 in both arms.

## Fresh bugs
- **Projects** (`benchmarks/preregistration/dev34_projects.json`, with the dependency names given to the resolver):
  bleach, dateparser, faker, falcon, folium, furl, mimesis, oauthlib, parsedatetime, peewee, pycparser, pygments,
  python-benedict, email-validator, python-multipart and tzlocal.
  - **Chosen as:** pure Python; the package at the repository root and a root `tests/` directory; no plugin needed by
    the pytest options; pytest-runnable; active in the window; long histories of small fixes, for more bugs than
    DEV33's 48.
  - **Never used by ASM:** none is a BugsInPy project, a DEV13–DEV21 subject or mined project, or a DEV31–DEV33
    project. Some may have been installed before as dependencies of earlier bugs; no ASM run repaired them.
  - **Seen before this commit:** only depth-1 clones, to read the top-level file list and the packaging and pytest
    configuration. No history, no commit and no test was looked at.
  - **Left out:** charset_normalizer (`src/` layout), gunicorn, holidays and diskcache (coverage options), dacite
    (benchmark plugin options), recurring-ical-events (tests inside the package).
- **Mining, environments, VALID:** DEV32's, unchanged (`dev32_mine_bugs.py`; window 2023-01-01 to 2026-10-31; ≤ 20 bugs
  per project, seed 32; Python 3.11; DEV14's envs and validate). No project is added or swapped after mining.

## Arms (`benchmarks/dev34_realbugs.py`; DEV29's per-bug evaluation)
- **checked:** the shipped workflow with DEV15's repair families, 150 s, with the project's suite as regression suite.
- **checked_learned:** the same with DEV20's sealed libraries in phase 3 and 150 s of its own (DEV31).
- **checked_long:** checked with 300 s, on every bug checked_learned resolves and checked does not.
- The unchecked control and learned arms of DEV33 are not run (G33-A passed; the check's rejections are in the records).
- **Running:** the arms are paired, one after the other in one process per bug. 3 detached shards (bug index modulo 3),
  a background task keeps the session alive, nothing else runs on the machine. A run stopped by the machine is
  finished with `--resume`.
- **Sandbox:** tests run only through ASM's `SafeTestRunner`.

## Judging each accepted patch (as DEV31–DEV33)
Every patch accepted (`resolved`) in any arm is read against the developer's patch, with the verdict correct or wrong
(DEV15's definition). A probe on a distinguishing input decides when reading alone does not; it runs in the bug's
environment inside ASM's sandbox. Verdicts, reasons and probes go into `benchmarks/results/dev34/REALBUGS_REVIEW.md`.

## Gate G34-A (= G33-B on these bugs; person-read verdicts)
- **A1 learned repairs:** at least 2 bugs are repaired correctly by checked_learned, and correctly neither by checked
  nor by checked_long.
- **A2 no loss:** at most 1 bug that checked repairs correctly is not repaired correctly by checked_learned.
- **A3 safety:** checked_learned's wrong accepted patches number at most checked's plus 1.
- **A4 the clock holds:** no checked_learned run takes longer than 360 s.
- **Passes iff A1-A4 all hold.**

## Reported, not gated
- the mining counts and the attrition, per project and reason;
- the check: suites, rejections, and the developer fixes it would reject (as DEV33's A3);
- localization ranks, how often phase 3 is reached, time per arm;
- every accepted patch with both diffs and its verdict, and the oracle against the reading.

## Predictions (honest prior)
- **A1 is the risk:** DEV32 had 2 learned-only correct repairs in 143 bugs, DEV33 1 in 48. The development study says
  learned knowledge rarely meets a fix it has seen. A pass needs about as many bugs as DEV32 and some luck.
- **A3 and A4 should hold** with the fixed check.

## Decision rules
- **No promotion, no default change.** Promoting 0.4.9 or M4, and any default, are the owner's decisions.
- **R3.** Bugs found during the run are fixed with a regression test; affected runs are discarded, kept, and re-run in
  full. Nothing else changes after seeing DEV34 data.
- **R4.** Every result is reported, including unfavourable ones.
