# ASM Alpha 8 Coding DEV8 — Autonomous Coding Research (implementation report)

Status: **experimental branch; NOT promoted**
Parent: `ASM_alpha8_CODING_DEV7` (preserved unchanged in its own directory)

## Added capability
`asm/coding/research.py` adds `CodingResearchLoop`, a bounded multi-round research loop:

1. **Baseline**: runs pytest on an unmodified disposable copy; records failing test IDs and diagnoses them (DEV7 `FailureAnalyzer`). If the baseline passes, nothing is attempted.
2. **Generate**: calls a trusted caller-supplied generator with a `ResearchContext` (task, round, baseline failures, diagnostics, prior failure evidence).
3. **Verify**: each candidate is hash-bound, syntax-checked, applied to a fresh disposable copy and tested.
4. **Compare**: per attempt records fixed tests, **regressions** (new failures vs baseline), failure count, diff size, duration. Ranking: passes > fewer regressions > fewer failures > smaller diff > faster.
5. **Learn from failure**: failed/rejected attempts go into an append-only, SHA-256 integrity-checked `FailureLedger`. Evidence is fed to later rounds (and later sessions); identical candidates already known to fail are skipped.
6. **Return, never apply**: result carries best attempt, proposal and diff preview. A tree fingerprint proves the original was unchanged. A `ProcedureStore` record is written only on a passing result.

Guards: test files/`conftest.py` are protected by default (a candidate cannot "pass" by editing tests); hard caps of 10 rounds and 8 candidates/round; wall-clock budget; copy-size limit; unparsable non-zero pytest runs never count as clean.

## Validation (actually run)
- Baseline before changes: DEV7 coding tests 16 passed; all `tests/test_alpha8_*.py` 156 passed, 8 subtests.
- After: **13 new DEV8 tests; all `test_alpha8_*.py`: 169 passed, 8 subtests**. `compileall` passed.
- Mutation check: 4 deliberate defects (protection off, duplicate check off, regression ranking off, parse fallback off). Initially 2 survived (weak tests); tests were strengthened and **all 4 are now caught**.
- DEV7 directory diff: only `asm/coding/__init__.py` (2 export additions), plus 2 new files.
- The full historical suite (non-alpha8 tests, benchmarks) was **not** rerun; its status is unverified.

## Limits — read before relying on this
- **ASM has no code-generating model.** DEV8 supplies the search, comparison and memory *machinery*. Real capability depends on the generator attached, which does not exist yet here.
- **No benchmark was run, so no improvement over DEV7 is claimed.** The unit tests use scripted generators and prove mechanism correctness, not coding skill.
- Pytest in a copy is **not an OS sandbox**; use trusted repos/tests only. Passing tests is evidence, not proof of correctness.
- Single-file candidates only; Python/pytest only. "Learning" is bounded to ledger feedback to the generator plus duplicate avoidance; ASM's own weights/policies do not change.
- Cost: one full repo copy + pytest run per candidate (worst case 80 + baseline). Large repos are slow; memory is bounded by copy-size limit, not profiled.
- No consciousness-related claim: behavior is fully explained by deterministic parsing, hashing, file copies and subprocess test runs.

## Promotion gate for DEV8
Keep experimental until: (1) a real generator adapter exists; (2) preregistered real-bug task set, DEV7 single-shot vs DEV8 loop, same generator, same candidate/time budget; (3) metrics: resolve rate, false-accept rate (passes tests but wrong on held-out tests), regression rate, tests-run cost, wall time; (4) unfamiliar-repo generalization check; (5) human approval for any apply to a real tree.
