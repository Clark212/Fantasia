from __future__ import annotations

from collections import Counter
from math import log
import re
from typing import Dict, Iterable, List, Optional

from .config import ASMConfig
from .encoder import ConceptEncoder
from .parsing import StructuralParser


class EmotionLearner:
    """
    Learns emotion labels from examples instead of requiring a fixed emotion
    ontology.

    Example:
        "Maya felt disappointed because the goal failed"

    The label "disappointed" is learned as a prototype over contextual stems,
    structural cues and any active latent concepts supplied by ASM.
    """

    LABELED_RE = re.compile(
        r"^\s*(?P<agent>[A-Za-z][A-Za-z0-9_-]*)\s+"
        r"(?:felt|feels|is feeling|was feeling)\s+"
        r"(?P<label>[A-Za-z][A-Za-z_-]*)\s+"
        r"(?:because|when|after)\s+"
        r"(?P<context>.+?)\s*[.!]?\s*$",
        re.I,
    )

    def __init__(
        self,
        config: ASMConfig,
        encoder: ConceptEncoder,
        parser: StructuralParser,
    ):
        self.cfg = config
        self.encoder = encoder
        self.parser = parser
        self.labels: Dict[str, dict] = {}
        self.agent_states: Dict[str, dict] = {}

    def features(
        self,
        text: str,
        latent_concepts: Iterable[str] = (),
    ) -> List[str]:
        feats = [f"STEM:{s}" for s in self.encoder.content_stems(text)]
        frame = self.parser.parse(text)

        if frame.supported:
            feats.extend(f"REL:{r}" for r in frame.signature())
        feats.extend(f"CUE:{cue}" for cue in frame.cues)
        feats.extend(f"INTERNAL:{cid}" for cid in latent_concepts)

        return list(dict.fromkeys(feats))

    def observe_labeled(
        self,
        text: str,
        event_id: int,
        latent_concepts: Iterable[str] = (),
    ) -> Optional[dict]:
        m = self.LABELED_RE.match(text)
        if not m:
            return None

        agent = m.group("agent").lower()
        label = m.group("label").lower()
        context = m.group("context")

        feats = self.features(context, latent_concepts)
        if not feats:
            return None

        rec = self.labels.setdefault(
            label,
            {
                "examples": 0,
                "feature_counts": {},
                "last_event": 0,
            },
        )
        rec["examples"] = int(rec.get("examples", 0)) + 1
        rec["last_event"] = event_id

        counts = Counter(rec.get("feature_counts", {}))
        counts.update(feats)
        if len(counts) > self.cfg.emotion_max_features:
            counts = Counter(dict(counts.most_common(self.cfg.emotion_max_features)))
        rec["feature_counts"] = dict(counts)

        self.agent_states[agent] = {
            "label": label,
            "confidence": 1.0,
            "source": "explicit",
            "event_id": event_id,
        }

        return {
            "agent": agent,
            "label": label,
            "context": context,
            "features": feats,
        }

    def infer(
        self,
        text: str,
        latent_concepts: Iterable[str] = (),
        limit: int = 5,
    ) -> List[dict]:
        query = set(self.features(text, latent_concepts))
        if not query:
            return []

        ready = {
            label: rec
            for label, rec in self.labels.items()
            if int(rec.get("examples", 0)) >= self.cfg.emotion_min_examples
        }
        if not ready:
            return []

        label_count = len(ready)
        df = Counter()
        for rec in ready.values():
            df.update(set(rec.get("feature_counts", {})))

        results = []
        for label, rec in ready.items():
            examples = max(1, int(rec.get("examples", 1)))
            weights = {
                feat: count / examples
                for feat, count in rec.get("feature_counts", {}).items()
            }

            numerator = 0.0
            denominator = 0.0
            matched = []
            for feat, weight in weights.items():
                idf = log((1 + label_count) / (1 + df[feat])) + 1.0
                contribution = weight * idf
                denominator += contribution
                if feat in query:
                    numerator += contribution
                    matched.append((feat, contribution))

            score = numerator / denominator if denominator else 0.0
            if score >= self.cfg.emotion_min_score:
                matched.sort(key=lambda x: x[1], reverse=True)
                results.append({
                    "emotion": label,
                    "score": score,
                    "examples": examples,
                    "matched_features": [f for f, _ in matched[:8]],
                })

        results.sort(key=lambda x: (-x["score"], -x["examples"], x["emotion"]))
        return results[:limit]

    def update_agent_from_event(
        self,
        agent: str,
        text: str,
        event_id: int,
        latent_concepts: Iterable[str] = (),
    ) -> Optional[dict]:
        ranked = self.infer(text, latent_concepts, limit=1)
        if not ranked:
            return None

        best = ranked[0]
        self.agent_states[agent.lower()] = {
            "label": best["emotion"],
            "confidence": best["score"],
            "source": "inferred",
            "event_id": event_id,
        }
        return dict(self.agent_states[agent.lower()])

    def export_state(self) -> dict:
        return {
            "labels": self.labels,
            "agent_states": self.agent_states,
        }

    def import_state(self, payload: dict) -> None:
        self.labels = {
            str(label): dict(rec)
            for label, rec in payload.get("labels", {}).items()
        }
        self.agent_states = {
            str(agent): dict(state)
            for agent, state in payload.get("agent_states", {}).items()
        }
