"""Cognition-owned content planning. Writers have no database or engine handle."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Mapping


@dataclass
class CognitivePacket:
    user_intent: str
    slots: dict[str, str] = field(default_factory=dict)
    evidence: list[dict] = field(default_factory=list)
    uncertainty: float = 0.0
    self_state: dict = field(default_factory=dict)
    style: str = "full"
    answer_constraints: list[str] = field(default_factory=lambda: [
        "Copy supplied slots exactly; quoted reports are not world facts.",
        "Do not add beliefs, memories, goals, outcomes or certainty.",
    ])

    def as_dict(self):
        return asdict(self)


def build_packet(text: str, result: Mapping, engine, conversation) -> CognitivePacket:
    """Choose content using ASM's state, not the language decoder's guesses."""
    act = conversation.recognizer.recognize(text).label
    packet = CognitivePacket(act, style=engine.cfg.writer_style)
    semantic = result.get("semantic_event", {})
    if semantic.get("abstained"):
        packet.user_intent = "uncertainty"
        packet.uncertainty = 1.0
        packet.evidence = [{"kind": "semantic_abstain", "reason": semantic.get("reason", "abstained")}]
        return packet
    if act == "wellbeing":
        state = engine.self_state().get("internal", {})
        packet.self_state = dict(state)
        packet.slots = {"confidence": f"{float(state.get('confidence', .5)):.2f}",
                        "curiosity": f"{float(state.get('curiosity', 0)):.2f}"}
        packet.evidence = [{"kind": "self_state", "values": dict(packet.slots)}]
        return packet
    if act in {"greeting", "identity", "gratitude", "farewell", "negative_affect", "positive_affect"}:
        return packet
    if act == "belief_query":
        answer = conversation._belief_answer(engine, text)
        if answer:
            # This is a cognition-constructed statement, not neural wording.
            packet.user_intent = "belief_report"
            packet.slots = {"claim": answer}
            packet.evidence = [{"kind": "belief_report", "text": answer}]
            packet.uncertainty = 1.0 if "don't have" in answer or "uncertain" in answer else 0.0
        else:
            packet.user_intent = "uncertainty"
            packet.uncertainty = 1.0
        return packet
    if act == "memory_query" and re.search(r"\b(?:just|last message|right before)\b", text, re.I):
        if conversation.history:
            packet.user_intent = "previous_message"
            packet.slots = {"claim": conversation.history[-1]["user"]}
            packet.evidence = [{"kind": "session", "text": packet.slots["claim"]}]
            return packet
    structured = conversation._structured_ack(text, result)
    if act in {"memory_query", "question"} and not structured:
        rows = conversation._memory_search(engine, text, limit=3)
        if rows and float(rows[0].get("relevance", 0.0)) >= .10:
            packet.user_intent = "memory_report"
            packet.slots = {"claim": str(rows[0]["text"])}
            packet.evidence = [{"kind": "episode", "event_id": rows[0]["id"], "text": str(rows[0]["text"])}]
        else:
            packet.user_intent = "uncertainty"
            packet.uncertainty = 1.0
        return packet
    if structured:
        packet.user_intent = "cognitive_report"
        packet.slots = {"claim": structured}
        packet.evidence = [{"kind": "cognitive_event", "text": structured}]
    elif result.get("consolidation", {}).get("reason") == "short_unstructured":
        packet.user_intent = "confusion"
    elif result.get("consolidation", {}).get("persist", False):
        packet.user_intent = "stored"
        packet.evidence = [{"kind": "consolidated", "text": text}]
    else:
        packet.user_intent = "listening"
    return packet


def hybrid_generate(packet: CognitivePacket) -> str:
    """Explicit baseline/failover. Never called to repair a neural draft silently."""
    action, s = packet.user_intent, packet.slots
    if action == "wellbeing":
        return (f"My internal confidence signal is {s['confidence']} and my curiosity signal is {s['curiosity']}. "
                "These are computational signals.")
    if action in {"belief_report", "cognitive_report"}:
        return s["claim"]
    if action == "memory_report":
        return f"I remember this reported event: {s['claim']}"
    if action == "previous_message":
        return f"Your previous message was: {s['claim']}"
    return {
        "greeting": "Hey. What would you like to talk about?",
        "identity": "I'm ASM, a memory-centric AI with a recurrent language interface and structured memory.",
        "gratitude": "You're welcome.", "farewell": "See you.",
        "negative_affect": "You sound upset. What happened?",
        "positive_affect": "What happened? Tell me more.",
        "uncertainty": "I don't have enough reliable information to answer that yet.",
        "confusion": "I'm not sure what you mean. Can you explain?",
        "stored": "Got it. I'll keep that in long-term memory.",
        "listening": "Go on. What would you like to discuss?",
    }.get(action, "I don't know.")
