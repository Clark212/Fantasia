from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from .config import ASMConfig
from .parsing import StructuralFrame


@dataclass(slots=True)
class LatentMatch:
    concept_id: str
    score: float
    support: int
    promoted: bool


class EmergentConceptSystem:
    """
    Online latent concept formation.

    ASM does not receive a human-readable name for these concepts. Repeated
    co-active structural features are clustered and assigned internal IDs such
    as LATENT:000001.

    This is intentionally simple, but it is a real step away from requiring
    every abstraction to be named by the programmer.
    """

    def __init__(self, config: ASMConfig):
        self.cfg = config
        self.next_id = 1
        self.concepts: Dict[str, dict] = {}

    @staticmethod
    def frame_features(frame: StructuralFrame) -> List[str]:
        features: List[str] = []

        if frame.supported:
            signature = ">".join(frame.signature())
            if signature:
                features.append(f"SEQ:{signature}")
            for relation in frame.signature():
                features.append(f"REL:{relation}")

        for cue in frame.cues:
            features.append(f"CUE:{cue}")

        return list(dict.fromkeys(features))

    @staticmethod
    def _prototype_set(record: dict) -> set[str]:
        support = max(1, int(record.get("support", 1)))
        # Features that recur in at least ~35% of observations form the current
        # prototype. Strong one-off details are allowed to disappear naturally.
        return {
            feat
            for feat, count in record.get("feature_counts", {}).items()
            if count / support >= 0.35
        }

    def _score(self, query: set[str], record: dict) -> Tuple[float, int]:
        proto = self._prototype_set(record)
        if not query or not proto:
            return 0.0, 0

        shared = len(query & proto)
        if shared < self.cfg.latent_min_shared_features:
            return 0.0, shared

        # Partial observations should still be able to activate a learned
        # concept. Query coverage therefore matters more than symmetric Jaccard.
        coverage = shared / len(query)
        jaccard = shared / len(query | proto)
        score = 0.72 * coverage + 0.28 * jaccard
        return score, shared

    def match_features(self, features: Iterable[str]) -> List[LatentMatch]:
        query = set(features)
        matches: List[LatentMatch] = []

        for concept_id, record in self.concepts.items():
            score, _ = self._score(query, record)
            if score >= self.cfg.latent_match_threshold:
                matches.append(
                    LatentMatch(
                        concept_id=concept_id,
                        score=score,
                        support=int(record.get("support", 0)),
                        promoted=bool(record.get("promoted", False)),
                    )
                )

        matches.sort(key=lambda m: (-m.score, -m.support, m.concept_id))
        return matches

    def observe(self, features: Iterable[str], event_id: int) -> Optional[LatentMatch]:
        features = list(dict.fromkeys(features))
        if len(features) < self.cfg.latent_min_shared_features:
            return None

        matches = self.match_features(features)

        if matches:
            best = matches[0]
            record = self.concepts[best.concept_id]
        else:
            if len(self.concepts) >= self.cfg.latent_max_concepts:
                # Prefer forgetting the weakest unpromoted candidate.
                candidates = [
                    (cid, rec)
                    for cid, rec in self.concepts.items()
                    if not rec.get("promoted", False)
                ]
                if candidates:
                    weakest = min(
                        candidates,
                        key=lambda item: (
                            int(item[1].get("support", 0)),
                            int(item[1].get("last_event", 0)),
                        ),
                    )[0]
                    self.concepts.pop(weakest, None)

            concept_id = f"LATENT:{self.next_id:06d}"
            self.next_id += 1
            record = {
                "support": 0,
                "feature_counts": {},
                "promoted": False,
                "created_event": event_id,
                "last_event": event_id,
            }
            self.concepts[concept_id] = record
            best = LatentMatch(concept_id, 1.0, 0, False)

        record["support"] = int(record.get("support", 0)) + 1
        record["last_event"] = event_id

        counts = Counter(record.get("feature_counts", {}))
        counts.update(features)

        if len(counts) > self.cfg.latent_max_features:
            counts = Counter(dict(counts.most_common(self.cfg.latent_max_features)))
        record["feature_counts"] = dict(counts)

        if record["support"] >= self.cfg.latent_min_support:
            record["promoted"] = True

        score, _ = self._score(set(features), record)
        return LatentMatch(
            best.concept_id,
            score,
            int(record["support"]),
            bool(record["promoted"]),
        )

    def activate(self, features: Iterable[str], limit: int = 6) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for match in self.match_features(features):
            if not match.promoted:
                continue
            out[match.concept_id] = match.score
            if len(out) >= limit:
                break
        return out

    def inspect(self, concept_id: str) -> dict | None:
        record = self.concepts.get(concept_id)
        if not record:
            return None
        return {
            "id": concept_id,
            "support": int(record.get("support", 0)),
            "promoted": bool(record.get("promoted", False)),
            "prototype": sorted(self._prototype_set(record)),
            "feature_counts": dict(record.get("feature_counts", {})),
            "created_event": int(record.get("created_event", 0)),
            "last_event": int(record.get("last_event", 0)),
        }

    def promoted(self) -> List[dict]:
        rows = [
            self.inspect(cid)
            for cid, rec in self.concepts.items()
            if rec.get("promoted", False)
        ]
        rows = [r for r in rows if r is not None]
        rows.sort(key=lambda r: (-r["support"], r["id"]))
        return rows

    def export_state(self) -> dict:
        return {
            "next_id": self.next_id,
            "concepts": self.concepts,
        }

    def import_state(self, payload: dict) -> None:
        self.next_id = int(payload.get("next_id", 1))
        self.concepts = {
            str(k): dict(v)
            for k, v in payload.get("concepts", {}).items()
        }
