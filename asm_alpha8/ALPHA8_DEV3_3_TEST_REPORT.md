# Alpha 8 DEV3.3 Test Report

**Artifact:** `ASM_alpha8_DEV3_3.zip` (parent: `ASM_alpha8_DEV3_2.zip`, sha256 1fb7bc28613ae6a3e43aa147a491c85e43fde568813e9c7a7f6d6d3b42ced4d3).
Development prototype; not an official release; no Alpha 8 capability claim. **This revision changes a core default** (`extrapolation_guard`: `off` -> `abstain`).

## Verified
- Full non-torch regression: **518 passed, 57 failed, 1 skipped**. The 57 failures are exactly the same test set as the pre-DEV3.2 torch-only baseline (0 new, 0 fixed); they come from
  PyTorch being unavailable in this sandbox. An independent audit of DEV2.1 with PyTorch present reported them passing. The DEV3.1 expected-failure marker no longer appears because that test now passes.
- Targeted run (new default tests, guard tests, DEV3.1, DEV3, DEV2, DEV1, 7.9 compatibility, alpha 7.1 audit, alpha 7.2 autonomy): **156 passed**.
- What flipping the default broke, and how it was handled: 14 tests failed that had passed before. 5 older tests (alpha 7.1 audit x1, alpha 7.2 autonomy x4) assert extrapolated values at x=99/100/40/60; they now use the
  explicit legacy setting with **no assertion changed**. 9 tests written in DEV3.1/DEV3.2 encoded the old default and were updated (the DEV3.1 tripwires fired as designed).
- New tests (10) pin the defaults (cortex, config, engine), the one-setting rollback, behaviour on the alpha 7.1/7.2 scenarios under the default (inside range and both boundaries answered, interior gap answered, outside refused, survives
  close/reopen, untrusted evidence still suspends first, legacy mode still extrapolates), and that guarded predictions remain read-only.
- Mutation checks, all caught: default reverted in cortex, default reverted in config, engine ignoring config, guard never firing under the default, plus the 10 guard mutations from DEV3.2 re-run against the edited tests.
- Reproducibility: the pre-registered DEV3 and DEV3.1 results reproduce identically with the historical runners pinned to `extrapolation_guard="off"` (DEV3 suite log byte-identical). The regenerated guard comparison shows the default
  row equal to explicit `abstain` and identical ASM results on the DEV3 families with the guard off versus the default.

## Not verified
- The 3 torch-dependent test files and the 57 torch-related failures were not run with PyTorch here.
- Behaviour on real data, in downstream consumers of `predict_procedure` / `predict_routed`, or at scale (the guard reads a mechanism's evidence rows per prediction).
- One toy population and one seed for the evidence behind the decision; author-set thresholds; author and runner are the same party.
- Cross-task transfer, continual learning, causal discovery and cognitive-core integration remain unevaluated; DEV2 limits (Windows, multi-process writers, crash injection, very large logs) still apply.
