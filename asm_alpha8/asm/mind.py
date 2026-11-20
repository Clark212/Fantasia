from __future__ import annotations

import re
from typing import Dict, Optional

from .config import ASMConfig
from .encoder import STOPWORDS, light_stem
from .mental_language import MentalLanguagePerception


WORD = re.compile(r"[A-Za-z0-9_+#'-]+")


def _normalize_text(text: str) -> str:
    text = text.lower().replace("’", "'").strip()
    text = re.sub(r"\s+", " ", text)
    replacements = {
        "isn't": "is not",
        "aren't": "are not",
        "wasn't": "was not",
        "weren't": "were not",
        "doesn't": "does not",
        "don't": "do not",
        "didn't": "did not",
        "can't": "can not",
        "cannot": "can not",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text.strip(" .!?")


def canonical_proposition(text: str) -> tuple[str, bool]:
    """
    Return (base proposition, asserted truth value).

    Direct negation and a few high-value outcome/state oppositions are normalized
    into the same proposition slot so natural paraphrases can revise an existing
    belief rather than creating unrelated keys.

    Examples:
      "mission succeeds"      -> ("mission succeed", True)
      "mission failed"        -> ("mission succeed", False)
      "storm continues"       -> ("storm continue", True)
      "storm was gone"        -> ("storm continue", False)
    """
    raw = _normalize_text(text)

    # Strip a leading coreference pronoun when a caller already knows the holder.
    raw = re.sub(r"^(?:he|she|they|i)\s+(?:had\s+|has\s+|was\s+|is\s+)?", "", raw)

    explicit_negative = bool(re.search(r"\b(?:not|never|no)\b", raw))
    semantic_negative = False

    # Normalize success/failure onto one proposition.
    if re.search(r"\b(?:fail|fails|failed|failure)\b", raw):
        semantic_negative = not semantic_negative
        raw = re.sub(r"\b(?:fail|fails|failed|failure)\b", "succeed", raw)
    raw = re.sub(r"\b(?:success|successful|successfully|succeeds|succeeded)\b", "succeed", raw)

    # Normalize persistence/termination onto one proposition.
    if re.search(r"\b(?:gone|ended|finished|stopped|ceased)\b", raw):
        semantic_negative = not semantic_negative
        raw = re.sub(r"\b(?:gone|ended|finished|stopped|ceased)\b", "continue", raw)
    raw = re.sub(r"\b(?:continue|continues|continued|continuing|remain|remains|remained|remaining)\b", "continue", raw)
    raw = re.sub(r"\bstill\s+going\b", "continue", raw)

    # Auxiliary remnants do not define the proposition.
    raw = re.sub(r"\b(?:had|has|have|would|will|did|does|do)\b", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()

    tokens = []
    for token in WORD.findall(raw):
        if token in {"not", "never", "no"}:
            continue
        if token in STOPWORDS:
            continue
        if token.endswith("eed"):
            stem = token
        elif token.endswith("ues") and len(token) > 4:
            stem = token[:-1]
        elif token.endswith("ued") and len(token) > 4:
            stem = token[:-1]
        else:
            stem = light_stem(token)
        tokens.append(stem)

    negative = bool(explicit_negative) ^ bool(semantic_negative)
    return " ".join(tokens[:16]) or "unknown", not negative


class AgentMindModel:
    """
    Minimal explicit belief-state model.

    Reality and each agent get separate proposition stores. Observing a new
    contradictory belief revises that agent's state without rewriting reality
    or anybody else's beliefs.
    """

    BELIEF_RE = re.compile(
        r"^\s*(?P<holder>[A-Za-z][A-Za-z0-9_-]*)\s+"
        r"(?:believes?|thinks?|assumes?|expects?)\s+"
        r"(?:that\s+)?(?P<prop>.+?)\s*[.!]?\s*$",
        re.I,
    )

    REALITY_RE = re.compile(
        r"^\s*(?:actually|in reality|reality|fact)\s*[:,]?\s*(?P<prop>.+?)\s*[.!]?\s*$",
        re.I,
    )

    def __init__(self, config: ASMConfig):
        self.cfg = config
        self.states: Dict[str, Dict[str, dict]] = {}

    def _slot(self, holder: str, base: str) -> dict:
        holder = holder.lower()
        return self.states.setdefault(holder, {}).setdefault(
            base,
            {
                "true_evidence": 0.0,
                "false_evidence": 0.0,
                "observations": 0,
                "last_event": 0,
            },
        )

    def _observe(
        self,
        holder: str,
        proposition: str,
        truth: bool,
        event_id: int,
    ) -> dict:
        slot = self._slot(holder, proposition)

        t = float(slot.get("true_evidence", 0.0))
        f = float(slot.get("false_evidence", 0.0))

        # Old evidence decays when the same holder provides a new state for the
        # same proposition. Contradiction gets a little extra revision weight.
        t *= self.cfg.belief_decay
        f *= self.cfg.belief_decay

        opposite = f if truth else t
        gain = (
            self.cfg.belief_revision_gain
            if opposite > 0.0
            else self.cfg.belief_observation_gain
        )

        if truth:
            t += gain
        else:
            f += gain

        slot.update(
            true_evidence=t,
            false_evidence=f,
            observations=int(slot.get("observations", 0)) + 1,
            last_event=event_id,
        )
        return self.query_base(holder, proposition)

    def observe_proposition(
        self,
        holder: str,
        proposition_text: str,
        event_id: int,
        *,
        polarity: bool = True,
        source: str = "language_core",
    ) -> dict:
        base, truth = canonical_proposition(proposition_text)
        if not polarity:
            truth = not truth
        state = self._observe(holder.lower(), base, truth, event_id)
        return {
            "type": "belief",
            "holder": holder.lower(),
            "proposition": base,
            "asserted_truth": truth,
            "state": state,
            "source": source,
        }

    def observe_text(self, text: str, event_id: int) -> Optional[dict]:
        m = self.BELIEF_RE.match(text)
        if m:
            base, truth = canonical_proposition(m.group("prop"))
            state = self._observe(
                m.group("holder").lower(),
                base,
                truth,
                event_id,
            )
            return {
                "type": "belief",
                "holder": m.group("holder").lower(),
                "proposition": base,
                "asserted_truth": truth,
                "state": state,
            }

        m = self.REALITY_RE.match(text)
        if m:
            base, truth = canonical_proposition(m.group("prop"))
            state = self._observe(
                "__world__",
                base,
                truth,
                event_id,
            )
            return {
                "type": "world",
                "holder": "__world__",
                "proposition": base,
                "asserted_truth": truth,
                "state": state,
            }

        natural = MentalLanguagePerception.parse_direct_belief(text)
        if natural:
            base, truth = canonical_proposition(natural["proposition_text"])
            if not natural.get("polarity", True):
                truth = not truth
            state = self._observe(
                natural["holder"],
                base,
                truth,
                event_id,
            )
            return {
                "type": "belief",
                "holder": natural["holder"],
                "proposition": base,
                "asserted_truth": truth,
                "state": state,
                "source": natural.get("source", "mental_language"),
                "confidence": natural.get("confidence", 0.8),
            }

        return None

    def query_base(self, holder: str, base: str) -> dict:
        holder = holder.lower()
        slot = self.states.get(holder, {}).get(base)
        if not slot:
            return {
                "holder": holder,
                "proposition": base,
                "status": "unknown",
                "truth": None,
                "confidence": 0.0,
                "true_evidence": 0.0,
                "false_evidence": 0.0,
                "observations": 0,
            }

        t = float(slot.get("true_evidence", 0.0))
        f = float(slot.get("false_evidence", 0.0))
        total = t + f

        if total <= 0:
            confidence = 0.0
            truth = None
            status = "unknown"
        else:
            p_true = t / total
            margin = abs(p_true - 0.5)
            if margin < self.cfg.belief_confidence_margin:
                truth = None
                confidence = 2.0 * margin
                status = "uncertain"
            elif p_true > 0.5:
                truth = True
                confidence = p_true
                status = "believed_true"
            else:
                truth = False
                confidence = 1.0 - p_true
                status = "believed_false"

        return {
            "holder": holder,
            "proposition": base,
            "status": status,
            "truth": truth,
            "confidence": confidence,
            "true_evidence": t,
            "false_evidence": f,
            "observations": int(slot.get("observations", 0)),
            "last_event": int(slot.get("last_event", 0)),
        }

    def query(self, holder: str, proposition: str) -> dict:
        base, requested_truth = canonical_proposition(proposition)
        state = self.query_base(holder, base)
        state = dict(state)
        state["query_truth_form"] = requested_truth
        return state

    def compare_world_and_agent(self, holder: str, proposition: str) -> dict:
        return {
            "world": self.query("__world__", proposition),
            "agent": self.query(holder, proposition),
        }

    def concept_for_event(self, event: dict | None) -> Dict[str, float]:
        if not event:
            return {}
        state = event["state"]
        truth = state.get("truth")
        truth_tag = (
            "UNKNOWN"
            if truth is None
            else ("TRUE" if truth else "FALSE")
        )
        holder = event["holder"]
        proposition = event["proposition"].replace(" ", "_")[:80]
        return {
            f"MIND:{event['type'].upper()}:{holder}:{truth_tag}:{proposition}":
                0.75 + 0.35 * float(state.get("confidence", 0.0))
        }

    def export_state(self) -> dict:
        return {"states": self.states}

    def import_state(self, payload: dict) -> None:
        self.states = {
            str(holder): {
                str(prop): dict(slot)
                for prop, slot in props.items()
            }
            for holder, props in payload.get("states", {}).items()
        }
