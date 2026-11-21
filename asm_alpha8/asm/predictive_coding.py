from __future__ import annotations

from typing import Dict, List, Tuple

from .config import ASMConfig


class PredictiveCodingLearner:
    """
    Local prediction-error learning.

    Each active source concept predicts concepts in the next field state.
    Learning uses only:
      - source activation
      - local predicted target activation
      - actual target activation

    Positive error strengthens the responsible connection.
    False predictions are weakened.

    This is deliberately local: there is no global backpropagation through a
    deep network.
    """

    def __init__(self, config: ASMConfig):
        self.cfg = config
        self.weights: Dict[str, Dict[str, float]] = {}

    def predict(
        self,
        previous: List[Tuple[str, float]],
        limit: int = 32,
    ) -> Dict[str, float]:
        scores: Dict[str, float] = {}
        for src, src_act in previous[:16]:
            for dst, weight in self.weights.get(src, {}).items():
                scores[dst] = scores.get(dst, 0.0) + abs(src_act) * weight

        positive = [(k, v) for k, v in scores.items() if v > 0.0]
        positive.sort(key=lambda kv: kv[1], reverse=True)
        positive = positive[:limit]

        if not positive:
            return {}

        peak = max(v for _, v in positive) or 1.0
        return {
            k: min(1.0, v / peak)
            for k, v in positive
        }

    def learn(
        self,
        previous: List[Tuple[str, float]],
        current: List[Tuple[str, float]],
    ) -> float:
        if not previous or not current:
            return 0.0

        target = {
            k: min(1.0, abs(v))
            for k, v in current[:20]
        }
        predicted = self.predict(previous, limit=64)

        all_targets = set(target) | set(predicted)
        if not all_targets:
            return 0.0

        absolute_error = 0.0
        for dst in all_targets:
            actual = target.get(dst, 0.0)
            pred = predicted.get(dst, 0.0)
            error = actual - pred
            absolute_error += abs(error)

            for src, src_act in previous[:16]:
                act = abs(src_act)
                if act <= 0.0:
                    continue

                out = self.weights.setdefault(src, {})
                old = out.get(dst, 0.0)

                if error >= 0.0:
                    delta = self.cfg.prediction_lr * act * error
                else:
                    # Wrong predictions are actively unlearned.
                    delta = self.cfg.prediction_decay_lr * act * error

                new = old + self.cfg.predictive_error_gain * delta
                # Small continuous shrinkage prevents ancient weak links from
                # accumulating forever.
                new *= (1.0 - 0.001)

                if abs(new) < 1e-4:
                    out.pop(dst, None)
                else:
                    out[dst] = max(-1.0, min(1.0, new))

                if len(out) > self.cfg.max_prediction_fanout:
                    strongest = sorted(
                        out.items(),
                        key=lambda kv: abs(kv[1]),
                        reverse=True,
                    )[: self.cfg.max_prediction_fanout]
                    self.weights[src] = dict(strongest)

        return absolute_error / max(1, len(all_targets))

    def prune(self) -> int:
        removed = 0
        threshold = self.cfg.predictor_prune_threshold
        for src in list(self.weights):
            out = self.weights[src]
            for dst in list(out):
                if abs(out[dst]) < threshold:
                    del out[dst]
                    removed += 1
            if not out:
                del self.weights[src]
        return removed

    def export_state(self) -> dict:
        return self.weights

    def import_state(self, payload: dict) -> None:
        self.weights = {
            str(src): {
                str(dst): float(weight)
                for dst, weight in out.items()
            }
            for src, out in payload.items()
        }
