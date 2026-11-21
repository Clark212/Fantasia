from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Any, Iterable, Mapping

from .mental_language import MentalLanguagePerception
from .mind import canonical_proposition


EVENT_TYPES = {
    "observation",
    "belief",
    "nested_belief",
    "goal",
    "fear",
    "expectation",
    "self_outcome",
    "question",
    "other",
}

EPISTEMIC = {
    "asserted",
    "believed",
    "expected",
    "desired",
    "feared",
    "reported",
    "hypothetical",
    "queried",
    "unknown",
}


@dataclass(slots=True)
class Proposition:
    """Machine-normalized proposition paired with its original surface form."""

    surface: str
    canonical: str
    truth: bool

    @classmethod
    def from_surface(cls, text: str, *, polarity: bool = True) -> "Proposition":
        surface = " ".join(str(text).strip().rstrip(".!?").split())
        canonical, truth = canonical_proposition(surface)
        if not polarity:
            truth = not truth
        return cls(surface=surface, canonical=canonical, truth=bool(truth))

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class SemanticEvent:
    event_type: str
    epistemic: str
    confidence: float
    source: str
    agents: list[str] = field(default_factory=list)
    proposition: Proposition | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)
    persistent_eligible: bool = True

    def as_dict(self) -> dict:
        out = asdict(self)
        if self.proposition is not None:
            out["proposition"] = self.proposition.as_dict()
        return out


@dataclass(slots=True)
class SemanticDecision:
    primary: SemanticEvent
    alternatives: list[SemanticEvent] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    abstained: bool = False
    reason: str = ""

    def as_dict(self) -> dict:
        return {
            "primary": self.primary.as_dict(),
            "alternatives": [x.as_dict() for x in self.alternatives],
            "conflicts": list(self.conflicts),
            "abstained": self.abstained,
            "reason": self.reason,
        }


class SemanticEventCortex:
    """
    Alpha.6 semantic arbitration layer.

    The cortex does not own beliefs, goals or memories.  It sits *before* those
    stores and selects one primary language-derived cognitive event so the same
    utterance cannot independently become contradictory event types.

    It combines three signals:
      1. accepted language-core proposals,
      2. the stable native mental-language parser,
      3. query / uncertainty guards.

    The learned recurrent reader remains consequential through its proposals
    and embedding.  The cortex adds type exclusivity, epistemic semantics,
    surface/canonical proposition separation, and a pre-persistence consistency
    gate.
    """

    _QUESTION = re.compile(
        r"^\s*(?:why|how|what|when|where|who|which|can|could|is|are|do|does|did|should|would|will)\b",
        re.I,
    )
    _HYPOTHETICAL = re.compile(r"\b(?:maybe|perhaps|possibly|might|may|could|if)\b", re.I)
    _WORLD = re.compile(r"^\s*(?:actually|in reality|reality|fact)\s*[:,]?\s*(?P<prop>.+?)\s*[.!]?\s*$", re.I)

    def __init__(self):
        self.events_seen = 0
        self.conflicts_blocked = 0
        self.hypotheticals_abstained = 0

    @staticmethod
    def _event_from_proposal(kind: str, payload: Mapping[str, Any], confidence: float, source: str) -> SemanticEvent | None:
        kind = str(kind)
        p = dict(payload)
        c = max(0.0, min(1.0, float(confidence)))
        if kind == "belief":
            prop = Proposition.from_surface(str(p.get("proposition_text", "")), polarity=bool(p.get("polarity", True)))
            return SemanticEvent("belief", "believed", c, source, [str(p.get("holder", "")).lower()], prop, p, ["language-proposal"])
        if kind == "nested_belief":
            prop = Proposition.from_surface(str(p.get("proposition_text", "")), polarity=bool(p.get("polarity", True)))
            return SemanticEvent("nested_belief", "reported", c, source, [str(x).lower() for x in p.get("path", [])], prop, p, ["language-proposal"])
        if kind == "drive":
            drive_kind = str(p.get("kind", "goal")).lower()
            if drive_kind not in {"goal", "fear", "expectation"}:
                return None
            epi = {"goal": "desired", "fear": "feared", "expectation": "expected"}[drive_kind]
            prop = Proposition.from_surface(str(p.get("proposition_text", "")))
            return SemanticEvent(drive_kind, epi, c, source, [str(p.get("holder", "")).lower()], prop, p, ["language-proposal"])
        if kind == "self_outcome":
            return SemanticEvent("self_outcome", "asserted", c, source, ["self"], None, p, ["language-proposal"])
        return None

    @classmethod
    def _native_candidates(cls, text: str) -> list[SemanticEvent]:
        out: list[SemanticEvent] = []
        nested = MentalLanguagePerception.parse_nested(text, max_order=3)
        if nested:
            out.append(SemanticEvent(
                "nested_belief", "reported", float(nested.get("confidence", .8)),
                str(nested.get("source", "mental_language")),
                [str(x).lower() for x in nested.get("path", [])],
                Proposition.from_surface(str(nested.get("proposition_text", "")), polarity=bool(nested.get("polarity", True))),
                dict(nested), ["native-mental-language"],
            ))
        drive = MentalLanguagePerception.parse_drive(text)
        if drive:
            kind = str(drive.get("kind", "goal"))
            out.append(SemanticEvent(
                kind, {"goal": "desired", "fear": "feared", "expectation": "expected"}.get(kind, "unknown"),
                float(drive.get("confidence", .8)), str(drive.get("source", "mental_language")),
                [str(drive.get("holder", "")).lower()],
                Proposition.from_surface(str(drive.get("proposition_text", ""))),
                dict(drive), ["native-mental-language"],
            ))
        belief = MentalLanguagePerception.parse_direct_belief(text)
        if belief:
            out.append(SemanticEvent(
                "belief", "believed", float(belief.get("confidence", .8)), str(belief.get("source", "mental_language")),
                [str(belief.get("holder", "")).lower()],
                Proposition.from_surface(str(belief.get("proposition_text", "")), polarity=bool(belief.get("polarity", True))),
                dict(belief), ["native-mental-language"],
            ))
        outcome = MentalLanguagePerception.parse_self_outcome(text)
        if outcome:
            out.append(SemanticEvent(
                "self_outcome", "asserted", float(outcome.get("confidence", .8)), str(outcome.get("source", "mental_language")),
                ["self"], None, dict(outcome), ["native-mental-language"],
            ))
        world = cls._WORLD.match(text)
        if world:
            out.append(SemanticEvent(
                "observation", "asserted", .95, "world-language", ["__world__"],
                Proposition.from_surface(world.group("prop")), {"proposition_text": world.group("prop")}, ["world-assertion"],
            ))
        return out

    @staticmethod
    def _priority(event: SemanticEvent) -> int:
        # More specifically scoped events beat broader proposition reports.
        return {
            "nested_belief": 70,
            "self_outcome": 65,
            "fear": 60,
            "expectation": 60,
            "goal": 60,
            "belief": 50,
            "observation": 45,
            "question": 10,
            "other": 0,
        }.get(event.event_type, 0)

    def proposal_allowed(self, text: str, proposal) -> tuple[bool, str | None]:
        """Pre-persistence consistency gate for neural/external proposals."""
        if "?" in text or self._QUESTION.match(text):
            if proposal.kind in {"belief", "nested_belief", "drive", "self_outcome"}:
                self.conflicts_blocked += 1
                return False, "semantic_query_guard"
        if self._HYPOTHETICAL.search(text) and proposal.kind in {"belief", "nested_belief", "drive"}:
            self.hypotheticals_abstained += 1
            return False, "semantic_hypothetical_guard"

        native = self._native_candidates(text)
        native_types = {x.event_type for x in native}
        ptype = proposal.kind
        if ptype == "drive":
            ptype = str(proposal.payload.get("kind", "goal"))

        # Explicitly typed native drives beat the broad historical belief parser.
        if ptype == "belief" and native_types & {"goal", "fear", "expectation", "nested_belief", "self_outcome"}:
            self.conflicts_blocked += 1
            return False, "semantic_type_conflict"
        if ptype == "nested_belief" and native_types & {"goal", "fear", "expectation", "self_outcome"}:
            self.conflicts_blocked += 1
            return False, "semantic_type_conflict"
        if ptype in {"goal", "fear", "expectation"} and "self_outcome" in native_types:
            self.conflicts_blocked += 1
            return False, "semantic_type_conflict"
        return True, None

    def interpret(self, text: str, language_events: Mapping[str, Any]) -> SemanticDecision:
        self.events_seen += 1
        if "?" in text or self._QUESTION.match(text):
            event = SemanticEvent("question", "queried", .99, "semantic-cortex", [], None, {}, ["question-guard"], False)
            return SemanticDecision(event, reason="question")

        candidates: list[SemanticEvent] = []
        for proposal in language_events.get("_accepted", []):
            event = self._event_from_proposal(
                proposal.get("kind", ""), proposal.get("payload", {}),
                float(proposal.get("confidence", 0.0)), str(proposal.get("source", "language_core")),
            )
            if event:
                candidates.append(event)
        candidates.extend(self._native_candidates(text))

        if not candidates:
            return SemanticDecision(SemanticEvent("other", "unknown", .0, "semantic-cortex", persistent_eligible=False), reason="no_semantic_event")

        # Deduplicate equivalent candidates while preserving evidence sources.
        unique: dict[tuple, SemanticEvent] = {}
        for event in candidates:
            key = (
                event.event_type,
                tuple(event.agents),
                event.proposition.canonical if event.proposition else "",
                event.proposition.truth if event.proposition else None,
            )
            if key in unique:
                old = unique[key]
                old.confidence = max(old.confidence, event.confidence)
                old.evidence.extend(x for x in event.evidence if x not in old.evidence)
                if old.source != event.source:
                    old.evidence.append(f"corroborated:{event.source}")
            else:
                unique[key] = event
        candidates = list(unique.values())
        candidates.sort(key=lambda e: (self._priority(e), e.confidence), reverse=True)
        primary = candidates[0]
        alternatives = candidates[1:]

        conflicts = []
        for other in alternatives:
            if other.event_type != primary.event_type:
                shared_agent = bool(set(primary.agents) & set(other.agents))
                shared_prop = bool(primary.proposition and other.proposition and primary.proposition.canonical == other.proposition.canonical)
                if shared_agent and shared_prop:
                    conflicts.append({
                        "blocked_type": other.event_type,
                        "kept_type": primary.event_type,
                        "reason": "same-agent-proposition-type-conflict",
                    })

        if conflicts:
            self.conflicts_blocked += len(conflicts)

        hypothetical = bool(self._HYPOTHETICAL.search(text))
        abstained = False
        reason = "typed_event"
        if hypothetical and primary.event_type in {"belief", "nested_belief", "goal", "fear", "expectation"}:
            primary.epistemic = "hypothetical"
            primary.persistent_eligible = False
            abstained = True
            reason = "hypothetical_not_persisted"
            self.hypotheticals_abstained += 1

        return SemanticDecision(primary, alternatives, conflicts, abstained, reason)

    @staticmethod
    def workspace_features(decision: SemanticDecision) -> dict[str, float]:
        event = decision.primary
        out = {
            f"SEMEVENT:TYPE:{event.event_type.upper()}": max(.25, event.confidence),
            f"SEMEVENT:EPISTEMIC:{event.epistemic.upper()}": max(.25, event.confidence),
        }
        for agent in event.agents[:3]:
            if agent:
                out[f"SEMEVENT:AGENT:{agent.lower()}"] = max(.20, .8 * event.confidence)
        if decision.conflicts:
            out["SEMEVENT:CONFLICT_BLOCKED"] = 1.0
        if decision.abstained:
            out["SEMEVENT:ABSTAIN"] = 1.0
        return out

    def health(self) -> dict:
        return {
            "ready": True,
            "architecture": "typed-semantic-event-arbitration",
            "events_seen": self.events_seen,
            "conflicts_blocked": self.conflicts_blocked,
            "hypotheticals_abstained": self.hypotheticals_abstained,
            "event_types": sorted(EVENT_TYPES),
            "epistemic_states": sorted(EPISTEMIC),
        }
