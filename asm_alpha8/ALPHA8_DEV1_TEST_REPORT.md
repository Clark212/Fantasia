# Alpha 8 DEV1 Test Report

**Artifact:** `ASM_v0.4.0-alpha.8.0-DEV1.zip`  
**Parent:** frozen `ASM_v0.4.0-alpha.7.9.zip`  
**Status:** development prototype; not an official Alpha 8 release.

## Verified checks

- New hybrid-learning tests: **20 passed**.
- Alpha 7.9 compatibility tests (`test_alpha79_release.py`, `test_alpha79_signed_latent.py`): **14 passed**.
- Combined targeted test run: **34 passed**.
- Existing Alpha 7.9 smoke test: **passed**.
- Parent archive SHA-256 independently matched its recorded value: `e652329943b86d0a280af6405ad123036b650576d5349eb0c2f5a2893055edfc`.
- ZIP integrity (`ZipFile.testzip`) and package manifest verification: recorded in the package build output / sidecar checksum.

## Full-suite limitation

The full repository test suite was attempted twice with a 120-second execution limit. The first attempt reached 29%; the second, with numerical-library thread counts constrained to one, reached approximately 45% before timing out. **The full suite is therefore unverified**, not a pass. No claim of full regression success is made.

## Scope of the result

The targeted tests verify record validation, provenance-aware fingerprints, bounded storage, duplicate handling, CSV/JSONL parsing, deterministic group-aware splitting, simulation episode capture, prediction metrics, evidence-aware review ranking, and selected Alpha 7.9 compatibility behavior. They do not demonstrate improved broad reasoning, autonomous learning quality, general intelligence, or Alpha 8 stage completion.
