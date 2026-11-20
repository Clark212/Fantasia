# Alpha 8 DEV3.1 Test Report

**Artifact:** `ASM_alpha8_DEV3_1.zip` (parent: `ASM_alpha8_DEV3.zip`, sha256 075fd613cbb7330e7417c0e0d298db09fc3e1a903e890dbb518f7274a336c6b7).
Development prototype; not an official release; no Alpha 8 capability claim.

## Verified
- DEV3.1 tests: **15 passed, 1 expected failure**, stable over repeated runs. Harness: balanced deterministic population; shots never reveal the modulus yet extrapolation does;
  plain affine fits all training data of every task (underdetermination is real); queries unseen and typed; hand-checked confident-wrong metric; naive learner exposes the hazard;
  reference calibrated and safe variant never wrong; canary silent; determinism; support guard trades coverage for safety; criteria document equals code and hash recorded;
  verdicts pass for good learners and fail for an overconfident learner, a broken reference, and (via mutation) other faults; ASM adapter reports no errors.
- ASM regression: hazard pinned, easy regime and scarce-data safety pinned, desired behaviour marked expected-failure, mitigation shown in the lab.
- Targeted run (DEV3.1 + DEV3 + DEV2 + DEV1 + 7.9 compatibility): **107 passed, 1 xfailed**.
- Non-torch regression subset: **489 passed, 57 failed, 1 skipped, 1 xfailed** (489 = 474 + 15). The 57 failures match the 7.9 baseline run without PyTorch in this sandbox.
- Mutation checks on the harness (label ignores modulus, shots can show a wrap, every error counted confident, wrong reference prior, U2 no longer treats abstention as honest, U1 comparator flipped,
  query typing broken, interpolation queries leaked into the pool): all caught. Replacing ASM by a calibrated learner trips all three ASM tripwires.
- Reproducibility: the official run was repeated in a fresh process; results (excluding runtime) are identical.
- Process: criteria v1 -> v2 revised before any result existed (defect: U1 and U2 mutually exclusive); a regression-test sample of 40 tasks was found too noisy by mutation and replaced by the full 100-task population.

## Not verified
- The 3 torch-dependent test files and the 57 torch-related failures were not run with PyTorch here.
- One seed, one toy population, one ASM component and configuration. No fix has been implemented or evaluated in ASM core.
- Cross-task transfer, continual learning, causal discovery and cognitive-core integration remain unevaluated; DEV2 limits (Windows, multi-process writers, crash injection, very large logs) still apply.
