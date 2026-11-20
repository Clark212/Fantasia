# Alpha 8 Coding Intelligence DEV1 — Test Report

## Scope
First coding-intelligence increment built as a fork from the uploaded DEV4 archive. It adds a static Python repository analyzer and a transparent task planner. No pre-existing ASM core files were modified.

## Results

| Check | Result |
|---|---:|
| New coding-intelligence tests | 5 passed |
| DEV4 structural-discovery tests | 18 passed |
| DEV3.3 abstain-default tests | 9 passed |
| DEV3.2 extrapolation-guard tests | 19 passed |
| Combined targeted suite | **51 passed** |
| Python compile check (`asm/coding`, new tests) | Passed |
| Full historical suite | Not run |

The combined test run emitted `ResourceWarning` messages for unclosed SQLite connections in existing ASM procedure/structural-discovery paths. These warnings did not fail tests and were not introduced by the new coding package; they should be tracked separately.

## Real-repository self-scan

The analyzer scanned the extracted DEV4 repository:

- 235 Python files
- 2,345,027 source bytes
- 2,699 indexed classes/functions/methods
- 1,590 import declarations
- 457 local dependency edges
- 0 syntax/encoding/possible-local-import diagnostics
- 0.8248 seconds on this execution environment

The scan fingerprint and an example debug-task plan are in `results/ALPHA8_CODING_DEV1_SELF_SCAN.json`.

## Parent preservation

The uploaded DEV4 archive SHA-256 is `2951cc07f28658ee8389347e00c910831365a134b73a33b19c5008c8467372ed`.
All 451 files listed in `ALPHA8_DEV4_MANIFEST.json` were present and matched their recorded SHA-256 before packaging this fork. The new package adds files only; no DEV4 source or benchmark files were edited.

## Limitations

- This is not yet an autonomous coding agent.
- It does not generate or apply patches, run user project code, execute tests, use type checkers, or debug runtime failures.
- Python only. File ranking is token-overlap heuristic rather than semantic retrieval.
- Static checks do not establish program correctness.
- The full historical ASM suite has not been run for this increment.
