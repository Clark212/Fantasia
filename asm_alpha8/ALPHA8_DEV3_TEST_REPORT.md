# Alpha 8 DEV3 Test Report

**Artifact:** `ASM_alpha8_DEV3.zip` (parent: `ASM_alpha8_DEV2_fix1.zip`, sha256 f6ed645c9bd6f2fd6c3eb0b152d90b7476bf6b8b60983ac150eb8dec3a03e4d9).
Development prototype; not an official release; no Alpha 8 capability claim.

## Verified
- DEV3 harness tests: **20 passed**, stable over repeated runs. They check: tasks are deterministic and their truth lies inside the declared
  class; scored queries are never in the training pool and are determined by it; shots are nested and one pass covers the pool; hand-computed
  ECE/Brier/coverage values; abstention counted as not-correct; bootstrap sign and determinism; a fresh learner instance is built and fitted
  exactly once per task and budget; the memorizer canary is silent in the real protocol and fires when answers are leaked; the benchmark and
  its persisted suite log are deterministic and verify through the DEV2 log; the reference learner is safe and learns; honest vs overconfident
  calibration is separated; controls behave as controls; the pre-registration document and code are identical and the hash is recorded;
  verdicts pass for good learners and **fail** for an overconfident learner, an unsafe "reference", and a cheating canary; the ASM adapter
  reports exceptions instead of hiding them.
- Targeted run (DEV3 20 + DEV2 38 + DEV1 20 + 7.9 compatibility 14): **92 passed**.
- Non-torch regression subset: **474 passed, 57 failed, 1 skipped** (474 = 396 baseline + 20 DEV1 + 38 DEV2 + 20 DEV3). The 57 failures are the
  same count as the 7.9 baseline run without PyTorch in this sandbox; an independent audit of DEV2.1 with PyTorch present reported them passing.
- Mutation checks on the harness: leaking queries into shots, wrong ECE weighting, reusing one learner across tasks, flipping the H1 comparator,
  counting abstention as correct, flipping the bootstrap sign, making the overconfident learner honest, and removing the guess-mode fallback each
  make tests fail. Two mutants initially survived (learner reuse, because the test only counted factory calls; the guess fallback, which no test
  reached) and led to stronger tests.
- Reproducibility: the official benchmark was re-run in a fresh process; results (excluding runtime) and the persisted suite log are byte-identical
  (log head hash e3e57d5b3c068d07…).
- The benchmark outcome (H1-H6 PASS, A1 PASS, A2 FAIL, A3 FAIL) is reported as obtained; no threshold was changed after results existed.

## Not verified
- The 3 torch-dependent test files and the 57 torch-related failures were not run with PyTorch here.
- Single seed and 60 tasks per family; no multi-seed variance. Toy noise-free environments only.
- Cross-task transfer, continual learning/forgetting, causal discovery and cognitive-core integration are not evaluated or not implemented.
- DEV2 limits still apply (Windows, multi-process writers, crash injection, very large logs).
- `ALPHA8_DEV2_MANIFEST.json` is kept as history; `ALPHA8_DEV3_MANIFEST.json` is the manifest for this archive.
