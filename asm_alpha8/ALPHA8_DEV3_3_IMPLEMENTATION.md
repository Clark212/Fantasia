# ASM v0.4.0-alpha.8.0-DEV3.3 — `abstain` is now the default extrapolation guard

**Status:** experimental development branch, not an official release. **Parent:** `ASM_alpha8_DEV3_2.zip` (sha256 1fb7bc28613ae6a3…).
`asm.__version__` unchanged (`0.4.0-alpha.7.9`). **This release changes ASM's default behaviour on purpose.** Not an Alpha 8 pass.

## Decision record
The project owner decided to make `abstain` the default after reviewing the DEV3.2 evidence and its costs. Recorded here so the trade-off is not lost.
- **What changed:** `ProcedureCortex(extrapolation_guard=...)` and `ASMConfig.procedure_extrapolation_guard` now default to `"abstain"` (were `"off"`).
  `discount` and `off` remain available; the confidence cap default is unchanged (0.5, used only by `discount`).
- **Effect:** a procedure only answers when every integer input lies inside the [min, max] of the evidence behind it; otherwise it abstains with
  `reason: outside_evidence_support`. Unknown support (no evidence rows) abstains. Bool-only procedures are not guarded.
- **Cost, stated plainly:** on the DEV3.1 population this removed 600 extrapolation answers, of which 364 were correct and 236 wrong. ASM no longer extrapolates a
  validated rule beyond its data by default, even when the rule really does continue (a true linear trend). Callers that need that must opt out.
- **Rollback:** `ASMConfig(procedure_extrapolation_guard="off")` (engine) or `ProcedureCortex(..., extrapolation_guard="off")` restores the pre-DEV3.2 behaviour exactly.

## Consequences found by running the whole suite
Flipping the default broke 14 tests that had not failed before; nothing else changed.
- **5 older tests (alpha 7.1 audit, alpha 7.2 autonomy)** deliberately probe a validated affine rule at x = 99/100/40/60, far outside the evidence range (e.g. fit on 0..2,
  validate on 10..17), and assert the extrapolated value. Their intent is lifecycle (held-out validation, persistence, drift, reversal, read-only prediction), not extrapolation, but
  they use extrapolation as the probe. They now run with the explicit legacy setting (`extrapolation_guard='off'`); **no assertion was changed**. New tests show the same scenarios
  under the default: answers inside the range (including both boundaries and an interior gap), abstains outside, survives close/reopen, and prediction stays read-only.
- **9 tests written in DEV3.1/DEV3.2** encoded "default = off" or "ASM is still dishonest". The DEV3.1 tripwires fired as designed: the expected-failure test now passes and was
  converted to a normal test; the pinned-hazard test now targets the explicit legacy mode.
- The historical runners (`run_dev3_benchmark.py`, `run_dev3_1_underdetermined.py`) pin `extrapolation_guard="off"` so the pre-registered DEV3/DEV3.1 results remain reproducible
  (verified identical to the shipped results). The DEV3 families give identical ASM results under `abstain`, as the comparison table shows.

## What this does NOT fix
- The guard is a bounding box on integer inputs. It does not detect interior gaps (tested: x=5 between evidence at 2 and 10 is answered), novel input combinations, or boolean-only procedures.
- Abstaining is safe, not informative: DEV3.1's U2 passes vacuously. It does nothing for any other source of overconfidence.
- Competing hypotheses with reported disagreement (the more principled fix) are still not implemented.
- Real-data behaviour is unknown: evidence is toy and synthetic, one seed, author-set thresholds.
- Any downstream consumer of `predict_procedure` / `predict_routed` that assumed an answer now has to handle `abstained` for out-of-range inputs.

## Reproduce
    python -m pytest -q tests/test_alpha8_dev3_3_default_abstain.py tests/test_alpha8_dev3_2_extrapolation_guard.py tests/test_alpha8_dev3_1_underdetermined.py
    python run_dev3_2_guard_comparison.py results      # ~3-4 minutes; includes the "default (no setting)" row
