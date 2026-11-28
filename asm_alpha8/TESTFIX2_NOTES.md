# Alpha.12 release-check hotfix 2

No ASM cognition/architecture changes.

- `benchmark_v030a1.py` now migrates from the packaged `asm_v030a12_trained.db` instead of the removed alpha.11 trained DB.
- `run_release_checks.py` now prints the final 40 lines of stdout/stderr for any failed check, while still writing the complete log under `results/`.
- The prior test-loader fix (`tests/__init__.py` + explicit test paths) remains included.
