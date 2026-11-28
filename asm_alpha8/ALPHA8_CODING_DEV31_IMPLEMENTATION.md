# ASM Alpha 8 DEV31 — Phase 3 on Its Own Clock, on Fresh Real Bugs (implementation report)

Status: **experimental; NOT promoted; no default changed** (pre-registered; design approved by the project owner).
**The gate G31-A did not pass.** On 75 real bugs no ASM run had touched, learned knowledge repaired none that the
workflow without it does not; the gate needed 2. Alpha 8 (= milestone 0.4.9) plan items: alpha.8.8 (scaling and
efficiency), and alpha.8.1/8.2 on real data, with alpha.8.5. ASM contains no language model and no transformer.

## Headline (read this first)
- **What DEV31 tests.** In DEV29 phase 3 (learned knowledge) only got whatever time phases 1–2 left. It ran out of time
  in 30 of 37 bugs, and on youtube-dl it tested no candidate at all: building learned candidates for one suspect took
  minutes. DEV31 gives phase 3 its own 150 s and makes candidate building fast enough to test. It then asks, on fresh
  real bugs, whether learned knowledge repairs bugs the workflow without it does not, even given the same total time.
- **Result: G31-A not passed.** Every accepted patch was read by a person against the developer's fix
  (`benchmarks/results/dev31/REALBUGS_REVIEW.md`). On 75 fresh bugs (scrapy 33, black 19, fastapi 15, tornado 6,
  sanic 2):

  | | control (150 s) | learned (150 s + phase 3's own 150 s) |
  |---|---|---|
  | bugs with an accepted patch | 2 | 2 (the same, byte-identical) |
  | correct | 0 | 0 |
  | wrong | 2 (fastapi-4, scrapy-9) | 2 (the same) |
  | resolved only in this arm | 0 | **0** |

  C1 (≥ 2 learned-only correct repairs) failed with 0. C2 (no loss), C3 (no extra wrong patch) and C4 (the clock holds:
  longest learned run 298 s, limit 360) held.
- **The engineering worked; the learned knowledge did not repair.**
  - Phase 3 ran in 44 fresh bugs and tested candidates in every one (a median of 89).
  - It accepted nothing: it ran out of time in 40 bugs, exhausted its candidates in 3, and made 1 partial patch.
- **Candidate building is much faster, with identical candidates.** On 55 real functions from DEV15's bugs, the code
  before and after gave the same 4,400 candidates, 33× faster (2,434 s → 74 s). One youtube-dl function took 623 s
  before and 3.8 s after.
- **A safety warning from development.** With time to run on large modules, the learned shapes wrote a failing test's
  expected value straight into the code:
  - `return None` became `return 'rtmp://foo.de'`;
  - `upload_date = None` became `upload_date = '19681210'`.

  Both are wrong and passed the bug's tests (youtube-dl-13 and youtube-dl-41, on DEV15's development bugs). On the fresh
  bugs phase 3 accepted no patch, so this did not recur. It is the main risk of giving learned knowledge more room.
- **ASM could not reach black.** Its fault localization timed out tracing black's test suite on 14 of 19 bugs, so no
  arm could repair them; on the other 5 no repair phase started. In all, the developer-changed function was not among
  the suspects in 30 of 75 fresh bugs (DEV15's bugs: 8 of 83).
- **What it means.** Time and building speed were not the limit. With both fixed, the learned knowledge from DEV17–DEV20
  repairs no fresh real bug. In 44 bugs it tested a median of 89 candidates and none passed. DEV29's thefuck-19 stays
  the only real bug it has repaired.

## What DEV31 changed
| piece | code |
|---|---|
| phase 3's own clock | `RepairWorkflow(phase3_seconds=None\|s)`, opt-in, default unchanged: phase 3 gets `s` seconds once it starts, and the three learned libraries stop building at that deadline (`deadline=` in `KnowledgeBase`, `ShapeLibrary` and `StepLibrary.candidates_for`). The phase-3 block of `_run` moved into `_learned_candidates` (`_run` is 11 lines shorter) |
| one parse per module | `asm/coding/induction.py`: `_parsed` and `_in_span` are shared by every procedure; each of 1,471 procedures and 798 shapes had re-parsed and re-walked the whole module for every suspect |
| chunk checks | each expression, string or multi-place rewrite is checked and de-duplicated on its innermost self-contained statement, not on a deep copy and dump of the whole module (`_chunk`, `_keyed`, `steps._common_chunk`). Exact: a rewrite inside such a statement parses to the intended program iff the statement does, since the rest of the file tokenizes unchanged |
| smaller speedups, same results | `KnowledgeBase.candidates_for` passes `max_programs` (DEV18 A2's early stop); name similarity cached; string similarity pruned by difflib's upper bounds (as `get_close_matches`) |
| harnesses | `benchmarks/dev31_realbugs.py` (arms, time control, `--resume`); `dev31_analysis.py`; `dev31_probes.py` reusing `dev29_probes.run`; `dev29_realbugs.repair` passes workflow options through |
| environment fix | `dev14_realbugs.requirement_lines`: black, fastapi, luigi, sanic and scrapy ship UTF-16 requirement files, which crashed the envs stage; the six DEV15 projects read identically |
| tests | `tests/test_alpha8_dev31.py` (6) |

**Exactness of the speedups** (`benchmarks/results/dev31/development/phase3_equivalence.txt`):
- **Real inputs:** 55 developer-changed functions from DEV15's bugs gave identical candidates in all three libraries,
  4,400 in all.
- **Awkward layouts:** a test forces every rewrite onto the whole-module path, which is the pre-DEV31 algorithm. On
  decorators, one-line compound statements, `;`-joined statements, multi-line calls, f-strings and a form feed it gives
  the same output.
- **Fresh parses:** another test checks that the shared parse gives what a fresh parse gives.

| one suspect's building | before | after |
|---|---|---|
| youtube-dl `utils.urljoin` (3,643-line module) | 281 s for the procedures alone | 0.2 s for the procedures, 13 s for all three |
| youtube-dl `utils.unescapeHTML` (3,826 lines), all three libraries | 623 s | 3.8 s |
| cookiecutter `generate_files` (323 lines), all three | 134 s | 20 s |

## Fresh bugs
- **Projects:** 7 BugsInPy projects no ASM run had used: black, luigi, tornado, fastapi, scrapy, ansible and sanic (151
  bugs, corpus commit `11c5f1e`).
- **Environments:** built and validated with DEV14's stages under Python 3.8.20. Prepare's clone command was used;
  prepare's dependency install was skipped because validation does not use it
  (`benchmarks/results/dev31/environment/`).
- **75 valid:** scrapy 33, black 19, fastapi 15, tornado 6, sanic 2.
  - **luigi 0:** pytest cannot start. A requirement whose pin failed was installed unpinned and pulled in a modern
    anyio, whose pytest plugin needs a newer typing_extensions than luigi pins. Fixing it would change the stages
    DEV15 and DEV29 were built with, so it is reported as attrition.
  - **ansible 0:** its bugs do not reproduce under Python 3.8 (8 do not fail when buggy, 5 fail when fixed, 5 do not
    run).

## Development (DEV15's 83 bugs, already seen)
The learned arm was compared with DEV29's committed control records; the control's code is unchanged
(`benchmarks/results/dev31/development/dev31_learned_*`).
- **Resolved:** 12 (DEV29: control 9, learned 10). None lost.
- **Phase 3:** tested candidates in all 69 bugs where it ran (median 80). On youtube-dl, where DEV29 had tested none, it
  tested 19–153.
- **Longest run:** 323 s.
- **Learned-only:** thefuck-19 (correct, as in DEV29), and youtube-dl-13 and -41. Both youtube-dl patches are wrong:
  shape `s591385f62a4ee08c` put the failing test's expected value into the code. On these bugs C1 and C3 would fail.
- **No guard was added.** A guard would be a new mechanism, tuned on 2 cases.

The pre-registration (`44f0c6c`) records all of this before any fresh run.

## Pre-registered evaluation — G31-A not passed
Pre-registration `44f0c6c` (SHA-256 `47b5a6e2…`, in every manifest) was committed before any repair arm ran on a fresh
bug. Code: `asm.coding` `05cf0ee2…`, the same as development.

| check | rule | observed | |
|---|---|---|---|
| C1 learned repairs | ≥ 2 bugs correct with learned, correct neither with control nor control_long | 0 (no bug resolved by the learned arm alone; control_long had no bug to run) | ✗ |
| C2 no loss | ≤ 1 control-correct bug lost | 0 (the control repaired no bug correctly) | ✓ |
| C3 safety | learned wrong ≤ control wrong + 1 | 2 against 2 | ✓ |
| C4 the clock holds | no learned run over 360 s | longest 298.2 s; median 296.2 s; none over 300 s | ✓ |

### The interruption (reported under R4)
- **The cause:** the three evaluation shards were children of a launcher that hit its 2-hour background limit. They
  were stopped at 131 of 150 records: 64 bugs complete in both arms, 3 with only the control (scrapy-29, -30, -35), and
  8 not started.
- **The resume:** the 11 unfinished bugs ran again in both arms, paired as before, with the same code and
  pre-registration (`evaluate --resume`, committed as `2c10009` first; `dev31_control_learned_resume_*`). The shards
  were detached this time, so a launcher limit cannot stop them.
- **The orphans:** the 3 orphaned control records remain in the first files, superseded by the resumed pairs.
- **No effect on the outcome:** none of the 11 resumed bugs was resolved in either arm.

### Reported, not gated
- **Status per arm** (control → learned):

  | status | control | learned |
  |---|---|---|
  | no spectrum | 14 | 14 |
  | unresolved | 18 | 14 |
  | out of time | 37 | 40 |
  | partial | 4 | 5 |
  | resolved | 2 | 2 |

  The differences are phase 3: 5 control `unresolved` → learned out of time, and 1 control out of time → learned
  `unresolved`. Phase 3 also made one more partial patch (scrapy-32, below).
- **Each project** (control → learned):
  - black: no spectrum 14, unresolved 5, in both arms;
  - fastapi: resolved 1 / partial 1 / out of time 8 → 7 / unresolved 5 → 6;
  - scrapy: resolved 1 / partial 2 → 3 / out of time 24 → 27 / unresolved 6 → 2;
  - tornado: partial 1 / out of time 3 → 4 / unresolved 2 → 1;
  - sanic: out of time 2.
- **Localization:**
  - the developer-changed function ranked 1st in 27 bugs, 2nd in 6, 3rd in 4, lower in 8;
  - not ranked in 30, which are the 14 black bugs without a spectrum ("the traced test run timed out") and 16 others.
- **Phase 3:**
  - **reach:** it ran in 44 bugs (scrapy 29, fastapi 8, tornado 5, sanic 2) and tested a median of 89 learned
    candidates, never none;
  - **outcomes:** out of time 40, candidates exhausted 3;
  - **one partial patch,** on scrapy-32: a learned step replaced `verifyClass(ISpiderLoader, loader_cls)` with
    `KeyError(ISpiderLoader, loader_cls)`. That is an exception object that is never raised, so it disables the check.
    The developer's fix is elsewhere.
- **Time:** control longest 166 s (final checks past its 150 s). Learned: median 296 s, longest 298 s. The clock bounds building
  too: no learned run passed 300 s, where DEV29 had runs of up to 809 s.
- **Every accepted patch, read and probed:**
  - fastapi-4 is wrong. Inverting the repeat check drops sub-dependencies' parameters: the OpenAPI parameters are
    `['x']` against `['page', 'q', 'x']`.
  - scrapy-9 is wrong. Swallowing the error keeps the addresses as strings: the header is `To: a, @, e, x, …` against
    `To: a@example.com`.

  The oracle could judge neither (no replayable calls).

## Validation
- **`tests/test_alpha8_dev31.py`, 6 tests:**
  - UTF-16 requirement files;
  - the arms;
  - the shared parse against fresh parses;
  - chunk checks against whole-module checks on awkward layouts;
  - every library stopping at a past deadline;
  - phase 3's own clock, where the deadline phase 3 builds under is 40 s from its start, less the 5 s margin.
- **Full `test_alpha8_*`:** 617 passed, 3 skipped, 0 failed (DEV30: 611; plus DEV31's 6).
- **Equivalence:** see above; `benchmarks/results/dev31/development/phase3_equivalence.txt`.

## Limitations
- **75 bugs from 5 projects**, 33 of them scrapy. Two projects gave no valid bug, and black was out of reach of
  localization. "No learned-only repair" holds for these bugs.
- **The budget:** phase 3 still ran out of time in 40 of 44 bugs. More time would test more candidates. But in 44 bugs
  a median of 89 tested candidates gave nothing that passes, so more time is unlikely to be the answer.
- **Test overfitting:** learned content taken from the failing tests can hardcode an expected value. Two such patches
  passed their tests in development. No guard exists.
- **Localization:** DEV15's tracer times out on large test suites (black). The 180 s tracing limit is DEV15's.

## What this means, and what is next
DEV31 closes the "not enough time" explanation from DEV29. Phase 3 now has time and fast candidates, and on fresh real
bugs the learned knowledge from DEV17–DEV20 still repairs nothing the workflow without it does not. The limit is the
knowledge itself: what it proposes in the right place is not the fix. Nothing is promoted; M4 is not met on real data.
- **Owner's decision:** whether to keep `phase3_seconds` (opt-in) at all. The speedups are exact and help any learned
  configuration; they cost nothing when phase 3 is off.
- **Possible next steps, each needing its own pre-registered test:**
  - a guard against copying a failing test's expected value into the code, which development showed is the real risk;
  - learning from more fixes in the fresh projects' own histories (alpha.8.6), since knowledge from 45 other projects
    did not transfer;
  - localization that scales to large test suites, for black.

Consciousness-related architecture: not touched.
