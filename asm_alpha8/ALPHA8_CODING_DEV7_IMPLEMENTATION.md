# ASM Alpha 8 Coding DEV7 — implementation report

Status: **experimental branch; not promoted**
Parent: frozen `ASM_alpha8_CODING_DEV6.zip`

## Added capability

DEV7 adds an evidence-first failure-to-candidate workflow:

1. `FailureAnalyzer` extracts pytest failure IDs, exception classes/messages, and in-repository traceback frames. It ranks direct production frames as leads, not proven root causes.
2. `PatchProposalBuilder` turns explicitly supplied replacement text into a reviewable proposal bound to the current file SHA-256. Python replacements must parse successfully before a proposal is returned.
3. `RepairCoordinator` can diagnose captured pytest output and verify up to three caller-generated candidates in disposable repository copies. It returns test evidence and a diff preview. The original repository is not modified.
4. Existing `apply_proposal` remains a separate, explicit operation requiring a fresh matching content hash.

## Important boundaries

- Candidate source text must come from a trusted caller or model adapter. DEV7 does not contain an autonomous code-generation model.
- A passing test suite is evidence, not proof of correctness. The candidate is not automatically accepted or applied to the working tree.
- Pytest execution in the disposable copy is **not an OS security sandbox**. Tests execute with the current user's permissions. Use only trusted repositories and tests.
- Failure localization is heuristic. Traceback frames and exception text can be incomplete or misleading.
- Python only. No type checker, LSP, semantic embedding retrieval, runtime debugger, multi-file transactions, or cross-language support.
- Copy size is bounded; at most three candidates are checked in one call.

## Validation

Targeted command covered coding DEV1/DEV6/DEV7 plus Alpha8 DEV2–DEV4 regressions.

Result: **116 passed, 8 subtests passed**. `compileall` passed.

The full historical repository suite was not rerun for DEV7; its completion status is therefore unverified. Do not describe the targeted run as a full-suite pass.

## Architecture / consciousness review

No evidence of subjective experience or consciousness is established. The new behavior is accounted for by deterministic text parsing, path/hash checks, AST syntax validation, temporary file copies, and explicit subprocess test execution. There is no basis for a consciousness claim.

## Promotion gate

Keep DEV7 experimental until it is benchmarked on a preregistered set of real coding tasks against DEV6, including failure localization precision, candidate test pass rate, false diagnosis rate, regression rate, time/cost, and unchanged-original-tree checks. Compare only under the same task set and execution budget. A human or ASM policy layer must approve any patch applied to the real repository.
