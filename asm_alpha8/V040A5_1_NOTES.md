# ASM v0.4.0-alpha.5.1 — Belief-State Numerical & Contract Hardening

Same-stage hardening of alpha.5; not alpha.6.

Final changes:
- log-space belief retention and hypothesis resurrection;
- explicit structural-zero vs soft-near-zero distinction;
- strict fail-closed probability-likelihood contract validation;
- ranking-aware memo keys to prevent opposite-side near-tie merges while preserving compact DAG search;
- explicit partial-policy / expansion-budget reporting;
- new contract and torture tests;
- existing `asm_snapshot_v0_4_0_alpha_5_1` snapshot key with alpha.5 fallback retained.

See:
- `RELEASE_NOTES_ALPHA5_1.md`
- `BENCHMARK_ALPHA5_1_REPORT.md`
- `HARD_FEED_ALPHA5_1_REPORT.md`
