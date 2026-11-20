"""Bounded in-memory experience store with deterministic deduplication."""
from __future__ import annotations

from collections import OrderedDict
from threading import RLock
from .experience import Experience


class ExperienceStore:
    def __init__(self, capacity: int = 50_000) -> None:
        if not isinstance(capacity, int) or capacity < 1:
            raise ValueError("capacity must be a positive integer")
        self.capacity = capacity
        self._items: OrderedDict[str, Experience] = OrderedDict()
        self._fingerprints: set[str] = set()
        self._lock = RLock()
        self.dropped_oldest = 0
        self.duplicates = 0

    def add(self, experience: Experience) -> bool:
        if not isinstance(experience, Experience):
            raise TypeError("only Experience records may be stored")
        with self._lock:
            if experience.experience_id in self._items or experience.fingerprint in self._fingerprints:
                self.duplicates += 1
                return False
            self._items[experience.experience_id] = experience
            self._fingerprints.add(experience.fingerprint)
            if len(self._items) > self.capacity:
                _, removed = self._items.popitem(last=False)
                self._fingerprints.discard(removed.fingerprint)
                self.dropped_oldest += 1
            return True

    def get(self, experience_id: str) -> Experience | None:
        with self._lock:
            return self._items.get(experience_id)

    def recent(self, limit: int = 100, *, domain: str | None = None) -> list[Experience]:
        if limit < 0:
            raise ValueError("limit must be non-negative")
        with self._lock:
            values = reversed(self._items.values())
            result = [x for x in values if domain is None or x.domain == domain]
            return list(reversed(result[:limit]))

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {"size": len(self._items), "capacity": self.capacity,
                    "duplicates": self.duplicates, "dropped_oldest": self.dropped_oldest}
