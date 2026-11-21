# ASM v0.4.0-alpha.8.0-DEV3 — Controlled Simulation Learning Lab (evaluation harness + first ASM measurement)

**Status:** experimental development branch, not an official release. **Parent:** `ASM_alpha8_DEV2_fix1.zip`
(sha256 f6ed645c9bd6f2fd…, kept frozen). `asm.__version__` unchanged (`0.4.0-alpha.7.9`). Nothing here is wired into ASM
beliefs, memory or action selection. **This is not an Alpha 8 pass and not a capability breakthrough.**

## What DEV3 adds
| File | Purpose |
|---|---|
| `asm/learning/simlab.py` | Hidden-rule environments (3 families), learner interface, reference learners and controls, ASM adapter, calibration metrics, paired bootstrap, benchmark runner, pre-registration evaluator. |
| `asm/learning/simlab_prereg.py` | The pre-registered criteria (machine-readable). |
| `ALPHA8_DEV3_PREREGISTRATION.md` | The same criteria in prose + rules, with SHA-256. A test asserts doc and code are identical. |
| `run_dev3_benchmark.py` / `run_dev3_diagnostics.py` | Reproduce the official results / the exploratory diagnostics. |
| `results/ALPHA8_DEV3_RESULTS.{md,json}`, `results/ALPHA8_DEV3_SUITE_LOG.jsonl`, `results/ALPHA8_DEV3_DIAGNOSTIC.md` | Official results, the ground-truth task suite persisted in a DEV2 `ExperienceLog` (4,026 entries, head hash recorded), and diagnostics. |
| `tests/test_alpha8_dev3_simlab.py` | 20 tests. |

## Design in one paragraph
Each task is a hidden rule drawn uniformly from a declared hypothesis class: `boolean_4` (AND/OR of two literals), `xor_4`
(parity of a bit subset), `affine_mod` (y = a*x + b mod m). A fresh learner sees k noise-free examples and is scored on held-out
inputs whose answers are determined by the training pool under the declared class. Abstentions count as not-correct and wrong
answers are counted separately. Controls: memorizer (leakage canary), majority (chance floor), shuffled-label learner, and an
overconfident learner to test that calibration metrics discriminate. A reference learner that is *given the correct hypothesis
class* validates the harness (it must pass; controls must fail). ASM's existing `ProcedureCortex` is then measured unmodified
through a thin adapter (online `observe` with auto-induce, then `predict`).

## Official result (pre-registered `DEV3-prereg-1`, seed 20261031, 60 tasks per family)
- **Harness validity H1–H6: all PASS.** The reference learner is never wrong and reaches 1.00 correct (k>=12 on the bit families, k=2 on affine), the memorizer scores 0, shuffled labels collapse to <=0.25, the calibration metric separates honest from overconfident (ECE gap 0.21 and 0.32), and the majority floor is beaten by >=0.15.
- **A1 never confidently wrong: PASS.** ASM answered 584 queries across all cells and every answer was correct.
- **A2 learns with enough data: FAIL.** Correct rate at k=24: boolean_4 0.85 (meets 0.80), xor_4 0.58, affine_mod 0.00.
- **A3 beats majority (95% CI lower bound > 0): FAIL.** boolean_4 lower bound -0.008 (majority already reaches 0.75 on AND/OR rules), xor_4 +0.10 (passes), affine_mod 0.00 (ASM answers nothing; majority is also 0).

## What the numbers actually say
1. ASM's ProcedureCortex is **conservative and sample-hungry**: it answered nothing at k<=12 on any family; at k=16 it answered about half of the bit-family queries and at k=24 85% (boolean) and 58% (xor). The reference learner is fully correct from k=8-12. When ASM does answer, its confidence is slightly below its accuracy (ECE 0.05-0.09).
2. `affine_mod` is **outside ASM's representable class**: its procedure grammar has add, sub, mul, min, max, eq, lt, and, or but no modulus. Abstaining on all of it is correct behaviour given that grammar, so this family measures a capability gap, not a defect.
3. **A1 is partly vacuous**: ASM abstained on 100% of affine_mod and on every query at k<=12, so "never wrong" is established only over the 584 answered queries.
4. Exploratory diagnostics (not pre-registered, 20 trials): plain integer affine is learned and extrapolated at k=24 (120/120) but not at k=8 (0/120), so the adapter works. When shots happen not to reveal a modulus wrap, ASM can fit a plain affine rule and answer some held-out wrapped inputs confidently and wrongly (9 wrong of 54 answered in the saved diagnostic; an earlier ad-hoc run of the same setup with different seeds gave 16 wrong of 30). This is an underdetermination hazard worth a dedicated test; it is a signal, not a verdict.

## Limits (read these)
- Toy, noise-free, tiny environments (12-point pools for the bit families; ASM's cortex accepts at most 4 variables). Results do not speak to realistic data.
- The reference learner has the correct inductive bias by construction; it validates the harness only.
- One seed, 60 tasks per family; intervals resample tasks only. No multi-seed variance estimate.
- Within-task learning only. **Cross-task structural transfer, continual learning/forgetting, causal discovery and cognitive-core integration are not evaluated here.**
- The A thresholds are the author's judgment of a minimal bar; author and runner are the same party. Rerun with the included scripts.
- Calibration is evaluated on answered queries only; abstention quality beyond coverage/precision is not scored separately.

## Run
    python run_dev3_benchmark.py results        # ~2 minutes
    python run_dev3_diagnostics.py results
    python -m pytest -q tests/test_alpha8_dev3_simlab.py
