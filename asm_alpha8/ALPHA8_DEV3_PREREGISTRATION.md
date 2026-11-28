# Alpha 8 DEV3 — Pre-registration (written before the benchmark was run)

Scope: **within-task learning from experience** in controlled hidden-rule environments, with controls and calibration.
Not measured here: cross-task transfer (DEV4), continual learning, causal discovery, cognitive-core integration.

## Environments (ground truth known; rule sampled uniformly from a declared hypothesis class)
- `boolean_4`: AND/OR of two (optionally negated) features among 4 booleans (48 rules).
- `xor_4`: parity of a non-empty subset of 4 bits, plus constant 0/1 (30 rules).
- `affine_mod`: y = (a*x + b) mod m, m prime in {29, 31, 37, 41}.
Scored queries are held-out inputs whose answer is determined by the training pool under the declared class. Shots cycle
through a shuffled pool, so budget k >= pool size has seen every pool input. A fresh learner is built per task and per k.

## Learners
- `rulesearch_*` (abstain / vote / guess): reference learner **given the correct hypothesis class**. It validates the harness; it is not a claim about ASM.
- `memorizer` (leakage canary), `majority` (chance floor), `shuffled_rulesearch_abstain` (labels shuffled within task).
- `asm_procedure_cortex`: ASM's existing ProcedureCortex used unmodified (online observe with auto-induce, then predict).

## Criteria (machine-readable copy is asm/learning/simlab_prereg.py; a test asserts the two are identical)
```json
{
  "asm_claims": {
    "A1_never_confidently_wrong": {
      "max_wrong_rate": 0.02
    },
    "A2_learns_with_enough_data": {
      "min_correct_rate_at_kmax": 0.8
    },
    "A3_beats_majority_control": {
      "min_ci_lower_bound": 0.0
    },
    "learner": "asm_procedure_cortex"
  },
  "families": [
    "boolean_4",
    "xor_4",
    "affine_mod"
  ],
  "harness_validity": {
    "H1_rulesearch_safe": {
      "learner": "rulesearch_abstain",
      "max_wrong_rate": 0.0
    },
    "H2_rulesearch_learns": {
      "learner": "rulesearch_abstain",
      "min_correct_rate_at_kmax": 0.95
    },
    "H3_memorizer_canary": {
      "learner": "memorizer",
      "max_correct_rate": 0.0
    },
    "H4_shuffled_control_collapses": {
      "learner": "shuffled_rulesearch_abstain",
      "max_correct_rate_at_kmax": 0.25
    },
    "H5_calibration_metric_discriminates": {
      "at_k": 4,
      "families": [
        "boolean_4",
        "xor_4"
      ],
      "honest": "rulesearch_vote",
      "min_ece_gap": 0.1,
      "overconfident": "rulesearch_guess"
    },
    "H6_majority_floor_is_beaten": {
      "learner": "rulesearch_abstain",
      "min_gap_over_majority": 0.15
    }
  },
  "ks": [
    2,
    4,
    8,
    12,
    16,
    24
  ],
  "seed": 20261031,
  "tasks_per_family": 60,
  "version": "DEV3-prereg-1"
}
```
- **H1–H6 validate the harness.** If any fails, no ASM result from this run may be interpreted.
- **A1–A3 are the ASM claims**, evaluated only for the learner above: never confidently wrong (wrong_rate <= 0.02 at every k),
  learns given enough data (correct_rate >= 0.80 at k = 24 in every family), and beats the majority control (95% paired-bootstrap
  lower bound > 0 at k = 24). The A thresholds are the author's judgment of a minimal bar in very simple environments; they are
  not derived from any standard.

## Rules
1. Thresholds are fixed by the SHA-256 below. Changing one after results exist means a new labelled version; the original verdicts stay in the record.
2. Results are reported whether they pass or fail, with abstentions counted as not-correct and wrong answers counted separately.
3. A pass means "meets this bar in these three toy environments", nothing more.
4. Author and runner are the same party; the benchmark and its tests are included so others can rerun and check.

Pre-registration SHA-256 (canonical JSON of the criteria): `56635782fb4a41b28afb632c3a4fd77e7e9b8d5ceed1b5b1894ec345c3a02bef`
