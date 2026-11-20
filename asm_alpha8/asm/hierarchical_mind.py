from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from .config import ASMConfig
from .mind import canonical_proposition
from .mental_language import MentalLanguagePerception


class HierarchicalMindModel:
    """
    Nested belief model up to configurable order.

    A path is a tuple of minds:
      ("alice",)               Alice believes X
      ("alice", "bob")         Alice believes Bob believes X
      ("alice", "bob", "cara") Alice believes Bob believes Cara believes X

    The store is explicitly perspectival: updating one path does not rewrite
    reality or another path.
    """

    BELIEF_WORDS = ("believes", "believe", "thinks", "think", "assumes", "assume")

    def __init__(self, config: ASMConfig):
        self.cfg = config
        self.states: Dict[str, Dict[str, dict]] = {}

    @staticmethod
    def _path_key(path: Tuple[str, ...]) -> str:
        return ">>".join(x.lower() for x in path)

    def _slot(self, path: Tuple[str, ...], proposition: str) -> dict:
        key = self._path_key(path)
        return self.states.setdefault(key, {}).setdefault(
            proposition,
            {
                "true_evidence": 0.0,
                "false_evidence": 0.0,
                "observations": 0,
                "last_event": 0,
            },
        )

    def observe(
        self,
        path: Tuple[str, ...],
        proposition: str,
        truth: bool,
        event_id: int,
        confidence: float = 1.0,
    ) -> dict:
        if not path:
            raise ValueError("nested belief path cannot be empty")
        if len(path) > self.cfg.nested_belief_max_order:
            path = path[: self.cfg.nested_belief_max_order]

        slot = self._slot(path, proposition)
        t = float(slot.get("true_evidence", 0.0)) * self.cfg.nested_belief_decay
        f = float(slot.get("false_evidence", 0.0)) * self.cfg.nested_belief_decay

        conf = max(0.0, min(1.0, float(confidence)))
        opposite = f if truth else t
        gain = conf * (
            self.cfg.nested_revision_gain
            if opposite > 0.0
            else 1.0
        )

        if truth:
            t += gain
        else:
            f += gain

        slot.update(
            true_evidence=t,
            false_evidence=f,
            observations=int(slot.get("observations", 0)) + 1,
            last_event=int(event_id),
        )
        return self.query_base(path, proposition)

    def query_base(self, path: Tuple[str, ...], proposition: str) -> dict:
        key = self._path_key(path)
        slot = self.states.get(key, {}).get(proposition)
        if not slot:
            return {
                "path": list(path),
                "order": len(path),
                "proposition": proposition,
                "status": "unknown",
                "truth": None,
                "confidence": 0.0,
            }

        t = float(slot.get("true_evidence", 0.0))
        f = float(slot.get("false_evidence", 0.0))
        total = t + f
        if total <= 0:
            truth = None
            confidence = 0.0
            status = "unknown"
        else:
            p_true = t / total
            margin = abs(p_true - 0.5)
            if margin < self.cfg.belief_confidence_margin:
                truth = None
                confidence = 2 * margin
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
            "path": list(path),
            "order": len(path),
            "proposition": proposition,
            "status": status,
            "truth": truth,
            "confidence": confidence,
            "true_evidence": t,
            "false_evidence": f,
            "observations": int(slot.get("observations", 0)),
            "last_event": int(slot.get("last_event", 0)),
        }

    def query(self, path: Tuple[str, ...], proposition: str) -> dict:
        base, _ = canonical_proposition(proposition)
        return self.query_base(path, base)

    def parse_text(self, text: str, event_id: int) -> Optional[dict]:
        """
        Parse controlled nested forms such as:
          Alice believes Bob believes that the door is locked
          Alice thinks Bob thinks Cara believes X

        This remains a bootstrap parser, not unrestricted language understanding.
        """
        raw = " ".join(text.strip().rstrip(".!?").split())
        if not raw:
            return None

        tokens = raw.split()
        path: List[str] = []
        i = 0

        while i + 1 < len(tokens) and len(path) < self.cfg.nested_belief_max_order:
            holder = tokens[i]
            verb = tokens[i + 1].lower()
            if verb not in self.BELIEF_WORDS:
                break

            path.append(holder.lower())
            i += 2

            # If the next chunk starts with "that", remaining text is proposition.
            if i < len(tokens) and tokens[i].lower() == "that":
                i += 1
                break

            # Continue only if next token appears to be another holder followed
            # by another belief verb; otherwise remaining text is proposition.
            if i + 1 >= len(tokens) or tokens[i + 1].lower() not in self.BELIEF_WORDS:
                break

        if not path or i >= len(tokens):
            natural = MentalLanguagePerception.parse_nested(
                text,
                max_order=self.cfg.nested_belief_max_order,
            )
            if not natural:
                return None
            base, truth = canonical_proposition(natural["proposition_text"])
            if not natural.get("polarity", True):
                truth = not truth
            state = self.observe(
                tuple(natural["path"]),
                base,
                truth,
                event_id,
                confidence=float(natural.get("confidence", 0.8)),
            )
            return {
                "type": "nested_belief",
                "path": natural["path"],
                "order": len(natural["path"]),
                "proposition": base,
                "asserted_truth": truth,
                "state": state,
                "source": natural.get("source", "mental_language"),
            }

        proposition_text = " ".join(tokens[i:])
        base, truth = canonical_proposition(proposition_text)
        state = self.observe(
            tuple(path),
            base,
            truth,
            event_id,
        )
        return {
            "type": "nested_belief",
            "path": path,
            "order": len(path),
            "proposition": base,
            "asserted_truth": truth,
            "state": state,
        }

    def concepts_for_event(self, event: dict | None) -> Dict[str, float]:
        if not event:
            return {}
        state = event["state"]
        truth = state.get("truth")
        truth_tag = "UNKNOWN" if truth is None else ("TRUE" if truth else "FALSE")
        path = ">".join(event["path"])
        prop = event["proposition"].replace(" ", "_")[:72]
        return {
            f"MIND:NESTED:{event['order']}:{path}:{truth_tag}:{prop}":
                0.72 + 0.28 * float(state.get("confidence", 0.0))
        }

    def export_state(self) -> dict:
        return {"states": self.states}

    def import_state(self, payload: dict) -> None:
        self.states = {
            str(path): {
                str(prop): dict(slot)
                for prop, slot in props.items()
            }
            for path, props in payload.get("states", {}).items()
        }
