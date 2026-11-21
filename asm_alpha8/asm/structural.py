from __future__ import annotations
from collections import Counter, defaultdict
from dataclasses import asdict
from typing import Dict, List, Tuple
from .config import ASMConfig
from .parsing import Relation, StructuralFrame, StructuralParser


class StructuralMemory:
    """
    Learns reusable relation schemas and cross-domain structural analogies.

    A schema is based on relation structure rather than exact entity names.
    Repeated relation sequences can create an abstraction node.
    """

    def __init__(self, config: ASMConfig):
        self.cfg = config
        self.relation_counts: Counter[str] = Counter()
        self.transition_counts: Dict[str, Counter[str]] = defaultdict(Counter)
        self.cue_transition_counts: Dict[str, Dict[str, Counter[str]]] = defaultdict(
            lambda: defaultdict(Counter)
        )
        self.schemas: Dict[str, dict] = {}
        self.examples: List[dict] = []
        self.abstractions: Dict[str, dict] = {}

    def observe(self, frame: StructuralFrame) -> None:
        if not frame.supported:
            return

        kinds = list(frame.signature())
        for kind in kinds:
            self.relation_counts[kind] += 1

        for a, b in zip(kinds, kinds[1:]):
            self.transition_counts[a][b] += 1
            for cue in frame.cues:
                self.cue_transition_counts[cue][a][b] += 1

        signature = ">".join(kinds)
        schema = self.schemas.setdefault(
            signature,
            {
                "signature": signature,
                "support": 0,
                "cue_counts": {},
                "examples": [],
            },
        )
        schema["support"] += 1

        cue_counts = Counter(schema.get("cue_counts", {}))
        cue_counts.update(frame.cues)
        schema["cue_counts"] = dict(cue_counts)

        ex = {
            "text": frame.text,
            "signature": signature,
            "cues": list(frame.cues),
            "relations": [asdict(r) for r in frame.relations],
        }
        schema["examples"].append(ex)
        if len(schema["examples"]) > 20:
            schema["examples"] = schema["examples"][-20:]

        self.examples.append(ex)
        if len(self.examples) > 1200:
            self.examples = self.examples[-1200:]

        if schema["support"] >= self.cfg.abstraction_min_support:
            abstraction_id = f"ABS:{signature}"
            self.abstractions[abstraction_id] = {
                "signature": signature,
                "support": schema["support"],
                "dominant_cues": [
                    cue
                    for cue, _ in Counter(schema["cue_counts"]).most_common(6)
                ],
            }

    @staticmethod
    def _relation_similarity(a: List[str], b: List[str]) -> float:
        if not a or not b:
            return 0.0
        # Small LCS-based structural similarity.
        dp = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
        for i in range(1, len(a) + 1):
            for j in range(1, len(b) + 1):
                if a[i - 1] == b[j - 1]:
                    dp[i][j] = dp[i - 1][j - 1] + 1
                else:
                    dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
        lcs = dp[-1][-1]
        return (2.0 * lcs) / (len(a) + len(b))

    def analogies(
        self,
        frame: StructuralFrame,
        limit: int = 8,
    ) -> List[dict]:
        if not frame.supported:
            return []
        qsig = list(frame.signature())
        qcues = set(frame.cues)
        results = []
        seen = set()

        for ex in self.examples:
            if ex["text"] in seen:
                continue
            seen.add(ex["text"])
            esig = ex["signature"].split(">") if ex["signature"] else []
            # The observed relation prefix, including polarity, must match.
            if esig[:len(qsig)] != qsig:
                continue
            structural = self._relation_similarity(qsig, esig)

            ecues = set(ex.get("cues", []))
            cue_score = (
                len(qcues & ecues) / max(1, len(qcues | ecues))
                if (qcues or ecues)
                else 0.0
            )

            # Surface overlap is deliberately a minor term.
            qents = set(frame.entities)
            eents = set()
            for r in ex.get("relations", []):
                eents.add(r["left"])
                eents.add(r["right"])
            surface = len(qents & eents) / max(1, len(qents | eents))

            score = 0.68 * structural + 0.24 * cue_score + 0.08 * surface
            if score >= self.cfg.structural_min_confidence:
                results.append({
                    "score": score,
                    "structural": structural,
                    "cue_similarity": cue_score,
                    "surface_similarity": surface,
                    "text": ex["text"],
                    "signature": ex["signature"],
                    "relations": ex["relations"],
                    "cues": ex.get("cues", []),
                })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    def predict_next_relations(
        self,
        frame: StructuralFrame,
        limit: int = 5,
    ) -> List[Tuple[str, float]]:
        if not frame.supported:
            return []

        last = frame.relations[-1].key
        global_counts = self.transition_counts.get(last, Counter())

        # Global evidence is the prior. Active structural cues then provide
        # context-specific evidence. This lets the same relation lead to
        # different futures in different kinds of problems.
        scores: Dict[str, float] = defaultdict(float)
        total_global = sum(global_counts.values()) or 1

        for kind, count in global_counts.items():
            scores[kind] += 0.30 * (count / total_global)

        active_cue_sources = 0
        for cue in frame.cues:
            counts = self.cue_transition_counts.get(cue, {}).get(last)
            if not counts:
                continue
            active_cue_sources += 1
            total = sum(counts.values()) or 1
            for kind, count in counts.items():
                scores[kind] += 0.70 * (count / total)

        if not scores:
            return []

        # Average cue contribution so adding extra cues does not inflate scores.
        if active_cue_sources > 1:
            cue_scale = 1.0 / active_cue_sources
            rebuilt: Dict[str, float] = defaultdict(float)

            for kind, count in global_counts.items():
                rebuilt[kind] += 0.30 * (count / total_global)

            for cue in frame.cues:
                counts = self.cue_transition_counts.get(cue, {}).get(last)
                if not counts:
                    continue
                total = sum(counts.values()) or 1
                for kind, count in counts.items():
                    rebuilt[kind] += (
                        0.70
                        * cue_scale
                        * (count / total)
                    )
            scores = rebuilt

        ranked = sorted(
            scores.items(),
            key=lambda x: (-x[1], x[0]),
        )
        return ranked[:limit]

    def assess(self, frame: StructuralFrame) -> dict:
        """Heuristic evidence ranking with abstention; scores are not probabilities."""
        base = {"status": "unsupported", "relation": None, "score": 0.0,
                "margin": 0.0, "support": 0, "candidates": [],
                "reason": "; ".join(frame.warnings) or "No recognized relation."}
        if not frame.supported:
            return base
        ranked = self.predict_next_relations(frame)
        if not ranked:
            return {**base, "status": "no_evidence",
                    "reason": "No learned continuation for this relation and polarity."}
        counts = self.transition_counts[frame.relations[-1].key]
        candidates = [{"relation": k, "score": v, "support": counts[k]} for k,v in ranked]
        best, score = ranked[0]
        margin = score - (ranked[1][1] if len(ranked) > 1 else 0.0)
        base.update(score=score, margin=margin, support=counts[best], candidates=candidates)
        if counts[best] < self.cfg.structural_min_support:
            return {**base, "status": "no_evidence", "reason": "Too few supporting observations."}
        if margin < self.cfg.structural_min_margin:
            return {**base, "status": "ambiguous", "reason": "Competing continuations have similar evidence."}
        return {**base, "status": "predicted", "relation": best,
                "reason": "Learned relation continuation; not a logical guarantee."}

    def export_state(self) -> dict:
        return {
            "relation_counts": dict(self.relation_counts),
            "transition_counts": {
                k: dict(v)
                for k, v in self.transition_counts.items()
            },
            "cue_transition_counts": {
                cue: {
                    src: dict(counter)
                    for src, counter in by_source.items()
                }
                for cue, by_source in self.cue_transition_counts.items()
            },
            "schemas": self.schemas,
            "examples": self.examples,
            "abstractions": self.abstractions,
        }

    def import_state(self, payload: dict) -> None:
        self.relation_counts = Counter(
            {str(k): int(v) for k, v in payload.get("relation_counts", {}).items()}
        )
        self.transition_counts = defaultdict(Counter)
        for k, v in payload.get("transition_counts", {}).items():
            self.transition_counts[str(k)] = Counter(
                {str(kk): int(vv) for kk, vv in v.items()}
            )

        self.cue_transition_counts = defaultdict(
            lambda: defaultdict(Counter)
        )
        for cue, by_source in payload.get(
            "cue_transition_counts",
            {},
        ).items():
            for src, values in by_source.items():
                self.cue_transition_counts[str(cue)][str(src)] = Counter(
                    {
                        str(dst): int(count)
                        for dst, count in values.items()
                    }
                )

        self.schemas = dict(payload.get("schemas", {}))
        self.examples = list(payload.get("examples", []))
        self.abstractions = dict(payload.get("abstractions", {}))
