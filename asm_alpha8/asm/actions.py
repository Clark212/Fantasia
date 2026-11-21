from __future__ import annotations

from typing import Dict, List, Tuple


class ActionSelector:
    """
    Minimal observable output layer.

    This is not a language model. It converts ASM's state into a small set of
    explicit actions so the architecture can be benchmarked end-to-end.
    """

    def choose(
        self,
        text: str,
        observed: Dict[str, float],
        workspace: List[Tuple[str, float]],
        recalled: List[dict],
        predicted_next: Dict[str, float],
        surprise: float,
        consolidation: dict | None = None,
    ) -> dict:
        if consolidation and not consolidation.get("persist", True):
            reason = str(consolidation.get("reason", "transient"))
            social = reason == "high_confidence_social"
            return {
                "type": "SOCIAL" if social else "TRANSIENT",
                "confidence": (
                    float(consolidation.get("social_probability", 0.75))
                    if social else 0.80
                ),
                "utterance": (
                    "Social input recognized; kept in working context."
                    if social
                    else "Input processed transiently; long-term learning skipped."
                ),
            }

        is_question = "ACT:QUESTION" in observed

        if is_question and recalled:
            best = recalled[0]
            return {
                "type": "RECALL",
                "confidence": max(0.0, min(1.0, best["relevance"])),
                "utterance": f"I remember a related event: {best['text']}",
                "source_event_id": best["id"],
            }

        if is_question and not recalled:
            return {
                "type": "ASK_CLARIFY",
                "confidence": 0.35,
                "utterance": "I don't have a strong matching memory yet.",
            }

        if surprise >= 0.78:
            return {
                "type": "LEARN",
                "confidence": surprise,
                "utterance": "New pattern registered.",
            }

        if predicted_next:
            concept, score = max(
                predicted_next.items(),
                key=lambda kv: kv[1],
            )
            return {
                "type": "TRACK",
                "confidence": max(0.0, min(1.0, score)),
                "utterance": f"Tracking likely next state: {concept}",
            }

        return {
            "type": "OBSERVE",
            "confidence": 0.5,
            "utterance": "Event integrated.",
        }
