from __future__ import annotations

from collections import Counter
from math import log
import re
from typing import Dict, Iterable, List, Optional

from .config import ASMConfig
from .mind import canonical_proposition
from .mental_language import MentalLanguagePerception


class AppraisalSystem:
    """
    Persistent agent goals/fears/expectations + learned appraisal->emotion map.

    This is intentionally not a fixed "if goal failed => sad" table.
    Instead:
      1. ASM stores what an agent wants/fears/expects.
      2. Belief evidence says what that agent currently thinks is true.
      3. Appraisal features are derived from the relationship between the two.
      4. Emotion labels are learned from examples of those appraisal states.

    The hand-written part here is the small grammar that extracts explicit
    wants/fears/expects statements. The mapping from appraisal state to emotion
    label is learned.
    """

    WANT_RE = re.compile(
        r"^\s*(?P<agent>[A-Za-z][A-Za-z0-9_-]*)\s+"
        r"(?:wants?|wanted|hopes?|hoped)\s+"
        r"(?:that\s+)?(?P<prop>.+?)\s*[.!]?\s*$",
        re.I,
    )
    FEAR_RE = re.compile(
        r"^\s*(?P<agent>[A-Za-z][A-Za-z0-9_-]*)\s+"
        r"(?:fears?|feared|worries?|worried)\s+"
        r"(?:that\s+)?(?P<prop>.+?)\s*[.!]?\s*$",
        re.I,
    )
    EXPECT_RE = re.compile(
        r"^\s*(?P<agent>[A-Za-z][A-Za-z0-9_-]*)\s+"
        r"(?:expects?|expected|predicts?|predicted)\s+"
        r"(?:that\s+)?(?P<prop>.+?)\s*[.!]?\s*$",
        re.I,
    )

    def __init__(self, config: ASMConfig, minds):
        self.cfg = config
        self.minds = minds
        self.drives: Dict[str, List[dict]] = {}
        self.emotion_map: Dict[str, dict] = {}

    def observe_drive_proposal(
        self,
        holder: str,
        kind: str,
        proposition_text: str,
        event_id: int,
        *,
        priority: float | None = None,
        source: str = "language_core",
    ) -> dict | None:
        kind = str(kind).lower().strip()
        if kind not in {"goal", "fear", "expectation"}:
            return None
        base, truth = canonical_proposition(proposition_text)
        defaults = {
            "goal": self.cfg.appraisal_goal_priority_default,
            "fear": self.cfg.appraisal_fear_priority_default,
            "expectation": self.cfg.appraisal_expectation_priority_default,
        }
        rec = {
            "kind": kind,
            "proposition": base,
            "desired_truth": bool(truth),
            "priority": float(defaults[kind] if priority is None else priority),
            "event_id": int(event_id),
            "active": True,
            "source": source,
        }
        holder = str(holder).lower()
        bucket = self.drives.setdefault(holder, [])
        for i, existing in enumerate(bucket):
            if existing.get("kind") == kind and existing.get("proposition") == base:
                bucket[i] = rec
                break
        else:
            bucket.append(rec)
        return {"type": "drive", "holder": holder, **rec}

    def observe_drive(self, text: str, event_id: int) -> Optional[dict]:
        for regex, kind, priority in (
            (self.WANT_RE, "goal", self.cfg.appraisal_goal_priority_default),
            (self.FEAR_RE, "fear", self.cfg.appraisal_fear_priority_default),
            (self.EXPECT_RE, "expectation", self.cfg.appraisal_expectation_priority_default),
        ):
            m = regex.match(text)
            if not m:
                continue

            holder = m.group("agent").lower()
            base, truth = canonical_proposition(m.group("prop"))

            rec = {
                "kind": kind,
                "proposition": base,
                "desired_truth": bool(truth),
                "priority": float(priority),
                "event_id": int(event_id),
                "active": True,
            }

            bucket = self.drives.setdefault(holder, [])
            # Replace exact same kind/proposition goal instead of duplicating it.
            replaced = False
            for i, existing in enumerate(bucket):
                if (
                    existing.get("kind") == kind
                    and existing.get("proposition") == base
                ):
                    bucket[i] = rec
                    replaced = True
                    break
            if not replaced:
                bucket.append(rec)

            return {
                "type": "drive",
                "holder": holder,
                **rec,
            }

        natural = MentalLanguagePerception.parse_drive(text)
        if natural:
            holder = natural["holder"]
            base, truth = canonical_proposition(natural["proposition_text"])
            rec = {
                "kind": natural["kind"],
                "proposition": base,
                "desired_truth": bool(truth),
                "priority": float(natural.get("priority", 0.6)),
                "event_id": int(event_id),
                "active": True,
                "source": natural.get("source", "mental_language"),
            }
            bucket = self.drives.setdefault(holder, [])
            for i, existing in enumerate(bucket):
                if existing.get("kind") == rec["kind"] and existing.get("proposition") == base:
                    bucket[i] = rec
                    break
            else:
                bucket.append(rec)
            return {"type": "drive", "holder": holder, **rec}

        return None

    def _belief_for(self, holder: str, proposition: str) -> dict:
        return self.minds.query_base(holder, proposition)

    def appraisal_features(self, holder: str) -> List[str]:
        holder = holder.lower()
        features: List[str] = []

        for drive in self.drives.get(holder, []):
            if not drive.get("active", True):
                continue

            belief = self._belief_for(holder, drive["proposition"])
            believed_truth = belief.get("truth")
            confidence = float(belief.get("confidence", 0.0))
            if believed_truth is None or confidence <= 0.0:
                continue

            desired = bool(drive.get("desired_truth", True))
            kind = drive.get("kind")

            if kind == "goal":
                state = "GOAL_ACHIEVED" if believed_truth == desired else "GOAL_BLOCKED"
            elif kind == "fear":
                # A fear is undesirable. If the feared proposition's desired_truth
                # is True, believing True means the threat is present. If the fear
                # statement was explicitly negated, invert accordingly.
                state = "THREAT_PRESENT" if believed_truth == desired else "THREAT_REMOVED"
            elif kind == "expectation":
                state = "EXPECTATION_CONFIRMED" if believed_truth == desired else "EXPECTATION_VIOLATED"
            else:
                continue

            features.append(f"APPRAISAL:{state}")
            if confidence >= 0.8:
                features.append("APPRAISAL:HIGH_CONFIDENCE")
            elif confidence <= 0.55:
                features.append("APPRAISAL:LOW_CONFIDENCE")

        return list(dict.fromkeys(features))

    def _label_features(self, label: str) -> set[str]:
        rec = self.emotion_map.get(label, {})
        examples = max(1, int(rec.get("examples", 1)))
        return {
            feat
            for feat, count in rec.get("feature_counts", {}).items()
            if count / examples >= 0.25
        }

    def learn_emotion_from_agent(
        self,
        holder: str,
        label: str,
        event_id: int,
    ) -> Optional[dict]:
        feats = self.appraisal_features(holder)
        if not feats:
            return None

        label = label.lower()
        rec = self.emotion_map.setdefault(
            label,
            {"examples": 0, "feature_counts": {}, "last_event": 0},
        )
        rec["examples"] = int(rec.get("examples", 0)) + 1
        rec["last_event"] = int(event_id)

        counts = Counter(rec.get("feature_counts", {}))
        counts.update(feats)
        if len(counts) > self.cfg.appraisal_max_features:
            counts = Counter(dict(counts.most_common(self.cfg.appraisal_max_features)))
        rec["feature_counts"] = dict(counts)

        return {
            "holder": holder.lower(),
            "emotion": label,
            "appraisal_features": feats,
        }

    def infer_emotion_for_agent(self, holder: str, limit: int = 5) -> List[dict]:
        query = set(self.appraisal_features(holder))
        if not query:
            return []

        ready = {
            label: rec
            for label, rec in self.emotion_map.items()
            if int(rec.get("examples", 0)) >= self.cfg.appraisal_emotion_min_examples
        }
        if not ready:
            return []

        df = Counter()
        for label in ready:
            df.update(self._label_features(label))

        label_count = len(ready)
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
            if score >= self.cfg.appraisal_min_score:
                matched.sort(key=lambda x: x[1], reverse=True)
                results.append({
                    "emotion": label,
                    "score": score,
                    "source": "appraisal",
                    "appraisal_features": sorted(query),
                    "matched_features": [x for x, _ in matched[:8]],
                    "examples": examples,
                })

        results.sort(key=lambda x: (-x["score"], -x["examples"], x["emotion"]))
        return results[:limit]

    def concepts_for_agent(self, holder: str) -> Dict[str, float]:
        return {
            f"MIND:{feature}": 0.85
            for feature in self.appraisal_features(holder)
        }

    def export_state(self) -> dict:
        return {
            "drives": self.drives,
            "emotion_map": self.emotion_map,
        }

    def import_state(self, payload: dict) -> None:
        self.drives = {
            str(holder): [dict(x) for x in rows]
            for holder, rows in payload.get("drives", {}).items()
        }
        self.emotion_map = {
            str(label): dict(rec)
            for label, rec in payload.get("emotion_map", {}).items()
        }
