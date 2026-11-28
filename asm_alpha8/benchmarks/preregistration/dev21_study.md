# DEV21 pre-registration: sharing a candidate budget between learned sources (negative transfer protection)

Written and committed to git before any Part A held-out attempt was run and before any DEV21 fresh project (Part B) was
cloned or mined. Its SHA-256 is recorded in every DEV21 run manifest. Anything not listed here is exploratory.
Alpha 8 plan item: **alpha.8.4 — Negative Transfer Protection**. Nothing is promoted in DEV21, and no default changes.

## Question
DEV4 and DEV20 each found a learned candidate source using up a shared budget before the right candidate got a turn:
- **DEV4 (structural transfer).** `ProcedureCortex.induce` walks the learned families in listing order with one shared
  budget of 64 proposals. A two-parameter family (17 × 17 = 289 instantiations) listed first uses all of it, so a
  relevant family listed after it is never tried: DEV4's T3b (no interference) failed, success 1.00 → 0.00.
- **DEV20 (learned edit steps).** One step, "a name → an exception name", was learned in `raise` positions but applied
  to every name in a function, and filled up to 40 of the 50 single-step slots.

DEV21 tests one budget-sharing rule in both systems, and one guard for steps (the code as in this commit; all opt-in,
the defaults unchanged):
- **Round-robin sharing.** Every source proposes its next candidate before any source proposes another; budgets and
  each source's own order are unchanged.
  - Part A: `ProcedureCortex(family_sharing='round_robin')` — the sources are learned families (default `'listing'`).
  - Part B: `StepLibrary.candidates_for(sharing='round_robin')` — the sources are learned steps, within each candidate
    kind (default `'key'`, DEV20's ordering by ranking key).
- **Exception-site guard** (Part B): `StepLibrary.candidates_for(exception_sites='raise')` — an expression step with
  an exception hole applies only to the exception of a `raise` (or that exception's callee), the role the hole was
  learned in (default `'any'`).

## Development evidence (on data already inspected; reported before the held-out data exists)
Outputs: `benchmarks/results/dev21/development/`.
- **Part A on DEV4's own lab** (structure x*x + c, DEV4's seed and donors; `benchmarks/dev21_transfer.py --development`;
  48 attempts per arm and mode):

  | arm | listing (default) | round-robin |
  |---|---|---|
  | mixed, relevant donors named last | 0.00 | 1.00 (31 evaluator calls) |
  | mixed, relevant donors named first | 1.00 | 1.00 (29) |
  | relevant | 1.00 (13) | 1.00 (13) |
  | unrelated | 0.00 (302) | 0.00 (319; ratio to none 1.06) |
  | none, one relevant, shuffled labels | 0.00 | 0.00 |

  No wrong answer in any arm or mode. With the default, DEV4's published verdicts reproduce exactly (T3b fails); with
  round-robin all of DEV4's criteria pass. This confirms DEV4's diagnosis, but on DEV4's own data, so it is not a test.
- **Learned steps** (`benchmarks/dev21_dev_steps.py`; S20 within 80; "new" = reproduced by none of B, P17, S18 in that
  DEV's own evaluation):

  | setting (knowledge → test) | key order (DEV20 as run) | round-robin | exception guard | both |
  |---|---|---|---|---|
  | DEV18 (91 → 472) | 2 (0 new) | 1 (0) | 2 (0) | 1 (0) |
  | DEV19 (1,151 → 103) | 2 (2 new) | 0 (0) | 3 (2) | 1 (1) |
  | DEV20 (1,254 → 483) | 4 (1 new) | 10 (5) | 7 (3) | 10 (5) |

  - Key order reproduces DEV20's published S20 result exactly (4, 1 new).
  - Round-robin gains 7 and loses 4 over the three settings, and its effect depends on the library. In DEV20's setting
    (747 steps) many right candidates sit behind a few high-ranked steps and it gains 7 for 1 lost; in the smaller
    settings it cuts a top step's second or third place (losses 1 and 2, no gain).
  - The guard gains 4 and loses none. Its 3 gains in DEV20's setting are fixes the exception-name step had pushed out.
  - Both together behave like round-robin (the guard adds back one fix in DEV19's setting).
  - DEV20's fresh fixes were inspected in DEV20's exploratory analysis, so they are development data here.

## Part A (primary): held-out structural transfer (`benchmarks/dev21_transfer.py`)
- **Targets never run before:** cube y = x*x*x + c, shift y = (x + c)*x, flip y = c − x*x. In-range c ∈ −8..8
  except 0 (16 constants), out-of-range |c| ∈ 9..12 (8); 3 fit seeds; seed 20261123.
- **Donors:** relevant (two donors of the target's structure, never with its constant); a new unrelated set (affine
  4x + 2 and −2x + 5: a two-parameter family; min(x, 2) and min(x, 7): a one-parameter family); for the stress arm a
  fourth family (x − 3, x − 6). Checked before this pre-registration without any target: the sets form exactly these
  families and no cross-family.
- **Arms:** none, one_relevant, relevant, unrelated, relevant_shuffled, mixed (relevant + unrelated: 3 families),
  mixed4 (+ the fourth: 4 families). The mixed arms run twice, with the relevant donors' names sorting first and last,
  because listing order is what DEV4's defect depends on.
- **Paired modes:** every attempt runs with `family_sharing='listing'` (control) and `'round_robin'` (candidate).
  Otherwise DEV4's protocol: a fresh cortex, donors through propose + held-out validation, 3 fit examples, one induce
  (budget 512), 8 validation examples; success = every held-out interior query answered correctly.
- **Gate G21-A** (in-range constants, pooled over the three structures, round-robin unless stated):
  - **V3 (validity):** the control shows interference: success(listing, relevant) − success(listing, mixed, relevant
    named last) ≥ 0.10. If not, G21-A is *inconclusive* (the held-out data does not probe the defect).
  - **C1 no interference:** success(relevant) − success(mixed) ≤ 0.10, for both name orders (DEV4's T3b threshold).
  - **C2 transfer kept:** success(relevant) − success(none) ≥ 0.50 (DEV4's T1), and success(relevant) ≥
    success(listing, relevant) − 0.05.
  - **C3 no false transfer:** success(unrelated) ≤ success(none) + 0.05, and success(relevant_shuffled) ≤ 0.05.
  - **C4 safety:** wrong answers per held-out query ≤ 0.02 in every arm and both modes (DEV4's T4).
  - **C5 cost:** mean evaluator calls, unrelated / none ≤ 1.10 (DEV4's T3).
  - **Passes iff V3 and C1–C5 all hold.**
- **Reported with it:** Wilson 95% intervals; the paired mixed comparison (relevant named last) with an exact one-sided
  McNemar test; each structure separately; out-of-range constants (as DEV4's T5, predicted ≤ 0.10: parameters span
  −8..8); mixed4 (stress, descriptive) against a prediction from the budget arithmetic: with four families sharing 64
  proposals in turns, the relevant family's 17th instantiation (c = +8) comes 68th when it is listed last and 65th when
  listed first, so in-range success with round-robin is at most 15/16 in either order.

## Part B (secondary): learned steps on fresh fixes (`benchmarks/dev21_evaluate.py`)
- **Fresh fixes:** commits from 12 projects that nobody working on ASM has inspected, none used in DEV17–DEV20 and
  none from BugsInPy (`benchmarks/dev21_mine.py`: six, colorama, prettytable, simplejson, python-sortedcontainers,
  pyrsistent, funcy, python-json-patch, Box, cattrs, parso, asttokens), with DEV18's selection criteria and problem
  context. A project that cannot be cloned is reported and left out; none is added or swapped after mining.
- **Knowledge:** all 1,737 real fixes of DEV17–DEV20, in this order and per-project batches, for P17, S18 and S20:
  DEV17 history (91), DEV18 fresh (472), DEV19 training (588), DEV19 fresh (103), DEV20 fresh (483).
- **Arms** (S20 within K = 80, paired on the same fixes): control (DEV20 as run), round_robin, guard, both
  (descriptive). B, P17 (any position) and S18 (within 80) as in DEV20, for "new".
- **G21-B (round_robin vs control) and G21-C (guard vs control):** b = fixes only the arm reproduces, c = fixes only
  the control reproduces. Each passes iff b − c ≥ 3 AND its exact one-sided sign test survives Holm's correction over
  the two at 0.05 (the smaller p ≤ 0.025, then the other ≤ 0.05).
- **Expectation: uncertain.** Round-robin's development effect depends on the library: −1 and −2 in the two smaller
  settings, +6 in DEV20's (7 gained, 1 lost; p = 0.035 on its own), the setting closest to Part B's 1,737 fixes. The
  guard never lost a fix in development but gained 4 in 1,058; at that rate G21-C is unlikely to reach significance on a
  set of this size (with no loss it needs a net of at least 6).
- **Reported with it:** each arm's reproduced and new counts, the kinds, the discordant fixes, and each project.

## Decision rules
- **No promotion, no default change.** If G21-A passes, making `'round_robin'` the cortex's default is a release
  decision for the project owner, in a later labelled change. The same holds for Part B's guard.
- **R3.** Bugs in ASM found during the runs are fixed with a regression test; affected runs are discarded, kept, and
  re-run in full. Nothing else changes after seeing DEV21 data.
- **R4.** Every result is reported, including unfavourable ones.
