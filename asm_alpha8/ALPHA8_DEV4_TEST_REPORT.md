# Alpha 8 DEV4 Test Report

**Artifact:** `ASM_alpha8_DEV4.zip` (parent: `ASM_alpha8_DEV3_3.zip`, sha256 f4be197c51eb3ba1974d4f07d0e7605c77eaf9790ae939fe5999d2638b32b5e5).
Development prototype; not an official release; no Alpha 8 capability claim. **No ASM core file was modified** (additions only under `asm/learning/`, tests, docs, results).

## Verified
- DEV4 tests: **18 passed**. Part A: tasks deterministic, truth inside the grid, queries unseen, interior in every dimension and determined by the pool; hand-computed values for all six family formulas and grid sizes;
  reference safe and learning; controls collapse; deterministic runs; verdicts pass for good learners and fail for sabotaged ones (liar, quitter, cheating canary); ASM adapter value mapping, learning of an in-grammar family, and exception reporting.
  Part B: donor constants never equal the target and are distinct; each arm installs the intended number of ACTIVE donors; attempts deterministic; the discovered capability is pinned (two relevant donors solve what none/one donor cannot, via the family mechanism,
  with at least 5x fewer evaluator calls; shuffled labels never get proposed); out-of-range constants unreachable; derangement property; evaluator verdicts flip correctly on synthetic results including a donor leak; pre-registration doc equals code and the hash is recorded.
- Targeted run (DEV4, DEV3.3, DEV3.2, DEV3.1, DEV3, DEV2, DEV1, 7.9 compatibility): **154 passed**.
- Full non-torch regression: **536 passed, 57 failed, 1 skipped**; the 57 failures are the same test set as the torch-only baseline (0 new). An independent audit of DEV2.1 with PyTorch present reported them passing.
- Mutation checks, all caught: held-out inputs left in the pool; determined-query filter removed; queries allowed outside the pool range; reference answering when undetermined; wrong linear2 formula; donors allowed to use the target constant;
  donors never validated; T1 comparator flipped; donor-leak check disabled; shuffled arm not shuffled; shuffled arm using a plain shuffle instead of a derangement. Three survived at first and led to stronger tests (hand-value formulas, a status check on the shuffled arm, and a derangement).
- A harness defect (identity shuffle in the shuffled control, 1 time in 6 for 3 labels) was found before any result was read; the run was restarted after the fix.
- Reproducibility: the official benchmark was repeated in a fresh process and its results (excluding runtime) are identical.
- Outcome reported as obtained: harness checks all pass; A1, A2, T1, T2, T3, T4, T5 PASS; **A3 and T3b FAIL**. No threshold was changed after results existed.

## Not verified
- The 3 torch-dependent test files and the 57 torch-related failures were not run with PyTorch here.
- The diagnosed cause of the T3b failure (shared 64-candidate family budget consumed by an earlier template) comes from reading `induce` and listing the families; it has not been confirmed by a fix and re-test.
- One seed; toy families; one target structure for transfer; donors installed through the public API, not learned autonomously; ASM information queries unanswered.
- Cross-domain transfer, continual learning, causal discovery, real data: not evaluated. DEV2 limits (Windows, multi-process writers, crash injection, very large logs) still apply.
