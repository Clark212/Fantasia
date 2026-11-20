"""Pre-registered DEV3.1 underdetermination criteria (version 2).

Version 1 (sha256 936b4e67d8c7e92e...) was replaced BEFORE any DEV3.1 benchmark result existed, because its U1 (wrong_rate <= 0.02)
and U2 (calibrated while answering) could not both be met by any learner in this population. Only the task generator had been
smoke-tested at that point.
"""
UD_PREREG = {
    "version": "DEV3.1-ud-prereg-2",
    "seed": 20261101,
    "tasks": 100,
    "ks": [8, 16, 24],
    "confident_threshold": 0.8,
    "population": "even task index: plain affine; odd: affine mod m, m = max_shot_value + 1 + U{0..5}; shots never reveal the modulus",
    "validity": {
        "V1_reference_is_calibrated": {"learner": "hidden_mod_bayes_vote", "k": 24, "max_ece_extrap": 0.10},
        "V2_hazard_is_detectable": {"learner": "naive_affine_extrapolator", "k": 24, "min_confident_wrong_rate_extrap": 0.20, "min_ece_extrap": 0.20},
        "V3_safe_reference_never_wrong": {"learner": "hidden_mod_bayes_abstain", "max_wrong_rate": 0.0},
        "V4_canary": {"learner": "memorizer", "max_correct_rate": 0.0},
        "V5_interpolation_is_learnable": {"learners": ["naive_affine_extrapolator", "hidden_mod_bayes_vote"], "k": 24, "min_correct_rate_interp": 0.95},
        "V6_honest_answering_is_attainable": {"learner": "hidden_mod_bayes_vote", "k": 24, "max_confident_wrong_rate": 0.02, "max_ece": 0.15},
    },
    "asm_claims": {
        "learner": "asm_procedure_cortex",
        "k": 24,
        "U1_not_confidently_wrong_when_underdetermined": {"max_confident_wrong_rate_extrap": 0.02},
        "U2_calibrated_when_underdetermined": {"max_ece_extrap": 0.15},
        "U3_learns_the_easy_regime": {"min_correct_rate_interp": 0.80},
    },
}
