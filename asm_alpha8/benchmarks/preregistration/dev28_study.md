# DEV28 pre-registration: tolerating one contradicting label

Written and committed to git before any held-out attempt was run. Its SHA-256 is recorded in the DEV28 run manifest.
Anything not listed here is exploratory. Alpha 8 (= milestone 0.4.9) plan item: alpha.8.7 (adversarial generalization
hardening). Testing this change to the contradiction policy was approved by the project owner as an opt-in experiment;
nothing is promoted in DEV28, and no default changes.

## Question
DEV24 measured the strict policy under wrong labels. A hypothesis is suspended at its first contradicting label, so
transfer succeeds only when every label of the target and of both donors is right, and wrong labels never caused a wrong
answer. DEV28 asks: if a hypothesis may survive one contradicting label in total, beside enough agreeing ones, how much
transfer does that recover under wrong labels, and does it ever cost a wrong answer, a false transfer, or transfer on
clean data?

Mechanism (the code as in this commit): `ProcedureCortex(contradiction_policy='tolerant')`, opt-in (default `'strict'`,
unchanged).
- **The rule.** A hypothesis stands with at most one contradicting label in total, counting fit and validation
  together, beside at least `TOLERATED_AGREEMENT` = 4 agreeing labels (`_tolerates`).
- **Where it applies:**
  - `propose`: its training check, which records the contradiction on the version;
  - `observe`: a second contradiction suspends a proposed version and makes an active one suspicious, as the first
    does under `'strict'`;
  - the 2–4-input family step of `induce`;
  - parameter solving (`_solve_tolerant`): each example, or pair of examples for two parameters, votes in order for the
    value it determines until one has as many votes as n + 1 consistent examples give it, so one wrong label cannot
    decide it. The value must then agree with all examples but one and be identified.
- **Unchanged:** the other searches of `induce` and the one-input path stay strict.

## Development evidence (development data only)
DEV24's development structures x·(y + c) + z and x·x·y − z + c, and DEV24's development unrelated set.
- **Labels:** targets and donors get 5 fit labels and 10 validation labels; one wrong label cannot be tolerated among
  three.
- **Noise arms (role order 0):** every label of the target and of the relevant donors is wrong with probability 0.05 or
  0.10 (offsets ±1..3), with one corruption pattern per attempt shared by both modes. A mixed arm at 0.10 adds
  unrelated donors.
- **Clean arms:** none, unrelated, shuffled labels, relevant_r0, relevant_r5, mixed_r0.
- **Constants and seeds:** c = −12..12 except 0; 3 fit seeds; seed 28001.
- **Modes:** both use `family_parameters='solve'`.

Files: `benchmarks/dev28_transfer.py --development`, `benchmarks/results/dev28/development/transfer_dev.jsonl`.

| cell (144 attempts per arm) | strict (control) | tolerant |
|---|---|---|
| wrong labels at 0.05 | 0.118 | **0.597** |
| wrong labels at 0.10 | 0.007 | **0.146** |
| wrong labels at 0.10, with unrelated donors | 0.000 | **0.090** |
| noisy arms together (432) | 0.042 (2,118 evaluator calls) | **0.278** (1,456); 102 vs 0 paired, p = 2.0 × 10⁻³¹ |
| clean relevant and mixed arms (432) | 0.998 (66 calls) | 0.993 (100 calls) |
| none / unrelated / shuffled labels | 0 / 0 / 0 | 0 / 0 / 0 |

- **No wrong answer in any cell.**
- **The 2 clean losses** were in the mixed arm. An unrelated two-parameter family agreeing with 4 of 5 fit labels was
  proposed first, and clean validation suspended it (no answer).
- **Under noise at 0.10**, success needs at most one wrong label in the target and in each donor; a donor with two
  never activates, so no family forms.
- **Changes after looking at development results:**
  - **The solver.** It first scored a solution from every example on all examples, which cost 4.3× strict's
    evaluator calls on clean arms (C5 not met). It now votes with early stopping: the same successes, at 1.5×.
  - **One test expectation** was corrected: strict solving returns the value of the first label, which the check then
    rejects.
- **Defaults unchanged.** With `'strict'`, all eight committed DEV21–DEV24 lab runs reproduce every attempt record
  (`benchmarks/lab_check.py <dir> family_mapping=exact`).
- **Static checks on the held-out material** (no attempt run): the held-out unrelated donors form two families (one
  and two parameters); each held-out structure forms one one-parameter family; every target is valid.
- Tests: `tests/test_alpha8_dev28.py` (6).

## Held-out test (`benchmarks/dev28_transfer.py`)
- **Targets never run before:** y·(x + c) − z, z·z + x·(y − c), (x − y)·(z + c). c = −12..12 except 0 (24);
  3 fit seeds; seed 20261130.
- **Donors:**
  - **Relevant:** two donors (constants from `donor_constants`) over (u, v, w).
  - **Unrelated** (new set over (p, q, r)): p + 2q + 3r + 2 and p + 2q − r − 3 (two parameters), max(p, q + 2) − r
    and max(p, q + 6) − r (one parameter).
- **Arms:** as in development. Clean: none, unrelated, relevant_shuffled, relevant_r0, relevant_r5, mixed_r0. Noisy:
  noise05_r0, noise10_r0, noise10_mixed_r0.
- **Paired modes:** `contradiction_policy='strict'` (control: the default) and `'tolerant'`. Both use
  `family_parameters='solve'`, `family_scope='any_int'` and `family_mapping='rename'`. 5 fit labels, 10 validation
  labels, success = 6 queries answered correctly.
- **Gate G28-A** (pooled over the three structures; noisy = the three noise arms; clean relevant = relevant_r0,
  relevant_r5 and mixed_r0):
  - **C1 noise gain:** success(tolerant) − success(strict) ≥ 0.15 on noisy arms, and the paired exact one-sided McNemar
    test p < 0.01.
  - **C2 no clean loss:** success(strict) − success(tolerant) ≤ 0.02 on clean relevant arms.
  - **C3 no false transfer:** with tolerance, success(unrelated) ≤ success(none) + 0.05, and success(relevant_shuffled)
    ≤ 0.05.
  - **C4 safety:** wrong answers per query ≤ 0.02 in every cell, and with tolerance at most 0.005 above strict in every
    arm.
  - **C5 cost:** mean evaluator calls on clean relevant arms, tolerant / strict ≤ 3.0.
  - **Passes iff C1–C5 all hold.**
- **Reported, not gated:**
  - each noise level and structure;
  - success by the number of wrong labels;
  - the attempts that tolerance loses, and why;
  - the evaluator calls under noise.

## Decision rules
- **No promotion, no default change.** This changes a safety-critical policy. If G28-A passes, whether to use
  `'tolerant'` anywhere by default is a decision for the project owner.
- **R3.** Bugs found during the run are fixed with a regression test; affected runs are discarded, kept, and re-run in
  full. Nothing else changes after seeing DEV28 data.
- **R4.** Every result is reported, including unfavourable ones.
