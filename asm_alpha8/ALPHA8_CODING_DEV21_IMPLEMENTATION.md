# ASM Alpha 8 DEV21 — Sharing a Candidate Budget Between Learned Sources (implementation report)

Status: **experimental; NOT promoted; no default changed** (pre-registered). **The primary gate G21-A passed** on
held-out structural-transfer tasks; Part B's gates G21-B and G21-C (learned edit steps on fresh fixes) did not pass.
Alpha 8 plan item: **alpha.8.4 — Negative Transfer Protection**. Built on DEV20. ASM contains no language model and no
transformer; DEV21 uses no model-generated data.

## Headline (read this first)
- **What DEV21 tests.** DEV4 and DEV20 each found a learned source using up a shared candidate budget before the right
  candidate got a turn.
  - DEV4: `ProcedureCortex.induce` walks learned families in listing order with one budget of 64 proposals, so a
    two-parameter family listed first starves a relevant family listed after it (T3b interference failed, 1.00 → 0.00).
  - DEV20: one generic step ("a name → an exception name") filled up to 40 of the 50 single-step slots.
  - DEV21's rule is round-robin sharing: every source proposes its next candidate before any source proposes another.
    It also tests a guard that keeps exception holes at `raise` positions. Everything is opt-in.
- **Part A (primary): G21-A passed.** On three structures no run had used, round-robin removes the interference with
  no loss anywhere:

  | in-range, 144 attempts per cell | listing (default) | round-robin |
  |---|---|---|
  | relevant + unrelated donors (relevant named last) | **0.000** | **1.000** |
  | relevant donors only | 1.000 | 1.000 |
  | unrelated / none / one relevant / shuffled labels | 0.000 | 0.000 |
  | wrong answers, any arm or mode | 0 | 0 |

  Paired: 144 attempts succeed only with round-robin, none only with listing (exact p = 4.5 × 10⁻⁴⁴).
- **Part B (secondary): G21-B and G21-C not passed.** On 197 fresh fixes from 10 new projects, round-robin
  reproduced 3 fixes against the control's 1 (2 gained, none lost; net 2 < 3, p = 0.25); the guard changed nothing.
- **What it means.**
  - Round-robin family sharing is a validated fix for interference between learned families: it passed a
    pre-registered gate on held-out tasks. The evidence is a noise-free integer lab with one seed. Making it the
    default is a release decision for the project owner.
  - For learned edit steps, the same rule helps where the library is large and hurts where it is small. On the fresh
    set it moved in the right direction (2 gained, 0 lost) but was too small to establish.
  - A limit found on the way: learned families are consulted only for one-input integer targets. Structural transfer
    by families does not yet exist for any other kind of task.

## What DEV21 added
| piece | code |
|---|---|
| family sharing | `asm/procedure_cortex.py`: `ProcedureCortex(family_sharing='listing'|'round_robin')`, default `'listing'` (unchanged). `'round_robin'`: in `induce`, every learned family proposes its next instantiation before any family proposes another; the 64-proposal budget and each family's own order are unchanged |
| step sharing | `asm/coding/steps.py`: `StepLibrary.candidates_for(sharing='key'|'round_robin')`, default `'key'` (DEV20). `'round_robin'`: within each candidate kind, every step gives its next candidate before any step gives another |
| exception-site guard | `asm/coding/steps.py`: `candidates_for(exception_sites='any'|'raise')`, default `'any'`. `'raise'`: an expression step with an exception hole applies only to the exception of a `raise` (or its callee) |
| DEV4 harness | `asm/learning/structtransfer.py`: optional `cortex_options` (default `None` = DEV4 as run) |
| Part A | `benchmarks/dev21_transfer.py`: DEV4's protocol generalized to new structures, donor sets and name orders, paired modes, gate G21-A |
| Part B | `benchmarks/dev21_mine.py` (12 new projects), `benchmarks/dev21_evaluate.py` (four paired S20 arms, gates G21-B and G21-C with Holm's correction) |
| development | `benchmarks/dev21_dev_steps.py`; outputs in `benchmarks/results/dev21/development/` |

Every new behaviour is opt-in: with the defaults, ASM behaves exactly as before (DEV4's lab and DEV20's S20 results
reproduce exactly). Nothing is promoted and no default changes; that is a release decision for the project owner.

## Development, before the pre-registration (already inspected data)
- **Part A on DEV4's own lab:** the default reproduces DEV4's published verdicts exactly (T3b fails: mixed donors
  0.00); with round-robin every DEV4 criterion passes (mixed 1.00, relevant 1.00, unrelated 0.00 at a cost ratio of
  1.06, no wrong answer). This confirmed DEV4's diagnosis, on DEV4's own data.
- **Steps, three settings** (S20 within 80; "new" = none of B, P17, S18):

  | setting (knowledge → test) | key order (DEV20 as run) | round-robin | exception guard | both |
  |---|---|---|---|---|
  | DEV18 (91 → 472) | 2 (0 new) | 1 (0) | 2 (0) | 1 (0) |
  | DEV19 (1,151 → 103) | 2 (2 new) | 0 (0) | 3 (2) | 1 (1) |
  | DEV20 (1,254 → 483) | 4 (1 new) | 10 (5) | 7 (3) | 10 (5) |

  Round-robin gained 7 and lost 4, depending on the library size; the guard gained 4 and lost none.
- I first judged round-robin harmful for steps from the two smaller settings; DEV20's setting reversed that, so both
  mechanisms went into Part B. The pre-registration reports all three settings.
- Full `tests/` (minus the 3 modules that need `torch` to import): 957 passed, 4 skipped, 57 failed. The same 57 fail
  on the commit before DEV21 (`a8ca82f`), run without DEV21's changes: they are pre-existing, in v0.2–v0.4 modules
  that need PyTorch, which is not installed.

## Part A (primary): held-out structural transfer — G21-A passed
`benchmarks/results/dev21/transfer.jsonl` (pre-registration `37d6d7f`; amendment A1 `3271d17`; 3,888 paired attempts).
Three target structures no run had used (cube y = x·x·x + c, shift y = (x + c)·x, flip y = c − x·x), a new unrelated
donor set (an affine two-parameter family and a `min` family), and a fourth family for the stress arm. In-range
constants, 144 attempts per arm and mode (16 constants × 3 fit seeds × 3 structures):

| arm | listing (default) | round-robin |
|---|---|---|
| mixed, relevant donors named last | **0.000** [0.000, 0.026] | **1.000** [0.974, 1.000] (33 calls) |
| mixed, relevant donors named first | 1.000 | 1.000 (30 calls) |
| relevant | 1.000 (14 calls) | 1.000 (14 calls) |
| none, one relevant, unrelated, shuffled labels | 0.000 | 0.000 |
| mixed4 (4 families), named last / first | 0.000 / 1.000 | 0.938 / 0.938 (predicted ≤ 15/16) |

(Wilson 95% intervals in brackets.)

| check | rule | observed | |
|---|---|---|---|
| V3 control shows interference | listing: relevant − mixed (last) ≥ 0.10 | 1.000 | ✓ |
| C1 no interference | relevant − mixed ≤ 0.10, both orders | 0.000, 0.000 | ✓ |
| C2 transfer kept | relevant − none ≥ 0.50; not below listing − 0.05 | 1.000; equal | ✓ |
| C3 no false transfer | unrelated ≤ none + 0.05; shuffled ≤ 0.05 | 0.000; 0.000 | ✓ |
| C4 safety | wrong per held-out query ≤ 0.02, every arm and mode | 0 wrong answers | ✓ |
| C5 cost | unrelated / none evaluator calls ≤ 1.10 | 321.0 / 302.5 = 1.06 | ✓ |

- Paired (mixed, relevant named last): 144 attempts succeed only with round-robin, 0 only with listing; exact
  one-sided McNemar p = 4.5 × 10⁻⁴⁴. Every check also holds for each structure on its own.
- Out-of-range constants (|c| = 9..12): 0.000 in every arm and mode, as predicted (parameters span −8..8).
- The stress arm's 0.938 is exactly the 15/16 the budget arithmetic predicted: with four families taking turns in 64
  proposals, the relevant family's 17th instantiation (c = +8) comes after the budget in either name order.
- Amendment A1: the shuffled-labels fallback was used in 16 of 432 shuffled attempts (all shift); none succeeded.

## Part B (secondary): learned edit steps on fresh fixes — G21-B and G21-C not passed
`benchmarks/results/dev21/dev21_eval.jsonl` (pre-registration `37d6d7f`; code hash `9a106b80…`, unchanged since).
- **Fresh fixes:** 197 from 10 of the 12 pre-registered projects. python-json-patch could not be cloned (GitHub asked
  for credentials, as it does for an address with no repository); Box was cloned but had no qualifying fix commit.
  Both are reported and neither was replaced, as pre-registered.
- **Knowledge:** all 1,737 DEV17–DEV20 fixes: 2,016 procedures (71 active), 1,076 shapes (79 active), 991 steps
  (86 active), 61 of them multi-site, 26 usable pairs.

| system | within 80 | any position |
|---|---|---|
| B: built-in operations | 4 | 6 |
| P17: DEV17 procedures | 1 | 6 |
| S18: DEV18 shapes | 1 | – |
| S20 control (DEV20 as run) | 1 (1 new) | – |
| S20 round-robin | 3 (1 new) | – |
| S20 exception guard | 1 (1 new) | – |
| S20 both | 3 (1 new) | – |

| gate | arm-only | control-only | net | exact one-sided p | Holm | verdict |
|---|---|---|---|---|---|---|
| G21-B round-robin vs control | 2 | 0 | 2 (needed 3) | 0.25 | not rejected | **not passed** |
| G21-C guard vs control | 0 | 0 | 0 | 1.00 | not rejected | **not passed** |

- Round-robin's two gains are cattrs `make_mapping_structure_fn` (position 14) and `make_iterable_unstructure_fn`
  (35). DEV17's procedures also produce both, past position 80, so neither is new.
- The one new fix in every arm is parso `BaseParser.error_recovery`. The control finds it at position 78 and
  round-robin at 10.
- No exception-hole step crowded this set, so the guard had nothing to remove.
- By project: parso 61 fixes (S20 1 in every arm), funcy 25 (0), cattrs 23 (round-robin 2), pyrsistent 21 (P17 1
  within 80, S18 1), prettytable 20 (B 3), asttokens 18 (0), colorama 17 (B 1), sortedcontainers 6, six 4,
  simplejson 2 (0 each).
- Power: S20 reproduces so few fixes on this set (1–3 of 197) that the pre-registered gate (a net gain of 3 or more,
  significant after Holm) needed a larger effect than any arm could show here.

## Bugs found and fixed
| | bug | found by | effect |
|---|---|---|---|
| A1 | the Part A harness used DEV4's label derangement, which has no solution when one label fills more than half the positions (shift's fit labels repeat for some negative constants) | the first pre-registered Part A run stopped after 1,876 of 3,888 attempts | the run is discarded and kept unread; the fix uses DEV4's derangement whenever one exists, else a permutation changing as many positions as possible (regression test); the full re-run used it in 16 of 432 shuffled attempts, none successful |

A pre-existing inefficiency was noticed, not changed: DEV18's exception filler is called without the current name, so
an exception hole can be "filled" with the name already there (a no-op candidate that uses a slot).

## Validation
- `tests/test_alpha8_dev21.py`, 13 tests:
  - family sharing (5): the default is `'listing'` and keeps DEV4's interference; round-robin reaches a relevant
    family listed after a two-parameter family (first, middle and last instantiation); one family is unchanged;
    unrelated families still find nothing; an unknown rule is refused;
  - step sharing (2): with key order a generic step fills the budget, with round-robin every step gets a turn; key
    order is the default and an unknown rule is refused;
  - exception sites (1): with the guard, an exception-hole step rewrites only the raised exception;
  - gate logic (5): the exact sign test, Holm's procedure, the gate verdicts, Wilson intervals, and amendment A1's
    shuffle (DEV4's derangement raises on repeated labels).
- Full `test_alpha8_*` on the final DEV21 code: **562 passed, 3 skipped, 0 failed** (DEV11–DEV21).
- Full `tests/` except the 3 modules that cannot import without `torch`: 957 passed, 4 skipped, 57 failed, before
  amendment A1's test was added. The same 57 fail on `a8ca82f` without DEV21's changes (pre-existing; they need PyTorch).

## Limitations
- Part A is a noise-free integer lab with one seed. It uses three one-parameter target structures, at most four
  families, and donors installed through the public API rather than learned autonomously. The same party designed
  and ran it.
- Round-robin keeps DEV4's budget of 64 proposals. With four families it already misses one instantiation (the
  stress arm's 15/16), and with more it would miss more.
- Learned families are consulted only when the target has one integer input
  (`asm/procedure_cortex.py`, the `input_types=={'x':'int'}` branch). Boolean and multi-input induction ignore them.
- Part B's fresh set is small for its gate: S20 reproduces 1–3 of 197.
- The no-op exception candidate (above) is unchanged.

## What this means, and what is next
DEV21 gives alpha 8 its first held-out transfer gate passed. The interference DEV4 found between learned families is
removed by round-robin sharing on structures no run had used. Nothing is lost: transfer from relevant donors is
unchanged, there is no false transfer and no wrong answer, and the cost is 6% in the unrelated case. For learned edit
steps, the same rule is not established.

- **Release decision (project owner):** make `family_sharing='round_robin'` the cortex's default. The two rules
  behave identically when there is one family, and G21-A shows no cost elsewhere. It changes the frozen baseline's
  behaviour, so it needs your approval and a labelled change, with the cortex's tests re-run.
- **Next engineering task (recommended DEV22, toward M4):** structural transfer beyond one-input integer targets.
  - Today `induce` ignores learned families for boolean and multi-input targets, so the transfer DEV4 and DEV21
    measured exists for one task shape only.
  - Extending family proposals to those paths, then pre-registering a held-out transfer test on them, would serve
    alpha.8.2 (compositional reuse) and alpha.8.5 (held-out transfer benchmarking).
- **Also open:** solving a one-parameter template's constant from a fit example, instead of enumerating −8..8, would
  remove the budget limit (alpha.8.8). For learned steps, the better-founded next step remains DEV20's: the repair
  workflow on real bugs, with fault localization.
- Each of these is a change made after seeing DEV21 data, so it needs its own pre-registration and new held-out data.

Consciousness-related architecture: not touched.
