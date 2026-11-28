# DEV24 pre-registration: three-input transfer across input names, and wrong labels

Written and committed to git before any held-out attempt was run. Its SHA-256 is recorded in the DEV24 run manifest.
Anything not listed here is exploratory. Alpha 8 (= milestone 0.4.9) plan items: alpha.8.7 (adversarial generalization
hardening) and alpha.8.4 (negative transfer protection), with alpha.8.3 and alpha.8.8 (scaling). Nothing is promoted in
DEV24, no default changes, and no ASM code changes: DEV24 measures the cortex as it is (the defaults since 2026-11-23).

## Questions
- **Part A.** DEV23 showed transfer across input names for two-input targets (two mappings per family). With three
  inputs there are six mappings per family. Does the same mechanism find the right one in every role order, without
  false transfer, wrong answers or losses, and how does the per-source budget share out when unrelated families also
  propose?
- **Part B** (measure only, by the owner's choice). The cortex suspends a hypothesis at its first contradicting label and
  activates one only after 8 matching validation labels, so a wrong label cannot be absorbed. With wrong labels at a
  pre-registered rate in the target's and the donors' evidence: does any wrong answer appear, and does success fall by
  no more than the corrupted attempts predict?

Mechanism under test (unchanged code): `ProcedureCortex(family_scope='any_int', family_mapping='rename')`.
- **Search order:** for an all-integer target with 2–4 inputs, `induce` first tries the instantiations (parameters −8..8)
  of every learned family under every type-preserving mapping of its inputs onto the target's.
- **Sources and budget:** each (family, mapping) is a source in round robin, with 17 proposals per source up to
  256. The positional mapping comes first; then the affine solve and the generic searches run.

## Development evidence (development data only)
Development structures x·(y + c) + z and x·x·y − z + c. A development unrelated set over (p, q, r): affine
2p + q + r + 1 and 3p + q + r − 4, max(p, q + 1) + r and max(p, q + 5) + r. Seed 20261123; 96 in-range attempts per
cell, paired (`benchmarks/dev24_transfer.py --development`, `benchmarks/results/dev24/development/transfer_dev.jsonl`).

| arm | control (`exact`) | renaming (`rename`, the default) |
|---|---|---|
| relevant donors over (u, v, w), role orders 0, 1, 2 | 0/96 each (1,536 evaluator calls) | **96/96** each (53–55) |
| relevant donors, role orders 3, 4, 5 | 0/96 each | **95/96** each (56–58) |
| mixed (relevant + unrelated), role order 0 / 5 | 0/96 | 78/96 / 77/96 (302, 307) |
| the same, constants within the budget's reach (−8..5) | 0/78 | **78/78 / 77/78** |
| none / unrelated / shuffled labels | 0/96 each | 0/96 each |
| donors over (x, y, z) (exact names) | 96/96 (12) | 96/96 (12) |
| unrelated arm, evaluator calls | 1,536.0 | 1,133.1 (ratio 0.74) |
| label noise 0.10: target / donors / both | 0/96 each | 32/96, 5/96, 2/96 |
| the same, per-attempt prediction | 0 | 32/96, 5/96, 2/96 |

- Paired over the six role orders: 573 attempts succeed only with renaming, none only with the control (p = 3.2 × 10⁻¹⁷³).
- **No wrong answer in any cell**, noise arms included. No attempt with a wrong target label gave any answer (in
  rename mode, 57 unresolved and 37 proposed and then refuted by validation).
- **The search without families solves no three-input target with three fit points.** The affine solve refuses
  underdetermined fits, and the other searches either find nothing or find programs that only fit the three points:
  - x + y + z + c: unresolved in 47 of 48 attempts;
  - x·y + z + c, x·y + c·z, max(x, y) + z + c: 0 of 48 each.

  So **Part A has no separate regression target**; C7 uses the exact-name and unrelated arms.
- **The 3 role-order failures** are one fit: x·(y + c) + z at c = 2 with fit points (1,6,1), (2,2,2), (2,4,2). There
  x = z at every point, so a mapping that swaps them fits too. It comes earlier than the right one for orders 3, 4 and
  5; validation refutes it and no answer is given (DEV23's mapping ambiguity).
- **Budget arithmetic, confirmed.** The mixed arms have 1 relevant and 2 unrelated families, 6 mappings each: 18 sources
  share 256 proposals. Each source reaches 14 parameter values (−8..5); constants 6, 7 and 8 are out of reach. In
  development every out-of-reach mixed attempt failed and every within-reach one matched the relevant arm.
- Out-of-range constants (|c| = 9..12): 0 in both modes (parameters span −8..8).
- **Noise and donor survival.** Under donor noise, 74, 58 and 12 of 144 attempts kept 0, 1 and 2 active donors, as
  0.9¹¹ per donor predicts (68, 62, 14). A family needs two.
- **Design checks on the held-out material** (static: no attempt run, no outcome measured):
  - the held-out unrelated donors form exactly two families, with two parameters and one;
  - the donors of each held-out structure form one one-parameter family in every role order;
  - every held-out donor and target is a valid program equal to its function.
- Tests: `tests/test_alpha8_dev24.py` (7).

## Held-out test (`benchmarks/dev24_transfer.py`)
- **Targets never run before** (one constant c each): (x + c)·y − z, x·y·y + z + c, (x − z)·(y + c). In-range
  c ∈ −8..8 except 0 (16), out-of-range |c| ∈ 9..12 (8); 3 fit seeds; seed 20261126.
- **Donors:**
  - **Relevant:** two donors of the target's structure, never with its constant (`donor_constants`), over inputs
    (u, v, w), in role order k = 0..5 (the cortex's k-th mapping is the right one), named to sort after the unrelated
    donors.
  - **Exact names:** the same donors over (x, y, z).
  - **Unrelated** (new set over (p, q, r)): 4p − q + 2r + 3 and 4p + 2q + 2r − 5 (a two-parameter family);
    max(p − 2, q) + r and max(p − 6, q) + r (one parameter).
- **Part A arms:** none, unrelated, relevant_r0 … relevant_r5, relevant_shuffled (order 0, target labels shuffled),
  mixed_r0 and mixed_r5 (relevant + unrelated: the right mapping first and last), exact_names.
- **Part B arms** (role order 0): noise_target, noise_donors, noise_both.
  - Each label of the target (3 fit + 8 validation), of each relevant donor (3 + 8), or of both is wrong with
    probability 0.10, by an offset in ±1..3.
  - One corruption pattern per attempt for the target and one for the donors, shared by the arms.
- **Paired modes:** every attempt runs with `family_mapping='exact'` (control) and `'rename'` (the default), both with
  `family_scope='any_int'`.
- **Protocol:** DEV23's, in three dimensions.
  - A fresh cortex. Donors go through propose + validation: 3 fit points, then 8 validation points with coordinates in
    10..17.
  - The target gets 3 fit points drawn from the 10 × 10 × 10 grid, one induce (budget 512), then 8 validation points.
  - Success = 6 query points all answered correctly. Queries are drawn from the fit's minima up to 9, extended to 17
    minus the validation points if fewer than 6 exist.
- **Gate G24-A** (in-range constants, pooled over the three structures, renaming unless stated; relevant = the six
  role orders together):
  - **C1 gain over the control:** success(rename, relevant) − success(exact, relevant) ≥ 0.30, and the paired exact
    one-sided McNemar test p < 0.01.
  - **C2 no role-order penalty:** success(relevant_r0) − success(relevant_rk) ≤ 0.10 for every k.
  - **C3 transfer gain:** success(relevant) − success(none) ≥ 0.50.
  - **C4 no interference within the budget's reach:** for k = 0 and 5, success(relevant_rk) − success(mixed_rk) ≤ 0.10
    on the constants the budget reaches (−8..5 except 0).
  - **C5 no false transfer:** success(unrelated) ≤ success(none) + 0.05, and success(relevant_shuffled) ≤ 0.05.
  - **C6 safety:** wrong answers per query ≤ 0.02 in every Part A cell (each arm and mode, in and out of range).
  - **C7 no regression:** success(rename) ≥ success(exact) − 0.05 on exact_names and on unrelated.
  - **C8 cost:** mean evaluator calls on the unrelated arm, rename / exact ≤ 1.10.
  - **Passes iff C1–C8 all hold.**
- **Gate G24-B** (noise arms, both modes):
  - **B1 safety under noise:** wrong answers per query in every noise cell (each arm and mode, in and out of range)
    ≤ 0.02, and at most 0.005 above the noise-free relevant_r0 cell.
  - **B2 success at least as predicted:** success ≥ prediction − 0.05 for each noise arm and mode. The prediction, per
    attempt:
    - no success if a target label is wrong;
    - the arm without donors' outcome if only donor labels are wrong (two active donors are needed for a family);
    - the noise-free role-order-0 outcome otherwise.
  - **Passes iff B1 and B2 hold.**
- **Predictions** (reported, not gated):
  - **The control:** about 0 on every arm but exact_names.
  - **Mixed arms:** constants 6, 7, 8 out of reach, about the none arm's success; overall about 13/16 of the
    relevant arm's.
  - **Out-of-range constants:** about 0 in both modes.
  - **Role-order failures:** only at fits where a wrong mapping also fits, refuted without an answer.
  - **Noise:** success about the probability of clean labels times the noise-free success: about 0.31 (target),
    0.10 (donors), 0.03 (both). No answer from an attempt with a wrong target label.

## Decision rules
- **No promotion, no default change.** A pass is evidence from a noise-free and a noisy lab, not a validated alpha 8
  target.
- **R3.** Bugs found during the run are fixed with a regression test; affected runs are discarded, kept, and re-run in
  full. Nothing else changes after seeing DEV24 data.
- **R4.** Every result is reported, including unfavourable ones.
