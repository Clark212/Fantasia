from __future__ import annotations

from pathlib import Path
from dataclasses import asdict
from typing import Dict, List

from .actions import ActionSelector
from .attention import AttentionSystem
from .appraisal import AppraisalSystem
from .config import ASMConfig
from .encoder import ConceptEncoder
from .expansion import AssociativeExpander
from .emergent import EmergentConceptSystem
from .emotion import EmotionLearner
from .field import SeismicField
from .generalizer import LocalRuleLearner
from .hierarchical_mind import HierarchicalMindModel
from .goals import GoalSystem
from .memory import EpisodicMemory
from .language_core import (
    FallbackLanguageCore, LanguageCore, LanguageProposal,
    LanguageReadResult, create_language_core, validate_language_proposal,
)
from .mind import AgentMindModel, canonical_proposition
from .mental_language import MentalLanguagePerception
from .predictor import TransitionPredictor
from .predictive_coding import PredictiveCodingLearner
from .perception import LearnedRelationPerception
from .relation_discovery import SelfDiscoveredRelationSystem
from .structural import StructuralMemory, StructuralParser
from .self_model import SelfModel
from .consolidation import ConsolidationGate, ConsolidationDecision
from .semantic_memory import SemanticEpisodicIndex
from .social_probe import FrozenSocialProbe
from .dialogue import DialogueActRecognizer, ConversationManager
from .recurrent_writer import RecurrentWriter
from .semantic_event import SemanticEventCortex
from .event_memory import SemanticEventMemory
from .world_model import PersistentWorldModel
from .transition_mechanism import TransitionMechanismBank
from .planning import BoundedInternalPlanner, ProbabilisticInternalPlanner, ContingentInternalPlanner, BeliefStateInternalPlanner, DiscreteBeliefState, StateGoal
from .adaptive_evidence import AdaptiveEvidenceModel
from .evidence_lineage import EvidenceLineageGraph, EvidenceLedger
from .procedure_cortex import ProcedureCortex
from .proposal_contract import validate_proposal
from .evidence_dependency import EvidenceDependencyModel


class ASMEngine:
    """
    ASM v0.4.0-alpha.7.9 — Adversarial Latent-Structure Hardening & Stage-Closure.

    Alpha.7.9 preserves alpha.7.8 latent routing and adds a bounded component-wise
    signed latent redundancy guard.  It can detect sparse hidden subgroups, signed
    / anti-correlated common causes, overlapping rank<=2 factors, and moving latent
    groups while remaining monotone: it may only reduce alpha.7.8 evidence weight.
    Frustrated, weak, undersampled, sparse, oversized, non-finite, or numerically
    invalid structures fall back locally to the certified alpha.7.8 latent router.

    Alpha.5 preserves alpha.4 contingent policy trees and adds compact bounded
    latent belief states. Repeated evidence is fused across observations, contradictory
    evidence revises the posterior, and equivalent posteriors share policy-DAG nodes.
    Simulated belief updates remain read-only.
    """

    SNAPSHOT_KEY = "asm_snapshot_v0_4_0_alpha_7_9"
    ALPHA78_V04_SNAPSHOT_KEY = "asm_snapshot_v0_4_0_alpha_7_8"
    ALPHA77_V04_SNAPSHOT_KEY = "asm_snapshot_v0_4_0_alpha_7_7"
    ALPHA76_V04_SNAPSHOT_KEY = "asm_snapshot_v0_4_0_alpha_7_6"
    ALPHA74_V04_SNAPSHOT_KEY = "asm_snapshot_v0_4_0_alpha_7_4"
    ALPHA73_V04_SNAPSHOT_KEY = "asm_snapshot_v0_4_0_alpha_7_3"
    ALPHA72_V04_SNAPSHOT_KEY = "asm_snapshot_v0_4_0_alpha_7_2"
    ALPHA71_V04_SNAPSHOT_KEY = "asm_snapshot_v0_4_0_alpha_7_1"
    ALPHA7_V04_SNAPSHOT_KEY = "asm_snapshot_v0_4_0_alpha_7"
    ALPHA62_V04_SNAPSHOT_KEY = "asm_snapshot_v0_4_0_alpha_6_2"
    ALPHA61_V04_SNAPSHOT_KEY = "asm_snapshot_v0_4_0_alpha_6_1"
    ALPHA6_V04_SNAPSHOT_KEY = "asm_snapshot_v0_4_0_alpha_6"
    ALPHA52_V04_SNAPSHOT_KEY = "asm_snapshot_v0_4_0_alpha_5_2"
    ALPHA51_V04_SNAPSHOT_KEY = "asm_snapshot_v0_4_0_alpha_5_1"
    ALPHA5_V04_SNAPSHOT_KEY = "asm_snapshot_v0_4_0_alpha_5"
    ALPHA4_V04_SNAPSHOT_KEY = "asm_snapshot_v0_4_0_alpha_4"
    ALPHA3_V04_SNAPSHOT_KEY = "asm_snapshot_v0_4_0_alpha_3"
    ALPHA2_V04_SNAPSHOT_KEY = "asm_snapshot_v0_4_0_alpha_2"
    ALPHA1_V04_SNAPSHOT_KEY = "asm_snapshot_v0_4_0_alpha_1"
    ALPHA12_V03_SNAPSHOT_KEY = "asm_snapshot_v0_3_0_alpha_12"
    ALPHA11_V03_SNAPSHOT_KEY = "asm_snapshot_v0_3_0_alpha_11"
    ALPHA10_V03_SNAPSHOT_KEY = "asm_snapshot_v0_3_0_alpha_10"
    ALPHA9_V03_SNAPSHOT_KEY = "asm_snapshot_v0_3_0_alpha_9"
    ALPHA8_V03_SNAPSHOT_KEY = "asm_snapshot_v0_3_0_alpha_8"
    ALPHA7_V03_SNAPSHOT_KEY = "asm_snapshot_v0_3_0_alpha_7"
    ALPHA6_V03_SNAPSHOT_KEY = "asm_snapshot_v0_3_0_alpha_6"
    ALPHA5_V03_SNAPSHOT_KEY = "asm_snapshot_v0_3_0_alpha_5"
    ALPHA4_V03_SNAPSHOT_KEY = "asm_snapshot_v0_3_0_alpha_4"
    ALPHA3_V03_SNAPSHOT_KEY = "asm_snapshot_v0_3_0_alpha_3"
    ALPHA2_V03_SNAPSHOT_KEY = "asm_snapshot_v0_3_0_alpha_2"
    ALPHA1_V03_SNAPSHOT_KEY = "asm_snapshot_v0_3_0_alpha_1"
    ALPHA7_SNAPSHOT_KEY = "asm_snapshot_v0_2_0_alpha_7"
    ALPHA6_SNAPSHOT_KEY = "asm_snapshot_v0_2_0_alpha_6"
    # v0.2 alpha.5 intentionally reused v0.2 alpha.4's snapshot key; keep compatibility.
    ALPHA5_SNAPSHOT_KEY = "asm_snapshot_v0_2_0_alpha_4"
    ALPHA3_SNAPSHOT_KEY = "asm_snapshot_v0_2_0_alpha_3"
    ALPHA2_SNAPSHOT_KEY = "asm_snapshot_v0_2_0_alpha_2"
    ALPHA1_SNAPSHOT_KEY = "asm_snapshot_v0_2_0_alpha_1"
    LEGACY_SNAPSHOT_KEY = "asm_snapshot_v1_1_10"
    OLDER_SNAPSHOT_KEY = "asm_snapshot_v1_1_9"
    OLDEST_SNAPSHOT_KEY = "asm_snapshot_v1_1_8"
    ANCIENT_SNAPSHOT_KEY = "asm_snapshot_v1_1_7"
    PREHISTORIC_SNAPSHOT_KEY = "asm_snapshot_v1_1_6"
    PRIMITIVE_SNAPSHOT_KEY = "asm_snapshot_v1_1_5"
    ARCHAIC_SNAPSHOT_KEY = "asm_snapshot_v1_1_4"
    ORIGINAL_SNAPSHOT_KEY = "asm_snapshot_v1_1_3"

    def __init__(
        self,
        db_path: str | Path = "asm_state.db",
        config: ASMConfig | None = None,
        language_core: LanguageCore | None = None,
    ):
        self.cfg = config or ASMConfig()

        self.encoder = ConceptEncoder(
            semantic_similarity_threshold=self.cfg.semantic_similarity_threshold,
            semantic_min_observations=self.cfg.semantic_min_observations,
            semantic_max_aliases=self.cfg.semantic_max_aliases,
            semantic_alias_gain=self.cfg.semantic_alias_gain,
        )
        self.language_core = language_core or create_language_core(
            self.cfg.language_core_backend,
            self.cfg,
            self.encoder,
        )
        self.last_language_read: LanguageReadResult | None = None
        self.last_language_error: str | None = None
        data_dir = Path(__file__).resolve().parent / "data"
        self.social_probe = FrozenSocialProbe(
            model_path=data_dir / "social_probe_v020a3.pt",
            metadata_path=data_dir / "social_probe_v020a3.json",
            threshold=self.cfg.consolidation_social_threshold,
        )
        self.consolidation = ConsolidationGate(self.cfg)
        self.writer = RecurrentWriter(
            self.cfg.writer_model_path or None, max_tokens=self.cfg.writer_max_tokens,
            min_confidence=self.cfg.writer_min_confidence,
        ) if self.cfg.writer_backend == "recurrent" else None
        self.semantic_cortex = SemanticEventCortex()
        self.dialogue_recognizer = DialogueActRecognizer()
        self.conversation = ConversationManager(
            self.dialogue_recognizer,
            history_limit=16,
        )

        self.field = SeismicField(self.cfg)
        self.predictor = TransitionPredictor(self.cfg)
        self.predictive_coder = PredictiveCodingLearner(self.cfg)
        self.generalizer = LocalRuleLearner(self.cfg)

        self.structural_parser = StructuralParser()
        self.perception = LearnedRelationPerception(
            self.cfg,
            self.encoder,
            self.structural_parser,
        )
        self.relation_discovery = SelfDiscoveredRelationSystem(
            self.cfg,
            self.encoder,
            self.structural_parser,
            self.perception,
        )
        self.structural_memory = StructuralMemory(self.cfg)
        self.expander = AssociativeExpander(
            self.cfg,
            self.structural_memory,
        )

        # v0.1.1.5 cognition foundations.
        self.emergent = EmergentConceptSystem(self.cfg)
        self.minds = AgentMindModel(self.cfg)
        self.emotions = EmotionLearner(
            self.cfg,
            self.encoder,
            self.structural_parser,
        )
        self.appraisal = AppraisalSystem(
            self.cfg,
            self.minds,
        )

        # v0.1.1.7: ASM models its own state as well as other minds.
        self.hierarchical_minds = HierarchicalMindModel(self.cfg)
        self.self_model = SelfModel(self.cfg)
        self.attention = AttentionSystem(self.cfg)

        self.memory = EpisodicMemory(
            db_path,
            max_concepts=self.cfg.recall_max_concepts,
            per_concept_limit=self.cfg.recall_per_concept_limit,
            max_candidates=self.cfg.recall_max_candidates,
            common_ratio_cutoff=self.cfg.recall_common_ratio_cutoff,
            common_absolute_cutoff=self.cfg.recall_common_absolute_cutoff,
        )
        self.semantic_memory = SemanticEpisodicIndex(
            db_path,
            tables=self.cfg.semantic_lsh_tables,
            bits=self.cfg.semantic_lsh_bits,
            min_candidates=self.cfg.semantic_lsh_min_candidates,
            max_candidates=self.cfg.semantic_lsh_max_candidates,
            min_similarity=self.cfg.semantic_memory_min_similarity,
        )
        self.event_memory = SemanticEventMemory(db_path)
        self.world_model = PersistentWorldModel(
            db_path,
            max_schedule_candidates=self.cfg.world_scheduler_max_candidates,
        ) if self.cfg.world_model_enabled else None
        self.transition_mechanisms = TransitionMechanismBank(
            db_path,
            input_dim=self.cfg.transition_input_dim,
            hidden_dim=self.cfg.transition_hidden_dim,
            max_outcomes=self.cfg.transition_max_outcomes,
            learning_rate=self.cfg.transition_learning_rate,
            train_steps=self.cfg.transition_train_steps,
            seed=self.cfg.transition_seed,
            retention_anchor_limit=self.cfg.transition_retention_anchor_limit,
            retention_anchor_batch_limit=self.cfg.transition_retention_anchor_batch_limit,
            outcome_capacity_limit=self.cfg.transition_outcome_capacity_limit,
            outcome_growth_factor=self.cfg.transition_outcome_growth_factor,
            consolidation_table_size=self.cfg.transition_consolidation_table_size,
            consolidation_hashes=self.cfg.transition_consolidation_hashes,
            consolidation_min_support=self.cfg.transition_consolidation_min_support,
            consolidation_max_displacements=self.cfg.transition_consolidation_max_displacements,
            consolidation_enabled=self.cfg.transition_consolidation_enabled,
            abstraction_enabled=self.cfg.transition_abstraction_enabled,
            abstraction_min_support=self.cfg.transition_abstraction_min_support,
            abstraction_min_precision=self.cfg.transition_abstraction_min_precision,
            abstraction_min_diversity=self.cfg.transition_abstraction_min_diversity,
            abstraction_max_dropped_features=self.cfg.transition_abstraction_max_dropped_features,
            abstraction_sparse_enabled=self.cfg.transition_abstraction_sparse_enabled,
            abstraction_pending_enabled=self.cfg.transition_abstraction_pending_enabled,
            abstraction_sparse_max_retained_features=self.cfg.transition_abstraction_sparse_max_retained_features,
            abstraction_candidates_per_observation=self.cfg.transition_abstraction_candidates_per_observation,
            abstraction_max_candidates=self.cfg.transition_abstraction_max_candidates,
            abstraction_exception_limit=self.cfg.transition_abstraction_exception_limit,
            scheduler_max_calls=self.cfg.mechanism_scheduler_max_calls,
            scheduler_medium_calls=self.cfg.mechanism_scheduler_medium_calls,
            scheduler_min_relevance=self.cfg.mechanism_scheduler_min_relevance,
            scheduler_high_confidence=self.cfg.mechanism_scheduler_high_confidence,
            scheduler_low_confidence=self.cfg.mechanism_scheduler_low_confidence,
            scheduler_min_margin=self.cfg.mechanism_scheduler_min_margin,
            scheduler_calibration_min_support=self.cfg.mechanism_scheduler_calibration_min_support,
            scheduler_recovery_uncertainty=self.cfg.mechanism_scheduler_recovery_uncertainty,
        ) if self.cfg.transition_mechanisms_enabled else None
        self.planner = BoundedInternalPlanner(
            self.transition_mechanisms.predict_simulated,
            max_horizon=self.cfg.planner_max_horizon,
            beam_width=self.cfg.planner_beam_width,
            max_expansions=self.cfg.planner_max_expansions,
            uncertainty_penalty=self.cfg.planner_uncertainty_penalty,
            step_penalty=self.cfg.planner_step_penalty,
            min_step_confidence=self.cfg.planner_min_step_confidence,
            adaptive_beam_max=self.cfg.planner_adaptive_beam_max,
            stall_patience=self.cfg.planner_stall_patience,
            uncertainty_widen_threshold=self.cfg.planner_uncertainty_widen_threshold,
            proximity_weight=self.cfg.planner_proximity_weight,
        ) if (self.cfg.planner_enabled and self.transition_mechanisms is not None) else None
        self.stochastic_planner = ProbabilisticInternalPlanner(
            self.transition_mechanisms.predict_distribution_simulated,
            max_horizon=self.cfg.stochastic_planner_max_horizon,
            beam_width=self.cfg.stochastic_planner_beam_width,
            max_expansions=self.cfg.stochastic_planner_max_expansions,
            max_scenarios=self.cfg.stochastic_planner_max_scenarios,
            top_k_outcomes=self.cfg.stochastic_planner_top_k_outcomes,
            risk_aversion=self.cfg.stochastic_planner_risk_aversion,
            unknown_risk_weight=self.cfg.stochastic_planner_unknown_risk_weight,
            cost_weight=self.cfg.stochastic_planner_cost_weight,
            proximity_weight=self.cfg.stochastic_planner_proximity_weight,
            step_penalty=self.cfg.stochastic_planner_step_penalty,
            min_goal_probability=self.cfg.stochastic_planner_min_goal_probability,
            max_hazard_probability=self.cfg.stochastic_planner_max_hazard_probability,
            max_unknown_probability=self.cfg.stochastic_planner_max_unknown_probability,
        ) if (self.cfg.stochastic_planner_enabled and self.transition_mechanisms is not None) else None
        self.contingent_planner = ContingentInternalPlanner(
            self.transition_mechanisms.predict_distribution_simulated,
            max_horizon=self.cfg.contingent_planner_max_horizon,
            max_expansions=self.cfg.contingent_planner_max_expansions,
            top_k_outcomes=self.cfg.contingent_planner_top_k_outcomes,
            risk_aversion=self.cfg.contingent_planner_risk_aversion,
            unknown_risk_weight=self.cfg.contingent_planner_unknown_risk_weight,
            cost_weight=self.cfg.contingent_planner_cost_weight,
            proximity_weight=self.cfg.contingent_planner_proximity_weight,
            step_penalty=self.cfg.contingent_planner_step_penalty,
            min_goal_probability=self.cfg.contingent_planner_min_goal_probability,
            max_hazard_probability=self.cfg.contingent_planner_max_hazard_probability,
            max_unknown_probability=self.cfg.contingent_planner_max_unknown_probability,
            memo_limit=self.cfg.contingent_planner_memo_limit,
        ) if (self.cfg.contingent_planner_enabled and self.transition_mechanisms is not None) else None
        self.adaptive_evidence = AdaptiveEvidenceModel(
            prior_strength=self.cfg.adaptive_evidence_prior_strength,
            min_shape=self.cfg.adaptive_evidence_min_shape,
            max_sources=self.cfg.adaptive_evidence_max_sources,
            drift_detection_enabled=self.cfg.adaptive_evidence_drift_enabled,
            drift_window=self.cfg.adaptive_evidence_drift_window,
            drift_min_abs_change=self.cfg.adaptive_evidence_drift_min_abs_change,
            drift_min_zscore=self.cfg.adaptive_evidence_drift_min_zscore,
            drift_min_log_bayes_factor=self.cfg.adaptive_evidence_drift_min_log_bayes_factor,
            max_regimes_per_source=self.cfg.adaptive_evidence_max_regimes_per_source,
        )
        self.evidence_lineage = EvidenceLineageGraph(
            max_nodes=self.cfg.evidence_lineage_max_nodes,
            max_roots_per_item=self.cfg.evidence_lineage_max_roots_per_item,
        )
        self.evidence_dependency = EvidenceDependencyModel(
            min_trials=self.cfg.evidence_dependency_min_trials,
            min_abs_correlation=self.cfg.evidence_dependency_min_abs_correlation,
            min_fisher_z=self.cfg.evidence_dependency_min_fisher_z,
            max_sources=self.cfg.evidence_dependency_max_sources,
            max_pairs=self.cfg.evidence_dependency_max_pairs,
            max_trials=self.cfg.evidence_dependency_max_trials,
            max_readings_per_source_trial=self.cfg.evidence_dependency_max_readings_per_source_trial,
            recent_window=self.cfg.evidence_dependency_recent_window,
            self_change_window=self.cfg.evidence_dependency_self_change_window,
            pair_change_window=self.cfg.evidence_dependency_pair_change_window,
            self_change_delta=self.cfg.evidence_dependency_self_change_delta,
            pair_change_delta=self.cfg.evidence_dependency_pair_change_delta,
            self_change_z=self.cfg.evidence_dependency_self_change_z,
            pair_change_z=self.cfg.evidence_dependency_pair_change_z,
            self_change_persistence=self.cfg.evidence_dependency_self_change_persistence,
            pair_change_persistence=self.cfg.evidence_dependency_pair_change_persistence,
        )

        # Additive donor integration: audited typed procedures. This does not
        # replace alpha.7.1 dependency learning or grant external proposals
        # authority over beliefs/actions. Procedure state persists in its own
        # bounded SQLite tables in the same DB file.
        self._procedure_db_path = str(db_path)
        self._procedures = None

        self.belief_planner = BeliefStateInternalPlanner(
            self.transition_mechanisms.predict_distribution_simulated,
            max_horizon=self.cfg.belief_planner_max_horizon,
            max_expansions=self.cfg.belief_planner_max_expansions,
            top_k_outcomes=self.cfg.belief_planner_top_k_outcomes,
            risk_aversion=self.cfg.belief_planner_risk_aversion,
            unknown_risk_weight=self.cfg.belief_planner_unknown_risk_weight,
            cost_weight=self.cfg.belief_planner_cost_weight,
            proximity_weight=self.cfg.belief_planner_proximity_weight,
            step_penalty=self.cfg.belief_planner_step_penalty,
            min_goal_probability=self.cfg.belief_planner_min_goal_probability,
            max_hazard_probability=self.cfg.belief_planner_max_hazard_probability,
            max_unknown_probability=self.cfg.belief_planner_max_unknown_probability,
            memo_limit=self.cfg.belief_planner_memo_limit,
            max_hypotheses=self.cfg.belief_planner_max_hypotheses,
            belief_key_precision=self.cfg.belief_planner_key_precision,
        ) if (self.cfg.belief_planner_enabled and self.transition_mechanisms is not None) else None
        self.goals = GoalSystem()
        self.actions = ActionSelector()

        self.event_count = self.memory.count_events()
        self.previous_workspace: List[tuple[str, float]] = []
        self.last_prediction: Dict[str, float] = {}
        self.last_predictive_error: float = 0.0

        self._load_snapshot()
        if self.cfg.semantic_memory_enabled:
            self._backfill_semantic_memory()
        self._backfill_event_memory()
        if self.world_model is not None:
            self.world_model.backfill_from_semantic_memory(
                limit=self.cfg.world_model_backfill_limit
            )

    def _read_language(self, text: str) -> LanguageReadResult:
        try:
            result = self.language_core.read(text)
            social_p = self.social_probe.probability(
                result.embedding,
                backend=result.backend,
            )
            result.metadata["social_probability"] = social_p
            result.metadata["social_candidate"] = (
                social_p >= self.cfg.consolidation_social_threshold
            )
            self.last_language_read = result
            self.last_language_error = None
            return result
        except Exception as exc:
            self.last_language_error = f"{type(exc).__name__}: {exc}"
            if not self.cfg.language_core_fail_open:
                raise
            fallback = FallbackLanguageCore(
                self.encoder,
                embedding_dims=self.cfg.language_core_embedding_dims,
            )
            result = fallback.read(text)
            result.metadata["failover_from"] = self.language_core.name
            result.metadata["failover_error"] = self.last_language_error
            self.last_language_read = result
            return result

    def _consume_language_proposals(self, read: LanguageReadResult) -> dict:
        events = {"_accepted": [], "_rejected": []}
        proposals = list(read.proposals[: self.cfg.language_core_max_proposals])
        if self.language_core.native_passthrough or read.backend == "fallback":
            # The fallback mirrors native parsing; applying both would double-count.
            for proposal in proposals:
                events["_rejected"].append({**proposal.as_dict(), "reason": "native_passthrough"})
            return events

        eligible = []
        for proposal in proposals:
            valid, validation_reason = validate_language_proposal(proposal)
            if not valid:
                try:
                    raw = proposal.as_dict()
                except Exception:
                    raw = {"kind": getattr(proposal, "kind", "invalid"), "source": getattr(proposal, "source", "language_core")}
                events["_rejected"].append({**raw, "reason": f"proposal_contract:{validation_reason}"})
                continue
            if float(proposal.confidence) < self.cfg.language_core_min_confidence:
                events["_rejected"].append({**proposal.as_dict(), "reason": "below_confidence_gate"})
                continue
            allowed, semantic_reason = self.semantic_cortex.proposal_allowed(read.text, proposal)
            if not allowed:
                events["_rejected"].append({**proposal.as_dict(), "reason": semantic_reason or "semantic_gate"})
                continue
            eligible.append(proposal)

        # Alpha.6 persistence invariant: at most one language-derived semantic
        # event may cross into long-term cognitive state for one utterance.
        # This prevents a noisy model from simultaneously writing a belief and
        # a fear/goal/expectation before the semantic cortex can arbitrate them.
        if eligible:
            def rank(proposal):
                kind = proposal.kind
                if kind == "drive":
                    kind = str(proposal.payload.get("kind", "goal"))
                priority = {
                    "nested_belief": 70, "self_outcome": 65,
                    "fear": 60, "expectation": 60, "goal": 60,
                    "belief": 50,
                }.get(kind, 0)
                return (priority, float(proposal.confidence))

            eligible.sort(key=rank, reverse=True)
            winner = eligible[0]
            for loser in eligible[1:]:
                events["_rejected"].append({**loser.as_dict(), "reason": "semantic_proposal_conflict"})
            try:
                event = self._apply_language_proposal(winner)
            except Exception as exc:
                events["_rejected"].append({**winner.as_dict(), "reason": f"invalid:{type(exc).__name__}"})
                event = None
            if event is None:
                if not any(x.get("source") == winner.source and x.get("kind") == winner.kind for x in events["_rejected"]):
                    events["_rejected"].append({**winner.as_dict(), "reason": "unsupported_kind"})
            else:
                events[winner.kind] = event
                events["_accepted"].append(winner.as_dict())
        return events

    def _apply_language_proposal(self, proposal: LanguageProposal) -> dict | None:
        p = proposal.payload
        source = proposal.source or self.language_core.name
        if proposal.kind == "belief":
            return self.minds.observe_proposition(
                str(p["holder"]),
                str(p["proposition_text"]),
                self.event_count,
                polarity=bool(p.get("polarity", True)),
                source=source,
            )
        if proposal.kind == "nested_belief":
            path = tuple(str(x).lower() for x in p["path"])
            base, truth = canonical_proposition(str(p["proposition_text"]))
            if not bool(p.get("polarity", True)):
                truth = not truth
            state = self.hierarchical_minds.observe(
                path, base, truth, self.event_count,
                confidence=float(proposal.confidence),
            )
            return {
                "type": "nested_belief",
                "path": list(path),
                "order": len(path),
                "proposition": base,
                "asserted_truth": truth,
                "state": state,
                "source": source,
            }
        if proposal.kind == "drive":
            return self.appraisal.observe_drive_proposal(
                str(p["holder"]),
                str(p["kind"]),
                str(p["proposition_text"]),
                self.event_count,
                priority=float(p.get("priority", 0.6)),
                source=source,
            )
        if proposal.kind == "self_outcome":
            result = self.self_model.record_strategy_outcome(
                str(p.get("task_family", "reasoning")),
                str(p["strategy"]),
                bool(p["success"]),
                self.event_count,
                score=float(p.get("score", proposal.confidence)),
            )
            result["source"] = source
            return result
        return None

    def language_core_status(self) -> dict:
        status = self.language_core.health()
        status["min_confidence"] = self.cfg.language_core_min_confidence
        status["last_error"] = self.last_language_error
        status["social_probe"] = self.social_probe.health()
        status["semantic_memory_vectors"] = self.semantic_memory.count()
        status["semantic_event_memory"] = self.event_memory.stats()
        status["world_model"] = self.world_model.stats() if self.world_model else {"enabled": False}
        status["transition_mechanisms"] = self.transition_mechanisms.stats() if self.transition_mechanisms else {"enabled": False}
        status["dialogue"] = self.dialogue_recognizer.health()
        status["writer"] = self.writer.health() if self.writer else {"backend": "hybrid", "ready": True}
        status["semantic_event_cortex"] = self.semantic_cortex.health()
        status["conversation_history_length"] = len(self.conversation.history)
        return status

    def set_language_core(self, core: LanguageCore) -> None:
        if not isinstance(core, LanguageCore):
            raise TypeError("core must implement LanguageCore")
        old = self.language_core
        self.language_core = core
        if old is not core:
            old.close()

    def embed_text(self, text: str) -> list[float]:
        return list(self._read_language(text).embedding)

    def generate_text(self, instruction: str = "") -> dict:
        if not self.cfg.language_core_allow_generation:
            return {
                "text": "",
                "backend": self.language_core.name,
                "confidence": 0.0,
                "metadata": {"disabled": True},
            }
        state = self.self_state()
        state["workspace"] = list(self.previous_workspace[: self.cfg.workspace_size])
        state["goals"] = [
            {"text": g.text, "priority": float(g.priority), "progress": float(g.progress)}
            for g in sorted(
                (x for x in self.goals.goals if x.active),
                key=lambda x: (-float(x.priority), x.text),
            )[:6]
        ]
        belief_rows = []
        for holder, props in self.minds.states.items():
            for proposition in props:
                row = self.minds.query_base(holder, proposition)
                if row.get("status") != "unknown":
                    belief_rows.append(row)
        belief_rows.sort(key=lambda x: (int(x.get("last_event", 0)), float(x.get("confidence", 0.0))), reverse=True)
        state["agent_beliefs"] = belief_rows[:8]
        state["world_states"] = self.world_model.current(limit=8) if self.world_model is not None else []
        state["relevant_memories"] = (
            self.event_memory.recall(instruction, limit=4)
            if str(instruction).strip() else []
        )
        return self.language_core.generate(state, instruction=instruction).as_dict()

    def chat(self, text: str, *, training: bool = False) -> dict:
        result = self.process(text, training=training)
        conversation = self.conversation.respond(text, result, self)
        result["conversation"] = conversation
        result["reply"] = conversation["reply"]
        return result

    def conversation_state(self) -> dict:
        return self.conversation.state()

    def recall_events(self, text: str, limit: int = 5) -> list[dict]:
        """Query alpha.7 typed semantic-event memory directly."""
        return self.event_memory.recall(text, limit=limit)

    def event_links(self, event_id: int) -> list[dict]:
        """Inspect descriptive revision/temporal links for a stored event."""
        return self.event_memory.links_for(int(event_id))

    def world_state(self, *, holder: str | None = None, event_type: str | None = None, limit: int = 32) -> list[dict]:
        """Return current explicit world/mind state slots from v0.3 alpha.1."""
        if self.world_model is None:
            return []
        return self.world_model.current(holder=holder, event_type=event_type, limit=limit)

    def world_transitions(self, *, state_key: str | None = None, limit: int = 32) -> list[dict]:
        """Return descriptive state-transition evidence. Alpha.1 never marks it causal."""
        if self.world_model is None:
            return []
        return self.world_model.transitions(state_key=state_key, limit=limit)

    def world_neighbors(self, node_key: str, *, limit: int = 24) -> list[dict]:
        if self.world_model is None:
            return []
        return self.world_model.graph_neighbors(node_key, limit=limit)

    def predict_world_transition(
        self,
        mechanism_type: str,
        *,
        entity_id: str,
        state: dict,
        action: str,
        neighborhood: dict | None = None,
        dt: float = 1.0,
    ) -> dict:
        """Predict a local action-conditioned state transition."""
        if self.transition_mechanisms is None:
            return {"predicted_state": None, "confidence": 0.0, "uncertainty": 1.0, "enabled": False}
        return self.transition_mechanisms.predict(
            mechanism_type,
            entity_id=entity_id,
            state=state,
            action=action,
            neighborhood=neighborhood,
            dt=dt,
        )

    def predict_world_transition_routed(
        self,
        *,
        entity_id: str,
        state: dict,
        action: str,
        neighborhood: dict | None = None,
        dt: float = 1.0,
        mode: str = "seismic",
        max_calls: int | None = None,
        recover: bool = True,
    ) -> dict:
        """Route a transition query through dense or selective seismic execution."""
        if self.transition_mechanisms is None:
            return {"mode": mode, "calls": 0, "chosen": None, "reason": "transition_mechanisms_disabled"}
        actual_mode = mode if self.cfg.mechanism_scheduler_enabled else "dense"
        return self.transition_mechanisms.predict_routed(
            entity_id=entity_id, state=state, action=action,
            neighborhood=neighborhood, dt=dt, mode=actual_mode,
            max_calls=max_calls, recover=recover,
        )

    def plan_world_actions(
        self,
        mechanism_type: str,
        *,
        entity_id: str,
        initial_state: dict,
        actions: list[str] | tuple[str, ...],
        goal: dict,
        avoid: dict | None = None,
        neighborhood: dict | None = None,
        dt: float = 1.0,
        horizon: int | None = None,
    ) -> dict:
        """Run a bounded internal rollout without writing simulated states to memory."""
        if self.planner is None:
            return {"status": "disabled", "simulated_only": True, "best": None}
        return self.planner.plan(
            mechanism_type,
            entity_id=entity_id,
            initial_state=initial_state,
            actions=actions,
            goal=StateGoal(target=goal, avoid=dict(avoid or {})),
            neighborhood=neighborhood,
            dt=dt,
            horizon=horizon,
        )

    def plan_world_actions_probabilistic(
        self,
        mechanism_type: str,
        *,
        entity_id: str,
        initial_state: dict,
        actions: list[str] | tuple[str, ...],
        goal: dict,
        avoid: dict | None = None,
        action_costs: dict[str, float] | None = None,
        neighborhood: dict | None = None,
        dt: float = 1.0,
        horizon: int | None = None,
    ) -> dict:
        """Plan over bounded multi-outcome futures without learning from them."""
        if self.stochastic_planner is None:
            return {"status": "disabled", "simulated_only": True, "probabilistic": True, "best": None}
        return self.stochastic_planner.plan(
            mechanism_type, entity_id=entity_id, initial_state=initial_state,
            actions=actions, goal=StateGoal(target=goal, avoid=dict(avoid or {})),
            action_costs=action_costs, neighborhood=neighborhood, dt=dt, horizon=horizon,
        )

    def plan_world_actions_contingent(
        self,
        mechanism_type: str,
        *,
        entity_id: str,
        initial_state: dict,
        actions: list[str] | tuple[str, ...],
        goal: dict,
        avoid: dict | None = None,
        action_costs: dict[str, float] | None = None,
        neighborhood: dict | None = None,
        dt: float = 1.0,
        horizon: int | None = None,
    ) -> dict:
        """Plan a bounded policy tree whose later actions may depend on observations."""
        if self.contingent_planner is None:
            return {
                "status": "disabled", "simulated_only": True, "probabilistic": True,
                "observation_conditioned": True, "best": None,
            }
        return self.contingent_planner.plan(
            mechanism_type, entity_id=entity_id, initial_state=initial_state,
            actions=actions, goal=StateGoal(target=goal, avoid=dict(avoid or {})),
            action_costs=action_costs, neighborhood=neighborhood, dt=dt, horizon=horizon,
        )

    @property
    def procedures(self) -> ProcedureCortex:
        """Lazily open the audited Procedure Cortex only when used."""
        if self._procedures is None:
            self._procedures = ProcedureCortex(
                self._procedure_db_path, trust_provider=self._procedure_trust_status,
                dependency_provider=(self._procedure_dependency_status if self.cfg.evidence_dependency_enabled else None),
                extrapolation_guard=self.cfg.procedure_extrapolation_guard,
                extrapolation_confidence_cap=self.cfg.procedure_extrapolation_confidence_cap,
            )
        return self._procedures

    def _procedure_dependency_status(self, source_ids) -> dict:
        """Expose bounded, read-only dependency diagnostics to Procedure Cortex.

        Results are cached by dependency-model version + source set. Any real
        dependency update increments the model version, so cached routing
        diagnostics cannot survive a learned correlation/regime change.
        """
        sources=[]
        for raw in source_ids:
            source=str(raw).strip()
            if not source:
                raise ValueError("procedure dependency source id must be non-empty")
            if source not in sources:
                sources.append(source)
        if not sources:
            raise ValueError("procedure dependency batch requires at least one source")
        canonical=tuple(sorted(sources))
        version=int(self.evidence_dependency.version)
        cache=getattr(self,"_procedure_dependency_cache",None)
        if cache is None:
            cache={};self._procedure_dependency_cache=cache
        key=(version,canonical)
        cached=cache.get(key)
        if cached is not None:
            return {**cached,"pairwise":dict(cached.get("pairwise",{})),
                    "pairwise_stats":{k:dict(v) for k,v in cached.get("pairwise_stats",{}).items()},
                    "sources":list(cached.get("sources",[]))}

        out=dict(self.evidence_dependency.effective_batch(canonical))

        # alpha.7.6 R4: routing-specific multiple-comparison guard.
        #
        # EvidenceDependencyModel deliberately keeps its historical per-pair
        # activation contract unchanged.  Procedure routing, however, may ask
        # about tens or hundreds of sources at once, which creates O(n^2) pair
        # hypotheses.  A fixed per-pair significance gate can therefore admit
        # occasional false dependencies simply because many independent pairs
        # were tested.  We apply a Benjamini-Hochberg FDR guard *only* at this
        # read-only routing boundary.  This preserves alpha.7/7.1 semantics and
        # persistence while preventing Procedure Cortex from treating a
        # multiple-testing artifact as routing evidence.
        import math
        from statistics import NormalDist
        pair_rows=[]
        for i,a in enumerate(canonical):
            for b in canonical[i+1:]:
                d=self.evidence_dependency.pair_dependency(a,b)
                rho=float(d.get("active_correlation",0.0))
                raw=float(d.get("raw_correlation",0.0))
                n=int(d.get("recent_trials",0) if d.get("view")=="recent" else d.get("trials",0))
                p=1.0
                if rho>0.0 and n>3 and math.isfinite(raw):
                    rr=max(-0.999999999999,min(0.999999999999,raw))
                    z=abs(math.atanh(rr))*math.sqrt(max(1.0,float(n-3)))
                    p=max(0.0,min(1.0,2.0*(1.0-NormalDist().cdf(z))))
                pair_rows.append({"key":f"{a}\t{b}","rho":rho,"raw":raw,"trials":n,"p":p})

        # q=1% is intentionally conservative because a false dependency costs
        # useful support/queries, while failure to discount a truly redundant
        # pair is already bounded by the original alpha.7 activation gate.
        q=0.01
        ranked=sorted((row for row in pair_rows if row["rho"]>0.0),key=lambda x:(x["p"],x["key"]))
        cutoff_rank=0
        m=max(1,len(pair_rows))
        for rank,row in enumerate(ranked,1):
            if row["p"] <= q*float(rank)/float(m):
                cutoff_rank=rank
        accepted={row["key"] for row in ranked[:cutoff_rank]}
        pairwise={row["key"]:(row["rho"] if row["key"] in accepted else 0.0) for row in pair_rows}
        out["pairwise"]=pairwise
        # alpha.7.8 experimental read-only diagnostics. The FDR graph remains
        # authoritative for direct covariance routing. Latent routing may use
        # the broader raw pair field only to detect additional redundancy.
        out["pairwise_stats"]={row["key"]:{
            "raw":float(row["raw"]), "active":float(row["rho"]),
            "trials":int(row["trials"]), "p":float(row["p"]),
            "fdr_accepted":bool(row["key"] in accepted),
        } for row in pair_rows}
        out["pairwise_fdr"]={
            "method":"benjamini_hochberg",
            "q":q,
            "tested_pairs":len(pair_rows),
            "base_active_pairs":sum(row["rho"]>0.0 for row in pair_rows),
            "accepted_pairs":len(accepted),
            "suppressed_pairs":sum(row["rho"]>0.0 and row["key"] not in accepted for row in pair_rows),
        }
        out["sources"]=list(canonical)
        out["version"]=version
        if len(cache)>=128:
            cache.pop(next(iter(cache)))
        cache[key]={**out,"pairwise":dict(pairwise),
                    "pairwise_stats":{k:dict(v) for k,v in out.get("pairwise_stats",{}).items()},
                    "sources":list(canonical)}
        return out


    def _procedure_trust_status(self, source_id: str) -> dict:
        """Map alpha.7.1 source calibration into Procedure Cortex trust.

        Procedure dependencies bind to the active reliability regime ID, so a
        real source-regime change invalidates stale procedures. Inference does
        not train reliability.
        """
        status = self.evidence_source_status(source_id)
        if status.get("status") == "disabled":
            raise RuntimeError("adaptive evidence learning is disabled")
        version = status.get("active_regime_id")
        return {
            "reliability": float(status.get("effective_reliability", status["reliability"])),
            "version": int(version) if version is not None else 1,
        }

    def new_evidence_ledger(self, prior, *, max_records: int = 4096) -> EvidenceLedger:
        """Create an explicit ancestry-aware ledger.

        This is complementary to alpha.7.1 hidden-dependency learning: callers
        may supply known ancestry, while the dependency model can still learn
        undeclared statistical dependence from externally resolved trials.
        """
        return EvidenceLedger(prior, max_records=max_records)

    def save_evidence_ledger(self, name: str, ledger: EvidenceLedger) -> None:
        if not isinstance(name, str) or not name.strip() or len(name) > 256:
            raise ValueError("ledger name must be a non-empty string <= 256 chars")
        if not isinstance(ledger, EvidenceLedger):
            raise ValueError("an ASM EvidenceLedger is required")
        self.memory.set_kv("asm_evidence_ledger:" + name.strip(), ledger.export_state())

    def load_evidence_ledger(self, name: str) -> EvidenceLedger:
        if not isinstance(name, str) or not name.strip() or len(name) > 256:
            raise ValueError("ledger name must be a non-empty string <= 256 chars")
        payload = self.memory.get_kv("asm_evidence_ledger:" + name.strip())
        if payload is None:
            raise KeyError(name)
        return EvidenceLedger.from_state(payload)

    def submit_structured_proposal(self, proposal: dict) -> dict:
        """Validate an external proposal without granting it cognitive authority.

        Candidate procedures enter the Procedure Cortex as hypotheses. Other
        proposal kinds remain data requiring ASM/host grounding; requested
        actions are never executed here.
        """
        data = validate_proposal(proposal)
        if data["kind"] == "candidate_procedure":
            payload = data["payload"]
            result = self.procedures.propose(
                payload["mechanism"], payload["program"],
                context=data["context"], provenance=data["source"],
                training_ids=payload["training_ids"],
            )
            return {"proposal": data, "result": result, "executed": False}
        return {"status": "requires_grounding", "proposal": data, "executed": False}

    def observe_procedure(self, mechanism: str, inputs: dict, expected, **evidence) -> dict:
        """Record externally resolved procedure evidence.

        Pass ``auto_induce=True`` to let ASM autonomously propose a bounded
        procedure hypothesis after enough independent, currently trusted roots.
        Promotion still requires later held-out observations.
        """
        return self.procedures.observe(mechanism, inputs, expected, **evidence)

    def observe_procedural_experience(self, mechanism: str, inputs: dict, expected, **evidence) -> dict:
        """Experience-stream procedure learning with autonomous induction enabled."""
        evidence['auto_induce'] = True
        return self.procedures.observe(mechanism, inputs, expected, **evidence)

    def procedure_autonomy_status(self, mechanism: str, *, context: str = "") -> dict:
        return self.procedures.auto_status(mechanism, context=context)

    def procedure_information_query(self, mechanism: str, *, context: str = "", candidate_inputs=None, budget: int = 256) -> dict:
        """Suggest a read-only discriminating observation for competing procedures.

        ASM does not execute the query or train on its own simulated answer; the
        returned input is only a proposal for externally resolved information.
        """
        return self.procedures.information_query(
            mechanism, context=context, candidate_inputs=candidate_inputs, budget=budget
        )

    def induce_procedure(self, mechanism: str, **options) -> dict:
        return self.procedures.induce(mechanism, **options)

    def predict_procedure(self, mechanism: str, inputs: dict, **options) -> dict:
        return self.procedures.predict(mechanism, inputs, **options)

    def procedure_versions(self, mechanism: str, *, context: str = "") -> list[dict]:
        return self.procedures.versions(mechanism, context=context)

    def procedure_families(self) -> list[dict]:
        return self.procedures.families()

    # alpha.7.5-parallel WIP: contextual applicability stays separate from
    # procedure correctness and learns only from externally resolved labels.
    def observe_procedure_route(self, mechanism: str, features: dict, target_context: str, **evidence) -> dict:
        return self.procedures.observe_route(mechanism, features, target_context, **evidence)

    def route_procedure_context(self, mechanism: str, observed_features: dict, **options) -> dict:
        return self.procedures.route(mechanism, observed_features, **options)

    def predict_routed_procedure(self, mechanism: str, procedure_inputs: dict, observed_features: dict, **options) -> dict:
        return self.procedures.predict_routed(mechanism, procedure_inputs, observed_features, **options)

    def plan_procedure_route_queries(self, mechanism: str, observed_features: dict, **options) -> dict:
        return self.procedures.route_query_plan(mechanism, observed_features, **options)

    def procedure_route_evidence_status(self, mechanism: str) -> dict:
        return self.procedures.route_evidence_status(mechanism)

    def observe_evidence_source(
        self,
        source_id: str,
        *,
        observation: str,
        resolved_hypothesis: str,
        supplied_reliability: float | None = None,
        weight: float = 1.0,
        temporal_index: float | int | None = None,
    ) -> dict:
        """Learn one source-reliability datum from externally resolved truth.

        This API deliberately requires ``resolved_hypothesis``. ASM never uses
        its own current posterior as a training label for source reliability.
        """
        if not self.cfg.adaptive_evidence_enabled:
            return {"status": "disabled", "source_id": str(source_id)}
        result = self.adaptive_evidence.observe_resolved(
            source_id,
            observation=observation,
            resolved_hypothesis=resolved_hypothesis,
            supplied_reliability=supplied_reliability,
            weight=weight,
            temporal_index=temporal_index,
        )
        result["status"] = "updated"
        return result

    def evidence_source_status(
        self,
        source_id: str,
        *,
        supplied_reliability: float | None = None,
    ) -> dict:
        if not self.cfg.adaptive_evidence_enabled:
            return {"status": "disabled", "source_id": str(source_id)}
        result = self.adaptive_evidence.status(
            source_id, supplied_reliability=supplied_reliability
        )
        result["status"] = "ok"
        return result

    def adaptive_evidence_likelihoods(
        self,
        source_id: str,
        *,
        observation: str,
        hypotheses: list[str] | tuple[str, ...],
        supplied_reliability: float | None = None,
    ) -> dict[str, float]:
        if not self.cfg.adaptive_evidence_enabled:
            raise RuntimeError("adaptive evidence learning is disabled")
        return self.adaptive_evidence.likelihoods(
            source_id,
            observation=observation,
            hypotheses=hypotheses,
            supplied_reliability=supplied_reliability,
        )

    def observe_evidence_dependency_trial(
        self,
        trial_id: str,
        *,
        resolved_hypothesis: str,
        observations: dict[str, list[str] | tuple[str, ...]],
        temporal_index: int | float | None = None,
    ) -> dict:
        """Learn hidden redundancy from an externally resolved trial.

        Trial boundaries are explicit so ASM does not invent correlation from
        unrelated observations. This API never uses ASM's own posterior as
        ground truth and does not itself update source reliability.
        """
        if not self.cfg.evidence_dependency_enabled:
            return {"status": "disabled", "trial_id": str(trial_id)}
        out = self.evidence_dependency.observe_trial(
            trial_id, resolved_hypothesis=resolved_hypothesis, observations=observations,
            temporal_index=temporal_index,
        )
        out["status"] = "updated"
        return out

    def evidence_dependency_status(self, source_a: str, source_b: str | None = None) -> dict:
        if not self.cfg.evidence_dependency_enabled:
            return {"status": "disabled"}
        if source_b is None or str(source_a).strip() == str(source_b).strip():
            return self.evidence_dependency.self_dependency(source_a)
        return self.evidence_dependency.pair_dependency(source_a, source_b)

    def evidence_dependency_regimes(self, source_a: str, source_b: str | None = None) -> list[dict]:
        if not self.cfg.evidence_dependency_enabled:
            return []
        return self.evidence_dependency.dependency_regimes(source_a, source_b)

    def register_evidence_lineage(
        self,
        evidence_id: str,
        *,
        source_id: str,
        parent_evidence_ids: list[str] | tuple[str, ...] | None = None,
        root_ids: list[str] | tuple[str, ...] | None = None,
    ) -> dict:
        """Register explicit provenance for an evidence item.

        Parent-derived evidence inherits its parents' independent roots. Unknown
        parents fail closed instead of being silently treated as independent.
        """
        if not self.cfg.evidence_lineage_enabled:
            return {"status": "disabled", "evidence_id": str(evidence_id)}
        record = self.evidence_lineage.register(
            evidence_id, source_id=source_id,
            parent_ids=parent_evidence_ids, root_ids=root_ids,
        )
        out = record.as_dict()
        out["status"] = "registered"
        return out

    def evidence_lineage_status(self, evidence_id: str) -> dict:
        if not self.cfg.evidence_lineage_enabled:
            return {"status": "disabled", "evidence_id": str(evidence_id)}
        record = self.evidence_lineage.get(evidence_id)
        if record is None:
            return {"status": "unknown", "evidence_id": str(evidence_id)}
        out = record.as_dict()
        out["status"] = "ok"
        return out

    def update_belief_from_source(
        self,
        belief: dict[str, float] | DiscreteBeliefState,
        *,
        source_id: str,
        observation: str,
        supplied_reliability: float | None = None,
        evidence_id: str | None = None,
        parent_evidence_ids: list[str] | tuple[str, ...] | None = None,
        lineage_root_ids: list[str] | tuple[str, ...] | None = None,
    ) -> DiscreteBeliefState:
        """Apply one observation using learned reliability and optional provenance.

        Alpha.6.2 preserves alpha.6.1 behavior when no ``evidence_id`` is
        supplied. With explicit lineage, only the fraction of independent roots
        not already present in the belief contributes fresh likelihood weight.
        Exact copies therefore contribute zero additional confidence.

        Inference still does not train source reliability; only
        :meth:`observe_evidence_source` can do that after external resolution.
        """
        state = belief if isinstance(belief, DiscreteBeliefState) else DiscreteBeliefState.from_mapping(belief)
        likes = self.adaptive_evidence_likelihoods(
            source_id,
            observation=observation,
            hypotheses=state.hypothesis_names(),
            supplied_reliability=supplied_reliability,
        )
        if evidence_id is None:
            if parent_evidence_ids or lineage_root_ids:
                raise ValueError("lineage metadata requires evidence_id")
            return state.update(likes)
        if not self.cfg.evidence_lineage_enabled:
            return state.update(likes)
        record = self.evidence_lineage.register(
            evidence_id, source_id=source_id,
            parent_ids=parent_evidence_ids, root_ids=lineage_root_ids,
        )
        combined_roots = set(state.evidence_roots()) | set(record.roots)
        if len(combined_roots) > int(self.cfg.evidence_lineage_max_roots_per_belief):
            raise RuntimeError("belief evidence-lineage root capacity reached")
        novelty = self.evidence_lineage.novelty(state.evidence_roots(), record.roots)
        return state.update_weighted(
            likes, evidence_weight=novelty, evidence_roots=record.roots,
        )

    def update_belief_from_evidence_batch(
        self,
        belief: dict[str, float] | DiscreteBeliefState,
        *,
        evidence: list[dict] | tuple[dict, ...],
    ) -> DiscreteBeliefState:
        """Fuse a resolved-group-shaped evidence batch with learned redundancy.

        Hidden dependency is a property of a *set* of observations. Alpha.7
        therefore uses symmetric batch tempering instead of order-dependent
        sequential discounting. The learned positive-correlation matrix yields
        an effective sample size n_eff = n^2 / sum(R); every likelihood in the
        batch receives the same scale n_eff/n. With no learned dependency the
        scale is exactly 1 and this is ordinary Bayesian fusion.

        Items require ``source_id`` and ``observation``; ``supplied_reliability``
        is optional. Explicit lineage remains handled by update_belief_from_source
        and is intentionally not mixed into this first hidden-dependency API.
        """
        if not isinstance(evidence, (list, tuple)) or not evidence:
            raise ValueError("evidence batch must be a non-empty list/tuple")
        if len(evidence) > int(self.cfg.evidence_dependency_max_batch_items):
            raise RuntimeError("evidence dependency inference batch capacity reached")
        state = belief if isinstance(belief, DiscreteBeliefState) else DiscreteBeliefState.from_mapping(belief)
        rows: list[tuple[str, str, float | None, dict[str, float]]] = []
        for item in evidence:
            if not isinstance(item, dict):
                raise ValueError("each evidence batch item must be a mapping")
            source = str(item.get("source_id", "")).strip()
            observation = str(item.get("observation", "")).strip()
            if not source or not observation:
                raise ValueError("batch evidence requires non-empty source_id and observation")
            if any(k in item for k in ("evidence_id", "parent_evidence_ids", "lineage_root_ids")):
                raise ValueError("explicit lineage is not supported inside hidden-dependency batch fusion")
            supplied = item.get("supplied_reliability")
            likes = self.adaptive_evidence_likelihoods(
                source, observation=observation, hypotheses=state.hypothesis_names(),
                supplied_reliability=supplied,
            )
            rows.append((source, observation, supplied, likes))

        n = len(rows)
        dep = {"raw_count": float(n), "effective_count": float(n), "scale": 1.0, "correlation_denominator": float(n)}
        if self.cfg.evidence_dependency_enabled and n > 1:
            dep = self.evidence_dependency.effective_batch(row[0] for row in rows)
        scale = float(dep["scale"])
        for _, _, _, likes in rows:
            state = state.update_weighted(likes, evidence_weight=scale)
        # Expose bounded diagnostics without mutating the belief schema.
        self._last_dependency_batch = {
            "raw_evidence_count": int(n),
            "effective_evidence_count": float(dep["effective_count"]),
            "evidence_scale": float(scale),
            "correlation_denominator": float(dep["correlation_denominator"]),
            "dependency_model_version": int(self.evidence_dependency.version),
        }
        return state

    def last_evidence_dependency_batch(self) -> dict:
        return dict(getattr(self, "_last_dependency_batch", {}))

    def plan_world_actions_belief(
        self,
        mechanism_type: str,
        *,
        entity_id: str,
        initial_state: dict,
        actions: list[str] | tuple[str, ...],
        goal: dict,
        initial_belief: dict[str, float] | DiscreteBeliefState,
        avoid: dict | None = None,
        likelihood_provider=None,
        evidence_source_id: str | None = None,
        supplied_reliability: float | None = None,
        action_costs: dict[str, float] | None = None,
        neighborhood: dict | None = None,
        dt: float = 1.0,
        horizon: int | None = None,
    ) -> dict:
        """Plan under partial observability using a compact latent belief state.

        ``likelihood_provider`` is optional and receives
        ``(belief, before_state, action, observation, predicted_state)``. It may
        return P(observation|hypothesis) for each latent hypothesis.

        Alpha.6 can instead receive ``evidence_source_id`` plus an optional
        supplied reliability. For categorical sensor outcomes whose observation
        names match hypothesis names, the planner then uses that source's learned
        reliability. Simulated branches never train the source model.
        """
        if self.belief_planner is None:
            return {
                "status": "disabled", "simulated_only": True,
                "probabilistic": True, "belief_state_planning": True, "best": None,
            }
        if likelihood_provider is not None and evidence_source_id is not None:
            raise ValueError("provide likelihood_provider or evidence_source_id, not both")
        if evidence_source_id is not None:
            if not self.cfg.adaptive_evidence_enabled:
                raise RuntimeError("adaptive evidence learning is disabled")
            source_id = str(evidence_source_id)
            def likelihood_provider(belief, before_state, action, observation, predicted_state):
                obs = str(observation)
                hypotheses = belief.hypothesis_names()
                # Alpha.6's initial symmetric source model only calibrates
                # categorical observations that name a latent hypothesis. Other
                # actions keep their explicit likelihood rows unchanged.
                if obs not in hypotheses:
                    return None
                return self.adaptive_evidence.likelihoods(
                    source_id,
                    observation=obs,
                    hypotheses=hypotheses,
                    supplied_reliability=supplied_reliability,
                )
        result = self.belief_planner.plan(
            mechanism_type, entity_id=entity_id, initial_state=initial_state,
            actions=actions, goal=StateGoal(target=goal, avoid=dict(avoid or {})),
            initial_belief=initial_belief, likelihood_provider=likelihood_provider,
            likelihood_provider_overrides=(evidence_source_id is not None),
            action_costs=action_costs, neighborhood=neighborhood, dt=dt, horizon=horizon,
        )
        if evidence_source_id is not None:
            result["evidence_source_id"] = str(evidence_source_id)
            result["evidence_source_status"] = self.adaptive_evidence.status(
                str(evidence_source_id), supplied_reliability=supplied_reliability
            )
        return result

    def learn_world_transition(
        self,
        mechanism_type: str,
        *,
        entity_id: str,
        state: dict,
        action: str,
        after_state: dict,
        neighborhood: dict | None = None,
        dt: float = 1.0,
    ) -> dict:
        """Learn from one observed local transition and persist the mechanism."""
        if self.transition_mechanisms is None:
            return {"learned": False, "reason": "transition_mechanisms_disabled"}
        return self.transition_mechanisms.observe(
            mechanism_type,
            entity_id=entity_id,
            state=state,
            action=action,
            after_state=after_state,
            neighborhood=neighborhood,
            dt=dt,
        )

    def _language_embedding_concepts(self, read: LanguageReadResult, *, allow_social: bool = False) -> Dict[str, float]:
        if not read.metadata.get("learned_reader") or not read.embedding:
            return {}
        topk = max(0, int(self.cfg.language_core_embedding_injection_topk))
        gain = max(0.0, float(self.cfg.language_core_embedding_injection_gain))
        ranked = sorted(
            enumerate(read.embedding),
            key=lambda item: abs(float(item[1])),
            reverse=True,
        )[:topk]
        out: Dict[str, float] = {}
        for idx, value in ranked:
            value = float(value)
            if abs(value) < 1e-6:
                continue
            sign = "POS" if value >= 0 else "NEG"
            out[f"LCORE:EMB:{idx}:{sign}"] = min(1.0, abs(value) * gain)
        social_p = float(read.metadata.get("social_probability", 0.0) or 0.0)
        if allow_social and social_p >= self.cfg.consolidation_social_threshold:
            out["LCORE:INTENT:SOCIAL"] = min(1.0, social_p)
        else:
            intent = str(read.metadata.get("intent", "")).strip()
            confidence = float(read.metadata.get("intent_confidence", 0.0) or 0.0)
            if intent and intent != "other" and confidence > 0.0:
                out[f"LCORE:INTENT:{intent.upper()}"] = min(1.0, confidence)
        return out

    @staticmethod
    def _semantic_tag(text: str) -> str:
        if MentalLanguagePerception.parse_nested(text, max_order=3):
            return "nested_belief"
        if MentalLanguagePerception.parse_direct_belief(text):
            return "belief"
        if MentalLanguagePerception.parse_drive(text):
            return "drive"
        if MentalLanguagePerception.parse_self_outcome(text):
            return "self_outcome"
        return "other"

    def _backfill_semantic_memory(self, limit: int = 4096) -> int:
        added = 0
        for event_id, text in self.semantic_memory.missing_events(limit=limit):
            try:
                read = self.language_core.read(text)
                if read.embedding:
                    self.semantic_memory.add(
                        event_id,
                        read.embedding,
                        tag=self._semantic_tag(text),
                    )
                    added += 1
            except Exception:
                continue
        return added

    def _backfill_event_memory(self, limit: int = 8192) -> int:
        """Build alpha.7 structured event records for older episodic rows.

        Backfill must not masquerade as live semantic-cortex activity, so the
        runtime health counters are restored after historical indexing.
        """
        added = 0
        counters = (
            self.semantic_cortex.events_seen,
            self.semantic_cortex.conflicts_blocked,
            self.semantic_cortex.hypotheticals_abstained,
        )
        try:
            for event_id, text in self.event_memory.missing_events(limit=limit):
                try:
                    decision = self.semantic_cortex.interpret(text, {"_accepted": []})
                    self.event_memory.add(event_id, decision, raw_text=text)
                    added += 1
                except Exception:
                    continue
        finally:
            (
                self.semantic_cortex.events_seen,
                self.semantic_cortex.conflicts_blocked,
                self.semantic_cortex.hypotheticals_abstained,
            ) = counters
        return added

    def _hybrid_recall(
        self,
        observed: Dict[str, float],
        embedding,
        limit: int,
        *,
        use_semantic: bool,
        semantic_tag: str | None = None,
        text: str = "",
        semantic_decision=None,
    ) -> list[dict]:
        retrieval_observed = {
            k: v for k, v in observed.items()
            if not (
                str(k).startswith("ATTEND:")
                or str(k).startswith("SELFSTATE:")
                or str(k).startswith("SELF:CAPABILITY:")
                or str(k).startswith("LCORE:EMB:")
            )
        }
        lexical = self.memory.recall(retrieval_observed, limit=max(limit * 2, limit))
        semantic = (
            self.semantic_memory.recall(
                embedding,
                limit=max(limit * 2, limit),
                tag=semantic_tag,
            )
            if self.cfg.semantic_memory_enabled and embedding and use_semantic
            else []
        )
        structured = self.event_memory.recall(
            text, decision=semantic_decision, limit=max(limit * 3, limit)
        ) if text else []

        merged = {}
        semantic_weight = max(0.0, min(1.0, float(self.cfg.semantic_memory_weight)))
        legacy_scale = 0.45 if structured else 1.0
        event_scale = 0.55 if structured else 0.0
        for row in lexical:
            rec = dict(row)
            rec["lexical_relevance"] = float(row["relevance"])
            rec["semantic_relevance"] = 0.0
            rec["structured_relevance"] = 0.0
            rec["relevance"] = legacy_scale * (1.0 - semantic_weight) * float(row["relevance"])
            rec["retrieval_source"] = "lexical"
            merged[row["id"]] = rec
        for row in semantic:
            sem = float(row["relevance"])
            contribution = legacy_scale * semantic_weight * sem
            if row["id"] in merged:
                rec = merged[row["id"]]
                rec["semantic_relevance"] = sem
                rec["relevance"] += contribution
                rec["retrieval_source"] = "hybrid"
                if "semantic_similarity" in row:
                    rec["semantic_similarity"] = row["semantic_similarity"]
            else:
                rec = dict(row)
                rec["lexical_relevance"] = 0.0
                rec["semantic_relevance"] = sem
                rec["structured_relevance"] = 0.0
                rec["relevance"] = contribution
                merged[row["id"]] = rec
        for row in structured:
            ev = float(row.get("event_relevance", row.get("relevance", 0.0)))
            contribution = event_scale * ev if event_scale else ev
            if row["id"] in merged:
                rec = merged[row["id"]]
                rec["structured_relevance"] = ev
                rec["relevance"] += contribution
                rec["event_type"] = row.get("event_type")
                rec["epistemic"] = row.get("epistemic")
                rec["agents"] = row.get("agents", [])
                rec["proposition_surface"] = row.get("proposition_surface", "")
                rec["proposition_canonical"] = row.get("proposition_canonical", "")
                rec["truth"] = row.get("truth")
                rec["matched_by"] = row.get("matched_by", [])
                rec["retrieval_source"] = "hybrid_event"
            else:
                rec = dict(row)
                rec["lexical_relevance"] = 0.0
                rec["semantic_relevance"] = 0.0
                rec["structured_relevance"] = ev
                rec["relevance"] = contribution
                merged[row["id"]] = rec
        rows = sorted(merged.values(), key=lambda x: x["relevance"], reverse=True)
        return rows[:limit]

    def process(self, text: str, *, training: bool = False) -> dict:
        self.event_count += 1
        self.field.begin_event()

        language_read = self._read_language(text)
        language_events = self._consume_language_proposals(language_read)
        semantic_decision = self.semantic_cortex.interpret(text, language_events)
        semantic_type = semantic_decision.primary.event_type

        learned_rule = None

        # v0.1.1.8: conservative hand-written parsing remains the bootstrap
        # teacher, but unsupported wording can now be interpreted by a learned
        # relation-perception layer. The query itself is not used to train the
        # perception model until after inference has completed.
        bootstrap_frame = self.structural_parser.parse(text)
        perception_decision = None
        post_observation_perception = None
        if bootstrap_frame.supported:
            frame = bootstrap_frame
        else:
            perception_decision = self.perception.infer(text)
            frame = (
                perception_decision.frame
                if perception_decision.frame.supported
                else bootstrap_frame
            )

        # Independent machine ontology. This query happens before the current
        # observation is learned, preventing same-event leakage. Named parser
        # relations remain available, but anonymous relations can represent
        # relation types the programmer never enumerated.
        discovered_decision = self.relation_discovery.infer_text(text)
        if not frame.supported and discovered_decision.frame.supported:
            frame = discovered_decision.frame

        # Keep the open-language perception layer's result separate from the
        # anonymous relation ontology. This preserves v0.1.1.8's semantics and
        # lets us measure whether wording was understood by perception or only
        # by the self-discovered structural fallback.
        perception_source = (
            "bootstrap"
            if bootstrap_frame.supported
            else (
                perception_decision.source
                if perception_decision is not None
                else "abstain"
            )
        )

        machine_relation_ids = list(discovered_decision.relation_ids)

        # Existing self-created concepts may activate before the current event
        # updates them, preventing query/training leakage.
        latent_features = self.emergent.frame_features(frame)
        latent_features.extend(f"MREL:{rid}" for rid in machine_relation_ids)

        # Nested mental models are parsed first so a sentence like
        # "Alice believes Bob believes X" is not flattened into a single
        # first-order proposition.
        # Alpha.6: one language utterance receives one primary semantic type
        # before long-term mental state is updated.  This prevents a sentence
        # such as "Oren expects X" from independently becoming both an
        # expectation and a belief through separate legacy parsers.
        allow_semantic_write = semantic_decision.primary.persistent_eligible

        nested_event = language_events.get("nested_belief")
        if nested_event is None and allow_semantic_write and semantic_type == "nested_belief":
            nested_event = self.hierarchical_minds.parse_text(
                text,
                self.event_count,
            )

        mind_event = language_events.get("belief")
        if mind_event is None and allow_semantic_write and semantic_type in {"belief", "observation"}:
            mind_event = self.minds.observe_text(
                text,
                self.event_count,
            )

        if mind_event:
            latent_features.append(
                f"MIND:{mind_event['type'].upper()}"
            )
        if nested_event:
            latent_features.append(
                f"MIND:NESTED_ORDER:{nested_event['order']}"
            )

        drive_event = language_events.get("drive")
        if drive_event is None and allow_semantic_write and semantic_type in {"goal", "fear", "expectation"}:
            drive_event = self.appraisal.observe_drive(
                text,
                self.event_count,
            )
        if drive_event:
            latent_features.append(
                f"MIND:DRIVE:{drive_event['kind'].upper()}"
            )

        active_holder = None
        if mind_event and mind_event.get("holder") != "__world__":
            active_holder = mind_event.get("holder")
        elif drive_event:
            active_holder = drive_event.get("holder")

        self_language_outcome = language_events.get("self_outcome")
        if self_language_outcome is None and allow_semantic_write and semantic_type == "self_outcome":
            self_language_outcome = self.self_model.observe_language_outcome(
                text,
                self.event_count,
            )
        if self_language_outcome:
            latent_features.append("SELF:LANGUAGE_OUTCOME")
            outcome = self_language_outcome.get("outcome", {})
            latent_features.append(
                f"SELF:OUTCOME:{'SUCCESS' if outcome.get('success') else 'FAILURE'}"
            )
            latent_features.append(
                f"SELF:STRATEGY:{outcome.get('strategy', 'unknown')}"
            )

        structured_event = False if semantic_type == "question" else bool(
            (semantic_type != "other" and semantic_decision.primary.persistent_eligible)
            or language_events.get("_accepted")
            or frame.supported
            or discovered_decision.frame.supported
            or nested_event
            or mind_event
            or drive_event
            or self_language_outcome
        )
        consolidation = self.consolidation.decide(
            text,
            training=training,
            structured=structured_event,
            social_probability=float(language_read.metadata.get("social_probability", 0.0) or 0.0),
            intent=str(language_read.metadata.get("intent", "other")),
            intent_confidence=float(language_read.metadata.get("intent_confidence", 0.0) or 0.0),
            token_count=len(self.encoder.tokenize(text)),
        )
        # Epistemic safety overrides generic training/consolidation. Questions
        # and explicitly hypothetical/abstained semantic events are not durable
        # experiences and must not become long-term memory by accident.
        if semantic_type == "question":
            consolidation = ConsolidationDecision(
                False, "transient", "semantic_question",
                float(language_read.metadata.get("social_probability", 0.0) or 0.0), False,
            )
        elif semantic_decision.abstained:
            consolidation = ConsolidationDecision(
                False, "transient", "semantic_abstain",
                float(language_read.metadata.get("social_probability", 0.0) or 0.0), False,
            )
        persistent = consolidation.persist
        if persistent:
            learned_rule = self.generalizer.learn_example(text)

        appraisal_features = (
            self.appraisal.appraisal_features(active_holder)
            if active_holder else []
        )
        latent_features.extend(appraisal_features)

        latent_active = self.emergent.activate(latent_features)

        explicit_emotion = (
            self.emotions.observe_labeled(
                text,
                self.event_count,
                latent_active.keys(),
            )
            if persistent else None
        )
        appraisal_emotion_learning = None
        if explicit_emotion:
            latent_features.append(
                f"EMOTION:{explicit_emotion['label']}"
            )
            appraisal_emotion_learning = self.appraisal.learn_emotion_from_agent(
                explicit_emotion["agent"],
                explicit_emotion["label"],
                self.event_count,
            )

        emotion_inference = []
        appraisal_inference = []
        if explicit_emotion is None:
            emotion_inference = self.emotions.infer(
                text,
                latent_active.keys(),
                limit=3,
            )
            if active_holder:
                appraisal_inference = self.appraisal.infer_emotion_for_agent(
                    active_holder,
                    limit=3,
                )

        observed = self.encoder.encode(text, semantic_expand=True)

        # Alpha.6: typed semantic events enter the same sparse seismic field as
        # lexical, recurrent and memory concepts.  Language is now converted
        # into an explicit epistemic event before downstream cognition.
        for concept_id, score in self.semantic_cortex.workspace_features(semantic_decision).items():
            observed[concept_id] = max(observed.get(concept_id, 0.0), score)

        # Alpha.2: learned recurrent state now enters ASM's sparse seismic field.
        # This makes the reader computationally consequential even when no
        # structured proposal crosses the confidence gate.
        for concept_id, score in self._language_embedding_concepts(
            language_read,
            allow_social=not structured_event,
        ).items():
            observed[concept_id] = max(observed.get(concept_id, 0.0), score)

        # Seismic activation now includes internal concepts and mind-state
        # changes. They participate in the same sparse field as other concepts.
        for concept_id, score in latent_active.items():
            observed[concept_id] = max(
                observed.get(concept_id, 0.0),
                self.cfg.latent_activation_gain * score,
            )

        for detail in discovered_decision.details:
            rid = detail["relation_id"]
            observed[f"MREL:{rid}"] = max(
                observed.get(f"MREL:{rid}", 0.0),
                float(detail.get("score", discovered_decision.confidence)),
            )

        for concept_id, score in self.minds.concept_for_event(mind_event).items():
            observed[concept_id] = max(
                observed.get(concept_id, 0.0),
                score,
            )

        for concept_id, score in self.hierarchical_minds.concepts_for_event(nested_event).items():
            observed[concept_id] = max(
                observed.get(concept_id, 0.0),
                score,
            )

        # ASM's own prior internal state and attention feed back into the next
        # seismic event. This makes self-state computationally consequential.
        for concept_id, score in self.self_model.concepts().items():
            observed[concept_id] = max(
                observed.get(concept_id, 0.0),
                score,
            )
        for concept_id, score in self.attention.concepts().items():
            observed[concept_id] = max(
                observed.get(concept_id, 0.0),
                score,
            )

        if active_holder:
            for concept_id, score in self.appraisal.concepts_for_agent(active_holder).items():
                observed[concept_id] = max(
                    observed.get(concept_id, 0.0),
                    score,
                )

        if explicit_emotion:
            observed[
                f"MIND:EMOTION:{explicit_emotion['label']}"
            ] = 1.0
        elif appraisal_inference:
            best_emotion = appraisal_inference[0]
            observed[
                f"MIND:EMOTION_APPRAISAL:{best_emotion['emotion']}"
            ] = 0.80 * best_emotion["score"]
        elif emotion_inference:
            best_emotion = emotion_inference[0]
            observed[
                f"MIND:EMOTION_HYP:{best_emotion['emotion']}"
            ] = 0.65 * best_emotion["score"]

        classic_prediction = self.predictor.predict(self.previous_workspace)
        local_prediction = self.predictive_coder.predict(self.previous_workspace)

        prediction = dict(classic_prediction)
        for key, value in local_prediction.items():
            prediction[key] = max(
                prediction.get(key, 0.0),
                value,
            )

        surprise = self.predictor.surprise(
            prediction,
            observed,
        )

        known_fraction = (
            sum(1 for c in observed if c in self.field.nodes)
            / max(1, len(observed))
        )
        novelty = 1.0 - known_fraction
        magnitude = max(
            0.0,
            min(1.0, 0.68 * surprise + 0.32 * novelty),
        )

        recalled = []
        if semantic_type == "nested_belief" or (nested_event and int(nested_event.get("order", 0)) > 1):
            semantic_tag = "nested_belief"
        elif semantic_type in {"belief", "observation"} or mind_event:
            semantic_tag = "belief"
        elif semantic_type in {"goal", "fear", "expectation"} or drive_event:
            semantic_tag = "drive"
        elif semantic_type == "self_outcome" or self_language_outcome:
            semantic_tag = "self_outcome"
        else:
            semantic_tag = self._semantic_tag(text)

        semantic_recall_allowed = semantic_tag != "other"
        if not training and (persistent or semantic_type == "question"):
            recalled = self._hybrid_recall(
                observed,
                language_read.embedding,
                limit=self.cfg.memory_recall_limit,
                use_semantic=semantic_recall_allowed,
                semantic_tag=semantic_tag if semantic_recall_allowed else None,
                text=text,
                semantic_decision=semantic_decision,
            )

        self.field.inject(
            observed,
            gain=1.0 + 0.35 * magnitude,
            event_id=self.event_count,
            persistent=persistent,
        )

        if recalled:
            recall_impulse: Dict[str, float] = {}
            for item in recalled:
                gain = (
                    self.cfg.recall_injection_gain
                    * min(1.0, item["relevance"] * 3.0)
                )
                for concept, strength in item["concepts"].items():
                    recall_impulse[concept] = max(
                        recall_impulse.get(concept, 0.0),
                        float(strength) * gain,
                    )
            self.field.inject(
                recall_impulse,
                event_id=self.event_count,
                persistent=persistent,
            )

        if not training:
            goal_impulse = {
                k: v * self.cfg.goal_boost
                for k, v in self.goals.concepts().items()
            }
            if goal_impulse:
                self.field.inject(
                    goal_impulse,
                    event_id=self.event_count,
                    persistent=persistent,
                )

        self.field.propagate(event_id=self.event_count, persistent=persistent)
        workspace = self.field.workspace()

        if persistent:
            self.field.learn_coactivation(workspace)
            self.field.learn_temporal(
                self.previous_workspace,
                workspace,
            )
            self.predictor.learn(
                self.previous_workspace,
                workspace,
            )
            self.last_predictive_error = self.predictive_coder.learn(
                self.previous_workspace,
                workspace,
            )
            self_state = self.self_model.observe_prediction_state(
                surprise=surprise,
                predictive_error=self.last_predictive_error,
                novelty=novelty,
                event_id=self.event_count,
            )
        else:
            self.last_predictive_error = 0.0
            self_state = self.self_model.internal_state()
        attention_state = self.attention.update(
            workspace,
            surprise=surprise,
            magnitude=magnitude,
            event_id=self.event_count,
        )

        if persistent:
            # Learn structural schemas after parsing. This is independent of the
            # lexical graph, so relation topology can transfer across domains.
            self.structural_memory.observe(frame)

            # Stable parser output is high-quality supervision for open perception.
            # Learned parses are retained only above the pseudo-learning threshold.
            if bootstrap_frame.supported:
                self.perception.observe_bootstrap(text, bootstrap_frame)
            elif perception_decision is not None and frame.supported:
                self.perception.learn_decision(perception_decision)

            # Distributional semantics learns from every observation, including
            # sentences whose relation could not yet be interpreted.
            self.encoder.learn_semantics(text)

            # One-experience lexical induction: if an unfamiliar relation phrase was
            # not interpretable before this observation, re-evaluate it only AFTER
            # the observation has entered lexical/semantic memory. A strong contextual
            # interpretation can then be stored for future events, without changing
            # the meaning used to reason about the current event retroactively.
            if (
                not bootstrap_frame.supported
                and (
                    perception_decision is None
                    or not perception_decision.frame.supported
                )
            ):
                post_observation_perception = self.perception.infer(text)
                if post_observation_perception.frame.supported:
                    self.perception.learn_decision(post_observation_perception)

            # Learn the machine ontology only after the current interpretation was
            # fixed. This can create a new anonymous relation or update an existing
            # one. It receives raw role/connector/context evidence, not human labels.
            relation_observations = self.relation_discovery.observe_text(
                text,
                self.event_count,
            )
            observed_relation_ids = {
                row["relation_id"] for row in relation_observations
            }
            relation_feedback = []
            for rid in machine_relation_ids:
                relation_feedback.append(
                    self.relation_discovery.feedback(
                        rid,
                        success=rid in observed_relation_ids,
                        prediction_error=(
                            max(0.0, 1.0 - discovered_decision.confidence)
                            if rid in observed_relation_ids else 1.0
                        ),
                    )
                )

            formed_concept = self.emergent.observe(
                latent_features,
                self.event_count,
            )

            event_id = self.memory.add_event(
                text=text,
                concepts=observed,
                workspace=workspace,
                surprise=surprise,
                magnitude=magnitude,
            )
            if self.cfg.semantic_memory_enabled and language_read.embedding:
                self.semantic_memory.add(
                    event_id,
                    language_read.embedding,
                    tag=semantic_tag,
                )
            event_memory_update = self.event_memory.add(
                event_id, semantic_decision, raw_text=text
            )
            world_model_update = (
                self.world_model.observe(event_id, semantic_decision, raw_text=text)
                if self.world_model is not None else None
            )
        else:
            relation_observations = []
            relation_feedback = []
            formed_concept = None
            event_id = None
            event_memory_update = None
            world_model_update = None

        self.previous_workspace = workspace

        p1 = self.predictor.predict(workspace)
        p2 = self.predictive_coder.predict(workspace)
        merged = dict(p1)
        for key, value in p2.items():
            merged[key] = max(
                merged.get(key, 0.0),
                value,
            )
        self.last_prediction = merged

        if self.event_count % self.cfg.prune_every_events == 0:
            self.field.prune()
            self.predictor.prune()
            self.predictive_coder.prune()

        if (
            not training
            and self.event_count % self.cfg.snapshot_every_events == 0
        ):
            self.save()

        if training:
            decision = {
                "type": "TRAIN",
                "confidence": 1.0,
                "utterance": "",
            }
        else:
            decision = self.actions.choose(
                text=text,
                observed=observed,
                workspace=workspace,
                recalled=recalled,
                predicted_next=self.last_prediction,
                surprise=surprise,
                consolidation=consolidation.as_dict(),
            )

        return {
            "event_id": event_id,
            "magnitude": magnitude,
            "surprise": surprise,
            "predictive_error": self.last_predictive_error,
            "workspace": workspace,
            "predicted_next": sorted(
                self.last_prediction.items(),
                key=lambda kv: kv[1],
                reverse=True,
            )[:10],
            "recalled": [
                {
                    "id": item["id"],
                    "text": item["text"],
                    "relevance": item["relevance"],
                    "retrieval_source": item.get("retrieval_source", "lexical"),
                    "semantic_similarity": item.get("semantic_similarity"),
                    "structured_relevance": item.get("structured_relevance"),
                    "event_type": item.get("event_type"),
                    "epistemic": item.get("epistemic"),
                    "agents": item.get("agents"),
                    "proposition_surface": item.get("proposition_surface"),
                    "truth": item.get("truth"),
                    "matched_by": item.get("matched_by"),
                }
                for item in recalled
            ],
            "relation_discovery": {
                "source": discovered_decision.source,
                "relation_ids": machine_relation_ids,
                "confidence": discovered_decision.confidence,
                "margin": discovered_decision.margin,
                "observations": relation_observations,
                "feedback": relation_feedback,
            },
            "perception": {
                "source": perception_source,
                "confidence": (
                    perception_decision.confidence
                    if perception_decision is not None else 1.0
                ),
                "margin": (
                    perception_decision.margin
                    if perception_decision is not None else 1.0
                ),
                "learned_after_observation": bool(
                    post_observation_perception is not None
                    and post_observation_perception.frame.supported
                ),
                "post_observation_signature": (
                    list(post_observation_perception.frame.signature())
                    if post_observation_perception is not None
                    and post_observation_perception.frame.supported
                    else []
                ),
            },
            "structure": {
                "signature": list(frame.signature()),
                "supported": frame.supported,
                "warnings": frame.warnings,
                "cues": frame.cues,
                "relations": [
                    {**asdict(r), "key": r.key}
                    for r in frame.relations
                ],
            },
            "latent_concepts": [
                {
                    "id": cid,
                    "score": score,
                }
                for cid, score in sorted(
                    latent_active.items(),
                    key=lambda kv: kv[1],
                    reverse=True,
                )
            ],
            "formed_concept": (
                {
                    "id": formed_concept.concept_id,
                    "score": formed_concept.score,
                    "support": formed_concept.support,
                    "promoted": formed_concept.promoted,
                }
                if formed_concept else None
            ),
            "semantic_event": semantic_decision.as_dict(),
            "semantic_event_memory_update": event_memory_update,
            "world_model_update": world_model_update,
            "mind_event": mind_event,
            "nested_belief_event": nested_event,
            "self_state": self_state,
            "self_language_outcome": self_language_outcome,
            "consolidation": consolidation.as_dict(),
            "language_core": {
                **language_read.as_dict(include_embedding=False),
                "accepted": language_events.get("_accepted", []),
                "rejected": language_events.get("_rejected", []),
            },
            "attention": attention_state,
            "drive_event": drive_event,
            "appraisal_features": appraisal_features,
            "explicit_emotion": explicit_emotion,
            "appraisal_emotion_learning": appraisal_emotion_learning,
            "emotion_inference": emotion_inference,
            "appraisal_inference": appraisal_inference,
            "learned_rule": learned_rule,
            "decision": decision,
            "stats": self.stats(),
        }

    def expand_problem(self, text: str) -> dict:
        """
        Analyze a new problem without learning from it first.

        This prevents the benchmark/query itself from leaking into the learned
        structural memory before analogy retrieval.
        """
        bootstrap_frame = self.structural_parser.parse(text)
        discovery = self.relation_discovery.infer_text(text)
        if bootstrap_frame.supported:
            frame = bootstrap_frame
            perception_info = {"source": "bootstrap", "confidence": 1.0, "margin": 1.0}
        else:
            decision = self.perception.infer(text)
            if decision.frame.supported:
                frame = decision.frame
                perception_info = {
                    "source": decision.source,
                    "confidence": decision.confidence,
                    "margin": decision.margin,
                }
            elif discovery.frame.supported:
                frame = discovery.frame
                perception_info = {
                    "source": "self_discovered",
                    "confidence": discovery.confidence,
                    "margin": discovery.margin,
                }
            else:
                frame = bootstrap_frame
                perception_info = {
                    "source": "abstain",
                    "confidence": 0.0,
                    "margin": 0.0,
                }
        encoded = self.encoder.encode(
            text,
            semantic_expand=True,
        )
        latent_features = self.emergent.frame_features(frame)
        latent_active = self.emergent.activate(latent_features)
        for concept_id, score in latent_active.items():
            encoded[concept_id] = max(
                encoded.get(concept_id, 0.0),
                self.cfg.latent_activation_gain * score,
            )

        result = self.expander.expand(
            frame,
            encoded,
            self.field.edges,
        )
        result["perception"] = perception_info
        result["self_discovered_relations"] = {
            "relation_ids": discovery.relation_ids,
            "confidence": discovery.confidence,
            "margin": discovery.margin,
            "details": discovery.details,
        }
        result["latent_concepts"] = [
            {"id": cid, "score": score}
            for cid, score in sorted(
                latent_active.items(),
                key=lambda kv: kv[1],
                reverse=True,
            )
        ]
        return result

    def belief(self, holder: str, proposition: str) -> dict:
        """Return one holder's current belief state for a proposition."""
        return self.minds.query(holder, proposition)

    def compare_belief(self, holder: str, proposition: str) -> dict:
        """Keep objective world evidence separate from another agent's belief."""
        return self.minds.compare_world_and_agent(holder, proposition)

    def infer_emotion(self, text: str, limit: int = 5) -> list[dict]:
        """Infer learned emotion labels without modifying the model."""
        frame = self.structural_parser.parse(text)
        latent = self.emergent.activate(
            self.emergent.frame_features(frame)
        )
        return self.emotions.infer(
            text,
            latent.keys(),
            limit=limit,
        )

    def infer_agent_emotion(
        self,
        holder: str,
        text: str | None = None,
        limit: int = 5,
    ) -> list[dict]:
        """
        Infer emotion from persistent goals/fears/beliefs, optionally merging
        direct text-prototype evidence.
        """
        appraisal = self.appraisal.infer_emotion_for_agent(holder, limit=limit)
        direct = self.infer_emotion(text, limit=limit) if text else []

        merged = {}
        for item in direct:
            rec = dict(item)
            rec["source"] = "direct_context"
            merged[item["emotion"]] = rec

        for item in appraisal:
            label = item["emotion"]
            if label not in merged or item["score"] > merged[label]["score"]:
                merged[label] = dict(item)

        rows = list(merged.values())
        rows.sort(key=lambda x: (-x["score"], x["emotion"]))
        return rows[:limit]

    def appraisal_state(self, holder: str) -> dict:
        return {
            "holder": holder.lower(),
            "drives": list(self.appraisal.drives.get(holder.lower(), [])),
            "features": self.appraisal.appraisal_features(holder),
            "emotion_hypotheses": self.appraisal.infer_emotion_for_agent(holder),
        }

    def latent_concepts(self) -> list[dict]:
        """Inspect promoted internal concepts. Names are machine IDs, not labels."""
        return self.emergent.promoted()

    def parse_open(self, text: str) -> dict:
        """Parse text without learning from the query."""
        bootstrap = self.structural_parser.parse(text)
        discovery = self.relation_discovery.infer_text(text)
        if bootstrap.supported:
            frame = bootstrap
            source = "bootstrap"
            confidence = 1.0
            margin = 1.0
            details = []
        else:
            decision = self.perception.infer(text)
            if decision.frame.supported:
                frame = decision.frame
                source = decision.source
                confidence = decision.confidence
                margin = decision.margin
                details = decision.details
            elif discovery.frame.supported:
                frame = discovery.frame
                source = "self_discovered"
                confidence = discovery.confidence
                margin = discovery.margin
                details = discovery.details
            else:
                frame = decision.frame
                source = "abstain"
                confidence = 0.0
                margin = 0.0
                details = decision.details
        return {
            "source": source,
            "confidence": confidence,
            "margin": margin,
            "supported": frame.supported,
            "warnings": list(frame.warnings),
            "signature": list(frame.signature()),
            "relations": [asdict(r) | {"key": r.key} for r in frame.relations],
            "details": details,
        }

    def discovered_relations(self) -> list[dict]:
        """Inspect promoted machine-created relation prototypes."""
        return self.relation_discovery.promoted()

    def infer_discovered_relation(self, text: str) -> dict:
        """Query the machine ontology without learning from the query."""
        decision = self.relation_discovery.infer_text(text)
        return {
            "source": decision.source,
            "relation_ids": decision.relation_ids,
            "confidence": decision.confidence,
            "margin": decision.margin,
            "supported": decision.frame.supported,
            "signature": list(decision.frame.signature()),
            "details": decision.details,
        }

    def relation_feedback(
        self,
        relation_id: str,
        *,
        success: bool,
        prediction_error: float = 0.0,
    ) -> dict:
        state = self.relation_discovery.feedback(
            relation_id,
            success=success,
            prediction_error=prediction_error,
        )
        self.save()
        return state

    def nested_belief(self, path, proposition: str) -> dict:
        """Query A believes B believes ... proposition."""
        return self.hierarchical_minds.query(
            tuple(str(x).lower() for x in path),
            proposition,
        )

    def self_belief(self, proposition: str) -> dict:
        return self.self_model.query(proposition)

    def set_self_belief(
        self,
        proposition: str,
        truth: bool,
        confidence: float = 0.7,
        source: str = "explicit_self_update",
    ) -> dict:
        self.event_count += 1
        state = self.self_model.believe(
            proposition,
            truth,
            confidence,
            self.event_count,
            source=source,
        )
        self.save()
        return state

    def report_strategy_outcome(
        self,
        task_family: str,
        strategy: str,
        success: bool,
        score: float = 1.0,
    ) -> dict:
        """
        Let ASM update beliefs about its own ability/strategy from an observed
        success or failure. The update also becomes a seismic event.
        """
        self.event_count += 1
        self.field.begin_event()

        result = self.self_model.record_strategy_outcome(
            task_family,
            strategy,
            success,
            self.event_count,
            score=score,
        )

        outcome_tag = "SUCCESS" if success else "FAILURE"
        observed = {
            f"SELF:TASK:{str(task_family).lower()}": 0.85,
            f"SELF:STRATEGY:{str(strategy).lower()}": 0.90,
            f"SELF:OUTCOME:{outcome_tag}": 1.0,
        }
        for concept, value in self.self_model.concepts().items():
            observed[concept] = max(observed.get(concept, 0.0), value)

        self.field.inject(observed, event_id=self.event_count)
        self.field.propagate(event_id=self.event_count, persistent=True)
        workspace = self.field.workspace()
        self.field.learn_coactivation(workspace)
        self.field.learn_temporal(self.previous_workspace, workspace)
        self.predictor.learn(self.previous_workspace, workspace)
        self.last_predictive_error = self.predictive_coder.learn(
            self.previous_workspace,
            workspace,
        )
        self.previous_workspace = workspace

        attention_state = self.attention.update(
            workspace,
            surprise=1.0 if not success else 0.25,
            magnitude=1.0 if not success else 0.55,
            event_id=self.event_count,
        )
        result["attention"] = attention_state
        self.save()
        return result

    def choose_strategy(self, task_family: str, candidates) -> list[dict]:
        return self.self_model.choose_strategy(task_family, candidates)

    def capability(self, task_family: str) -> dict:
        return self.self_model.capability(task_family)

    def self_state(self) -> dict:
        return {
            "beliefs": {
                key: self.self_model.query(key)
                for key in self.self_model.beliefs
            },
            "internal": self.self_model.internal_state(),
            "capabilities": {
                task: self.self_model.capability(task)
                for task in self.self_model.capabilities
            },
            "attention": self.attention.state(),
        }

    def attention_state(self) -> dict:
        return self.attention.state()

    def infer_rule(self, text: str, limit: int = 5):
        return self.generalizer.predict_text(
            text,
            limit=limit,
        )

    def train_texts(
        self,
        texts,
        *,
        reset_sequence: bool = False,
    ) -> dict:
        count = 0
        surprise_total = 0.0
        error_total = 0.0

        for text in texts:
            text = str(text).strip()
            if not text:
                continue

            if reset_sequence:
                self.previous_workspace = []

            result = self.process(
                text,
                training=True,
            )
            surprise_total += result["surprise"]
            error_total += result["predictive_error"]
            count += 1

        self.save()
        return {
            "trained_events": count,
            "mean_surprise": (
                surprise_total / count
                if count else 0.0
            ),
            "mean_predictive_error": (
                error_total / count
                if count else 0.0
            ),
            "stats": self.stats(),
        }

    def add_goal(
        self,
        text: str,
        priority: float = 0.6,
    ) -> None:
        self.goals.add(text, priority)
        self.save()

    def stats(self) -> dict:
        edge_count = sum(
            len(out)
            for out in self.field.edges.values()
        )
        prediction_edges = sum(
            len(out)
            for out in self.predictor.table.values()
        )
        predictive_edges = sum(
            len(out)
            for out in self.predictive_coder.weights.values()
        )
        rule_edges = sum(
            len(out)
            for out in self.generalizer.weights.values()
        )

        return {
            "events": self.event_count,
            "episodic_events": self.memory.count_events(),
            "semantic_memory_vectors": self.semantic_memory.count(),
            "semantic_event_records": self.event_memory.count(),
            "semantic_event_links": self.event_memory.link_count(),
            "world_model": self.world_model.stats() if self.world_model else {"enabled": False},
            "transition_mechanisms": self.transition_mechanisms.stats() if self.transition_mechanisms else {"enabled": False},
            "evidence_lineage": self.evidence_lineage.stats() if self.cfg.evidence_lineage_enabled else {"enabled": False},
            "concept_nodes": len(self.field.nodes),
            "association_edges": edge_count,
            "prediction_edges": prediction_edges,
            "predictive_coding_edges": predictive_edges,
            "rule_edges": rule_edges,
            "structural_schemas": len(
                self.structural_memory.schemas
            ),
            "structural_abstractions": len(
                self.structural_memory.abstractions
            ),
            "structural_examples": len(
                self.structural_memory.examples
            ),
            "latent_candidates": len(self.emergent.concepts),
            "latent_concepts": len(self.emergent.promoted()),
            "belief_holders": len(self.minds.states),
            "belief_propositions": sum(
                len(props)
                for props in self.minds.states.values()
            ),
            "emotion_labels": len(self.emotions.labels),
            "emotion_agent_states": len(self.emotions.agent_states),
            "appraisal_holders": len(self.appraisal.drives),
            "appraisal_drives": sum(
                len(rows) for rows in self.appraisal.drives.values()
            ),
            "appraisal_emotion_labels": len(self.appraisal.emotion_map),
            "nested_belief_paths": len(self.hierarchical_minds.states),
            "nested_belief_propositions": sum(
                len(props)
                for props in self.hierarchical_minds.states.values()
            ),
            "self_beliefs": len(self.self_model.beliefs),
            "self_capabilities": len(self.self_model.capabilities),
            "self_strategies": sum(
                len(rows)
                for rows in self.self_model.strategies.values()
            ),
            "attention_targets": len(self.attention.targets),
            "perception_examples": self.perception.stats()["examples"],
            "perception_connector_phrases": self.perception.stats()["connector_phrases"],
            "perception_inferred_phrases": self.perception.stats()["inferred_connector_phrases"],
            "discovered_relations": self.relation_discovery.stats()["relations"],
            "promoted_discovered_relations": self.relation_discovery.stats()["promoted"],
            "dormant_discovered_relations": self.relation_discovery.stats()["dormant"],
            "relation_discovery_episodes": self.relation_discovery.stats()["episodes"],
            "relation_merges": self.relation_discovery.stats()["merges"],
            "relation_splits": self.relation_discovery.stats()["splits"],
            "evidence_dependency": self.evidence_dependency.stats() if self.cfg.evidence_dependency_enabled else {"enabled": False},
            "language_core_backend": self.language_core.name,
            "language_core_embedding_dims": int(
                self.language_core.capabilities().get(
                    "embedding_dims",
                    self.cfg.language_core_embedding_dims,
                )
            ),
            "active_nodes": len(self.field.active),
            "semantic_terms": len(
                self.encoder.semantic.contexts
            ),
            "goals": len(
                [g for g in self.goals.goals if g.active]
            ),
        }

    def save(self) -> None:
        payload = {
            "version": "0.4.0-alpha.7.9",
            "field": self.field.export_state(),
            "predictor": self.predictor.export_state(),
            "predictive_coder": self.predictive_coder.export_state(),
            "generalizer": self.generalizer.export_state(),
            "structural_memory": self.structural_memory.export_state(),
            "emergent": self.emergent.export_state(),
            "minds": self.minds.export_state(),
            "emotions": self.emotions.export_state(),
            "appraisal": self.appraisal.export_state(),
            "hierarchical_minds": self.hierarchical_minds.export_state(),
            "self_model": self.self_model.export_state(),
            "attention": self.attention.export_state(),
            "perception": self.perception.export_state(),
            "relation_discovery": self.relation_discovery.export_state(),
            "adaptive_evidence": self.adaptive_evidence.export_state(),
            "evidence_lineage": self.evidence_lineage.export_state(),
            "evidence_dependency": self.evidence_dependency.export_state(),
            "encoder": self.encoder.export_state(),
            "goals": self.goals.export_state(),
            "previous_workspace": self.previous_workspace,
            "event_count": self.event_count,
        }
        self.memory.set_kv(
            self.SNAPSHOT_KEY,
            payload,
        )

    def _load_snapshot(self) -> None:
        payload = self.memory.get_kv(self.SNAPSHOT_KEY)
        # Alpha.6 keeps the alpha.5.2 cognitive snapshot schema and adds one
        # independent adaptive-evidence payload. Treat the shared cognition as
        # alpha.5.2 during compatibility loading.
        source_version = "0.4.0-alpha.5.2" if payload else None

        if not payload:
            payload = self.memory.get_kv(self.ALPHA78_V04_SNAPSHOT_KEY)
            if payload:
                # Alpha.7.9 changes bounded routing inference only. Procedure and
                # route evidence remain in additive SQLite tables; no synthetic
                # evidence is created while loading an alpha.7.8 snapshot.
                source_version = "0.4.0-alpha.5.2"

        if not payload:
            payload = self.memory.get_kv(self.ALPHA77_V04_SNAPSHOT_KEY)
            if payload:
                # Alpha.7.8 changes bounded routing inference only. Procedure and
                # route evidence remain in additive SQLite tables; no synthetic
                # evidence is created while loading an alpha.7.7 snapshot.
                source_version = "0.4.0-alpha.5.2"

        if not payload:
            payload = self.memory.get_kv(self.ALPHA76_V04_SNAPSHOT_KEY)
            if payload:
                # Alpha.7.7 changes only bounded routing inference. Procedure and
                # route evidence remain in additive SQLite tables; no synthetic
                # evidence is created while loading an alpha.7.6 snapshot.
                source_version = "0.4.0-alpha.5.2"

        if not payload:
            payload = self.memory.get_kv(self.ALPHA74_V04_SNAPSHOT_KEY)
            if payload:
                # Alpha.7.6 promotes the additive alpha.7.5/7.6 routing state
                # without fabricating new route evidence. Procedure/routing tables
                # already live in SQLite; cognition falls back to alpha.7.4.
                source_version = "0.4.0-alpha.5.2"

        if not payload:
            payload = self.memory.get_kv(self.ALPHA73_V04_SNAPSHOT_KEY)
            if payload:
                # Alpha.7.4 keeps alpha.7.3 cognition/procedure tables intact and
                # adds only bounded typed synthesis/query logic. No synthetic
                # procedure or query history is created during migration.
                source_version = "0.4.0-alpha.5.2"

        if not payload:
            payload = self.memory.get_kv(self.ALPHA72_V04_SNAPSHOT_KEY)
            if payload:
                # Alpha.7.3 keeps alpha.7.2 cognition/procedure tables intact and
                # only broadens bounded induction. No synthetic procedure history
                # is created during migration.
                source_version = "0.4.0-alpha.5.2"

        if not payload:
            payload = self.memory.get_kv(self.ALPHA71_V04_SNAPSHOT_KEY)
            if payload:
                # Alpha.7.2 keeps alpha.7.1 cognition intact and adds autonomous
                # procedure state in additive SQLite tables. No synthetic procedure
                # history is created during migration.
                source_version = "0.4.0-alpha.5.2"

        if not payload:
            payload = self.memory.get_kv(self.ALPHA7_V04_SNAPSHOT_KEY)
            if payload:
                # Alpha.7 uses the same established cognition payload plus
                # schema-1 dependency state. EvidenceDependencyModel migrates
                # it without fabricating temporal history or regimes.
                source_version = "0.4.0-alpha.5.2"

        if not payload:
            payload = self.memory.get_kv(self.ALPHA62_V04_SNAPSHOT_KEY)
            if payload:
                source_version = "0.4.0-alpha.5.2"

        if not payload:
            payload = self.memory.get_kv(self.ALPHA61_V04_SNAPSHOT_KEY)
            if payload:
                source_version = "0.4.0-alpha.5.2"

        if not payload:
            payload = self.memory.get_kv(self.ALPHA6_V04_SNAPSHOT_KEY)
            if payload:
                # Alpha.6 shares alpha.5.2 cognition and carries schema-1
                # adaptive evidence, which AdaptiveEvidenceModel migrates.
                source_version = "0.4.0-alpha.5.2"

        if not payload:
            payload = self.memory.get_kv(self.ALPHA52_V04_SNAPSHOT_KEY)
            if payload:
                source_version = "0.4.0-alpha.5.2"

        if not payload:
            payload = self.memory.get_kv(self.ALPHA51_V04_SNAPSHOT_KEY)
            if payload:
                source_version = "0.4.0-alpha.5.1"

        if not payload:
            payload = self.memory.get_kv(self.ALPHA5_V04_SNAPSHOT_KEY)
            if payload:
                source_version = "0.4.0-alpha.5"

        if not payload:
            payload = self.memory.get_kv(self.ALPHA4_V04_SNAPSHOT_KEY)
            if payload:
                source_version = "0.4.0-alpha.4"

        if not payload:
            payload = self.memory.get_kv(self.ALPHA3_V04_SNAPSHOT_KEY)
            if payload:
                source_version = "0.4.0-alpha.3"

        if not payload:
            payload = self.memory.get_kv(self.ALPHA2_V04_SNAPSHOT_KEY)
            if payload:
                source_version = "0.4.0-alpha.2"

        if not payload:
            payload = self.memory.get_kv(self.ALPHA1_V04_SNAPSHOT_KEY)
            if payload:
                source_version = "0.4.0-alpha.1"

        if not payload:
            payload = self.memory.get_kv(self.ALPHA12_V03_SNAPSHOT_KEY)
            if payload:
                source_version = "0.3.0-alpha.12"

        if not payload:
            payload = self.memory.get_kv(self.ALPHA11_V03_SNAPSHOT_KEY)
            if payload:
                source_version = "0.3.0-alpha.11"

        if not payload:
            payload = self.memory.get_kv(self.ALPHA10_V03_SNAPSHOT_KEY)
            if payload:
                source_version = "0.3.0-alpha.10"

        if not payload:
            payload = self.memory.get_kv(self.ALPHA9_V03_SNAPSHOT_KEY)
            if payload:
                source_version = "0.3.0-alpha.9"

        if not payload:
            payload = self.memory.get_kv(self.ALPHA8_V03_SNAPSHOT_KEY)
            if payload:
                source_version = "0.3.0-alpha.8"

        if not payload:
            payload = self.memory.get_kv(self.ALPHA7_V03_SNAPSHOT_KEY)
            if payload:
                source_version = "0.3.0-alpha.7"

        if not payload:
            payload = self.memory.get_kv(self.ALPHA6_V03_SNAPSHOT_KEY)
            if payload:
                source_version = "0.3.0-alpha.6"

        if not payload:
            payload = self.memory.get_kv(self.ALPHA5_V03_SNAPSHOT_KEY)
            if payload:
                source_version = "0.3.0-alpha.5"

        if not payload:
            payload = self.memory.get_kv(self.ALPHA4_V03_SNAPSHOT_KEY)
            if payload:
                source_version = "0.3.0-alpha.4"

        if not payload:
            payload = self.memory.get_kv(self.ALPHA3_V03_SNAPSHOT_KEY)
            if payload:
                source_version = "0.3.0-alpha.3"

        if not payload:
            payload = self.memory.get_kv(self.ALPHA2_V03_SNAPSHOT_KEY)
            if payload:
                source_version = "0.3.0-alpha.2"

        if not payload:
            payload = self.memory.get_kv(self.ALPHA1_V03_SNAPSHOT_KEY)
            if payload:
                source_version = "0.3.0-alpha.1"

        if not payload:
            payload = self.memory.get_kv(self.ALPHA7_SNAPSHOT_KEY)
            if payload:
                source_version = "0.2.0-alpha.7"

        if not payload:
            payload = self.memory.get_kv(self.ALPHA6_SNAPSHOT_KEY)
            if payload:
                source_version = "0.2.0-alpha.6"

        if not payload:
            payload = self.memory.get_kv(self.ALPHA5_SNAPSHOT_KEY)
            if payload:
                source_version = str(payload.get("version", "0.2.0-alpha.5"))

        if not payload:
            payload = self.memory.get_kv(self.ALPHA3_SNAPSHOT_KEY)
            if payload:
                source_version = "0.2.0-alpha.3"

        if not payload:
            payload = self.memory.get_kv(self.ALPHA2_SNAPSHOT_KEY)
            if payload:
                source_version = "0.2.0-alpha.2"

        if not payload:
            payload = self.memory.get_kv(self.ALPHA1_SNAPSHOT_KEY)
            if payload:
                source_version = "0.2.0-alpha.1"

        if not payload:
            payload = self.memory.get_kv(self.LEGACY_SNAPSHOT_KEY)
            if payload:
                source_version = "0.1.1.10"

        if not payload:
            payload = self.memory.get_kv(self.OLDER_SNAPSHOT_KEY)
            if payload:
                source_version = "0.1.1.9"

        if not payload:
            payload = self.memory.get_kv(self.OLDEST_SNAPSHOT_KEY)
            if payload:
                source_version = "0.1.1.8"

        if not payload:
            payload = self.memory.get_kv(self.ANCIENT_SNAPSHOT_KEY)
            if payload:
                source_version = "0.1.1.7"

        if not payload:
            payload = self.memory.get_kv(self.PREHISTORIC_SNAPSHOT_KEY)
            if payload:
                source_version = "0.1.1.6"

        if not payload:
            payload = self.memory.get_kv(self.PRIMITIVE_SNAPSHOT_KEY)
            if payload:
                source_version = "0.1.1.5"

        if not payload:
            payload = self.memory.get_kv(self.ARCHAIC_SNAPSHOT_KEY)
            if payload:
                source_version = "0.1.1.4"

        if not payload:
            payload = self.memory.get_kv(self.ORIGINAL_SNAPSHOT_KEY)
            if payload:
                source_version = "0.1.1.3"

        if not payload:
            self._rebuild_structural_memory()
            self._rebuild_new_cognition()
            self._rebuild_hierarchical_minds()
            self._rebuild_perception()
            # No prior v0.1.1.9 snapshot exists, so begin the anonymous
            # relation ontology cleanly. Replaying every historical event here
            # is expensive and mostly reproduces programmer-named bootstrap
            # relations rather than genuinely novel relation evidence.
            self.relation_discovery = SelfDiscoveredRelationSystem(
                self.cfg,
                self.encoder,
                self.structural_parser,
                self.perception,
            )
            return

        self.field.import_state(payload.get("field", {}))
        self.predictor.import_state(payload.get("predictor", {}))
        self.predictive_coder.import_state(
            payload.get("predictive_coder", {})
        )
        self.generalizer.import_state(
            payload.get("generalizer", {})
        )

        if source_version == "0.1.1.3":
            # Old structural snapshots cannot express v0.1.1.4 polarity.
            self._rebuild_structural_memory()
        else:
            self.structural_memory.import_state(
                payload.get("structural_memory", {})
            )

        self.encoder.import_state(payload.get("encoder", {}))
        self.goals.import_state(payload.get("goals", []))

        if source_version in {"0.1.1.5", "0.1.1.6", "0.1.1.7", "0.1.1.8", "0.1.1.9", "0.1.1.10", "0.2.0-alpha.1", "0.2.0-alpha.2", "0.2.0-alpha.3", "0.2.0-alpha.4", "0.2.0-alpha.5", "0.2.0-alpha.6", "0.2.0-alpha.7", "0.3.0-alpha.1", "0.3.0-alpha.2", "0.3.0-alpha.3", "0.3.0-alpha.4", "0.3.0-alpha.5", "0.3.0-alpha.6", "0.3.0-alpha.7", "0.3.0-alpha.8", "0.3.0-alpha.9", "0.3.0-alpha.10", "0.3.0-alpha.11", "0.3.0-alpha.12", "0.4.0-alpha.1", "0.4.0-alpha.2", "0.4.0-alpha.3", "0.4.0-alpha.4", "0.4.0-alpha.5", "0.4.0-alpha.5.1", "0.4.0-alpha.5.2"}:
            self.emergent.import_state(payload.get("emergent", {}))
            self.minds.import_state(payload.get("minds", {}))
            self.emotions.import_state(payload.get("emotions", {}))
            self.appraisal = AppraisalSystem(self.cfg, self.minds)
            if source_version in {"0.1.1.6", "0.1.1.7", "0.1.1.8", "0.1.1.9", "0.1.1.10", "0.2.0-alpha.1", "0.2.0-alpha.2", "0.2.0-alpha.3", "0.2.0-alpha.4", "0.2.0-alpha.5", "0.2.0-alpha.6", "0.2.0-alpha.7", "0.3.0-alpha.1", "0.3.0-alpha.2", "0.3.0-alpha.3", "0.3.0-alpha.4", "0.3.0-alpha.5", "0.3.0-alpha.6", "0.3.0-alpha.7", "0.3.0-alpha.8", "0.3.0-alpha.9", "0.3.0-alpha.10", "0.3.0-alpha.11", "0.3.0-alpha.12", "0.4.0-alpha.1", "0.4.0-alpha.2", "0.4.0-alpha.3", "0.4.0-alpha.4", "0.4.0-alpha.5", "0.4.0-alpha.5.1", "0.4.0-alpha.5.2"}:
                self.appraisal.import_state(payload.get("appraisal", {}))
            else:
                self._rebuild_appraisal_only()
        else:
            # v0.1.1.5+ cognition can be reconstructed from historical text.
            self._rebuild_new_cognition()

        # v0.1.1.7 state can be loaded directly. Older releases rebuild
        # nested beliefs from event text where possible and start with a neutral
        # self-model/attention state.
        self.hierarchical_minds = HierarchicalMindModel(self.cfg)
        self.self_model = SelfModel(self.cfg)
        self.attention = AttentionSystem(self.cfg)

        if source_version in {"0.1.1.7", "0.1.1.8", "0.1.1.9", "0.1.1.10", "0.2.0-alpha.1", "0.2.0-alpha.2", "0.2.0-alpha.3", "0.2.0-alpha.4", "0.2.0-alpha.5", "0.2.0-alpha.6", "0.2.0-alpha.7", "0.3.0-alpha.1", "0.3.0-alpha.2", "0.3.0-alpha.3", "0.3.0-alpha.4", "0.3.0-alpha.5", "0.3.0-alpha.6", "0.3.0-alpha.7", "0.3.0-alpha.8", "0.3.0-alpha.9", "0.3.0-alpha.10", "0.3.0-alpha.11", "0.3.0-alpha.12", "0.4.0-alpha.1", "0.4.0-alpha.2", "0.4.0-alpha.3", "0.4.0-alpha.4", "0.4.0-alpha.5", "0.4.0-alpha.5.1", "0.4.0-alpha.5.2"}:
            self.hierarchical_minds.import_state(
                payload.get("hierarchical_minds", {})
            )
            self.self_model.import_state(
                payload.get("self_model", {})
            )
            self.attention.import_state(
                payload.get("attention", {})
            )
        else:
            self._rebuild_hierarchical_minds()

        self.perception = LearnedRelationPerception(
            self.cfg,
            self.encoder,
            self.structural_parser,
        )
        if source_version in {"0.1.1.8", "0.1.1.9", "0.1.1.10", "0.2.0-alpha.1", "0.2.0-alpha.2", "0.2.0-alpha.3", "0.2.0-alpha.4", "0.2.0-alpha.5", "0.2.0-alpha.6", "0.2.0-alpha.7", "0.3.0-alpha.1", "0.3.0-alpha.2", "0.3.0-alpha.3", "0.3.0-alpha.4", "0.3.0-alpha.5", "0.3.0-alpha.6", "0.3.0-alpha.7", "0.3.0-alpha.8", "0.3.0-alpha.9", "0.3.0-alpha.10", "0.3.0-alpha.11", "0.3.0-alpha.12", "0.4.0-alpha.1", "0.4.0-alpha.2", "0.4.0-alpha.3", "0.4.0-alpha.4", "0.4.0-alpha.5", "0.4.0-alpha.5.1", "0.4.0-alpha.5.2"}:
            self.perception.import_state(payload.get("perception", {}))
        else:
            self._rebuild_perception()

        self.relation_discovery = SelfDiscoveredRelationSystem(
            self.cfg,
            self.encoder,
            self.structural_parser,
            self.perception,
        )
        if source_version in {"0.1.1.9", "0.1.1.10", "0.2.0-alpha.1", "0.2.0-alpha.2", "0.2.0-alpha.3", "0.2.0-alpha.4", "0.2.0-alpha.5", "0.2.0-alpha.6", "0.2.0-alpha.7", "0.3.0-alpha.1", "0.3.0-alpha.2", "0.3.0-alpha.3", "0.3.0-alpha.4", "0.3.0-alpha.5", "0.3.0-alpha.6", "0.3.0-alpha.7", "0.3.0-alpha.8", "0.3.0-alpha.9", "0.3.0-alpha.10", "0.3.0-alpha.11", "0.3.0-alpha.12", "0.4.0-alpha.1", "0.4.0-alpha.2", "0.4.0-alpha.3", "0.4.0-alpha.4", "0.4.0-alpha.5", "0.4.0-alpha.5.1", "0.4.0-alpha.5.2"}:
            self.relation_discovery.import_state(
                payload.get("relation_discovery", {})
            )
        # Older releases had no anonymous relation ontology. Starting this
        # subsystem empty is both faster and more faithful than pretending old
        # hand-labeled examples were already self-discovered relations.

        self.previous_workspace = [
            (str(name), float(value))
            for name, value in payload.get(
                "previous_workspace",
                [],
            )
        ]
        self.event_count = max(
            self.event_count,
            int(payload.get("event_count", 0)),
        )
        self.adaptive_evidence.import_state(payload.get("adaptive_evidence", {}))
        self.evidence_lineage.import_state(payload.get("evidence_lineage", {}))
        self.evidence_dependency.import_state(payload.get("evidence_dependency", {}))

    def _rebuild_structural_memory(self) -> None:
        self.structural_memory = StructuralMemory(self.cfg)
        self.expander.structural = self.structural_memory
        for (text,) in self.memory.db.execute(
            "SELECT text FROM events ORDER BY id"
        ):
            self.structural_memory.observe(
                self.structural_parser.parse(text)
            )

    def _rebuild_new_cognition(self) -> None:
        self.emergent = EmergentConceptSystem(self.cfg)
        self.minds = AgentMindModel(self.cfg)
        self.emotions = EmotionLearner(
            self.cfg,
            self.encoder,
            self.structural_parser,
        )
        self.appraisal = AppraisalSystem(
            self.cfg,
            self.minds,
        )

        rows = self.memory.db.execute(
            "SELECT id, text FROM events ORDER BY id"
        )
        for event_id, text in rows:
            frame = self.structural_parser.parse(text)
            features = self.emergent.frame_features(frame)

            mind_event = self.minds.observe_text(text, int(event_id))
            if mind_event:
                features.append(
                    f"MIND:{mind_event['type'].upper()}"
                )

            drive_event = self.appraisal.observe_drive(text, int(event_id))
            if drive_event:
                features.append(
                    f"MIND:DRIVE:{drive_event['kind'].upper()}"
                )

            latent = self.emergent.activate(features)
            labeled = self.emotions.observe_labeled(
                text,
                int(event_id),
                latent.keys(),
            )
            if labeled:
                features.append(
                    f"EMOTION:{labeled['label']}"
                )
                self.appraisal.learn_emotion_from_agent(
                    labeled["agent"],
                    labeled["label"],
                    int(event_id),
                )

            self.emergent.observe(features, int(event_id))

    def _rebuild_perception(self) -> None:
        self.perception = LearnedRelationPerception(
            self.cfg,
            self.encoder,
            self.structural_parser,
        )
        rows = self.memory.db.execute(
            "SELECT text FROM events ORDER BY id"
        )
        for (text,) in rows:
            frame = self.structural_parser.parse(text)
            if frame.supported:
                self.perception.observe_bootstrap(text, frame)

    def _rebuild_relation_discovery(self) -> None:
        self.relation_discovery = SelfDiscoveredRelationSystem(
            self.cfg,
            self.encoder,
            self.structural_parser,
            self.perception,
        )
        rows = self.memory.db.execute(
            "SELECT id, text FROM events ORDER BY id"
        )
        for event_id, text in rows:
            self.relation_discovery.observe_text(
                text,
                int(event_id),
            )

    def _rebuild_hierarchical_minds(self) -> None:
        self.hierarchical_minds = HierarchicalMindModel(self.cfg)
        rows = self.memory.db.execute(
            "SELECT id, text FROM events ORDER BY id"
        )
        for event_id, text in rows:
            self.hierarchical_minds.parse_text(
                text,
                int(event_id),
            )

    def _rebuild_appraisal_only(self) -> None:
        self.appraisal = AppraisalSystem(self.cfg, self.minds)
        rows = self.memory.db.execute(
            "SELECT id, text FROM events ORDER BY id"
        )
        for event_id, text in rows:
            self.appraisal.observe_drive(text, int(event_id))
            m = self.emotions.LABELED_RE.match(text)
            if m:
                self.appraisal.learn_emotion_from_agent(
                    m.group("agent").lower(),
                    m.group("label").lower(),
                    int(event_id),
                )

    def close(self, *, save_snapshot: bool = True) -> None:
        """Close all resources. ``save_snapshot=False`` is for migration/copy tooling."""
        if getattr(self, "_closed", False):
            return
        if save_snapshot:
            self.save()
        self.language_core.close()
        self.semantic_memory.close()
        self.event_memory.close()
        if self.transition_mechanisms is not None:
            self.transition_mechanisms.close()
        if self.world_model is not None:
            self.world_model.close()
        if getattr(self, "_procedures", None) is not None:
            self._procedures.close()
            self._procedures = None
        self.memory.close()
        self._closed = True
