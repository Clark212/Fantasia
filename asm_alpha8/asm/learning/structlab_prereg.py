"""Pre-registered DEV4 criteria (structural discovery map + structural transfer). Fixed BEFORE the benchmark was run.

A later change to any threshold must be a new labelled version with the original verdicts retained.
"""
PREREG = {
    "version": "DEV4-prereg-1",
    "seed": 20261102,
    "probe_disclosure": ("Before pre-registering, a 6-line exploratory probe showed that with two validated donors x*x+1 and x*x+5, "
                         "induce(use_families=True) found y=x*x+3 in 14 candidates while the baseline and use_families=False were unresolved after 291; "
                         "that y=max(x,7) is fitted spuriously by a constant when all examples lie below 7; and that threshold rules return needs_information. "
                         "Target structures and arms were chosen with that knowledge; thresholds below were set before any benchmark run."),
    "part_a": {
        "tasks_per_family": 40,
        "ks": [8, 16, 24],
        "families": ["affine", "quad", "clamp", "threshold", "linear2", "product2"],
        "validity": {
            "H1_reference_safe": {"learner": "grid_reference", "max_wrong_rate": 0.0},
            "H2_reference_learns": {"learner": "grid_reference", "min_correct_rate_at_kmax": 0.95},
            "H3_memorizer_canary": {"learner": "memorizer", "max_correct_rate": 0.0},
            "H4_shuffled_control_collapses": {"learner": "shuffled_grid_reference", "max_correct_rate_at_kmax": 0.25},
            "H5_majority_floor_is_beaten": {"learner": "grid_reference", "min_gap_over_majority": 0.15},
        },
        "asm_claims": {
            "learner": "asm_struct",
            "A1_never_wrong_on_determined_queries": {"max_wrong_rate": 0.02},
            "A2_shuffled_labels_never_answered_wrongly": {"learner": "shuffled_asm_struct", "max_wrong_rate": 0.02},
            "A3_coverage": {"min_correct_rate_at_kmax": 0.80, "min_families": 3},
        },
    },
    "part_b": {
        "target_structure": "y = x*x + c",
        "in_range_constants": [-8, -7, -6, -5, -4, -3, -2, -1, 1, 2, 3, 4, 5, 6, 7, 8],
        "out_of_range_constants": [-12, -11, -10, -9, 9, 10, 11, 12],
        "fit_seeds": 3,
        "arms": ["none", "one_relevant", "relevant", "unrelated", "mixed", "relevant_shuffled"],
        "validity": {
            "V1_donors_never_contain_the_target_constant": True,
            "V2_shuffled_labels_do_not_succeed": {"arm": "relevant_shuffled", "max_success": 0.05},
        },
        "claims": {
            "T1_capability_gain": {"min_success_gap_relevant_vs_none": 0.50},
            "T2_one_donor_is_not_enough": {"max_success_gain_over_none": 0.10},
            "T3_no_negative_transfer": {"arm": "unrelated", "max_success_drop": 0.05, "max_cost_ratio": 1.10},
            "T3b_no_interference": {"arm": "mixed", "max_success_drop_vs_relevant": 0.10},
            "T4_safe": {"max_wrong_active_rate": 0.02},
            "T5_parameter_range_limit": {"max_success_out_of_range": 0.10},
        },
    },
}
