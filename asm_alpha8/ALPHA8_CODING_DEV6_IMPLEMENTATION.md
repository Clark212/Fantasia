# ASM Alpha 8 — Coding Intelligence DEV6

## Status
Experimental coding-intelligence development fork based on `ASM_alpha8_CODING_DEV1.zip`. DEV3.2 and DEV4 remain untouched and are not promoted or overwritten.

## What DEV6 adds

1. **Repository model (DEV1 foundation):** deterministic Python AST indexing of files, symbols, imports, calls, and local dependency edges; stable repository fingerprint; bounded scan limits.
2. **Task planning:** explainable task classification and heuristic file ranking, with explicit evidence and cautions.
3. **Patch proposals:** single-file replacement proposals with unified-diff preview, expected-content SHA-256 guard, path traversal/symlink checks, atomic replacement, and a pre-change backup.
4. **Test execution:** pytest invocation through an argument list (never a shell), repository-relative target validation, bounded timeout, bounded captured output, and a reduced environment.
5. **Verified procedure memory:** append-only JSONL records; only passing test runs can be recorded; records are hash-checked when read.
6. **Workflow coordinator:** `CodingAgent.inspect()` produces a repository-backed plan; `CodingAgent.test()` runs an explicit test request. It does not silently modify files.

## Safety and authority boundaries

- ASM's core remains the decision authority; coding helpers return evidence and proposals.
- No automatic source generation model is included. A caller must supply replacement source in a `PatchProposal`.
- No automatic patch application is performed by `CodingAgent`.
- Patch application is explicit and hash-guarded, with backup enabled by default.
- The test runner is **not an OS security sandbox**. Tests execute repository code with the current user's permissions. Timeouts and argument validation do not isolate malicious code. Use only with repositories and tests you trust; a future isolated runner needs OS/container-level controls.
- Static analysis does not prove semantic correctness. Passing tests only establish that the selected tests passed in that run.
- Procedure records preserve successful workflow evidence, not generalized coding intelligence. They are not automatically replayed as trusted code.
- Current analyzer supports Python only; no semantic embeddings, type inference, LSP integration, multi-file transactional patches, or autonomous repair loop.

## Validation

### Targeted regression

Command:

```bash
python -m pytest -q \
  tests/test_alpha8_coding_intelligence.py \
  tests/test_alpha8_coding_dev6.py \
  tests/test_alpha8_dev2_persistence.py \
  tests/test_alpha8_dev3_1_underdetermined.py \
  tests/test_alpha8_dev3_2_extrapolation_guard.py \
  tests/test_alpha8_dev3_3_default_abstain.py \
  tests/test_alpha8_dev4_structdiscovery.py
```

Result: **111 passed, 8 subtests passed**.

### Full historical suite

Command: `python -m pytest -q`

The run reached 33% before the 240-second execution limit and was terminated. This is **incomplete**, not a pass or a test failure diagnosis. Full-suite status remains unverified.

### Compilation

`python -m compileall -q asm/coding tests/test_alpha8_coding_dev6.py` is included in the release checks.

## New test coverage

- Patch applies only when target hash matches.
- Stale patch rejected.
- Parent-directory traversal rejected.
- Patch backup created.
- Test runner executes an explicit repository-relative pytest target.
- Test target traversal rejected.
- Failed test evidence cannot enter procedure memory.
- Tampered procedure record is detected.
- Coding coordinator remains non-mutating.

## Next research steps

1. Add semantic symbol/call resolution and ranking beyond token overlap.
2. Add multi-file patch sets with all-files precondition checks and rollback.
3. Add a trusted isolated execution backend; do not call the current runner a sandbox.
4. Add failing-test-to-diagnostic localization and evidence-ranked repair hypotheses.
5. Add a proposal generator interface, keeping generator output untrusted until reviewed and tested.
6. Add cross-language indexing after Python workflows are measured.
7. Benchmark against a fixed coding-task set with hidden tests, time/call budgets, and ablations.

## Release decision

DEV6 is a useful coding-workflow foundation, not yet a coding system comparable to a large code-capable language model. Do not claim autonomous software engineering or broad coding competence from these tests. Keep this release experimental until the full historical suite and a reproducible coding benchmark complete.
