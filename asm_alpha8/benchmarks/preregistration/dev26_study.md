# DEV26 pre-registration: asking for the input that separates fitting family candidates

Written and committed to git before any held-out attempt was run. Its SHA-256 is recorded in the DEV26 run manifest.
Anything not listed here is exploratory. Alpha 8 (= milestone 0.4.9) plan item: alpha.8.3 (uncertain analogy mapping),
using Stage 4's active information gathering (0.4.4). Nothing is promoted in DEV26, and no default changes.

## Question
In DEV23–DEV25 nearly every remaining transfer failure had one cause. Several (family, mapping, value) candidates fit
the three fit points; the first in order was proposed, validation refuted it, and no answer was given:
- DEV23: 7 of 576 attempts;
- DEV24: 18 of 864;
- DEV25: 8, all in the last role order at degenerate fits.

DEV26 asks: when two or more solved candidates fit and disagree somewhere, does asking for the label of the input that
separates them best recover those attempts, without losses, wrong answers, many questions, or much extra cost?

Mechanism (the code as in this commit): `ProcedureCortex(family_ambiguity='ask')`, opt-in (default `'first'`,
unchanged).
- **Collect.** On a 2–4-input target, when a solved family candidate (`family_parameters='solve'`, DEV25) fits every fit
  example, `induce` also checks the remaining solved candidates.
- **Ask.** If two or more fit and they disagree on some input, `induce` returns `needs_information` with that input.
  `_disagreement_query` picks the input with the most disagreement (`choose_experiment`) from `_query_pool`, which
  holds values around the evidence that have not been observed yet. All fitting candidates take part: there is no size
  preference, unlike `_query_from_programs`, since all are instances of learned families.
- **Otherwise** the first fitting candidate is proposed as before. Enumerated candidates are not considered by `'ask'`.
- **The protocol** (the lab's oracle): the queried input's label becomes one more fit example, and `induce` runs again
  on all of them, at most 2 questions per attempt.

## Development evidence (development data only)
DEV24's development structures x·(y + c) + z and x·x·y − z + c, plus DEV24's held-out (x − z)·(y + c), whose data is
already inspected and which is the known ambiguity case. DEV24's development unrelated set; c = −12..12 except 0;
3 fit seeds; seed 20261125; paired modes, both with `family_parameters='solve'`
(`benchmarks/dev26_transfer.py --development`, `benchmarks/results/dev26/development/transfer_dev.jsonl`):

| cell (216 attempts per arm, 864 per group) | first (control) | ask |
|---|---|---|
| standard fits (10 × 10 × 10 grid): relevant and mixed, role orders 0 and 5 | 0.975 (49.1 evaluator calls) | **0.995** (56.9); 0.042 questions per attempt |
| degenerate fits (three points from {0,1,2}³) | 0.806 (55.7) | **0.998** (104.8); 0.387 questions per attempt |
| role order 5, degenerate fits, relevant / mixed | 0.620 / 0.620 | **0.995 / 1.000**, the same as role order 0 |
| none / unrelated / shuffled labels | 0 / 0 / 0 | 0 / 0 / 0, no question asked |

- **Paired, degenerate fits:** 166 attempts succeed only with asking, none only without (p = 1.1 × 10⁻⁵⁰).
- **No attempt that succeeds with `'first'` fails with `'ask'`.** No wrong answer in any cell. 354 attempts asked one
  question and 8 asked two; none was left unresolved.
- **The 6 remaining failures with asking** asked nothing: only one candidate fit, or the fitting candidates agreed on
  every input of the pool, and validation refuted the proposal.
- **Changes after looking at development results** (gate only):
  - the recovery threshold rose from 0.05 to 0.10, since development showed 0.19 and 0.05 would be a weak claim;
  - C7 (role order no longer matters) was added.
- **Defaults unchanged.** With `'first'`, all eight committed DEV21–DEV24 lab runs reproduce every attempt record
  (`benchmarks/lab_check.py <dir> family_mapping=exact`).
- **Static design checks on the held-out material** (no attempt run):
  - the unrelated donors form exactly two families, with one and two parameters;
  - each held-out structure forms one one-parameter family in every role order;
  - every donor and target is valid for every constant.
- Tests: `tests/test_alpha8_dev26.py` (5).

## Held-out test (`benchmarks/dev26_transfer.py`)
- **Targets never run before:** (y − x)·z + c, x·(z + c) − y·y, (x + z)·y + c·x. c = −12..12 except 0 (24);
  3 fit seeds; seed 20261128.
- **Donors:**
  - **Relevant:** two donors of the target's structure (constants from `donor_constants`) over (u, v, w), in role
    order 0 or 5.
  - **Unrelated** (new set over (p, q, r)): 2p + 3q − r + 1 and 2p + 3q + 2r − 6 (two parameters), max(p + 4, q) + r
    and max(p + 1, q) + r (one parameter).
- **Arms:**
  - none, unrelated, relevant_shuffled;
  - standard fits: relevant_r0, relevant_r5, mixed_r0, mixed_r5;
  - degenerate fits: the same four with the fit points drawn from {0,1,2}³.
- **Paired modes:** `family_ambiguity='first'` (control: the default) and `'ask'`. Both use
  `family_parameters='solve'`, `family_scope='any_int'` and `family_mapping='rename'`. Protocol as DEV25, with the
  oracle answering at most 2 questions.
- **Gate G26-A** (pooled over the three structures; standard = the four standard-fit arms, degenerate = the four
  degenerate-fit arms):
  - **C1 recovery:** success(ask) − success(first) ≥ 0.10 on degenerate fits, and the paired exact one-sided McNemar
    test p < 0.01.
  - **C2 no loss:** success(first) − success(ask) ≤ 0.02 on standard fits.
  - **C3 no false transfer:** with asking, success(unrelated) ≤ success(none) + 0.05, and success(relevant_shuffled)
    ≤ 0.05.
  - **C4 safety:** wrong answers per query ≤ 0.02 in every cell, and no more wrong answers with asking than without
    (standard and degenerate together).
  - **C5 few questions:** at most 0.10 questions per attempt on standard fits.
  - **C6 cost:** mean evaluator calls on standard fits, ask / first ≤ 1.50, counting all `induce` calls of an attempt.
  - **C7 role order no longer matters:** with asking, |success(role order 0) − success(role order 5)| ≤ 0.03 for
    relevant and mixed, standard and degenerate fits.
  - **Passes iff C1–C7 all hold.**
- **Reported, not gated:**
  - questions per attempt on degenerate fits;
  - each structure;
  - the attempts that fail with asking, and why;
  - the evaluator calls on degenerate fits.

## Decision rules
- **No promotion, no default change.** If G26-A passes, making `family_ambiguity='ask'` (with
  `family_parameters='solve'`) the default is a decision for the project owner. It changes what `induce` can return
  (`needs_information` from the family step), so callers must answer or ignore the question.
- **R3.** Bugs found during the run are fixed with a regression test; affected runs are discarded, kept, and re-run in
  full. Nothing else changes after seeing DEV26 data.
- **R4.** Every result is reported, including unfavourable ones.
