# ASM Alpha 8 DEV26 — Asking Which Family Candidate Is Right (implementation report)

Status: **experimental; NOT promoted; no default changed** (pre-registered). **The gate G26-A passed** on held-out
three-input structures. Alpha 8 (= milestone 0.4.9) plan item: alpha.8.3 (uncertain analogy mapping), using Stage 4's
active information gathering (0.4.4). ASM contains no language model and no transformer.

## Headline (read this first)
- **What DEV26 tests.** In DEV23–DEV25 nearly every remaining transfer failure had one cause. Several (family, mapping,
  value) candidates fit the three fit points, the first in order was proposed, and validation refuted it. With
  `family_ambiguity='ask'` (opt-in, with DEV25's solving), when two or more solved candidates fit and disagree, `induce`
  asks for the label of the input that separates them best instead of guessing.
- **Result: G26-A passed.** On three three-input structures no run had used (864 attempts per group):

  | cell | first (the default) | ask |
  |---|---|---|
  | degenerate fits (three points from {0,1,2}³) | 0.817 (58 evaluator calls) | **0.991** (106); 0.345 questions per attempt |
  | standard fits (10 × 10 × 10 grid) | 0.984 (49) | **1.000** (57); 0.032 questions per attempt |
  | role order 5, degenerate fits, relevant / mixed | 0.667 / 0.657 | **0.991 / 0.991**, the same as role order 0 |
  | none / unrelated / shuffled labels | 0 / 0 / 0 | 0 / 0 / 0 |
  | wrong answers (19,656 answers given) | 0 | 0 |

  Paired, degenerate fits: 150 attempts succeed only by asking, none only without (p = 7.0 × 10⁻⁴⁶). No attempt that
  succeeds without asking fails with it.
- **What it means.** The order in which ASM tries mappings no longer matters: when the evidence cannot tell candidates
  apart, ASM asks for one more example instead of guessing. One question settles nearly all cases: 299 attempts asked
  one and 14 asked two. That is the analogy-mapping problem DEV23 raised, closed in the lab.
- **Where it still fails:** 8 attempts, all x·(z + c) − y·y with x = 0 at every fit point. The right mapping's parameter
  is then undetermined, so it has no solved candidate, and a single wrong candidate fits; with nothing to compare, ASM
  proposes it and validation refutes it (no answer).

## What DEV26 added
| piece | code |
|---|---|
| ambiguity rule | `asm/procedure_cortex.py`: `ProcedureCortex(family_ambiguity='first'|'ask')`, default `'first'` (unchanged). With `'ask'`, on a 2–4-input target, once a solved candidate fits, `induce` also checks the remaining solved candidates. If two or more fit and disagree on some input, it returns `needs_information` with that input |
| query choice | `_disagreement_query`: the input of `_query_pool` (values around the evidence, not yet observed) with the most disagreement among the fitting candidates (`choose_experiment`). Every candidate takes part, with no size preference |
| harness | `benchmarks/dev26_transfer.py`: DEV25's protocol with an oracle answering at most 2 questions (the label becomes one more fit example, and `induce` re-fits on all of them), degenerate-fit arms, gate G26-A |
| tests | `tests/test_alpha8_dev26.py` (5) |

With the default, ASM behaves exactly as before: all eight committed DEV21–DEV24 lab runs reproduce every record
(`benchmarks/results/dev26/development/lab_check_first.txt`).

## Development (development structures only)
x·(y + c) + z, x·x·y − z + c, and DEV24's (x − z)·(y + c), whose data was already inspected
(`benchmarks/results/dev26/development/`).
- **Degenerate fits:** 0.806 → 0.998 (166 vs 0 paired).
- **Standard fits:** 0.975 → 0.995.
- No loss, no wrong answer, 0.042 questions per attempt on standard fits.

Changes after looking at development results concerned the gate only: the recovery threshold rose from 0.05 to 0.10,
and C7 (role order no longer matters) was added.

## Pre-registered held-out test — G26-A passed
`benchmarks/results/dev26/transfer.jsonl` (pre-registration `0333a75`, before any held-out attempt; 4,752 attempts,
58 s; no amendment).

| check | rule | observed | |
|---|---|---|---|
| C1 recovery | degenerate fits: ask − first ≥ 0.10, paired p < 0.01 | 0.991 − 0.817 = 0.174; 150 vs 0, p = 7.0 × 10⁻⁴⁶ | ✓ |
| C2 no loss | standard fits: first − ask ≤ 0.02 | 0.984 − 1.000 < 0 | ✓ |
| C3 no false transfer | unrelated ≤ none + 0.05; shuffled ≤ 0.05 | 0 = 0; 0 | ✓ |
| C4 safety | wrong per query ≤ 0.02 every cell; no more wrong answers with asking | no wrong answer | ✓ |
| C5 few questions | standard fits ≤ 0.10 per attempt | 0.032 | ✓ |
| C6 cost | standard fits, calls ask / first ≤ 1.50 | 56.5 / 49.4 = 1.14 | ✓ |
| C7 role order no longer matters | \|order 0 − order 5\| ≤ 0.03, each arm and fit kind | 0 in every cell | ✓ |

- **Per structure** (all relevant and mixed arms, first → ask): (y − x)·z + c 0.854 → 1.000; x·(z + c) − y·y
  0.962 → 0.986; (x + z)·y + c·x 0.885 → 1.000.
- **The 8 failures** are x·(z + c) − y·y at two degenerate fits, (0,2,0), (0,2,1), (0,2,2) and (0,0,1), (0,2,0),
  (0,2,2), in four arms each. With x = 0 everywhere, c is undetermined for the right mapping, so only a wrong mapping
  has a solved candidate that fits. Nothing was asked; it was proposed, and validation refuted it.
- **One question in the shuffled-label arm** ((y − x)·z + c at c = 9). Its answer led to a proposal that validation
  refuted: no false transfer.
- **Cost.** Asking checks the remaining solved candidates (one per source) in every attempt, so standard fits cost
  14% more evaluator calls. Each question then costs another `induce`, so degenerate fits cost 81% more.
  `choose_experiment` also runs the fitting candidates on up to 128 hypothetical inputs, which is not counted as
  evaluator calls (the cortex's existing convention for queries).

## Validation
- **`tests/test_alpha8_dev26.py`, 5 tests:**
  - the default and an unknown value;
  - `_disagreement_query`: separates candidates that agree on the evidence, never repeats an observed input, and
    returns nothing for one candidate or for equivalent ones;
  - asking recovers an ambiguous fit that `'first'` loses;
  - an unambiguous fit asks nothing;
  - without solved candidates, `'ask'` changes nothing.
- **Full `test_alpha8_*`:** 593 passed, 3 skipped, 0 failed (588 before, plus 5).
- **`benchmarks/lab_check.py <dir> family_mapping=exact`** reproduces all 38,224 committed lab records on the default.

## Limitations
- **A lab with an oracle** that answers any question correctly. In the real world an answer can be wrong or
  unavailable.
- **Solved candidates only.** `'ask'` considers solved candidates. When the right mapping's parameter is undetermined
  (the 8 failures) or its family is not affine, the ambiguity is not seen. Enumerated candidates are proposed first-fit
  as before.
- **2–4-input targets only.** The one-input path is unchanged.
- **Default change needs callers that answer.** Making `'ask'` the default would let `induce` return
  `needs_information` from the family step, so its callers must answer or ignore the question.

## What this means, and what is next
With DEV25's solving and DEV26's asking, the lab's family transfer reaches any affine constant in any role order, with
one question where the evidence is ambiguous, and has given no wrong answer.
- **Owner's decision:** make `family_ambiguity='ask'` (with `family_parameters='solve'`) the default. G26-A shows no
  loss; the cost is 14% more evaluator calls and about one question in thirty attempts on ordinary fits.
- **Next, DEV27 (alpha.8.6):** family memory past the 32 active versions `families()` reads, which survives restarts.

Consciousness-related architecture: not touched.
