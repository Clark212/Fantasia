# ASM Alpha 8 DEV22 — Learned Families for Two-Input Targets (implementation report)

Status: **experimental; NOT promoted; no default changed** (pre-registered). **The gate G22-A passed** on held-out
two-input transfer tasks. Alpha 8 (= milestone 0.4.9) plan items: alpha.8.2 and alpha.8.5. Built on DEV21 (with
round-robin family sharing as the default). ASM contains no language model and no transformer.

## Headline (read this first)
- **What DEV22 tests.** `ProcedureCortex.induce` used learned families only when the target has one integer input, so
  the structural transfer DEV4 and DEV21 measured existed for one task shape only. DEV22 lets families with the target's
  input schema also propose for integer targets with 2–4 inputs (`family_scope='any_int'`, opt-in).
- **Result: G22-A passed.** On three two-input structures no run had used (144 in-range attempts per cell):

  | arm | control (today) | families on two-input |
  |---|---|---|
  | relevant donors | 0.229 (758 evaluator calls) | **0.993** (12) |
  | relevant + unrelated donors | 0.139 | **0.993** (30) |
  | none / unrelated | 0.035 / 0.035 | 0.035 / 0.035 |
  | shuffled labels | 0.000 | 0.000 |
  | affine target + unrelated families (regression) | 0.979 (35) | 0.979 (96) |
  | wrong answers, any arm or mode | 0 | 0 |

  Paired: 110 attempts succeed only with families, none only with the control (exact one-sided p = 7.7 × 10⁻³⁴).
- **One design finding.** Families must come before the exact affine solve: three fit points almost always admit an
  exact integer affine fit, which today's pipeline proposes (wrong) before anything else. With families after it,
  development reached 56 of 96; with families first, 96 of 96.
- **The price.** On affine targets with unrelated families present, trying families first roughly triples the work
  (35 → 96 evaluator calls, of a budget of 512), with no loss of success.
- **What it means.** Structure learned from donors now transfers to two-input tasks, in a noise-free lab. Families
  still need identical input names: a family learned over (a, b) cannot help a task over (x, y).

## What DEV22 added
| piece | code |
|---|---|
| family scope | `asm/procedure_cortex.py`: `ProcedureCortex(family_scope='one_input'|'any_int')`, default `'one_input'` (unchanged). `'any_int'`: for all-integer targets with 2–4 inputs, `induce` first proposes up to 64 round-robin instantiations of the families with the target's schema, before the affine solve, inside the 512 budget; their cost counts in every reported total |
| shared helper | `ProcedureCortex._family_candidates(input_types, budget)`: one ordered stream per family, chained for `'listing'`, interleaved for `'round_robin'`, cut at the budget. The one-input path now calls it |
| harness | `benchmarks/dev22_transfer.py`: DEV21's protocol on (x, y), paired modes, a regression arm, gate G22-A |
| tests | `tests/test_alpha8_dev22.py` (5) |

With the defaults ASM behaves exactly as before: DEV21's two lab runs reproduce every committed attempt record (3,888
and 1,008) on the DEV22 code.

## Development (development structures only)
x·y + c and (x + c)·y with a development donor set, 96 in-range attempts per cell: relevant 19/96 → 96/96, mixed
14/96 → 96/96, none/one relevant/unrelated/shuffled unchanged (0, 10, 0, 0), no wrong answer. An affine development
target with unrelated families: 46/48 in both modes (59 → 120 calls). The first version (families after the affine
solve) reached 56/96: all 40 failures were wrong exact affine fits, proposed and then refuted by validation.

## Pre-registered held-out test — G22-A passed
`benchmarks/results/dev22/transfer.jsonl` (pre-registration `10afa3f`; amendment A1 `9eb46db`; 2,880 paired attempts).

| check | rule | observed | |
|---|---|---|---|
| C1 gain over the control | any_int − one_input on relevant ≥ 0.30, paired p < 0.01 | 0.993 − 0.229 = 0.764; p = 7.7 × 10⁻³⁴ | ✓ |
| C2 transfer gain | relevant − none ≥ 0.50 | 0.993 − 0.035 = 0.958 | ✓ |
| C3 no interference | relevant − mixed ≤ 0.10 | 0.000 | ✓ |
| C4 no false transfer | unrelated ≤ none + 0.05; shuffled ≤ 0.05 | 0.035 = 0.035; 0.000 | ✓ |
| C5 safety | wrong per query ≤ 0.02, every arm and mode | 0 wrong answers | ✓ |
| C6 no regression | affine target with unrelated families: not below control − 0.05 | 0.979 = 0.979 | ✓ |
| C7 cost | unrelated arm calls, any_int / one_input ≤ 1.10 | 899.5 / 959.9 = 0.94 | ✓ |

- Per structure (relevant donors, control → families): x·(y − c) 0.042 → 0.979; max(x, y) + c 0.417 → 1.000;
  x·x + c·y 0.229 → 1.000. The control's successes come from its composer reusing whole donor programs.
- The one failure with families: x·(y − 6) with all three fit points at x = 0, where the target is 0 for every c. The
  first instantiation fits, validation refutes it, and no answer is given (not a wrong answer).
- The control's 5 successes without donors are x·x ± y (c = ±1), which its composer builds directly.
- Out-of-range constants (|c| = 9..12): 0.042 in both modes (parameters span −8..8, as predicted).
- The near-miss unrelated family min(x, y) + c never produced a false transfer to max(x, y) + c.

## Bugs found and fixed
| | bug | found by | effect |
|---|---|---|---|
| A1 | the harness drew 6 query pairs from the region between the fit's lowest coordinates and 9; a fit near the grid's top corner leaves fewer | the first held-out run stopped (`Sample larger than population`) | that run is discarded and kept unread; the fix draws exactly as before whenever 6 pairs exist, otherwise extends the region to 17 (still inside the evidence range) minus validation pairs; regression test; the development run reproduces all 2,592 records; the re-run used the fallback in 4 regression-arm attempts, all successful |

## Validation
- `tests/test_alpha8_dev22.py`, 5 tests: the default and an unknown scope; transfer to a two-input target where the
  affine fit pre-empts today; an affine target still solved with the 64 family proposals counted; one-input targets
  unchanged by the scope; amendment A1's query draw.
- Full `test_alpha8_*` on the final DEV22 code: **567 passed, 3 skipped, 0 failed**. Full `tests/` except the 3 modules that cannot import without `torch`: 962
  passed, 4 skipped, 57 failed, the same 57 pre-existing PyTorch failures (before A1's test was added).

## Limitations
- A noise-free integer lab: two inputs, one constant per structure, one seed, donors installed through the public API.
- Families need identical input names on donors and target (`families()` pairs donors with equal inputs; `induce`
  uses families whose inputs equal the target's). Boolean and mixed targets are not covered.
- Parameters span −8..8 and at most 64 family proposals are tried.

## What this means, and what is next
DEV21 made learned families share their budget fairly; DEV22 makes them reach tasks with several inputs. Both passed
pre-registered held-out gates, in a lab. For M4 (verified cross-task structural transfer), the next limit is the
mapping between tasks.

- **Owner decision:** make `family_scope='any_int'` the default. G22-A shows no loss; the cost is about 60 extra
  evaluator calls on affine targets when unrelated families exist.
- **Recommended DEV23 (alpha.8.3, Uncertain Analogy Mapping):** let a family learned over one set of input names
  apply to a target over another, by trying the possible mappings of inputs (two inputs: 2 mappings), within the same
  budget. Today's composer already remaps whole donor programs onto a new schema; families do not.
- Each of these is a change made after seeing DEV22 data, so it needs its own pre-registration and held-out tasks.

Consciousness-related architecture: not touched.
