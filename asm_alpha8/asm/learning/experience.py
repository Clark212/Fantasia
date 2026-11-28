"""Canonical, provenance-aware records for ASM hybrid learning."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
import math
from typing import Any, Mapping

ALLOWED_SOURCES = {"dataset", "simulation", "interaction", "replay"}
ALLOWED_EVIDENCE = {"observed", "labeled", "inferred", "generated"}


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("experience values must be finite JSON-compatible data") from exc
    return value


@dataclass(frozen=True, slots=True)
class Experience:
    experience_id: str
    source: str
    domain: str
    task_id: str
    observation: Mapping[str, Any]
    prediction: Mapping[str, Any] | None = None
    outcome: Mapping[str, Any] | None = None
    evidence_status: str = "observed"
    timestamp: float = 0.0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("experience_id", "source", "domain", "task_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if self.source not in ALLOWED_SOURCES:
            raise ValueError(f"source must be one of {sorted(ALLOWED_SOURCES)}")
        if self.evidence_status not in ALLOWED_EVIDENCE:
            raise ValueError(f"evidence_status must be one of {sorted(ALLOWED_EVIDENCE)}")
        if not isinstance(self.observation, Mapping):
            raise ValueError("observation must be a mapping")
        if self.prediction is not None and not isinstance(self.prediction, Mapping):
            raise ValueError("prediction must be a mapping or None")
        if self.outcome is not None and not isinstance(self.outcome, Mapping):
            raise ValueError("outcome must be a mapping or None")
        if not math.isfinite(float(self.timestamp)):
            raise ValueError("timestamp must be finite")
        _json_safe(dict(self.observation)); _json_safe(self.prediction); _json_safe(self.outcome); _json_safe(dict(self.metadata))

    @property
    def fingerprint(self) -> str:
        payload = {"source": self.source, "evidence_status": self.evidence_status,
                   "domain": self.domain, "task_id": self.task_id,
                   "observation": self.observation, "prediction": self.prediction,
                   "outcome": self.outcome}
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return sha256(raw.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_mapping(cls, item: Mapping[str, Any], *, source: str | None = None,
                     evidence_status: str | None = None) -> "Experience":
        data = dict(item)
        if source is not None:
            data["source"] = source
        if evidence_status is not None:
            data["evidence_status"] = evidence_status
        return cls(**data)
