# ASM v0.4.0-alpha.5.1 — Hard-Feed / Torture Report

## Final executed suites

| Suite | Result |
|---|---:|
| Core alpha.5 benchmark | 13/13 PASS |
| Original alpha.5 hard feed | 6/6 PASS |
| Unchanged previous mega-feed | 13/14 (1 documented contract incompatibility) |
| Extreme resurrection torture | 9/9 PASS |
| New alpha.5.1 torture feed | 10/10 PASS |
| v0.4 unit tests incl. new contract tests | 59/59 PASS |

## Numerical stability

The final branch survived:

- the existing **1,000,000 posterior-update** log-oracle torture run;
- reversible contradiction chains from small cases through 200,000 updates in the added feed;
- 250 shuffled extreme contradiction sequences;
- priors down to `1e-300`;
- machine-subnormal likelihood input (`5e-324`) without NaN/inf in internal logs or entropy;
- 32 hypotheses with 10,000 hostile updates;
- repeated reversals and block recovery;
- entropy calculations near certainty.

The extreme suite's 1,000,000-update oracle comparison remained within its existing tolerance and passed.

## Structural zero vs soft near-zero

Verified behavior:

- A hypothesis initialized or eliminated with an exact structural zero remains impossible.
- A hypothesis with tiny but nonzero mass, including `1e-300`, remains internally represented and can later become MAP under sufficiently contradictory evidence.
- Public probability may display an astronomically small recoverable hypothesis as `0.0` while its finite internal log probability remains preserved.

## Likelihood contract validation

New contract tests exercised invalid likelihood inputs including:

- sums > 1;
- sums < 1;
- negative probabilities;
- NaN;
- +inf / -inf;
- empty maps;
- missing hypotheses;
- extra hypotheses;
- mixed rows with missing likelihood maps;
- all-zero evidence rows;
- duplicated/ambiguous observation identities;
- malformed direct update keys/values;
- materially invalid normalization.

Tiny normalization error within `1e-9` is accepted.

The direct contract unittest file contains 4 test methods, including 12 malformed matrix subcases; all passed in the final v0.4 unit rerun.

## Memoization attack

A new adversarial near-50/50 feed found a real failure before the final memo fix:

- BEFORE: **251 opposite-action memo-key collisions / 20,000 cases**.
- AFTER: **0 / 20,000**.

A first attempted exact-float memo key removed the collision but regressed the original hard feed to 5/6 due loss of useful posterior merging. That attempt was rejected. The final ranking-aware quantized key restored:

- core benchmark 13/13;
- original hard feed 6/6;
- seven-clue result 108 expansions / 140 memo hits / 77 nodes;
- near-tie attack 0/20,000 collisions.

## Model misspecification — measured, NOT fixed

Alpha.5.1 still trusts a structurally valid supplied model. The new feed deliberately measured this limitation:

| Supplied / assumed model | Actual world | Claimed | Actual | Confidence gap |
|---|---|---:|---:|---:|
| 90% sensor | 70% sensor | 99.144% | 83.692% | +15.452 pp |
| 70% sensor | 90% sensor | 83.692% | 99.144% | -15.452 pp |
| 70% independent | 70% fully correlated repeated evidence | 83.692% | 70.000% | +13.692 pp |
| 80% sensor | actual 20% | 89.600% | 10.400% | +79.200 pp |
| assumed 90% | adversarial flip 90%,90%,10%,10%,10% | 99.144% | 22.456% | +76.688 pp |
| assumed 90% | sensor breaks to 50% after two clues | 99.144% | 80.000% | +19.144 pp |
| assumed 80% | stale after world change 80%,80%,20%,20%,20% | 94.208% | 34.592% | +59.616 pp |

`automatic_mismatch_detection` remains **false**. That is intentionally left visible as evidence for a future capability stage rather than patched with hard-coded corrections.

## Sensor choice / sensing cost

With equal sensing cost, the planner selected the 90%-reliable sensor over the 70%-reliable sensor. When the 90% sensor was assigned a 0.25 action cost under the tested utility settings, it selected the 70% sensor instead. This confirms reliability-vs-cost behavior in the tested bounded setup.

## Known limitations / bottleneck evidence

The strongest remaining architectural bottleneck is **model validity vs model truth**:

- alpha.5.1 can reject structurally malformed probability models;
- it cannot determine that a structurally valid model is factually wrong;
- it does not estimate sensor reliability online;
- it does not detect correlated evidence automatically;
- it does not learn likelihoods;
- it does not discover new latent causes;
- it does not automatically flag persistent calibration mismatch.

That failure evidence supports the proposed later direction of model learning/calibration, but no alpha.6 implementation is included here.

A separate planning limitation remains: astronomically rare evidence branches with probability `<= 1e-15` are pruned by bounded planning even though the underlying hypothesis remains preserved in log-space.

## Suite not fully rerun

A repository-wide `unittest discover` attempt was started but did not complete within the execution window, so it is **not** counted as a pass. The very old alpha.8-alpha.10 mega long-stream suites were also not freshly rerun. Therefore this package does **not** claim full-stack historical recertification.

The unchanged old mega-feed reports 13/14 because its top-k truncation check expects an incomplete conditional likelihood matrix to remain usable. Alpha.5.1 now rejects that input under the strict probability contract. The old suite was kept unchanged so this incompatibility remains visible.
