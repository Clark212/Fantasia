from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from typing import Dict, List

from .config import ASMConfig
from .structural import StructuralFrame, StructuralMemory


class AssociativeExpander:
    """
    Expands a problem through three channels:

    1. graph association: nearby learned concept connections
    2. structural analogy: problems with similar relation topology
    3. abstraction: reusable schemas formed from repeated structures

    It returns ranked hypotheses, not a claim of certainty.
    """

    def __init__(self, config: ASMConfig, structural: StructuralMemory):
        self.cfg = config
        self.structural = structural

    def graph_expand(
        self,
        seed_concepts: Dict[str, float],
        edges: Dict[str, Dict[str, float]],
    ) -> List[dict]:
        frontier = {
            k: abs(v)
            for k, v in seed_concepts.items()
            if abs(v) > 0.0
        }
        visited = dict(frontier)
        paths: Dict[str, List[str]] = {
            k: [k]
            for k in frontier
        }

        for depth in range(self.cfg.expansion_depth):
            nxt: Dict[str, float] = defaultdict(float)
            nxt_path: Dict[str, List[str]] = {}

            strongest_frontier = sorted(
                frontier.items(),
                key=lambda kv: kv[1],
                reverse=True,
            )[: self.cfg.expansion_beam]

            for src, activation in strongest_frontier:
                outgoing = sorted(
                    edges.get(src, {}).items(),
                    key=lambda kv: abs(kv[1]),
                    reverse=True,
                )[: self.cfg.expansion_beam]

                for dst, weight in outgoing:
                    score = activation * abs(weight) * (0.72 ** (depth + 1))
                    if score <= visited.get(dst, 0.0):
                        continue
                    nxt[dst] = max(nxt[dst], score)
                    nxt_path[dst] = paths.get(src, [src]) + [dst]

            for node, score in nxt.items():
                if score > visited.get(node, 0.0):
                    visited[node] = score
                    paths[node] = nxt_path[node]

            frontier = dict(
                sorted(
                    nxt.items(),
                    key=lambda kv: kv[1],
                    reverse=True,
                )[: self.cfg.expansion_beam]
            )
            if not frontier:
                break

        seeds = set(seed_concepts)
        expanded = [
            {
                "concept": node,
                "score": score,
                "path": paths.get(node, [node]),
            }
            for node, score in visited.items()
            if node not in seeds
        ]
        expanded.sort(key=lambda x: x["score"], reverse=True)
        return expanded[: self.cfg.expansion_beam]

    def hypotheses(
        self,
        frame: StructuralFrame,
        graph_links: List[dict],
        analogies: List[dict],
    ) -> List[dict]:
        scores: Dict[str, dict] = {}
        assessment = self.structural.assess(frame)
        if assessment["status"] != "predicted":
            return []

        # Candidate next relations from structural transitions.
        for relation, confidence in self.structural.predict_next_relations(frame):
            key = f"RELATION:{relation}"
            scores[key] = {
                "hypothesis": key,
                "score": 0.55 * confidence,
                "evidence": [f"learned structural transition -> {relation}"],
            }

        # Analogy-derived relation hypotheses.
        for analogy in analogies:
            rels = analogy.get("relations", [])
            if not rels:
                continue
            for relation in rels:
                kind = ("NOT:" if relation.get("negated", False) else "") + relation["kind"]
                key = f"ANALOGY:{kind}"
                contribution = 0.45 * analogy["score"]
                entry = scores.setdefault(
                    key,
                    {
                        "hypothesis": key,
                        "score": 0.0,
                        "evidence": [],
                    },
                )
                entry["score"] += contribution
                if len(entry["evidence"]) < 3:
                    entry["evidence"].append(
                        f"{analogy['text']} ({analogy['score']:.2f})"
                    )

        # Analogy-derived abstract cues. This is where a new domain can inherit
        # a structural idea such as FAILURE or THRESHOLD without sharing nouns.
        present_cues = set(frame.cues)
        for analogy in analogies:
            for cue in analogy.get("cues", []):
                if cue in present_cues:
                    continue
                key = f"CUE:{cue}"
                entry = scores.setdefault(
                    key,
                    {
                        "hypothesis": key,
                        "score": 0.0,
                        "evidence": [],
                    },
                )
                entry["score"] += 0.32 * analogy["score"]
                if len(entry["evidence"]) < 3:
                    entry["evidence"].append(
                        f"transferred from {analogy['text']} ({analogy['score']:.2f})"
                    )

        # Graph-derived conceptual hypotheses.
        for link in graph_links[:10]:
            key = f"CONCEPT:{link['concept']}"
            entry = scores.setdefault(
                key,
                {
                    "hypothesis": key,
                    "score": 0.0,
                    "evidence": [],
                },
            )
            entry["score"] += min(0.4, 0.4 * link["score"])
            if len(entry["evidence"]) < 2:
                entry["evidence"].append(" -> ".join(link["path"][:5]))

        ranked = list(scores.values())
        for item in ranked:
            item["score"] = min(1.0, item["score"])

        ranked.sort(key=lambda x: x["score"], reverse=True)
        limit = self.cfg.expansion_max_hypotheses
        top_relation = next((h for h in ranked if h["hypothesis"].startswith("RELATION:")), None)
        selected = ranked[:limit]
        if top_relation and top_relation not in selected and limit > 0:
            selected[-1] = top_relation
        return selected

    def expand(
        self,
        frame: StructuralFrame,
        encoded: Dict[str, float],
        field_edges: Dict[str, Dict[str, float]],
    ) -> dict:
        graph_links = self.graph_expand(encoded, field_edges)
        analogies = self.structural.analogies(
            frame,
            limit=self.cfg.expansion_max_hypotheses,
        )

        abstraction_hits = []
        frame_sig = ">".join(frame.signature()) if frame.supported else ""
        for abstraction_id, data in self.structural.abstractions.items():
            sig = data.get("signature", "")
            if not sig:
                continue

            # Related if they share at least one relation type.
            fparts = set(frame_sig.split(">")) if frame_sig else set()
            sparts = set(sig.split(">"))
            overlap = len(fparts & sparts) / max(1, len(fparts | sparts))
            cue_overlap = len(
                set(frame.cues) & set(data.get("dominant_cues", []))
            )
            score = 0.75 * overlap + 0.08 * cue_overlap
            if score > 0:
                abstraction_hits.append({
                    "id": abstraction_id,
                    "score": min(1.0, score),
                    "support": data.get("support", 0),
                    "cues": data.get("dominant_cues", []),
                })

        abstraction_hits.sort(key=lambda x: x["score"], reverse=True)

        return {
            "frame": {
                "entities": frame.entities,
                "relations": [
                    {**asdict(r), "key": r.key}
                    for r in frame.relations
                ],
                "cues": frame.cues,
                "supported": frame.supported,
                "warnings": frame.warnings,
            },
            "prediction": self.structural.assess(frame),
            "graph_links": graph_links,
            "association_note": "Graph links and analogy cues are associations, not logical implications.",
            "analogies": analogies,
            "abstractions": abstraction_hits[:8],
            "hypotheses": self.hypotheses(
                frame,
                graph_links,
                analogies,
            ),
        }
