from dataclasses import dataclass


@dataclass(slots=True)
class ASMConfig:
    # Sparse field
    workspace_size: int = 24
    propagation_steps: int = 3
    activation_decay: float = 0.74
    activation_floor: float = 0.025
    propagation_gain: float = 0.52
    max_active_nodes: int = 256
    max_fanout: int = 16

    # Competition / homeostasis
    inhibition_strength: float = 0.16
    homeostasis_strength: float = 0.035

    # Plasticity
    association_lr: float = 0.045
    temporal_lr: float = 0.065
    prediction_lr: float = 0.08
    prediction_decay_lr: float = 0.035
    predictive_error_gain: float = 0.85
    edge_prune_threshold: float = 0.012
    predictor_prune_threshold: float = 0.018
    max_edge_weight: float = 1.5
    max_prediction_fanout: int = 48

    # Rule/generalization learner
    rule_lr: float = 0.22
    rule_negative_lr: float = 0.08
    rule_l2_decay: float = 0.002
    rule_min_confidence: float = 0.20
    rule_max_features: int = 16

    # Associative expansion / structural analogy
    structural_lr: float = 0.18
    structural_decay: float = 0.997
    structural_min_confidence: float = 0.16
    structural_min_support: int = 2
    structural_min_margin: float = 0.08
    expansion_depth: int = 3
    expansion_beam: int = 24
    expansion_max_hypotheses: int = 8
    abstraction_min_support: int = 2
    max_association_fanout: int = 64

    # Semantic learning
    semantic_similarity_threshold: float = 0.62
    semantic_alias_gain: float = 0.55
    semantic_min_observations: int = 2
    semantic_max_aliases: int = 3


    # Emergent / self-created concepts
    latent_min_support: int = 3
    latent_match_threshold: float = 0.46
    latent_min_shared_features: int = 2
    latent_max_concepts: int = 512
    latent_max_features: int = 48
    latent_activation_gain: float = 0.90

    # Agent beliefs / mind-state revision
    belief_decay: float = 0.72
    belief_observation_gain: float = 1.0
    belief_revision_gain: float = 1.35
    belief_confidence_margin: float = 0.12

    # Learned emotion prototypes
    emotion_min_examples: int = 2
    emotion_min_score: float = 0.16
    emotion_max_features: int = 64


    # Appraisal / agent-state integration
    appraisal_min_score: float = 0.14
    appraisal_max_features: int = 48
    appraisal_emotion_min_examples: int = 1
    appraisal_goal_priority_default: float = 0.70
    appraisal_fear_priority_default: float = 0.70
    appraisal_expectation_priority_default: float = 0.55


    # Self model / metacognition
    self_belief_decay: float = 0.86
    self_success_gain: float = 1.00
    self_failure_gain: float = 1.15
    self_capability_min_confidence: float = 0.10
    strategy_exploration_bonus: float = 0.22
    strategy_failure_penalty: float = 0.40

    # Hierarchical/nested beliefs
    nested_belief_max_order: int = 3
    nested_belief_decay: float = 0.82
    nested_revision_gain: float = 1.55

    # Attention / internal state
    attention_inertia: float = 0.62
    attention_surprise_gain: float = 0.75
    attention_max_targets: int = 8
    curiosity_uncertainty_gain: float = 0.60
    curiosity_novelty_gain: float = 0.40
    frustration_failure_window: int = 6
    frustration_failure_gain: float = 0.22
    confidence_success_gain: float = 0.18
    internal_state_decay: float = 0.88

    # Learned open-language perception
    perception_min_relation_support: float = 2.0
    perception_min_confidence: float = 0.235
    perception_min_margin: float = 0.055
    perception_min_evidence: float = 0.16
    perception_min_unlabeled_exposures: int = 1
    perception_pseudolearn_threshold: float = 0.34
    perception_pseudolearn_weight: float = 0.55
    perception_max_connector_tokens: int = 4
    perception_connector_weight: float = 0.39
    perception_role_weight: float = 0.34
    perception_cue_weight: float = 0.12
    perception_length_weight: float = 0.11
    perception_prior_weight: float = 0.04

    # Self-discovered relation ontology
    relation_discovery_min_support: int = 3
    relation_discovery_join_threshold: float = 0.36
    relation_discovery_query_threshold: float = 0.39
    relation_discovery_min_margin: float = 0.05
    relation_discovery_merge_threshold: float = 0.68
    relation_discovery_split_min_support: int = 8
    relation_discovery_split_coherence: float = 0.50
    relation_discovery_max_relations: int = 512
    relation_discovery_max_episodes: int = 64
    relation_discovery_max_connector_tokens: int = 3
    relation_discovery_strength_lr: float = 0.12
    relation_discovery_dormant_strength: float = 0.16
    relation_discovery_prediction_error_gain: float = 0.35
    # Sense induction / indexed lookup
    relation_discovery_polysemy_min_support: int = 6
    relation_discovery_polysemy_cue_gap: float = 0.55
    relation_discovery_exact_connector_index: bool = True
    relation_discovery_capacity_reject_when_full: bool = True

    # Natural mental-state perception
    mental_language_confidence: float = 0.82
    mental_language_doubt_confidence: float = 0.72

    # v0.2 language cortex
    language_core_backend: str = "recurrent"
    language_core_min_confidence: float = 0.62
    language_core_embedding_dims: int = 96
    language_core_max_proposals: int = 12
    language_core_allow_generation: bool = True
    language_core_fail_open: bool = True
    language_core_recurrent_min_intent_confidence: float = 0.80
    language_core_recurrent_min_validation_accuracy: float = 0.80
    language_core_embedding_injection_topk: int = 8
    language_core_embedding_injection_gain: float = 0.18

    # v0.2.0-alpha.3: consolidation + semantic episodic retrieval
    consolidation_social_threshold: float = 0.99
    consolidation_short_token_limit: int = 3
    consolidation_uncertain_intent_threshold: float = 0.62
    consolidation_uncertain_token_limit: int = 5
    semantic_memory_enabled: bool = True
    semantic_memory_weight: float = 0.62
    semantic_memory_min_similarity: float = 0.55
    semantic_lsh_tables: int = 4
    semantic_lsh_bits: int = 10
    semantic_lsh_min_candidates: int = 24
    semantic_lsh_max_candidates: int = 256
    rwkv7_model_path: str = ""
    rwkv7_strategy: str = "cpu fp32"
    rwkv7_tokenizer: str = "rwkv_vocab_v20230424"
    rwkv7_embedding_dims: int = 128
    rwkv7_chunk_len: int = 128
    rwkv7_max_new_tokens: int = 96
    rwkv7_temperature: float = 0.8
    rwkv7_top_p: float = 0.5
    rwkv7_extract_proposals: bool = True
    rwkv7_extractor_max_tokens: int = 160

    # v0.3.0-alpha.1: persistent world-state graph + bounded seismic scheduler
    world_model_enabled: bool = True
    world_model_backfill_limit: int = 20000
    world_scheduler_max_candidates: int = 12

    # v0.3.0-alpha.3: multi-domain recurrent mechanisms with balanced replay and bounded recurrent credit
    transition_mechanisms_enabled: bool = True
    transition_input_dim: int = 128
    transition_hidden_dim: int = 64
    transition_max_outcomes: int = 32
    transition_learning_rate: float = 0.012
    transition_train_steps: int = 6
    transition_seed: int = 17

    # v0.3.0-alpha.6: bounded long-horizon rehearsal against sequential forgetting
    transition_retention_anchor_limit: int = 96
    transition_retention_anchor_batch_limit: int = 6

    # v0.3.0-alpha.7+: elastic recurrent outcome head. 32 remains the initial
    # allocation. Alpha.10 raises only the lazy ceiling to 4096 so packed
    # consolidation can be stress-tested beyond 1024 without preallocating it.
    transition_outcome_capacity_limit: int = 4096
    transition_outcome_growth_factor: float = 2.0

    # v0.3.0-alpha.10: packed fixed-memory multi-choice consolidation for stable
    # visible mappings. The 64-bit fingerprint is retained, while slot+support
    # metadata is packed into uint32 so the same byte budget holds more cells.
    transition_consolidation_enabled: bool = True
    transition_consolidation_table_size: int = 1024
    transition_consolidation_hashes: int = 3
    transition_consolidation_min_support: int = 4
    transition_consolidation_max_displacements: int = 24

    # v0.3.0-alpha.11: validated feature-projection abstractions for reusable
    # local transition rules. Exact late exceptions override generalized rules.
    transition_abstraction_enabled: bool = True
    transition_abstraction_min_support: int = 8
    transition_abstraction_min_precision: float = 0.95
    transition_abstraction_min_diversity: int = 4
    transition_abstraction_max_dropped_features: int = 2
    # v0.3.0-alpha.12: bounded sparse-retained-feature projection search for
    # rules hidden behind many visible nuisance dimensions.
    transition_abstraction_sparse_enabled: bool = True
    transition_abstraction_pending_enabled: bool = True
    transition_abstraction_sparse_max_retained_features: int = 2
    transition_abstraction_candidates_per_observation: int = 48
    transition_abstraction_max_candidates: int = 2048
    transition_abstraction_exception_limit: int = 512

    # v0.3.0-alpha.5: competitive routing, empirical calibration + adaptive breadth
    mechanism_scheduler_enabled: bool = True
    mechanism_scheduler_max_calls: int = 1
    mechanism_scheduler_medium_calls: int = 3
    mechanism_scheduler_min_relevance: float = 0.45
    mechanism_scheduler_high_confidence: float = 0.74
    mechanism_scheduler_low_confidence: float = 0.46
    mechanism_scheduler_min_margin: float = 0.08
    mechanism_scheduler_calibration_min_support: int = 4
    mechanism_scheduler_recovery_uncertainty: float = 0.72

    # v0.4.0-alpha.3: robust bounded planning / internal simulation
    planner_enabled: bool = True
    planner_max_horizon: int = 5
    planner_beam_width: int = 8
    planner_max_expansions: int = 64
    planner_uncertainty_penalty: float = 0.35
    planner_step_penalty: float = 0.01
    planner_min_step_confidence: float = 0.0
    planner_adaptive_beam_max: int = 16
    planner_stall_patience: int = 1
    planner_uncertainty_widen_threshold: float = 0.55
    planner_proximity_weight: float = 0.20

    # v0.4.0-alpha.3: probabilistic futures, explicit residual uncertainty,
    # tail-risk thresholds, and action/resource costs.
    stochastic_planner_enabled: bool = True
    stochastic_planner_max_horizon: int = 5
    stochastic_planner_beam_width: int = 8
    stochastic_planner_max_expansions: int = 128
    stochastic_planner_max_scenarios: int = 24
    stochastic_planner_top_k_outcomes: int = 4
    stochastic_planner_risk_aversion: float = 2.0
    stochastic_planner_unknown_risk_weight: float = 0.65
    stochastic_planner_cost_weight: float = 0.02
    stochastic_planner_proximity_weight: float = 0.20
    stochastic_planner_step_penalty: float = 0.005
    stochastic_planner_min_goal_probability: float = 0.70
    stochastic_planner_max_hazard_probability: float = 0.10
    stochastic_planner_max_unknown_probability: float = 0.25

    # v0.4.0-alpha.4: active information gathering and observation-conditioned
    # contingent policy trees.
    contingent_planner_enabled: bool = True
    contingent_planner_max_horizon: int = 5
    contingent_planner_max_expansions: int = 192
    contingent_planner_top_k_outcomes: int = 4
    contingent_planner_risk_aversion: float = 2.0
    contingent_planner_unknown_risk_weight: float = 0.65
    contingent_planner_cost_weight: float = 0.02
    contingent_planner_proximity_weight: float = 0.20
    contingent_planner_step_penalty: float = 0.005
    contingent_planner_min_goal_probability: float = 0.70
    contingent_planner_max_hazard_probability: float = 0.10
    contingent_planner_max_unknown_probability: float = 0.25
    contingent_planner_memo_limit: int = 4096

    # v0.4.0-alpha.5: compact latent belief states for partial observability.
    # Equivalent posteriors are memoized as one policy state instead of raw
    # observation histories producing duplicate subtrees.
    belief_planner_enabled: bool = True
    belief_planner_max_horizon: int = 8
    belief_planner_max_expansions: int = 256
    belief_planner_top_k_outcomes: int = 4
    belief_planner_risk_aversion: float = 2.0
    belief_planner_unknown_risk_weight: float = 0.65
    belief_planner_cost_weight: float = 0.02
    belief_planner_proximity_weight: float = 0.20
    belief_planner_step_penalty: float = 0.005
    belief_planner_min_goal_probability: float = 0.70
    belief_planner_max_hazard_probability: float = 0.10
    belief_planner_max_unknown_probability: float = 0.25
    belief_planner_memo_limit: int = 8192
    belief_planner_max_hypotheses: int = 32
    belief_planner_key_precision: int = 12

    # v0.4.0-alpha.6: online evidence-source reliability learning.
    # Reliability is updated only from externally resolved outcomes, never from
    # ASM's own current guess. Drift/correlation learning remains out of scope.
    adaptive_evidence_enabled: bool = True
    adaptive_evidence_prior_strength: float = 4.0
    adaptive_evidence_min_shape: float = 1e-6
    adaptive_evidence_max_sources: int = 1024
    # alpha.6.1: bounded two-window temporal change detection. Drift is only
    # evaluated when resolved observations carry explicit temporal indices.
    adaptive_evidence_drift_enabled: bool = True
    adaptive_evidence_drift_window: int = 32
    adaptive_evidence_drift_min_abs_change: float = 0.25
    adaptive_evidence_drift_min_zscore: float = 3.0
    adaptive_evidence_drift_min_log_bayes_factor: float = 10.0
    adaptive_evidence_max_regimes_per_source: int = 16

    # alpha.6.2: explicit evidence-lineage hardening. This does not infer hidden
    # correlations; it prevents known copies/derived observations from being
    # counted as fresh independent support.
    evidence_lineage_enabled: bool = True
    evidence_lineage_max_nodes: int = 65536
    evidence_lineage_max_roots_per_item: int = 256
    evidence_lineage_max_roots_per_belief: int = 4096

    # alpha.7 candidate: learn hidden evidence redundancy from externally
    # resolved trial groups. Positive within-source and cross-source correlation
    # reduces effective evidence count; no latent-cause invention is performed.
    evidence_dependency_enabled: bool = True
    # Honesty guard for ProcedureCortex predictions outside the evidence range: 'abstain' (default since DEV3.3) | 'discount' | 'off' (pre-DEV3.2 behaviour).
    procedure_extrapolation_guard: str = "abstain"
    procedure_extrapolation_confidence_cap: float = 0.5
    evidence_dependency_min_trials: int = 64
    evidence_dependency_min_abs_correlation: float = 0.25
    evidence_dependency_min_fisher_z: float = 4.0
    evidence_dependency_max_sources: int = 256
    evidence_dependency_max_pairs: int = 32768
    evidence_dependency_max_trials: int = 131072
    evidence_dependency_max_readings_per_source_trial: int = 4096
    evidence_dependency_max_batch_items: int = 4096
    evidence_dependency_max_sources_per_belief: int = 256

    # alpha.7.1: optional explicit-time dependency adaptation. These settings
    # affect only trials that supply a strictly increasing temporal_index.
    # Historical/unordered training without a temporal_index retains alpha.7
    # cumulative semantics.
    evidence_dependency_recent_window: int = 192
    evidence_dependency_self_change_window: int = 64
    evidence_dependency_pair_change_window: int = 96
    evidence_dependency_self_change_delta: float = 0.35
    evidence_dependency_pair_change_delta: float = 0.45
    evidence_dependency_self_change_z: float = 4.5
    evidence_dependency_pair_change_z: float = 6.0
    evidence_dependency_self_change_persistence: int = 3
    evidence_dependency_pair_change_persistence: int = 5

    # Memory
    memory_recall_limit: int = 5
    recall_injection_gain: float = 0.18
    recall_max_concepts: int = 10
    recall_per_concept_limit: int = 96
    recall_max_candidates: int = 256
    recall_common_ratio_cutoff: float = 0.18
    recall_common_absolute_cutoff: int = 220

    # Goal influence
    goal_boost: float = 0.20

    # Persistence / maintenance
    snapshot_every_events: int = 250
    prune_every_events: int = 100

    # alpha.5: offline frozen recurrent surface realizer.
    writer_backend: str = "recurrent"
    writer_style: str = "full"
    writer_model_path: str = ""
    writer_max_tokens: int = 80
    writer_min_confidence: float = 0.65
