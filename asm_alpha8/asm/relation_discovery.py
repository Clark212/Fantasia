from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import re
from typing import Dict, Iterable, List, Optional, Tuple

from .config import ASMConfig
from .encoder import STOPWORDS, ConceptEncoder, light_stem
from .parsing import Relation, StructuralFrame, StructuralParser, WORDS
from .perception import LearnedRelationPerception


@dataclass(slots=True)
class RelationDiscoveryDecision:
    frame: StructuralFrame
    relation_ids: List[str]
    confidence: float
    margin: float
    source: str
    details: List[dict]


class SelfDiscoveredRelationSystem:
    """Online machine-created relation ontology.

    This layer deliberately does not receive labels such as CAUSE/INCREASE as
    clustering features.  It observes raw relation episodes: left role,
    connector, right role, cues, polarity and surrounding lexical context.
    Repeated compatible episodes form anonymous machine relations such as
    ``RELATION:000001``.

    Named relations from the bootstrap parser can still provide *boundaries*
    (where the left/connector/right spans are), but their human relation names
    are not copied into this ontology.
    """

    def __init__(
        self,
        config: ASMConfig,
        encoder: ConceptEncoder,
        parser: StructuralParser,
        perception: LearnedRelationPerception,
    ):
        self.cfg = config
        self.encoder = encoder
        self.parser = parser
        self.perception = perception
        self.next_id = 1
        self.relations: Dict[str, dict] = {}
        self.redirects: Dict[str, str] = {}
        self.total_episodes = 0
        self.merges = 0
        self.splits = 0
        self.capacity_rejections = 0
        # Derived exact-connector index.  It is rebuilt on import/merge/split,
        # so it does not need to be persisted separately.
        self.connector_index: Dict[str, set[str]] = {}

        # Runtime-only acceleration indexes. These are derived from the learned
        # relation records and are never persisted as authoritative state.
        #
        # - prototype cache avoids rebuilding thresholded relation prototypes
        #   for every pairwise comparison;
        # - merge connector postings turn the old O(R) merge sweep into a
        #   candidate lookup over relations that share (or semantically alias)
        #   connector evidence;
        # - role mass removes another O(R) scan from generic boundary induction.
        self._prototype_cache: Dict[int, dict] = {}
        self._merge_connector_index: Dict[str, set[str]] = {}
        self._merge_tokens_by_relation: Dict[str, set[str]] = {}
        self._feature_index: Dict[str, Dict[str, set[str]]] = {
            "left": {}, "connector": {}, "right": {}, "context": {}, "cues": {}
        }
        self._feature_tokens_by_relation: Dict[str, Dict[str, set[str]]] = {}
        self._role_mass: Dict[str, float] = {}

    def _resolve(self, relation_id: str) -> str:
        seen = set()
        rid = relation_id
        while rid in self.redirects and rid not in seen:
            seen.add(rid)
            rid = self.redirects[rid]
        return rid

    @staticmethod
    def _clean(text: str) -> str:
        return " ".join(text.lower().replace("’", "'").strip().split())

    def _stems(self, text: str) -> List[str]:
        return [
            light_stem(x)
            for x in WORDS.findall(text.lower())
            if x not in STOPWORDS
        ]

    def _conn_stems(self, text: str) -> List[str]:
        return self.perception._connector_stems(text)

    def _cues(self, text: str) -> List[str]:
        return self.perception._cues(text)

    def _safety(self, text: str) -> List[str]:
        return self.perception._safety_warnings(text)

    def _clauses(self, text: str) -> List[str]:
        return self.perception._clauses(text)

    @staticmethod
    def _connector_key(stems: Iterable[str]) -> str:
        return " ".join(str(x) for x in stems if str(x))

    def _rebuild_connector_index(self) -> None:
        index: Dict[str, set[str]] = {}
        for rid, rec in self.relations.items():
            if rec.get("dormant", False):
                continue
            for ep in rec.get("episodes", []):
                key = self._connector_key(ep.get("connector", []))
                if key:
                    index.setdefault(key, set()).add(rid)
            # Older snapshots may have no episodes but do have connector counts.
            for stem in rec.get("connector_counts", {}):
                if stem:
                    index.setdefault(str(stem), set()).add(rid)
        self.connector_index = index

    def _drop_merge_index(self, rid: str) -> None:
        for token in self._merge_tokens_by_relation.pop(rid, set()):
            bucket = self._merge_connector_index.get(token)
            if bucket is None:
                continue
            bucket.discard(rid)
            if not bucket:
                self._merge_connector_index.pop(token, None)
        for field, tokens in self._feature_tokens_by_relation.pop(rid, {}).items():
            field_index = self._feature_index.get(field, {})
            for token in tokens:
                bucket = field_index.get(token)
                if bucket is None:
                    continue
                bucket.discard(rid)
                if not bucket:
                    field_index.pop(token, None)
        rec = self.relations.get(rid)
        if rec is not None:
            self._prototype_cache.pop(id(rec), None)

    def _refresh_relation_index(self, rid: str) -> None:
        self._drop_merge_index(rid)
        rec = self.relations.get(rid)
        if rec is None or rec.get("dormant", False):
            return
        proto = self._prototype_uncached(rec)
        self._prototype_cache[id(rec)] = proto
        tokens = set(proto.get("connector", ()))
        self._merge_tokens_by_relation[rid] = tokens
        for token in tokens:
            self._merge_connector_index.setdefault(str(token), set()).add(rid)

        feature_tokens: Dict[str, set[str]] = {}
        for field in ("left", "connector", "right", "context", "cues"):
            values = {str(x) for x in proto.get(field, ()) if str(x)}
            feature_tokens[field] = values
            field_index = self._feature_index[field]
            for token in values:
                field_index.setdefault(token, set()).add(rid)
        self._feature_tokens_by_relation[rid] = feature_tokens

    def _rebuild_runtime_indexes(self) -> None:
        self._prototype_cache = {}
        self._merge_connector_index = {}
        self._merge_tokens_by_relation = {}
        self._feature_index = {"left": {}, "connector": {}, "right": {}, "context": {}, "cues": {}}
        self._feature_tokens_by_relation = {}
        role_mass: Dict[str, float] = {}
        for rid, rec in self.relations.items():
            for key in ("left_counts", "right_counts"):
                for stem, value in rec.get(key, {}).items():
                    role_mass[str(stem)] = role_mass.get(str(stem), 0.0) + float(value)
            self._refresh_relation_index(rid)
        self._role_mass = role_mass

    def _index_episode(self, rid: str, ep: dict) -> None:
        key = self._connector_key(ep.get("connector", []))
        if key:
            self.connector_index.setdefault(key, set()).add(rid)

    def _repair_candidate_polarity(self, candidate: dict) -> dict:
        """Move trailing auxiliary negation out of the left role if needed."""
        out = dict(candidate)
        left = str(out.get("left", "")).strip()
        connector = str(out.get("connector", "")).strip()

        m = re.search(
            r"\b(?P<neg>(?:(?:do|does|did|is|are|was|were|has|have|had)\s+)?(?:not|never))\s*$",
            left,
            re.I,
        )
        if m:
            neg = m.group("neg")
            left = left[:m.start()].strip()
            connector = f"{neg} {connector}".strip()
            out["left"] = left
            out["connector"] = connector
            out["negated"] = True
        elif re.search(r"\b(?:not|never)\b", connector, re.I):
            out["negated"] = True
        return out

    def _indexed_boundary_candidate(self, clause: str) -> Optional[dict]:
        """Use a known exact connector only as a span boundary, never as a label."""
        if not self.connector_index:
            return None
        tokens = WORDS.findall(clause)
        max_conn = max(1, int(self.cfg.relation_discovery_max_connector_tokens))
        # Longest exact known connector wins.
        for length in range(min(max_conn, len(tokens) - 2), 0, -1):
            for start in range(1, len(tokens) - length):
                end = start + length
                raw = " ".join(tokens[start:end])
                key = self._connector_key(self._conn_stems(raw))
                if key and key in self.connector_index:
                    cand = {
                        "left": " ".join(tokens[:start]),
                        "connector": raw,
                        "right": " ".join(tokens[end:]),
                        "negated": False,
                        "boundary_source": "connector_index",
                    }
                    return self._repair_candidate_polarity(cand)
        return None

    def _generic_candidate(self, clause: str) -> Optional[dict]:
        """Find a plausible relation span without assigning a semantic label."""
        known = self.perception._known_clause_match(clause)
        if known:
            return self._repair_candidate_polarity({
                "left": known["left"],
                "connector": known["connector"],
                "right": known["right"],
                "negated": bool(known.get("negated", False)),
                "boundary_source": "bootstrap_boundary",
            })

        indexed = self._indexed_boundary_candidate(clause)
        if indexed:
            return indexed

        # If v0.1.1.8 can already understand the wording, its selected span is a
        # useful boundary, but again we intentionally ignore the named kind.
        learned = self.perception.infer(clause)
        if learned.frame.supported and learned.details:
            d = learned.details[0]
            return self._repair_candidate_polarity({
                "left": d["left_raw"],
                "connector": d["connector_raw"],
                "right": d["right_raw"],
                "negated": bool(d.get("negated", False)),
                "boundary_source": "learned_boundary",
            })

        tokens = WORDS.findall(clause)
        if len(tokens) < 3:
            return None

        # Generic relation-boundary induction. Prefer short central connector
        # spans and role phrases with at least one content token on both sides.
        # No ontology/verb list is used here.
        candidates = []
        max_conn = max(1, int(self.cfg.relation_discovery_max_connector_tokens))
        for start in range(1, len(tokens) - 1):
            for length in range(1, max_conn + 1):
                end = start + length
                if end >= len(tokens):
                    break
                conn_tokens = tokens[start:end]
                useful = [
                    x for x in conn_tokens
                    if x not in self.perception.AUXILIARY and x not in {"not", "never"}
                ]
                if not useful:
                    continue
                left = " ".join(tokens[:start])
                right = " ".join(tokens[end:])
                if not self._stems(left) or not self._stems(right):
                    continue

                # Centrality + compactness + evidence that the surrounding words
                # are used as relation roles elsewhere.
                center = (start + end - 1) / 2.0
                midpoint = (len(tokens) - 1) / 2.0
                centrality = 1.0 / (1.0 + abs(center - midpoint))
                compact = 1.0 / length
                left_known = self._role_usage(self._stems(left))
                right_known = self._role_usage(self._stems(right))
                role_support = min(1.0, 0.5 * left_known + 0.5 * right_known)
                score = 0.48 * compact + 0.32 * centrality + 0.20 * role_support
                candidates.append((score, start, end, left, " ".join(conn_tokens), right))

        if not candidates:
            return None
        candidates.sort(key=lambda x: (-x[0], x[2] - x[1], x[1]))
        _, _, _, left, connector, right = candidates[0]
        return self._repair_candidate_polarity({
            "left": left,
            "connector": connector,
            "right": right,
            "negated": bool(re.search(r"\b(?:not|never)\b", connector)),
            "boundary_source": "generic_boundary",
        })

    def _role_usage(self, stems: Iterable[str]) -> float:
        vals = [min(1.0, float(self._role_mass.get(str(stem), 0.0)) / 3.0) for stem in stems]
        return max(vals) if vals else 0.0

    def _episode(self, text: str, clause: str, candidate: dict) -> dict:
        left_stems = list(dict.fromkeys(self._stems(candidate["left"])))
        right_stems = list(dict.fromkeys(self._stems(candidate["right"])))
        conn_stems = list(dict.fromkeys(self._conn_stems(candidate["connector"])))
        cues = self._cues(text)
        all_stems = self._stems(text)
        role_set = set(left_stems) | set(right_stems) | set(conn_stems)
        context = [x for x in all_stems if x not in role_set][:16]
        return {
            "text": text,
            "clause": clause,
            "left_raw": candidate["left"],
            "connector_raw": candidate["connector"],
            "right_raw": candidate["right"],
            "left": left_stems,
            "connector": conn_stems,
            "right": right_stems,
            "cues": cues,
            "context": list(dict.fromkeys(context)),
            "negated": bool(candidate.get("negated", False)),
            "boundary_source": candidate.get("boundary_source", "unknown"),
        }

    @staticmethod
    def _counter_set(counter: dict, support: float, floor: float = 0.25) -> set[str]:
        support = max(1.0, float(support))
        return {str(k) for k, v in counter.items() if float(v) / support >= floor}

    def _prototype_uncached(self, rec: dict) -> dict:
        support = float(rec.get("support", 0.0))
        return {
            "left": self._counter_set(rec.get("left_counts", {}), support, 0.22),
            "connector": self._counter_set(rec.get("connector_counts", {}), support, 0.18),
            "right": self._counter_set(rec.get("right_counts", {}), support, 0.22),
            "cues": self._counter_set(rec.get("cue_counts", {}), support, 0.20),
            "context": self._counter_set(rec.get("context_counts", {}), support, 0.18),
            "negated": float(rec.get("negative_support", 0.0)) > support * 0.5,
        }

    def _prototype(self, rec: dict) -> dict:
        key = id(rec)
        cached = self._prototype_cache.get(key)
        if cached is None:
            cached = self._prototype_uncached(rec)
            self._prototype_cache[key] = cached
        return cached

    def _semantic_set_similarity(self, query: Iterable[str], proto: Iterable[str]) -> float:
        q = list(dict.fromkeys(query)); p = set(proto)
        if not q or not p:
            return 0.0
        scores = []
        for token in q:
            if token in p:
                scores.append(1.0); continue
            best = 0.0
            for alias, sim in self.encoder.semantic.similar(token):
                if alias in p:
                    best = max(best, float(sim))
            scores.append(best)
        # Query coverage is more useful here than symmetric overlap because an
        # episode can be a short sample of a broad learned relation.
        return sum(scores) / len(scores)

    @staticmethod
    def _jaccard(a: Iterable[str], b: Iterable[str]) -> float:
        a=set(a); b=set(b)
        if not a and not b: return 0.0
        if not a or not b: return 0.0
        return len(a & b) / len(a | b)

    def _episode_similarity(self, ep: dict, rec: dict) -> float:
        proto = self._prototype(rec)
        conn = self._semantic_set_similarity(ep["connector"], proto["connector"])
        left = self._semantic_set_similarity(ep["left"], proto["left"])
        right = self._semantic_set_similarity(ep["right"], proto["right"])
        context = self._semantic_set_similarity(ep["context"], proto["context"])
        cues = self._jaccard(ep["cues"], proto["cues"])
        polarity = 1.0 if bool(ep["negated"]) == bool(proto["negated"]) else 0.0

        # Preserve the v0.1.1.9 learning geometry.  Polysemy-specific context is
        # added only at query ranking time so it does not fragment early learning.
        score = (
            0.46 * conn
            + 0.18 * left
            + 0.18 * right
            + 0.10 * context
            + 0.04 * cues
            + 0.04 * polarity
        )
        return score * (0.55 + 0.45 * float(rec.get("strength", 0.5)))

    def _new_relation(self, ep: dict, event_id: int) -> Optional[str]:
        if len(self.relations) >= self.cfg.relation_discovery_max_relations:
            # Reclaim dormant or not-yet-promoted hypotheses first.  Promoted
            # knowledge is not silently overwritten just because the ontology is
            # full; if everything is active, abstain from allocating a new ID.
            reclaimable = [
                (rid, rec)
                for rid, rec in self.relations.items()
                if bool(rec.get("dormant", False))
                or not bool(rec.get("promoted", False))
            ]
            if reclaimable:
                rid = min(
                    reclaimable,
                    key=lambda x: (
                        0 if x[1].get("dormant", False) else 1,
                        float(x[1].get("support", 0.0)),
                        float(x[1].get("strength", 0.0)),
                        int(x[1].get("last_event", 0)),
                    ),
                )[0]
                self.relations.pop(rid, None)
                self._rebuild_connector_index()
                self._rebuild_runtime_indexes()
            elif self.cfg.relation_discovery_capacity_reject_when_full:
                self.capacity_rejections += 1
                return None

        rid = f"RELATION:{self.next_id:06d}"
        self.next_id += 1
        self.relations[rid] = {
            "support": 0.0,
            "strength": 0.55,
            "promoted": False,
            "dormant": False,
            "created_event": int(event_id),
            "last_event": int(event_id),
            "left_counts": {}, "connector_counts": {}, "right_counts": {},
            "cue_counts": {}, "context_counts": {},
            "negative_support": 0.0,
            "generic_support": 0.0,
            "episodes": [],
            "prediction_error_ema": 0.5,
            "successes": 0,
            "failures": 0,
            "split_generation": 0,
        }
        self._update_relation(rid, ep, event_id, similarity=1.0)
        return rid

    @staticmethod
    def _inc(counter: dict, values: Iterable[str], weight: float = 1.0) -> dict:
        c = Counter({str(k): float(v) for k,v in counter.items()})
        c.update({str(x): float(weight) for x in set(values)})
        return dict(c)

    def _update_relation(self, rid: str, ep: dict, event_id: int, similarity: float) -> None:
        rid=self._resolve(rid); rec=self.relations[rid]
        rec["support"] = float(rec.get("support",0.0)) + 1.0
        rec["last_event"] = int(event_id)
        rec["left_counts"] = self._inc(rec.get("left_counts",{}), ep["left"])
        rec["connector_counts"] = self._inc(rec.get("connector_counts",{}), ep["connector"])
        rec["right_counts"] = self._inc(rec.get("right_counts",{}), ep["right"])
        rec["cue_counts"] = self._inc(rec.get("cue_counts",{}), ep["cues"])
        rec["context_counts"] = self._inc(rec.get("context_counts",{}), ep["context"])
        if ep["negated"]: rec["negative_support"] = float(rec.get("negative_support",0.0))+1.0
        if ep.get("boundary_source") in {"generic_boundary", "connector_index"}:
            rec["generic_support"] = float(rec.get("generic_support",0.0)) + 1.0

        episodes=list(rec.get("episodes",[])); episodes.append(dict(ep))
        rec["episodes"] = episodes[-int(self.cfg.relation_discovery_max_episodes):]
        rec["promoted"] = rec["support"] >= self.cfg.relation_discovery_min_support

        err=max(0.0,min(1.0,1.0-float(similarity)))
        old=float(rec.get("prediction_error_ema",0.5))
        rec["prediction_error_ema"] = 0.82*old + 0.18*err
        target=1.0-err
        rec["strength"] = max(0.0,min(1.0,
            float(rec.get("strength",0.55))
            + self.cfg.relation_discovery_strength_lr*(target-float(rec.get("strength",0.55)))
        ))
        rec["dormant"] = rec["strength"] < self.cfg.relation_discovery_dormant_strength
        for stem in set(ep.get("left", ())):
            self._role_mass[str(stem)] = self._role_mass.get(str(stem), 0.0) + 1.0
        for stem in set(ep.get("right", ())):
            self._role_mass[str(stem)] = self._role_mass.get(str(stem), 0.0) + 1.0
        self._index_episode(rid, ep)
        self._refresh_relation_index(rid)

    def _episode_candidate_ids(self, ep: dict) -> set[str]:
        """Candidate retrieval aligned with `_episode_similarity`.

        Semantic fields use exactly the same query->alias expansion as the
        scorer; cue overlap is exact. Polarity alone contributes only 0.04 and
        cannot meet the normal join/query thresholds, so relations with no
        indexed evidence cannot be valid winners.
        """
        candidates: set[str] = set()
        for field in ("left", "connector", "right", "context"):
            index = self._feature_index[field]
            for raw in ep.get(field, ()):
                token = str(raw)
                candidates.update(index.get(token, ()))
                for alias, _score in self.encoder.semantic.similar(token):
                    candidates.update(index.get(str(alias), ()))
        cue_index = self._feature_index["cues"]
        for raw in ep.get("cues", ()):
            candidates.update(cue_index.get(str(raw), ()))
        return {self._resolve(rid) for rid in candidates if self._resolve(rid) in self.relations}

    def infer_episode(
        self,
        ep: dict,
        *,
        promoted_only: bool = True,
        require_novel_support: bool = False,
    ) -> List[dict]:
        rows = []

        candidate_ids = None
        exact_connector_candidates = False
        if self.cfg.relation_discovery_exact_connector_index:
            key = self._connector_key(ep.get("connector", []))
            indexed = self.connector_index.get(key)
            if indexed:
                candidate_ids = set(self._resolve(rid) for rid in indexed)
                exact_connector_candidates = True

        if candidate_ids is None:
            candidate_ids = self._episode_candidate_ids(ep)

        iterable = ((rid, self.relations[rid]) for rid in candidate_ids if rid in self.relations)

        seen = set()
        for rid, rec in iterable:
            rid = self._resolve(rid)
            if rid in seen or rid not in self.relations:
                continue
            seen.add(rid)
            rec = self.relations[rid]
            if rec.get("dormant", False):
                continue
            if promoted_only and not rec.get("promoted", False):
                continue
            if (
                require_novel_support
                and float(rec.get("generic_support", 0.0))
                < float(self.cfg.relation_discovery_min_support)
            ):
                continue
            score = self._episode_similarity(ep, rec)
            if exact_connector_candidates:
                proto = self._prototype(rec)
                q_cues = set(ep.get("cues", []))
                p_cues = set(proto.get("cues", []))

                # Once an exact connector has branched into multiple provisional
                # senses, cue-regime compatibility helps later episodes reinforce
                # the right sense instead of spawning one-off relations.
                if len(candidate_ids) > 1:
                    if q_cues and p_cues:
                        score += 0.20 * self._jaccard(q_cues, p_cues)
                    elif not q_cues and not p_cues:
                        score += 0.20

                if promoted_only:
                    # Exact connector identity is strong query evidence, including
                    # negated uses where polarity should not erase the base relation.
                    score += 0.05
                score = min(1.0, score)
            rows.append({
                "relation_id": rid,
                "score": score,
                "support": rec.get("support", 0.0),
                "strength": rec.get("strength", 0.0),
            })
        rows.sort(key=lambda x: (-x["score"], -x["support"], x["relation_id"]))
        return rows

    def _polysemy_guard(self, ep: dict, best: Optional[dict]) -> bool:
        """Return True when an exact connector likely needs a new sense."""
        if not best:
            return False
        rec = self.relations.get(self._resolve(best["relation_id"]))
        if not rec:
            return False
        if float(rec.get("support", 0.0)) < float(self.cfg.relation_discovery_polysemy_min_support):
            return False

        proto = self._prototype(rec)
        exact_connector = bool(
            set(ep.get("connector", []))
            and set(ep.get("connector", [])) & set(proto.get("connector", []))
        )
        if not exact_connector:
            return False

        q_cues = set(ep.get("cues", []))
        p_cues = set(proto.get("cues", []))
        # A stable cue-rich sense encountering a cue-free regime (or vice versa)
        # is evidence for polysemy rather than automatic connector collapse.
        cue_regime_gap = bool(q_cues) != bool(p_cues)
        if cue_regime_gap:
            return True

        # Disjoint non-empty cue families are not split immediately: they may
        # represent one broad mechanism.  Repeated prediction error can still
        # split them later using the existing feedback-driven clustering path.
        return False

    def observe_episode(self, ep: dict, event_id: int) -> dict:
        rows=self.infer_episode(ep,promoted_only=False)
        best=rows[0] if rows else None
        second=rows[1]["score"] if len(rows)>1 else 0.0
        margin=(best["score"]-second) if best else 1.0
        split_sense = self._polysemy_guard(ep, best)
        if (
            best
            and not split_sense
            and best["score"] >= self.cfg.relation_discovery_join_threshold
            and margin >= self.cfg.relation_discovery_min_margin
        ):
            rid=best["relation_id"]; sim=best["score"]
            self._update_relation(rid,ep,event_id,sim)
            action="joined"
        else:
            rid=self._new_relation(ep,event_id); sim=1.0
            action="sense_created" if split_sense and rid else ("created" if rid else "capacity_abstain")
        self.total_episodes += 1
        if rid is None:
            return {
                "relation_id": None,
                "action": action,
                "similarity": 0.0,
                "margin": margin,
                "promoted": False,
                "split": None,
            }
        rid=self._resolve(rid)
        # Merge discovery is maintenance, not part of every observation's hot
        # path. New senses are checked immediately; established relations are
        # rechecked at promotion and bounded support milestones. This preserves
        # eventual consolidation while avoiding repeated ontology-wide semantic
        # work when a prototype has only changed marginally.
        support_premerge = int(self.relations.get(rid, {}).get("support", 0))
        merge_due = (
            action in {"created", "sense_created"}
            or support_premerge == int(self.cfg.relation_discovery_min_support)
            or (support_premerge >= 2 and (support_premerge & (support_premerge - 1)) == 0)
            or (support_premerge >= 8 and support_premerge % 8 == 0)
        )
        merged_into = self._maybe_merge(rid,event_id) if merge_due else None
        rid=self._resolve(merged_into or rid)
        # Coherence checks are bounded maintenance, not a per-event quadratic
        # tax. Prediction-error feedback can still force an immediate split.
        support_now = int(self.relations.get(rid, {}).get("support", 0))
        split = (
            self._maybe_split(rid, event_id)
            if support_now >= self.cfg.relation_discovery_split_min_support
            and support_now % 8 == 0
            else None
        )
        return {"relation_id":rid,"action":action,"similarity":sim,"margin":margin,"promoted":bool(self.relations.get(rid,{}).get("promoted",False)),"split":split}

    def observe_text(self, text: str, event_id: int) -> List[dict]:
        if self._safety(text): return []
        out=[]
        for clause in self._clauses(text):
            cand=self._generic_candidate(clause)
            if not cand: continue
            ep=self._episode(text,clause,cand)
            if not ep["connector"]: continue
            row=self.observe_episode(ep,event_id)
            row["episode"]={k:ep[k] for k in ("left_raw","connector_raw","right_raw","boundary_source")}
            out.append(row)
        return out

    def infer_text(self, text: str) -> RelationDiscoveryDecision:
        warnings=self._safety(text)
        if warnings:
            return RelationDiscoveryDecision(StructuralFrame(text,[],[],self._cues(text),warnings),[],0.0,0.0,"abstain",[])
        relations=[]; ids=[]; details=[]; confidences=[]; margins=[]
        for clause in self._clauses(text):
            cand=self._generic_candidate(clause)
            if not cand: continue
            ep=self._episode(text,clause,cand)
            rows=self.infer_episode(
                ep,
                promoted_only=True,
                require_novel_support=True,
            )
            if not rows: continue
            best=rows[0]; second=rows[1]["score"] if len(rows)>1 else 0.0
            margin=best["score"]-second
            if best["score"] < self.cfg.relation_discovery_query_threshold or margin < self.cfg.relation_discovery_min_margin:
                continue
            rid=self._resolve(best["relation_id"])
            relations.append(Relation(
                self.parser.normalize_phrase(cand["left"]),rid,
                self.parser.normalize_phrase(cand["right"]),
                confidence=best["score"],negated=bool(cand.get("negated",False))))
            ids.append(rid); confidences.append(best["score"]); margins.append(margin)
            details.append({"relation_id":rid,"score":best["score"],"margin":margin,"support":best["support"],"strength":best["strength"],"left_raw":cand["left"],"connector_raw":cand["connector"],"right_raw":cand["right"],"boundary_source":cand["boundary_source"]})
        entities=list(dict.fromkeys(x for r in relations for x in (r.left,r.right)))
        frame=StructuralFrame(text,entities,relations,self._cues(text),[] if relations else ["self-discovered relation: no confident match"])
        return RelationDiscoveryDecision(frame,ids,min(confidences) if confidences else 0.0,min(margins) if margins else 0.0,"self_discovered" if frame.supported else "abstain",details)

    def _relation_similarity(self, a: dict, b: dict) -> float:
        pa=self._prototype(a); pb=self._prototype(b)
        conn=0.5*(self._semantic_set_similarity(pa["connector"],pb["connector"])+self._semantic_set_similarity(pb["connector"],pa["connector"]))
        left=0.5*(self._semantic_set_similarity(pa["left"],pb["left"])+self._semantic_set_similarity(pb["left"],pa["left"]))
        right=0.5*(self._semantic_set_similarity(pa["right"],pb["right"])+self._semantic_set_similarity(pb["right"],pa["right"]))
        context=self._jaccard(pa["context"],pb["context"]); cues=self._jaccard(pa["cues"],pb["cues"])
        return 0.45*conn+0.18*left+0.18*right+0.10*context+0.09*cues

    def _merge_candidate_ids(self, rid: str, rec: dict) -> set[str]:
        """Return plausible merge peers without sweeping the whole ontology.

        The merge score gives connectors 45% of the weight while every other
        component together can contribute at most 55%. With the default 0.68
        threshold, a successful merge therefore needs non-zero connector
        compatibility. Candidate postings use exact connector prototype tokens
        plus the same semantic aliases used by the scorer. If a custom threshold
        <= 0.55 removes that guarantee, we conservatively fall back to a full scan.
        """
        if float(self.cfg.relation_discovery_merge_threshold) <= 0.55:
            return {x for x in self.relations if x != rid}

        proto = self._prototype(rec)
        tokens = set(proto.get("connector", ()))
        if not tokens:
            return {x for x in self.relations if x != rid}

        candidates: set[str] = set()
        for token in tokens:
            candidates.update(self._merge_connector_index.get(str(token), ()))
            for alias, _score in self.encoder.semantic.similar(str(token)):
                candidates.update(self._merge_connector_index.get(str(alias), ()))
        candidates.discard(rid)
        return {self._resolve(x) for x in candidates if self._resolve(x) in self.relations}

    def _maybe_merge(self, rid: str, event_id: int) -> Optional[str]:
        rid=self._resolve(rid)
        if rid not in self.relations: return None
        rec=self.relations[rid]
        candidates=[]
        for other in self._merge_candidate_ids(rid, rec):
            orec = self.relations.get(other)
            if orec is None or orec.get("dormant",False):
                continue
            sim=self._relation_similarity(rec,orec)
            if sim >= self.cfg.relation_discovery_merge_threshold:
                candidates.append((sim,other))
        if not candidates: return None
        candidates.sort(reverse=True); _,other=candidates[0]
        a=self.relations[rid]; b=self.relations[other]
        keep,drop=(rid,other) if float(a.get("support",0))>=float(b.get("support",0)) else (other,rid)
        kr=self.relations[keep]; dr=self.relations[drop]
        # Invalidate prototype identities before mutating the kept record.
        self._prototype_cache.pop(id(kr), None)
        self._prototype_cache.pop(id(dr), None)
        for key in ("left_counts","connector_counts","right_counts","cue_counts","context_counts"):
            c=Counter({str(k):float(v) for k,v in kr.get(key,{}).items()}); c.update({str(k):float(v) for k,v in dr.get(key,{}).items()}); kr[key]=dict(c)
        kr["support"]=float(kr.get("support",0))+float(dr.get("support",0))
        kr["negative_support"]=float(kr.get("negative_support",0))+float(dr.get("negative_support",0))
        kr["generic_support"]=float(kr.get("generic_support",0))+float(dr.get("generic_support",0))
        kr["episodes"]=(list(kr.get("episodes",[]))+list(dr.get("episodes",[])))[-int(self.cfg.relation_discovery_max_episodes):]
        kr["strength"]=(float(kr.get("strength",0.5))+float(dr.get("strength",0.5)))/2.0
        kr["promoted"]=kr["support"]>=self.cfg.relation_discovery_min_support
        kr["last_event"]=int(event_id)
        self._drop_merge_index(drop)
        self.redirects[drop]=keep; self.relations.pop(drop,None); self.merges+=1
        self._rebuild_connector_index()
        self._refresh_relation_index(keep)
        return keep

    def _coherence(self, rec: dict) -> float:
        eps=list(rec.get("episodes",[]))
        if not eps: return 1.0
        return sum(self._episode_similarity(ep,rec) for ep in eps)/len(eps)

    def _episode_pair_similarity(self, a: dict, b: dict) -> float:
        return 0.30*self._semantic_set_similarity(a["connector"],b["connector"])+0.25*self._semantic_set_similarity(a["left"],b["left"])+0.25*self._semantic_set_similarity(a["right"],b["right"])+0.12*self._jaccard(a["context"],b["context"])+0.08*self._jaccard(a["cues"],b["cues"])

    def _build_record_from_episodes(self, rid: str, episodes: List[dict], old: dict, event_id: int) -> dict:
        rec={"support":0.0,"strength":max(0.35,float(old.get("strength",0.5))),"promoted":False,"dormant":False,"created_event":old.get("created_event",event_id),"last_event":event_id,"left_counts":{},"connector_counts":{},"right_counts":{},"cue_counts":{},"context_counts":{},"negative_support":0.0,"generic_support":0.0,"episodes":[],"prediction_error_ema":old.get("prediction_error_ema",0.5),"successes":old.get("successes",0),"failures":old.get("failures",0),"split_generation":int(old.get("split_generation",0))+1}
        self.relations[rid]=rec
        for ep in episodes: self._update_relation(rid,ep,event_id,1.0)
        return self.relations[rid]

    def _maybe_split(self, rid: str, event_id: int, *, force: bool = False) -> Optional[dict]:
        rid=self._resolve(rid); rec=self.relations.get(rid)
        if not rec or rec.get("support",0)<self.cfg.relation_discovery_split_min_support: return None
        if (not force) and self._coherence(rec)>=self.cfg.relation_discovery_split_coherence: return None
        eps=list(rec.get("episodes",[]))
        if len(eps)<6: return None

        ga=[]; gb=[]
        # If repeated prediction failures coincide with two strong, mutually
        # exclusive contextual cue regimes, use them as split anchors. This is
        # a data-derived partition; the cue names are only observed context
        # features and do not name the new relation itself.
        cue_counts=Counter(c for ep in eps for c in set(ep.get("cues",[])))
        top=cue_counts.most_common(2)
        used_cue_split=False
        if len(top)>=2 and top[0][1]>=3 and top[1][1]>=3:
            c1,c2=top[0][0],top[1][0]
            g1=[ep for ep in eps if c1 in ep.get("cues",[]) and c2 not in ep.get("cues",[])]
            g2=[ep for ep in eps if c2 in ep.get("cues",[]) and c1 not in ep.get("cues",[])]
            if len(g1)>=3 and len(g2)>=3:
                ga,gb=g1,g2
                leftovers=[ep for ep in eps if ep not in ga and ep not in gb]
                seed_a,seed_b=ga[0],gb[0]
                for ep in leftovers:
                    sa=self._episode_pair_similarity(ep,seed_a); sb=self._episode_pair_similarity(ep,seed_b)
                    (ga if sa>=sb else gb).append(ep)
                used_cue_split=True

        if not used_cue_split:
            # Farthest pair as deterministic two-cluster seeds.
            far=(1.0,0,1)
            for i in range(len(eps)):
                for j in range(i+1,len(eps)):
                    sim=self._episode_pair_similarity(eps[i],eps[j])
                    if sim<far[0]: far=(sim,i,j)
            _,i,j=far; seed_a,seed_b=eps[i],eps[j]; ga=[]; gb=[]
            for ep in eps:
                sa=self._episode_pair_similarity(ep,seed_a); sb=self._episode_pair_similarity(ep,seed_b)
                (ga if sa>=sb else gb).append(ep)
        if min(len(ga),len(gb))<3: return None
        # Keep old ID for larger cluster; create a new machine relation for other.
        if len(gb)>len(ga): ga,gb=gb,ga
        old=dict(rec); self._build_record_from_episodes(rid,ga,old,event_id)
        new_id=f"RELATION:{self.next_id:06d}"; self.next_id+=1
        self._build_record_from_episodes(new_id,gb,old,event_id)
        self.splits+=1
        self._rebuild_connector_index()
        self._rebuild_runtime_indexes()
        return {"kept":rid,"created":new_id,"sizes":[len(ga),len(gb)]}

    def feedback(self, relation_id: str, *, success: bool, prediction_error: float = 0.0) -> dict:
        rid=self._resolve(relation_id); rec=self.relations.get(rid)
        if not rec: return {"relation_id":rid,"status":"missing"}
        err=max(0.0,min(1.0,float(prediction_error)))
        lr=float(self.cfg.relation_discovery_strength_lr)
        if success:
            rec["successes"]=int(rec.get("successes",0))+1
            target=max(0.55,1.0-self.cfg.relation_discovery_prediction_error_gain*err)
        else:
            rec["failures"]=int(rec.get("failures",0))+1
            target=max(0.0,0.35-self.cfg.relation_discovery_prediction_error_gain*err)
        rec["strength"]=max(0.0,min(1.0,float(rec.get("strength",0.5))+lr*(target-float(rec.get("strength",0.5)))))
        rec["dormant"]=rec["strength"]<self.cfg.relation_discovery_dormant_strength
        split = None
        # Repeated predictive failure is evidence that one relation prototype
        # may be hiding multiple mechanisms. Force a two-way episode split once
        # enough evidence exists; if the episodes are not separable, no split
        # occurs.
        if (not success) and int(rec.get("failures", 0)) >= 3:
            split = self._maybe_split(rid, int(rec.get("last_event", 0)), force=True)
        return {"relation_id":rid,"strength":rec["strength"],"dormant":rec["dormant"],"successes":rec["successes"],"failures":rec["failures"],"split":split}

    def inspect(self, relation_id: str) -> Optional[dict]:
        rid=self._resolve(relation_id); rec=self.relations.get(rid)
        if not rec: return None
        proto=self._prototype(rec)
        return {"id":rid,"support":rec.get("support",0.0),"strength":rec.get("strength",0.0),"promoted":bool(rec.get("promoted",False)),"dormant":bool(rec.get("dormant",False)),"prototype":{k:sorted(v) if isinstance(v,set) else v for k,v in proto.items()},"prediction_error_ema":rec.get("prediction_error_ema",0.0),"generic_support":rec.get("generic_support",0.0),"successes":rec.get("successes",0),"failures":rec.get("failures",0),"split_generation":rec.get("split_generation",0)}

    def promoted(self) -> List[dict]:
        rows=[self.inspect(rid) for rid,rec in self.relations.items() if rec.get("promoted",False) and not rec.get("dormant",False)]
        rows=[x for x in rows if x]; rows.sort(key=lambda x:(-x["support"],-x["strength"],x["id"])); return rows

    def stats(self) -> dict:
        return {
            "relations": len(self.relations),
            "promoted": sum(1 for x in self.relations.values() if x.get("promoted",False) and not x.get("dormant",False)),
            "dormant": sum(1 for x in self.relations.values() if x.get("dormant",False)),
            "episodes": self.total_episodes,
            "merges": self.merges,
            "splits": self.splits,
            "redirects": len(self.redirects),
            "capacity_rejections": self.capacity_rejections,
            "indexed_connectors": len(self.connector_index),
        }

    def export_state(self) -> dict:
        return {
            "next_id": self.next_id,
            "relations": self.relations,
            "redirects": self.redirects,
            "total_episodes": self.total_episodes,
            "merges": self.merges,
            "splits": self.splits,
            "capacity_rejections": self.capacity_rejections,
        }

    def import_state(self, payload: dict) -> None:
        self.next_id=int(payload.get("next_id",1))
        self.relations={str(k):dict(v) for k,v in payload.get("relations",{}).items()}
        self.redirects={str(k):str(v) for k,v in payload.get("redirects",{}).items()}
        self.total_episodes=int(payload.get("total_episodes",0))
        self.merges=int(payload.get("merges",0))
        self.splits=int(payload.get("splits",0))
        self.capacity_rejections=int(payload.get("capacity_rejections",0))
        self._rebuild_connector_index()
        self._rebuild_runtime_indexes()
