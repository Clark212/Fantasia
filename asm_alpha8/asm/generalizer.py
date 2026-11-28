from __future__ import annotations

import re
from collections import defaultdict
from math import exp
from typing import Dict, Iterable, List, Tuple

from .config import ASMConfig
from .encoder import light_stem, STOPWORDS, TOKEN_RE


RELATION_SPLIT = re.compile(r"\s*(?:=>|->|→)\s*")


class LocalRuleLearner:
    """
    Sparse local rule learner for explicit experience pairs.

    Example:
        red cube => left
        blue cube => right
        red sphere => left

    It learns feature -> outcome weights rather than memorizing whole strings.
    Therefore:
        red pyramid
    can generalize to:
        left

    This is intentionally simple, online, sparse, and inspectable.
    """

    def __init__(self, config: ASMConfig):
        self.cfg = config
        self.weights: Dict[str, Dict[str, float]] = {}
        self.outcomes: set[str] = set()

    def parse_example(self, text: str):
        parts = RELATION_SPLIT.split(text.strip(), maxsplit=1)
        if len(parts) != 2:
            return None

        left, right = parts
        features = self._features(left)
        targets = self._targets(right)
        if not features or not targets:
            return None
        return features, targets

    def _features(self, text: str) -> List[str]:
        toks = [
            m.group(0).lower()
            for m in TOKEN_RE.finditer(text)
        ]
        stems = [
            light_stem(t)
            for t in toks
            if t not in STOPWORDS
        ]

        result = []
        seen = set()

        for s in stems:
            key = f"F:{s}"
            if key not in seen:
                seen.add(key)
                result.append(key)

        # Lightweight pair features capture useful conjunctions without making
        # the learner depend entirely on exact examples.
        for a, b in zip(stems, stems[1:]):
            key = f"P:{a}+{b}"
            if key not in seen:
                seen.add(key)
                result.append(key)

        return result[: self.cfg.rule_max_features]

    def _targets(self, text: str) -> List[str]:
        toks = [
            light_stem(m.group(0).lower())
            for m in TOKEN_RE.finditer(text)
            if m.group(0).lower() not in STOPWORDS
        ]
        return [f"O:{t}" for t in toks[:4]]

    def learn_example(self, text: str) -> dict | None:
        parsed = self.parse_example(text)
        if parsed is None:
            return None

        features, targets = parsed
        target_set = set(targets)
        self.outcomes.update(target_set)

        scores_before = self.predict_features(features)

        # Positive local updates.
        for feature in features:
            out = self.weights.setdefault(feature, {})
            for target in target_set:
                old = out.get(target, 0.0)
                out[target] = old + self.cfg.rule_lr * (1.0 - old)

            # Weak negative updates for competing outcomes the current feature
            # had predicted but this example contradicted.
            for other in list(out):
                if other in target_set:
                    continue
                if out[other] > 0.0:
                    out[other] -= self.cfg.rule_negative_lr * out[other]

            # L2-ish shrinkage.
            for outcome in list(out):
                out[outcome] *= (1.0 - self.cfg.rule_l2_decay)
                if abs(out[outcome]) < 1e-5:
                    del out[outcome]

        return {
            "features": features,
            "targets": targets,
            "before": scores_before,
            "after": self.predict_features(features),
        }

    def predict_text(self, text: str, limit: int = 5) -> List[Tuple[str, float]]:
        return self.predict_features(
            self._features(text),
            limit=limit,
        )

    def predict_features(
        self,
        features: Iterable[str],
        limit: int = 5,
    ) -> List[Tuple[str, float]]:
        features = list(features)
        if not features:
            return []

        raw: Dict[str, float] = defaultdict(float)
        support: Dict[str, int] = defaultdict(int)

        for feature in features:
            for outcome, weight in self.weights.get(feature, {}).items():
                if weight > 0.0:
                    raw[outcome] += weight
                    support[outcome] += 1

        if not raw:
            return []

        # Normalize by feature count, then add a small agreement bonus when
        # multiple independent features support the same outcome.
        scored = []
        for outcome, score in raw.items():
            normalized = score / max(1, len(features))
            agreement = min(1.0, support[outcome] / 3.0)
            confidence = min(1.0, normalized + 0.15 * agreement)
            if confidence >= self.cfg.rule_min_confidence:
                scored.append((outcome, confidence))

        scored.sort(key=lambda kv: kv[1], reverse=True)
        return scored[:limit]

    def export_state(self) -> dict:
        return {
            "weights": self.weights,
            "outcomes": sorted(self.outcomes),
        }

    def import_state(self, payload: dict) -> None:
        self.weights = {
            str(feature): {
                str(outcome): float(weight)
                for outcome, weight in out.items()
            }
            for feature, out in payload.get("weights", {}).items()
        }
        self.outcomes = set(
            str(x)
            for x in payload.get("outcomes", [])
        )
