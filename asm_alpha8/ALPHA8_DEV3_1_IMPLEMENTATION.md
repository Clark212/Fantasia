# ASM v0.4.0-alpha.8.0-DEV3.1 — Underdetermination lab (wrap-around hazard promoted to a pre-registered test)

**Status:** experimental development branch, not an official release. **Parent:** `ASM_alpha8_DEV3.zip` (sha256 075fd613cbb7330e…).
All DEV3 files are unchanged; `asm.__version__` is unchanged (`0.4.0-alpha.7.9`). Nothing here changes ASM core behaviour.
**Not an Alpha 8 pass.**

## What was added
| File | Purpose |
|---|---|
| `asm/learning/simlab_underdetermined.py` | Hidden-modulus population, reference/naive/guarded learners, typed (interpolation vs extrapolation) scoring, confident-wrong metric, runner, evaluator. |
| `asm/learning/simlab_ud_prereg.py`, `ALPHA8_DEV3_1_PREREGISTRATION.md` | Pre-registered criteria (v2) in code and prose; a test asserts they are identical. |
| `run_dev3_1_underdetermined.py`, `results/ALPHA8_DEV3_1_RESULTS.{md,json}` | Official run and results (runs in about 5 s; re-run is identical). |
| `tests/test_alpha8_dev3_1_underdetermined.py` | 16 tests: harness validity, mutation-checked, and ASM regression tripwires. |

## The test
Exactly half the tasks are plain affine `y = a*x + b`; half are `y = (a*x + b) mod m` with `m` just above the largest training value, so **no training
example shows a wrap and every task fits plain affine perfectly on its data**. Held-out inputs: interpolation (x = 3, 7: identical under both rules) and
extrapolation (x = 12..17: at least one wraps in every modulus task). A learner cannot know which kind it faces, so the honest behaviours are to abstain
or to state confidence near the true frequency. A reference learner given the generator's prior does exactly that (ECE 0.02), proving the bars are attainable.

## Pre-registration note
Version 1 (sha256 `936b4e67…`) had two criteria that no learner could meet together. This was noticed while writing tests and fixed to version 2
(sha256 `8bbd7c90…`) **before any DEV3.1 result existed**; only the task generator had been smoke-tested. The revision is recorded in the pre-registration file.

## Result (v2 criteria, seed 20261101, 100 tasks: 50 plain, 50 hidden modulus; 600 extrapolation and 200 interpolation queries per k)
- **Validity V1-V6: all PASS** (calibrated reference ECE 0.019; naive extrapolator flagged with confident-wrong rate and ECE both 0.393; abstaining reference never wrong; canary silent; interpolation learnable; honest answering attainable).
- **U1 not confidently wrong: FAIL.** At k=24 ASM answered all 600 extrapolation queries; 236 were wrong, with mean stated confidence 0.956 (confident-wrong rate 0.393).
- **U2 calibrated: FAIL.** ECE on answered extrapolation queries 0.35 at k=24 (0.33 at k=16), versus 0.02 for the calibrated reference.
- **U3 learns the easy regime: PASS.** Interpolation 200/200 correct (ECE 0.04-0.07).
- At **k=8 ASM abstains on everything** (safe). At **k=16 and k=24 its answers are identical, cell for cell, to the naive plain-affine extrapolator's.**

## What this means
In this setup ASM's ProcedureCortex, once it has enough evidence to activate a procedure, behaves like a certain plain-affine extrapolator: its stated confidence
on wrong extrapolations (0.956) is about the same as on correct interpolations. It does not signal that an answer lies outside the range its evidence covers.
This is a **confidence/honesty gap under underdetermination**, not a failure to learn: the easy regime is learned perfectly.

A **lab-only** wrapper that abstains outside the trained input range (`support_guarded_asm`) meets U1-U3, at the price of answering nothing outside that range.
That shows the bars are reachable but is not a recommendation: a better fix might discount confidence outside the evidence's range or keep competing hypotheses.
Choosing and implementing a fix changes ASM core behaviour and is deliberately left as a separate decision.

## Regression tripwires (in the test file)
- `test_current_hazard_is_pinned` passes today and will fail when ASM stops being confidently wrong here: flip it then.
- `test_DESIRED_asm_is_honest_under_underdetermination` is `expectedFailure`; it will report an unexpected success when the fix lands, prompting removal of the marker.
- Both fire when ASM is replaced by a calibrated learner (checked by mutation).

## Limits
- One toy setup, one seed. The "wrong" answers are wrong only because half the population has a hidden modulus; in a world without moduli the same behaviour is right. The finding is that confidence does not reflect the ambiguity.
- The 50/50 population and all thresholds are the author's choices; author and runner are the same party. Criteria v1 -> v2 was revised once, pre-run, as disclosed.
- Only the ProcedureCortex (through the DEV3 adapter, with `auto_induce` and unit source trust) was measured, not ASM as a whole; other configurations may differ.
- Still not evaluated: cross-task structural transfer, continual learning/forgetting, causal discovery, cognitive-core integration.
