from __future__ import annotations

from typing import Dict, List, Tuple

from .config import ASMConfig


class TransitionPredictor:
    """
    Sparse online next-state predictor.

    It predicts future active concepts, not next text tokens.
    v0.1.1 adds pruning and per-source fanout caps.
    """

    def __init__(self, config: ASMConfig):
        self.cfg = config
        self.table: Dict[str, Dict[str, float]] = {}

    def predict(
        self,
        workspace: List[Tuple[str, float]],
        limit: int = 24,
    ) -> Dict[str, float]:
        scores: Dict[str, float] = {}
        for src, activation in workspace[:12]:
            for dst, strength in self.table.get(src, {}).items():
                scores[dst] = scores.get(dst, 0.0) + abs(activation) * strength

        if not scores:
            return {}

        top = sorted(
            scores.items(),
            key=lambda kv: kv[1],
            reverse=True,
        )[:limit]
        high = top[0][1] or 1.0
        return {k: max(0.0, v / high) for k, v in top if v > 0.0}

    def learn(
        self,
        previous: List[Tuple[str, float]],
        current: List[Tuple[str, float]],
    ) -> None:
        if not previous or not current:
            return

        for src, sa in previous[:12]:
            out = self.table.setdefault(src, {})
            for dst, da in current[:12]:
                target = abs(sa * da)
                old = out.get(dst, 0.0)
                out[dst] = old + self.cfg.prediction_lr * (target - old)

            # Keep only the strongest outgoing predictions.
            if len(out) > self.cfg.max_prediction_fanout:
                strongest = sorted(
                    out.items(),
                    key=lambda kv: kv[1],
                    reverse=True,
                )[: self.cfg.max_prediction_fanout]
                self.table[src] = dict(strongest)

    @staticmethod
    def surprise(
        prediction: Dict[str, float],
        observed: Dict[str, float],
    ) -> float:
        if not observed:
            return 0.0
        if not prediction:
            return 1.0

        obs_total = sum(abs(v) for v in observed.values()) or 1.0
        matched = 0.0
        for key, strength in observed.items():
            matched += abs(strength) * min(1.0, prediction.get(key, 0.0))
        return max(0.0, min(1.0, 1.0 - matched / obs_total))

    def prune(self) -> int:
        removed = 0
        threshold = self.cfg.predictor_prune_threshold
        for src in list(self.table):
            out = self.table[src]
            for dst in list(out):
                if out[dst] < threshold:
                    del out[dst]
                    removed += 1

            if len(out) > self.cfg.max_prediction_fanout:
                strongest = sorted(
                    out.items(),
                    key=lambda kv: kv[1],
                    reverse=True,
                )[: self.cfg.max_prediction_fanout]
                removed += len(out) - len(strongest)
                self.table[src] = dict(strongest)
                out = self.table[src]

            if not out:
                del self.table[src]

        return removed

    def export_state(self) -> dict:
        return self.table

    def import_state(self, payload: dict) -> None:
        self.table = {
            src: {dst: float(v) for dst, v in out.items()}
            for src, out in payload.items()
        }
