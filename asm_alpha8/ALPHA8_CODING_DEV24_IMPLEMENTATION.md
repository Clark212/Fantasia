# ASM Alpha 8 DEV24 — Three-Input Transfer Across Input Names, and Wrong Labels (implementation report)

Status: **experimental; NOT promoted; no default changed; no ASM code changed** (pre-registered). **Both gates passed**
on held-out structures: G24-A (three-input transfer) and G24-B (wrong labels, measured only, by the owner's choice).
Alpha 8 (= milestone 0.4.9) plan items: alpha.8.7 and alpha.8.4, with alpha.8.3 and alpha.8.8. ASM contains no language
model and no transformer.

## Headline (read this first)
- **What DEV24 tests.** The cortex as it is since 2026-11-23 (`family_scope='any_int'`, `family_mapping='rename'`),
  outside DEV23's two-input lab:
  - **Part A, three-input targets:** six possible mappings per family, donors in all six role orders, and unrelated
    families competing for the budget.
  - **Part B, wrong labels:** each label of the target and of the donors wrong with probability 0.10.
- **Result: both gates passed.** On three three-input structures no run had used (144 in-range attempts per cell),
  with donors over (u, v, w):

  | arm | control (no renaming) | renaming (the default) |
  |---|---|---|
  | relevant donors, role orders 0–5 | 0.000 each (1,523 evaluator calls) | 0.986, 0.986, 0.972, 0.972, 0.986, 0.972 (52–57) |
  | relevant + unrelated donors, role order 0 / 5 | 0 / 0 | 0.799 / 0.792 (292, 297) |
  | the same, constants within the budget's reach (−8..5) | 0 / 0 | **0.983 / 0.974**, equal to relevant donors alone |
  | none / unrelated / shuffled labels | 0 each | 0 each |
  | donors with the target's own names | 1.000 (11) | 1.000 (11) |
  | wrong labels at 0.10: target / donors / both | 0 each | 0.326 / 0.076 / 0.035 (predicted 0.326 / 0.076 / 0.035) |
  | wrong answers, any cell | 0 | 0 |

  Paired over the six role orders: 846 attempts succeed only with renaming, none only with the control (exact one-sided
  p = 2.1 × 10⁻²⁵⁵). Of 8,640 answers given in the run, none was wrong.
- **Two limits, both predicted or explained:**
  - **The budget's reach.** With one relevant and two unrelated families there are 18 sources sharing 256 proposals,
    so each reaches 14 of its 17 parameter values. Constants 6, 7 and 8 failed in every mixed attempt (0 of 54); every
    other mixed attempt matched the relevant arm. That 19% loss grows with more inputs: four inputs give 24 mappings
    per family.
  - **Ambiguous mappings.** All 18 relevant-arm failures are fits where a wrong mapping also fits the three points. It
    is proposed first, refuted by validation, and no answer is given.
- **Wrong labels cost exactly the attempts they touch.** The cortex suspends a hypothesis at its first contradicting
  label, so a wrong label among an attempt's evidence ends that attempt. No attempt with a wrong target label gave any
  answer (600 attempts), and every noise success had all labels clean.
- **The search without families solves no three-input target with three fit points** (development: x + y + z + c was
  unresolved in 47 of 48 attempts). On three inputs, learned families are the only route.

## What DEV24 added
| piece | code |
|---|---|
| harness | `benchmarks/dev24_transfer.py`: DEV23's protocol in three dimensions. Role-order donors (`role_donor`: order k makes the cortex's k-th mapping the right one), label noise (`corrupt`: probability 0.10, offsets ±1..3, one pattern per attempt for the target and one for the donors), a donor rejected or suspended by its own wrong labels is recorded rather than an error, three-dimensional queries (DEV22's amendment A1 included), gates G24-A and G24-B, and the per-attempt noise prediction (`predicted_noise`) |
| tests | `tests/test_alpha8_dev24.py` (7) |

No ASM module changed, so every earlier run reproduces as before.

## Development (development structures only)
x·(y + c) + z and x·x·y − z + c, a development unrelated set over (p, q, r), 96 in-range attempts per cell
(`benchmarks/results/dev24/development/`):
- **Part A:** relevant donors 0/576 → 573/576 over the six role orders. Mixed 78/96 and 77/96: every out-of-reach
  attempt failed, and every within-reach one matched the relevant arm. Exact-name donors 96/96 in both modes; none,
  unrelated and shuffled 0; unrelated cost ratio 0.74.
- **Part B:** 32/96, 5/96 and 2/96, exactly the per-attempt predictions.
- **No wrong answer anywhere.**
- **No regression target.** I looked for a three-input target the control solves, for a regression arm, and found
  none: x + y + z + c, x·y + z + c, x·y + c·z and max(x, y) + z + c each succeeded in 0 of 48 attempts. The affine
  solve refuses three-input fits from three points, and the composer reaches at most two layers.
- **Static checks before the pre-registration** (no attempt run on held-out material):
  - the held-out unrelated donors form exactly the two families the reach arithmetic assumes;
  - each held-out structure forms one one-parameter family in every role order.

## Pre-registered held-out test — G24-A and G24-B passed
`benchmarks/results/dev24/transfer.jsonl` (pre-registration `9404bd6`, before any held-out attempt; 6,480 attempts,
144 s; no amendment).

| check | rule | observed | |
|---|---|---|---|
| C1 gain over the control | rename − exact on relevant ≥ 0.30, paired p < 0.01 | 0.979 − 0.000; 846 vs 0, p = 2.1 × 10⁻²⁵⁵ | ✓ |
| C2 no role-order penalty | order 0 − order k ≤ 0.10, every k | at most 0.986 − 0.972 = 0.014 | ✓ |
| C3 transfer gain | relevant − none ≥ 0.50 | 0.979 − 0.000 | ✓ |
| C4 no interference within reach | relevant − mixed ≤ 0.10 on −8..5, orders 0 and 5 | 0.983 − 0.983; 0.974 − 0.974 | ✓ |
| C5 no false transfer | unrelated ≤ none + 0.05; shuffled ≤ 0.05 | 0 = 0; 0 | ✓ |
| C6 safety | wrong per query ≤ 0.02, every Part A cell | no wrong answer | ✓ |
| C7 no regression | exact names and unrelated: not below control − 0.05 | 1.000 = 1.000; 0 = 0 | ✓ |
| C8 cost | unrelated arm calls, rename / exact ≤ 1.10 | 1,119.1 / 1,522.7 = 0.73 | ✓ |
| B1 safety under noise | wrong per query ≤ 0.02 and ≤ noise-free + 0.005, every noise cell | no wrong answer | ✓ |
| B2 success as predicted | ≥ prediction − 0.05, each noise arm and mode | equal to the prediction in every cell | ✓ |

- **Per structure** (relevant donors, six orders, control → renaming): (x + c)·y − z 0.000 → 1.000; x·y·y + z + c
  0.000 → 0.990; (x − z)·(y + c) 0.000 → 0.948.
- **The 18 failures** come from four fits. In every one a wrong mapping was proposed and validation refuted it, so no
  answer was given:
  - **(x − z)·(y + c) at c = 2 and c = 3, all six role orders fail.** Fits (3,1,5), (4,5,4), (5,1,2) and (0,0,8),
    (4,0,6), (9,7,9): the points with x ≠ z share one y value, and the third has x = z. The mapping that swaps x and
    z changes the sign of (x − z), so it fits with the constant −c − 2y (−4 and −3). That value comes earlier in the
    round robin than c, so it wins even in role order 0, where the right mapping is first in the cortex's order.
  - **(x − z)·(y − 1), one fit:** role orders 2, 3 and 5 fail.
  - **x·y·y + z + c at c = 6:** the fit points all have y = 0, so x·y·y vanishes under several mappings; orders 2, 3
    and 5 fail.
- **Budget reach, as predicted:** mixed success is 0 of 54 at c = 6, 7, 8. Overall it is 0.799 and 0.792, against
  13/16 of the relevant arm's (0.80, 0.79).
- **Noise in detail** (renaming, in-range):
  - **Wrong target labels:** 47 of 144 succeed; 48 attempts had all labels clean, and the 48th is one of the clean
    role-order-0 failures above.
  - **Wrong donor labels:** 11 of 11 clean attempts succeed. Donors survive as 0.9¹¹ predicts: of 216 attempts, 104, 94
    and 18 kept 0, 1 and 2 active donors (predicted 102, 93, 21). A family needs two.
  - **Both:** 5 of 5 clean attempts succeed.
  - **Corrupted targets:** in rename mode, attempts with a wrong target label were unresolved (243) or proposed and
    then refuted by validation (57). No such attempt gave an answer, in either mode.
- **Out-of-range constants:** 0 in both modes with donors over other names, as predicted. With exact-name donors, 7 of
  72 in both modes, from today's composer combining a whole donor with another term.
- **Every pre-registered prediction held.** The noise rates were about the probability of clean labels: 0.326, 0.076,
  0.035 observed against about 0.31, 0.10, 0.03.

## Validation
- **`tests/test_alpha8_dev24.py`, 7 tests:**
  - role-order donors match their expressions;
  - role order k is solved by the cortex's k-th mapping;
  - 18 sources share 256 proposals with 14 or 15 values each;
  - the noise is deterministic with nonzero offsets;
  - a donor with a wrong label never becomes active and the harness continues;
  - an attempt with a wrong target label never answers;
  - queries stay inside the evidence range.
- **Full `test_alpha8_*` on the DEV24 code:** 582 passed, 3 skipped, 0 failed (575 before, plus 7).
- **No ASM module changed**, so the full-suite and lab-reproduction results recorded for the defaults on 2026-11-23
  still apply.

## Limitations
- **Still a lab:** integer targets, one constant per structure, three fit points, one seed, and donors installed
  through the public API. Noise is independent label offsets at one rate.
- **The first fitting candidate wins.** When several (family, mapping, value) candidates fit the three fit points,
  the earliest in the round robin is proposed. It can be wrong even when the right mapping is first in order, as in
  the (x − z) case. ASM does not yet ask for a disambiguating example there.
- **Budget reach shrinks with scale.** 18 sources over 256 proposals leave 3 of 16 constants out of reach. With four
  inputs (24 mappings per family), one relevant and two unrelated families would leave about 3 values per source.
- **Wrong labels can't be absorbed.** A single wrong label ends its attempt: success falls to the probability of clean
  labels. Safety holds. Changing this means changing how contradictions are treated, which is the owner's decision.

## What this means, and what is next
DEV21–DEV24 show that structure learned from donors transfers across tasks, input names and role orders, up to three
inputs, with no wrong answer even under wrong labels. All of this is in a lab. For M4 the open problems are now
concrete and measured:
- **Recommended DEV25 (alpha.8.8): family budget by first-example screening.** Check each source's whole parameter
  range against the first fit example alone (one evaluator call per value), and spend full checks only on the
  survivors. Opt-in, pre-registered on new structures. Prediction: the mixed arms' out-of-reach loss (19% here, more
  with four inputs) disappears at similar cost.
- **Follow-up (alpha.8.3):** when fitting candidates disagree elsewhere, ask for one disambiguating example before
  proposing. Prediction: it recovers the 18 failures here and DEV23's 7.
- **Owner's decision:** whether to test a noise-tolerant contradiction policy (alpha.8.7).
- Each of these is a change made after seeing DEV24 data, so it needs its own pre-registration and held-out tasks.

Consciousness-related architecture: not touched.
