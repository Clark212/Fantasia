from __future__ import annotations

from collections import defaultdict
from math import sqrt
from typing import Dict, Iterable, List, Set, Tuple


class OnlineSemanticMap:
    """
    Bounded online distributional-semantic learner.

    v0.1.1.1 avoids a scaling trap where very common context words could connect
    a term to thousands of candidate aliases.

    Each term keeps a bounded context vector, and alias discovery prefers
    discriminative contexts whose reverse posting lists are not enormous.
    """

    def __init__(
        self,
        similarity_threshold: float = 0.62,
        min_observations: int = 2,
        max_aliases: int = 3,
        max_contexts: int = 96,
        max_context_reverse: int = 128,
        max_candidates: int = 128,
        pair_cache_enabled: bool = True,
    ):
        self.threshold = similarity_threshold
        self.min_observations = min_observations
        self.max_aliases = max_aliases
        self.max_contexts = max_contexts
        self.max_context_reverse = max_context_reverse
        self.max_candidates = max_candidates
        self.pair_cache_enabled = bool(pair_cache_enabled)
        self._pair_cache_limit = max(256, min(32768, self.max_candidates * self.max_candidates))

        self.contexts: Dict[str, Dict[str, float]] = {}
        self.usage: Dict[str, int] = {}
        self.reverse: Dict[str, Set[str]] = defaultdict(set)

        # Cache semantic views and final similarity decisions while the map is
        # unchanged. A single ASM event can ask about the same terms repeatedly
        # across the encoder, perception, and relation-discovery layers. Without
        # this cache those layers rebuild the same bounded vectors and cosine
        # comparisons over and over, making per-event cost grow badly with the
        # learned vocabulary. Any observation invalidates the cache, so results
        # remain exactly tied to the current semantic-map state.
        self._view_cache: Dict[str, Dict[str, float]] = {}
        self._view_norm_cache: Dict[str, float] = {}
        self._view_version: Dict[str, int] = {}
        self._view_reverse: Dict[str, Dict[str, float]] = defaultdict(dict)
        self._pair_cosine_cache: Dict[Tuple[str, str], tuple] = {}
        self._pair_query_versions: Dict[str, int] = {}
        self._similar_cache: Dict[str, Tuple[Tuple[str, float], ...]] = {}

    def _invalidate_cache(self) -> None:
        self._view_cache.clear()
        self._view_norm_cache.clear()
        self._view_version.clear()
        self._view_reverse = defaultdict(dict)
        self._pair_cosine_cache.clear()
        self._pair_query_versions.clear()
        self._similar_cache.clear()

    def _invalidate_terms(self, terms: Iterable[str]) -> None:
        for term in set(str(x) for x in terms if str(x)):
            old_view = self._view_cache.pop(term, None)
            if old_view:
                for ctx in old_view:
                    posting = self._view_reverse.get(ctx)
                    if posting is not None:
                        posting.pop(term, None)
                        if not posting:
                            self._view_reverse.pop(ctx, None)
            self._view_norm_cache.pop(term, None)
            self._view_version[term] = self._view_version.get(term, 0) + 1
        # Final nearest-neighbor rankings can change when any candidate usage or
        # view changes, so that small cache is conservatively reset. Pairwise
        # cosine work survives when both term versions are unchanged.
        self._similar_cache.clear()

    def observe(self, terms: Iterable[str]) -> None:
        unique = list(dict.fromkeys(t for t in terms if t))
        if not unique:
            return

        affected: Set[str] = set(unique)
        if len(unique) < 2:
            for term in unique:
                self.usage[term] = self.usage.get(term, 0) + 1
            # Usage may cross the min-observation gate even though no vector
            # changed. Rankings must refresh; cosine/view caches remain valid.
            self._similar_cache.clear()
            return

        for term in unique:
            self.usage[term] = self.usage.get(term, 0) + 1
            vec = self.contexts.setdefault(term, {})

            for ctx in unique:
                if ctx == term:
                    continue
                is_new_edge = ctx not in vec
                vec[ctx] = vec.get(ctx, 0.0) + 1.0
                bucket = self.reverse[ctx]
                if is_new_edge and term not in bucket:
                    # reverse_size participates in selectivity for every term
                    # using this context, so all members of the posting can have
                    # a changed bounded view when cardinality changes.
                    affected.update(bucket)
                    bucket.add(term)
                    affected.update(bucket)
                else:
                    bucket.add(term)

            # Keep vectors bounded. Strong repeated context survives; one-off
            # context noise is discarded.
            if len(vec) > self.max_contexts * 2:
                keep = dict(
                    sorted(
                        vec.items(),
                        key=lambda kv: kv[1],
                        reverse=True,
                    )[: self.max_contexts]
                )
                removed = set(vec) - set(keep)
                self.contexts[term] = keep
                vec = keep
                for ctx in removed:
                    bucket = self.reverse.get(ctx)
                    if bucket is not None:
                        affected.update(bucket)
                        bucket.discard(term)
                        affected.update(bucket)
                        if not bucket:
                            self.reverse.pop(ctx, None)

        self._invalidate_terms(affected)

    def _view(self, term: str) -> Dict[str, float]:
        cached = self._view_cache.get(term)
        if cached is not None:
            return cached

        vec = self.contexts.get(term, {})
        if not vec:
            self._view_cache[term] = {}
            self._view_norm_cache[term] = 0.0
            return self._view_cache[term]

        scored = []
        for ctx, weight in vec.items():
            reverse_size = len(self.reverse.get(ctx, ()))
            if reverse_size > self.max_context_reverse:
                continue

            # Prefer frequent-with-this-term but globally selective context.
            selectivity = weight / max(1.0, reverse_size ** 0.5)
            scored.append((ctx, weight, selectivity))

        scored.sort(key=lambda x: x[2], reverse=True)
        view = {
            ctx: weight
            for ctx, weight, _ in scored[: self.max_contexts]
        }
        self._view_cache[term] = view
        norm = sqrt(sum(v * v for v in view.values()))
        self._view_norm_cache[term] = norm
        if norm > 0.0:
            for ctx, weight in view.items():
                self._view_reverse[ctx][term] = float(weight) / norm
        return view

    def similar(self, term: str) -> List[Tuple[str, float]]:
        cached = self._similar_cache.get(term)
        if cached is not None:
            return list(cached)
        if self.usage.get(term, 0) < self.min_observations:
            self._similar_cache[term] = ()
            return []

        view = self._view(term)
        if not view:
            self._similar_cache[term] = ()
            return []

        candidates: Set[str] = set()
        for ctx in view:
            bucket = self.reverse.get(ctx, ())
            if len(bucket) <= self.max_context_reverse:
                candidates.update(bucket)

            if len(candidates) >= self.max_candidates * 2:
                break

        candidates.discard(term)

        # Materialize candidate views once, then accumulate exact cosine scores
        # through normalized context postings. This replaces candidate-by-vector
        # nested Python loops with one sparse inverted pass while preserving the
        # same bounded views, shared-context ranking and cosine geometry.
        eligible = []
        for other in candidates:
            if self.usage.get(other, 0) < self.min_observations:
                continue
            other_view = self._view(other)
            if other_view:
                eligible.append(other)

        eligible_set = set(eligible)
        shared_counts: Dict[str, int] = defaultdict(int)
        dot_scores: Dict[str, float] = defaultdict(float)
        norm = self._view_norm_cache.get(term, 0.0)
        version = self._view_version.get(term, 0)
        use_pairs = self.pair_cache_enabled and self._pair_query_versions.get(term) == version
        if self.pair_cache_enabled:
            self._pair_query_versions[term] = version
        # A newly changed query view invalidates every pair for that query. Use
        # the original inverted pass until its version survives another query.
        # This avoids paying pairwise-cache miss costs during rapid cold learning.
        if use_pairs and norm > 0.0:
            normalized_view = None
            for other in eligible:
                other_version = self._view_version.get(other, 0)
                key = (term, other)
                cached_pair = self._pair_cosine_cache.get(key)
                if cached_pair is not None and cached_pair[:2] == (version, other_version):
                    shared_counts[other], dot_scores[other] = cached_pair[2:]
                    continue
                # Retain the original query-context accumulation order and
                # normalized factors. Version stamps include reverse-posting
                # cardinality changes, which can change bounded view membership.
                other_view = self._view_cache[other]
                count = 0
                score = 0.0
                if normalized_view is None:
                    normalized_view = tuple((ctx, float(weight) / norm) for ctx, weight in view.items())
                for ctx, qn in normalized_view:
                    if ctx in other_view:
                        count += 1
                        score += qn * float(self._view_reverse[ctx][other])
                shared_counts[other], dot_scores[other] = count, score
                if key not in self._pair_cosine_cache and len(self._pair_cosine_cache) >= self._pair_cache_limit:
                    self._pair_cosine_cache.pop(next(iter(self._pair_cosine_cache)))
                self._pair_cosine_cache[key] = (version, other_version, count, score)
        elif norm > 0.0 and eligible_set:
            for ctx, weight in view.items():
                qn = float(weight) / norm
                for other, on in self._view_reverse.get(ctx, {}).items():
                    if other == term or other not in eligible_set:
                        continue
                    shared_counts[other] += 1
                    dot_scores[other] += qn * float(on)

        ranked_candidates = [
            (other, shared_counts.get(other, 0))
            for other in eligible
            if shared_counts.get(other, 0)
        ]
        ranked_candidates.sort(key=lambda x: x[1], reverse=True)

        scored: List[Tuple[str, float]] = []
        for other, _shared in ranked_candidates[: self.max_candidates]:
            score = float(dot_scores.get(other, 0.0))
            if score >= self.threshold:
                scored.append((other, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        result = tuple(scored[: self.max_aliases])
        self._similar_cache[term] = result
        return list(result)

    @staticmethod
    def _cosine(a: Dict[str, float], b: Dict[str, float]) -> float:
        if not a or not b:
            return 0.0

        if len(a) > len(b):
            a, b = b, a

        dot = 0.0
        for key, value in a.items():
            dot += value * b.get(key, 0.0)

        na = sqrt(sum(v * v for v in a.values()))
        nb = sqrt(sum(v * v for v in b.values()))
        if na == 0.0 or nb == 0.0:
            return 0.0
        return dot / (na * nb)

    def export_state(self) -> dict:
        return {
            "contexts": self.contexts,
            "usage": self.usage,
        }

    def import_state(self, payload: dict) -> None:
        self.contexts = {
            str(term): {
                str(k): float(v)
                for k, v in vec.items()
            }
            for term, vec in payload.get("contexts", {}).items()
        }
        self.usage = {
            str(term): int(count)
            for term, count in payload.get("usage", {}).items()
        }

        self.reverse = defaultdict(set)
        for term, vec in self.contexts.items():
            for ctx in vec:
                self.reverse[ctx].add(term)

        self._invalidate_cache()
