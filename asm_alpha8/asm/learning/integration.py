"""Evidence-aware intake: rank records for review, never auto-promote beliefs."""
from __future__ import annotations

from typing import Iterable
from .experience import Experience
from .store import ExperienceStore


class ExperienceIntegrator:
    def __init__(self, store: ExperienceStore) -> None:
        self.store = store

    @staticmethod
    def priority(record: Experience) -> float:
        score = 0.0
        if record.prediction is not None and record.outcome is not None:
            score += 0.35
            if record.prediction != record.outcome:
                score += 0.35
        if record.evidence_status == "observed":
            score += 0.20
        elif record.evidence_status == "labeled":
            score += 0.15
        elif record.evidence_status == "inferred":
            score += 0.05
        # Generated examples are deliberately not treated as independent evidence.
        if record.source in {"simulation", "interaction"}:
            score += 0.10
        return min(score, 1.0)

    def ingest(self, records: Iterable[Experience]) -> dict[str, int]:
        accepted = rejected = 0
        for record in records:
            if self.store.add(record):
                accepted += 1
            else:
                rejected += 1
        return {"accepted": accepted, "rejected_or_duplicate": rejected}

    def review_queue(self, limit: int = 100) -> list[tuple[float, Experience]]:
        ranked = [(self.priority(x), x) for x in self.store.recent(max(limit * 4, limit))]
        ranked.sort(key=lambda pair: (pair[0], pair[1].timestamp), reverse=True)
        return ranked[:limit]
