"""Prediction comparison helpers; metrics are descriptive, not capability claims."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class PredictionMetrics:
    compared: int
    exact_matches: int
    numeric_mae: float | None


def _numeric_pairs(prediction: Any, outcome: Any):
    if isinstance(prediction, Mapping) and isinstance(outcome, Mapping):
        for key in prediction.keys() & outcome.keys():
            yield from _numeric_pairs(prediction[key], outcome[key])
    elif isinstance(prediction, (int, float)) and not isinstance(prediction, bool) and isinstance(outcome, (int, float)) and not isinstance(outcome, bool):
        a, b = float(prediction), float(outcome)
        if isfinite(a) and isfinite(b):
            yield abs(a - b)


def evaluate_predictions(records) -> PredictionMetrics:
    compared = exact = 0
    errors: list[float] = []
    for record in records:
        if record.prediction is None or record.outcome is None:
            continue
        compared += 1
        exact += int(record.prediction == record.outcome)
        errors.extend(_numeric_pairs(record.prediction, record.outcome))
    return PredictionMetrics(compared, exact, sum(errors) / len(errors) if errors else None)
