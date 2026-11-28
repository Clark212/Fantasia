# ASM v0.4.0-alpha.5.1 — Release Notes

Same-stage hardening of **ASM v0.4.0-alpha.5 — Belief-State Planning & Partial Observability**. This is not alpha.6 and does not add a new cognitive capability category.

## What changed

- Beliefs are retained internally in normalized **log-probability space**, so floating-point underflow in the public probability view does not permanently delete a merely tiny hypothesis.
- **Structural zero** hypotheses are now distinguished from soft numerical near-zero hypotheses. Structural zeros remain impossible; tiny nonzero hypotheses remain recoverable.
- Likelihood inputs now fail closed when structurally invalid: non-finite values, negatives, values above 1, empty maps, missing/extra hypotheses, mixed malformed rows, all-zero observation likelihoods, duplicate/ambiguous observation rows, and materially non-normalized conditional distributions are rejected.
- Tiny normalization error is tolerated at an absolute per-hypothesis tolerance of `1e-9`.
- Memo keys retain alpha.5's compact quantized posterior representation but also include the exact posterior ranking, preventing near-50/50 opposite-ranking states from collapsing to the same memo entry.
- Planner status now distinguishes search that completed from search that stopped because its expansion budget was exhausted. A budget-limited result is reported as `budget_exhausted_partial_policy` rather than looking like a fully evaluated plan.
- Result metadata now exposes `search_complete`, `search_budget_exhausted`, `hypothesis_cap_reached`, and `probability_mass_truncated`.
- Snapshot key remains the alpha.5.1 key already present in this candidate: `asm_snapshot_v0_4_0_alpha_5_1`, with the existing alpha.5 migration fallback retained.

## BEFORE vs AFTER fixes

| Failure | BEFORE | AFTER alpha.5.1 |
|---|---|---|
| Hypothesis resurrection | 200 × 99%-A followed by 200 × 99%-B could remain stuck at A≈100% after probability underflow | Returns to A≈50%, B≈50%; underflowed public probability remains recoverable from internal log belief |
| Malformed likelihood matrix | Invalid probability models could be accepted or effectively normalized into a usable posterior | Structurally invalid likelihood models fail closed |
| Memo boundary attack | 12-decimal posterior quantization produced **251 opposite-action collisions / 20,000** adversarial near-50/50 cases | **0 / 20,000** after ranking-aware memo keys |
| Search-budget reporting | A partial policy could still carry a normal plan-found style status in low-budget cases | Low-budget cases explicitly report `budget_exhausted_partial_policy` and `search_complete=false` |

The first two BEFORE failures were the failures that motivated this hardening branch. The memo collision result was reproduced directly during this session before and after its fix.

## Compatibility / scope

The 32-hypothesis architectural cap was **not raised**. No model-learning, latent discovery, calibration, correlation detection, or automatic sensor-reliability estimation was added.

The old mega-feed's top-k truncation case intentionally supplies an incomplete conditional likelihood matrix and expects it to be accepted while omitted mass becomes unknown. Under the stricter alpha.5.1 probability contract, that input is now invalid. The unchanged old mega suite therefore reports 13/14; the failing check is preserved and documented rather than rewritten to manufacture a green result.
