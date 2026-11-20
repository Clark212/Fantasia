# DEV6 Architecture Review

## Decision authority
The ASM cognitive core is not replaced. The coding subsystem is an evidence-producing tool layer: analyzer and planner report; patch proposal is untrusted input; explicit patch application requires a matching file hash; test runner reports outcomes; procedure store accepts only passing-run evidence.

## Capability boundary
The package now supports Python repository indexing, heuristic task decomposition, single-file replacement proposals, guarded application, bounded pytest invocation, and provenance-aware procedure records. It does not yet autonomously invent reliable source code, reason semantically at large-project scale, or perform unattended repair loops.

## Failure and adversarial cases considered
- Stale patch after a concurrent edit: rejected by expected SHA-256 mismatch.
- `../` path traversal or absolute path: rejected.
- Symlink in target path: rejected.
- Test process hangs: bounded by timeout.
- Test target escapes repository: rejected.
- Failed or timed-out test evidence: rejected by procedure store.
- Procedure record edited after writing: hash mismatch detected on read.

## Remaining risks
- The test runner is not a security sandbox. Repository tests run with the current user's permissions; hostile tests can still access the host within those permissions.
- Patch writes are single-file atomic replacements, not multi-file transactions.
- A backup filename collision with a different prior content hash is avoided by including the old hash prefix, but backup-directory permissions remain host filesystem permissions.
- Heuristic file ranking can miss relevant code or over-rank token coincidences.
- Static AST parsing is Python-only and does not resolve dynamic imports, runtime monkey-patching, or full type semantics.

## Consciousness-related review
No evidence in this coding subsystem supports a claim of subjective experience or consciousness. Its behavior is explained by deterministic parsing, heuristics, explicit subprocess execution, hashing, and storage. No consciousness claim is made.

## Release recommendation
Keep DEV6 experimental. It is a meaningful engineering foundation, not yet a coding agent comparable to a large code-capable language model. Require full historical regression and a preregistered coding benchmark before promotion.
