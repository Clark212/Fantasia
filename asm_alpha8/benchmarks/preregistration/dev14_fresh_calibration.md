# DEV14 pre-registration: fresh calibration set

Written before any fresh-calibration data was produced. Its SHA-256 is recorded in every fresh run manifest and was
sent to the user before the runs started. Any analysis not listed here is exploratory and labelled as such.

## Data
- Subjects (independent repositories only; ASM's own code excluded from the fresh set):
  toolz 1.2.0, cachetools 8.0.0, inflection 0.5.1 (new in DEV14). PyPI sdists, hashes in the run manifests.
- Seed 53 (DEV13 used 31). Faults: single-site injected faults detected by the subject's full test suite.
- Calibration: 10 faults per subject, realistic suite (failing + half of the passing tests) and weak suite (failing only).
- Decoys: 10 faults per subject, up to 8 decoys per fault (true fix + one extra single-site edit in the faulty function),
  kept only if they pass the repair suite. Correct controls: the true fix and single-site plausible patches.
- Code: the DEV14 tree at the time of the run (its `asm.coding` hash is in each manifest). Workflow verification uses
  DEV14 defaults (100 generated inputs, seed 0). Oracle: DEV14 oracle (200 generated inputs, seed 7919).

## Outcome definitions
- WRONG (primary): oracle class `wrong`, or `wrong_generated` where the original program returned normally on at least one
  differing input (`original_ok`). Sensitivity analysis: `wrong` only.
- CORRECT: `restored` or `equivalent`. `unknown` is excluded from rates and reported separately.

## Decision rules (fixed in advance)
- R1 `tied_localization`. On the fresh decoy set compute TPR = P(flag | WRONG decoy), FPR = P(flag | CORRECT control),
  LR+ = TPR / FPR.
  - If fewer than 10 WRONG decoys: "insufficient evidence"; the label rule stays unchanged.
  - Else keep the flag in the label iff LR+ >= 2.0 and TPR >= 0.20; otherwise demote it to informational (still shown in
    dossiers, no longer counted toward the label).
- R2 Label ordering. Claim "labels order risk" only if the point estimates satisfy
  P(WRONG | high) < P(WRONG | medium) < P(WRONG | low) on the fresh decoy set, evaluated with the label rule that R1
  produces. Otherwise report "ordering not confirmed". No claim of calibrated probabilities either way.
- R3 No flag, label rule, weight or threshold other than the R1 outcome is changed after seeing fresh data.
- R4 Results are reported in full, including outcomes that are unfavourable to DEV14.
