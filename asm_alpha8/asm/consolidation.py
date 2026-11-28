from __future__ import annotations
from dataclasses import dataclass


@dataclass(slots=True)
class ConsolidationDecision:
    persist: bool
    mode: str
    reason: str
    social_probability: float
    structured: bool

    def as_dict(self) -> dict:
        return {
            "persist":self.persist,
            "mode":self.mode,
            "reason":self.reason,
            "social_probability":self.social_probability,
            "structured":self.structured,
        }


class ConsolidationGate:
    """
    Working-memory -> long-term-memory gate.

    The social probe is advisory, never authoritative. Structured cognition
    (beliefs, drives, relations, self outcomes) always wins and is persisted.
    """
    def __init__(self, config):
        self.cfg=config

    def decide(
        self,
        text: str,
        *,
        training: bool,
        structured: bool,
        social_probability: float,
        intent: str,
        intent_confidence: float,
        token_count: int,
    ) -> ConsolidationDecision:
        if training:
            return ConsolidationDecision(True,"persistent","training",social_probability,structured)
        if structured:
            return ConsolidationDecision(True,"persistent","structured_cognitive_event",social_probability,True)
        if social_probability >= float(self.cfg.consolidation_social_threshold):
            return ConsolidationDecision(False,"transient","high_confidence_social",social_probability,False)
        if "?" in text:
            return ConsolidationDecision(False,"transient","unstructured_question",social_probability,False)
        if token_count <= int(self.cfg.consolidation_short_token_limit):
            return ConsolidationDecision(False,"transient","short_unstructured",social_probability,False)
        if (
            intent == "other"
            and intent_confidence < float(self.cfg.consolidation_uncertain_intent_threshold)
            and token_count <= int(self.cfg.consolidation_uncertain_token_limit)
        ):
            return ConsolidationDecision(False,"transient","uncertain_unstructured",social_probability,False)
        return ConsolidationDecision(True,"persistent","meaningful_unstructured",social_probability,False)
