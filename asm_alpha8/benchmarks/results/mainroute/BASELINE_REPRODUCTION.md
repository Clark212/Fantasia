# Main route, step 1: does the frozen baseline v0.4.0-alpha.7.9 reproduce here, and does today's code still pass it?

Run on 2026-11-28 in this session's container (CPython 3.13.18, CPU PyTorch 2.15.0 installed for the run). Before
any 0.4.9 closure check, the baseline it builds on must be verified (directive §8: "if a benchmark cannot be
reproduced, report that explicitly").

## 1. The historical unit regression
- `python3 -m pytest -q tests/ --ignore-glob='tests/test_alpha8_*'` on today's code: **470 passed, 1 skipped** (91
  subtests), exactly the alpha 7.9 release notes' "471 collected = 470 passed + 1 inherited intentional skip".
- The 57 failures recorded since DEV23 were all "PyTorch not installed". With PyTorch they pass.

## 2. The release gate (`run_release_checks.py`, alpha 7.7's runner, 55 jobs)
Both trees ran from scratch copies, because the runner writes into `results/`, which holds committed records.
Logs: `logs_baseline_79/`, `logs_current/`, `release_checks_*.log`.

| | frozen v0.4.0-alpha.7.9 archive | today's code |
|---|---|---|
| jobs passing | 48 of 55 | 41 of 55 |

**The 7 jobs failing in both trees fail for the runner's own reasons, not for a lost capability:**
- **Stale version pins** (6 jobs):
  - `planning_alpha1_preservation`, `planning_alpha2`, `planning_alpha3`, `planning_alpha4`: `__version__ == '0.4.0-alpha.7'`;
  - `abstraction_alpha11`: `version_is_current_release`;
  - `alpha12_finalize`: `version_is_alpha12`.

  These are the only false checks. With the pin satisfied (`asm.__version__` set to the pinned string), today's code
  passes:

  | benchmark | result |
  |---|---|
  | planning alpha 1 | runs cleanly |
  | planning alpha 2 | 8/8 |
  | planning alpha 3 | 10/10 |
  | planning alpha 4 | 10/10 |

- **`procedure_alpha74_performance`** reads `/tmp/perf73.json`, which another script writes outside this runner's
  jobs.
- **The runner itself** stops at its last step: `print(json.dumps(..., flush=True))` passes `flush` to `json.dumps`.

**The 7 jobs failing only on today's code** are the procedure cortex's alpha 7.2-7.4 benchmarks:

| benchmark | today | with `extrapolation_guard=off` |
|---|---|---|
| `benchmark_v040a72.py` | fails | passes |
| `benchmark_v040a72_torture.py` | 3/8 | 8/8 |
| `benchmark_v040a72_performance.py` | `KeyError 'value'` | passes |
| `benchmark_v040a73.py` | 7/10 | 10/10 |
| `benchmark_v040a73_torture.py` | 5/7 | 7/7 |
| `benchmark_v040a74.py` | 8/11 | 11/11 |
| `benchmark_v040a74_torture.py` | 6/8 | 8/8 |

- **Cause:** DEV3.3's default `extrapolation_guard='abstain'`, approved by the project owner with its trade-off
  recorded (`ALPHA8_DEV3_3_IMPLEMENTATION.md`). These benchmarks expect a learned rule to be applied beyond its
  evidence; the guard now abstains there by design.
- **How it was found:**
  - swapping files between the two trees (`procedure_cortex.py` alone carries the change, already present in the
    DEV14 import);
  - forcing each option: the family defaults of DEV21-DEV23 change nothing.
- **To reproduce the alpha 7.x numbers:** `python3 tools/with_cortex_options.py extrapolation_guard=off
  benchmark_v040a73.py`. The option is forced even when `ASMEngine` passes it from `ASMConfig`.

## Conclusion
- **The baseline reproduces.** Its unit regression passes exactly, and every release-gate failure is explained:
  version pins, a temp file, a runner bug, or the owner-approved extrapolation guard.
- **No Stage 4 planning capability was lost.**
- **Not changed** (benchmark definitions, the owner's call): the version pins, the runner, and running the procedure
  benchmarks with the guard off inside the release gate.

## 3. The refreshed release gate (owner-approved 2026-11-28)
- **What changed:**
  - the six version pins accept the alpha 7 line (`__version__.startswith('0.4.0-alpha.7')`);
  - the nine alpha 7.2-7.4 procedure jobs run with `extrapolation_guard=off`, through `tools/with_cortex_options.py`;
  - `benchmark_v040a74_performance.py` falls back to `ALPHA73_PERFORMANCE.json`, which the job before it writes, when
    `/tmp/perf73.json` is missing;
  - the runner's final print is fixed and its payload reports `asm.__version__`.

  No check's measure changed.
- **Result** (today's code, from a scratch copy): **56 of 56 pass**, the 55 jobs and the trained-state check; 393 unit
  tests; `pass: true` (`release_checks_refreshed.json`, `release_checks_refreshed.log`).
