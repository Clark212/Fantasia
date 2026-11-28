> **SUPERSEDED IN PART by DEV3.3:** the guard described here shipped opt-in (default `off`). As of DEV3.3 the default is `abstain` (see `ALPHA8_DEV3_3_IMPLEMENTATION.md`).
> Everything else below, including the mode semantics, limits and results, still holds; read "off by default" as historical.

# ASM v0.4.0-alpha.8.0-DEV3.2 — Opt-in extrapolation guard for ProcedureCortex

**Status:** experimental development branch, not an official release. **Parent:** `ASM_alpha8_DEV3_1.zip` (sha256 f970373f8038a642…).
`asm.__version__` unchanged (`0.4.0-alpha.7.9`). **The guard is OFF by default; default behaviour is unchanged** (verified, see test report).
**Not an Alpha 8 pass.**

## Why
DEV3.1 showed that the cortex's confidence, `(support+1)/(support+contradictions+2)`, depends only on how much evidence exists, never on where the query lies.
So a procedure fitted on x = 0..11 answers x = 50 with the same ~0.96 confidence, which is confidently wrong when a hidden rule changes outside the data.

## What changed (all additive, default off)
| Change | Detail |
|---|---|
| `ProcedureCortex(..., extrapolation_guard='off', extrapolation_confidence_cap=.5)` | Modes `off` (unchanged) / `abstain` / `discount`. Invalid settings raise `ValueError` before anything is opened. |
| `ProcedureCortex.predict` | In guarded modes, each integer input is checked against the [min, max] of that variable in the evidence from the active procedure's **dependency sources** (at the dependency versions). `abstain` returns `{'status':'abstained','reason':'outside_evidence_support','outside':[...]}`; `discount` still answers but caps confidence at the cap (never raises it). Guarded results carry `extrapolating: bool`; **off-mode results are byte-identical and carry no new key.** Unknown support (no evidence rows) abstains / is capped conservatively. |
| `ASMConfig.procedure_extrapolation_guard`, `procedure_extrapolation_confidence_cap` | Defaults `"off"` and `0.5`; `ASMEngine.procedures` passes them through. |
| `simlab.ASMProcedureLearner(**cortex_kwargs)` | Lab adapter can now enable the guard. |

## Result (DEV3.1 pre-registered criteria U1-U3, which were fixed before this guard existed; k=24; 600 extrapolation queries)
| mode | extrap answered / correct | confident-wrong rate | ECE | interp | U1 | U2 | U3 |
|---|---|---|---|---|---|---|---|
| off (default) | 600 / 364 | 0.393 | 0.350 | 200/200 | FAIL | FAIL | PASS |
| **abstain** | 0 / 0 | 0 | n/a | 200/200 | PASS | PASS (vacuous) | PASS |
| discount cap 0.3 | 600 / 364 | 0 | 0.307 | 200/200 | PASS | FAIL | PASS |
| discount cap 0.5 | 600 / 364 | 0 | 0.107 | 200/200 | PASS | PASS | PASS |
| discount cap 0.7 | 600 / 364 | 0 | 0.093 | 200/200 | PASS | PASS | PASS |
| discount cap 0.9 | 600 / 364 | 0.393 | 0.293 | 200/200 | FAIL | FAIL | PASS |
The cap sweep is exploratory. Enabling `abstain` leaves ASM's results on the DEV3 families identical (bit families have no integer inputs; affine_mod was abstained anyway).

## What this means, including the costs
- **`abstain` is parameter-free and removes the hazard, but passes U2 vacuously and the price is real**: here it gives up all 364 *correct* extrapolations to avoid 236 wrong ones. Where a rule genuinely continues beyond the data (a true linear trend), enabling it makes ASM refuse answers it would have got right.
- **`discount` keeps every answer and only lowers stated confidence, but it is only as honest as its cap**: caps of 0.5-0.7 happen to sit near this population's true extrapolation accuracy (0.607); 0.3 is under-confident; 0.9 leaves the hazard. A deployed system does not know that frequency, so the cap is a knob, not a calibration.
- Neither mode keeps competing hypotheses or reports the disagreement (the more principled option). That is not implemented.
- Why it stays off by default: turning it on changes what ASM answers. That is a product decision, not something this branch should make silently.

## Limits of the guard
- **Bounding box only** on integer inputs: it does not detect gaps in the interior (tested and documented), novel combinations of inputs, or boolean-only procedures (not guarded).
- Support is taken from stored evidence rows of the dependency sources; each guarded prediction reads those rows (cost grows with the evidence for that mechanism).
- Untrusted evidence already suspends a procedure (observed) instead of widening its range; a white-box test pins the dependency-source filter.
- Evaluated on one toy population and one seed; U-thresholds are the author's; author and runner are the same party.

## Side finding (exploratory, now covered by a test of current behaviour)
The cortex needs at least 8 **distinct** training inputs before a procedure activates: 7 distinct inputs repeated 8 times (56 observations) never activated one, while 8 distinct inputs activated within 16 observations (y = 2x + 3). Repetition does not substitute for distinct evidence, which is sensible design and explains part of the sample-hunger seen in DEV3.

## Not done
Fix option 3 (competing hypotheses); guarding other procedure types or the routing path beyond what `predict_routed` inherits; wiring the guard into belief updates; cross-task transfer and the rest of the Alpha 8 roadmap.
