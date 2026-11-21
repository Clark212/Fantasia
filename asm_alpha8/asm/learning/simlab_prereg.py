"""Pre-registered DEV3 criteria. Fixed BEFORE the benchmark was run; see ALPHA8_DEV3_PREREGISTRATION.md.

Changing a threshold after seeing results must be done as a new, labelled version with the original kept.
"""
PREREG = {
    "version": "DEV3-prereg-1",
    "seed": 20261031,
    "tasks_per_family": 60,
    "ks": [2, 4, 8, 12, 16, 24],
    "families": ["boolean_4", "xor_4", "affine_mod"],
    "harness_validity": {
        "H1_rulesearch_safe": {"learner": "rulesearch_abstain", "max_wrong_rate": 0.0},
        "H2_rulesearch_learns": {"learner": "rulesearch_abstain", "min_correct_rate_at_kmax": 0.95},
        "H3_memorizer_canary": {"learner": "memorizer", "max_correct_rate": 0.0},
        "H4_shuffled_control_collapses": {"learner": "shuffled_rulesearch_abstain", "max_correct_rate_at_kmax": 0.25},
        "H5_calibration_metric_discriminates": {"honest": "rulesearch_vote", "overconfident": "rulesearch_guess",
                                                "families": ["boolean_4", "xor_4"], "at_k": 4, "min_ece_gap": 0.10},
        "H6_majority_floor_is_beaten": {"learner": "rulesearch_abstain", "min_gap_over_majority": 0.15},
    },
    "asm_claims": {
        "learner": "asm_procedure_cortex",
        "A1_never_confidently_wrong": {"max_wrong_rate": 0.02},
        "A2_learns_with_enough_data": {"min_correct_rate_at_kmax": 0.80},
        "A3_beats_majority_control": {"min_ci_lower_bound": 0.0},
    },
}
