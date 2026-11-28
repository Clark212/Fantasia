from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from math import log1p
import re
from typing import Dict, Iterable, List, Optional, Tuple

from .config import ASMConfig
from .encoder import STOPWORDS, ConceptEncoder, light_stem
from .parsing import Relation, StructuralFrame, StructuralParser, WORDS


@dataclass(slots=True)
class PerceptionDecision:
    frame: StructuralFrame
    confidence: float
    margin: float
    source: str
    details: List[dict]


class LearnedRelationPerception:
    """
    Learned bridge from unfamiliar surface wording into ASM's structural space.

    The hand-written StructuralParser remains a conservative bootstrap teacher.
    Every parser-supported observation teaches this module:
      * what subject-side contexts tend to look like for each relation,
      * what object-side contexts tend to look like,
      * what connector words/phrases express that relation,
      * which abstract cues co-occur with it.

    For an unsupported sentence, this module searches possible subject / connector /
    object splits. It combines learned role-context evidence with distributional
    semantic similarity from ASM's OnlineSemanticMap. High-confidence inferences
    can then be retained as new connector knowledge.

    This is not unrestricted language understanding. A completely novel phrase in
    a completely novel context can still be unknowable without evidence, and the
    module abstains when competing interpretations are too close.
    """

    SAFE_KINDS = (
        "CAUSE", "INCREASE", "DECREASE", "ENABLE",
        "PREVENT", "TRIGGER", "BECOME",
    )

    AUXILIARY = {
        "do", "does", "did", "has", "have", "had",
        "is", "are", "was", "were", "be", "been", "being",
        "to", "into", "the", "a", "an", "very", "really", "directly",
        "gradually", "steadily", "significantly", "slightly",
        "usually", "often", "always", "reliably",
    }

    def __init__(
        self,
        config: ASMConfig,
        encoder: ConceptEncoder,
        bootstrap_parser: StructuralParser,
    ):
        self.cfg = config
        self.encoder = encoder
        self.parser = bootstrap_parser

        self.support: Counter[str] = Counter()
        self.left_counts: Dict[str, Counter[str]] = defaultdict(Counter)
        self.right_counts: Dict[str, Counter[str]] = defaultdict(Counter)
        self.cue_counts: Dict[str, Counter[str]] = defaultdict(Counter)
        self.connector_token_counts: Dict[str, Counter[str]] = defaultdict(Counter)
        self.connector_phrase_counts: Dict[str, Counter[str]] = defaultdict(Counter)
        self.left_len_counts: Dict[str, Counter[int]] = defaultdict(Counter)
        self.right_len_counts: Dict[str, Counter[int]] = defaultdict(Counter)
        self.learned_phrase_sources: Dict[str, dict] = {}
        self.total_examples = 0
        self.inferred_examples = 0

    @staticmethod
    def _clean_raw(text: str) -> str:
        return " ".join(text.lower().replace("’", "'").strip().split())

    def _clauses(self, text: str) -> List[str]:
        raw = self._clean_raw(text)
        for old, new in self.parser.CONTRACTIONS.items():
            raw = re.sub(rf"\b{re.escape(old)}\b", new, raw)
        return [
            c.strip(" ,!?")
            for c in re.split(
                r"[.;]+|\s+and\s+then\s+|\s+but\s+|"
                r"\s+and\s+(?=(?:[\w-]+\s+){0,4}(?:does|do|did)\s+not)",
                raw,
            )
            if c.strip(" ,!?")
        ]

    def _stems(self, phrase: str) -> List[str]:
        return [
            light_stem(tok)
            for tok in WORDS.findall(phrase.lower())
            if tok not in STOPWORDS
        ]

    def _connector_stems(self, phrase: str) -> List[str]:
        out = []
        for tok in WORDS.findall(phrase.lower()):
            if tok in self.AUXILIARY or tok in {"not", "never"}:
                continue
            stem = light_stem(tok)
            if stem:
                out.append(stem)
        return out

    def _cues(self, text: str) -> List[str]:
        return list(dict.fromkeys(
            self.parser.CUE_MAP[t]
            for t in WORDS.findall(text.lower())
            if t in self.parser.CUE_MAP
        ))

    def _known_clause_match(self, clause: str) -> Optional[dict]:
        """Recover raw role/connector spans from the bootstrap parser grammar."""
        m = self.parser.threshold.fullmatch(clause)
        if m:
            return {
                "kind": "THRESHOLD",
                "left": m["left"],
                "right": m["right"] or "threshold event",
                "connector": clause[m.end("left"):m.start("right") if m["right"] else len(clause)],
                "negated": bool(m["neg"]),
            }

        for kind, pattern in self.parser.passive:
            m = pattern.fullmatch(clause)
            if m:
                # For learning relation semantics we keep logical left/right, not
                # the English passive surface ordering.
                lo = min(m.end("left"), m.end("right"))
                hi = max(m.start("left"), m.start("right"))
                connector = clause[lo:hi]
                return {
                    "kind": kind,
                    "left": m["left"],
                    "right": m["right"],
                    "connector": connector,
                    "negated": bool(m["neg"]),
                }

        for kind, pattern in self.parser.active:
            m = pattern.fullmatch(clause)
            if m:
                return {
                    "kind": kind,
                    "left": m["left"],
                    "right": m["right"],
                    "connector": clause[m.end("left"):m.start("right")],
                    "negated": bool(m["neg"]),
                }
        return None

    def _learn_example(
        self,
        kind: str,
        left: str,
        connector: str,
        right: str,
        cues: Iterable[str],
        *,
        weight: float = 1.0,
        source: str = "bootstrap",
    ) -> None:
        if kind not in self.SAFE_KINDS:
            return

        weight = max(0.05, float(weight))
        self.support[kind] += weight
        self.left_counts[kind].update({x: weight for x in set(self._stems(left))})
        self.right_counts[kind].update({x: weight for x in set(self._stems(right))})
        self.cue_counts[kind].update({x: weight for x in set(cues)})
        self.left_len_counts[kind][len(self._stems(left))] += weight
        self.right_len_counts[kind][len(self._stems(right))] += weight

        conn = self._connector_stems(connector)
        phrase = " ".join(conn)
        if phrase:
            self.connector_phrase_counts[kind][phrase] += weight
            for stem in set(conn):
                self.connector_token_counts[kind][stem] += weight

            rec = self.learned_phrase_sources.setdefault(
                phrase,
                {"relations": {}, "sources": Counter(), "observations": 0.0},
            )
            rels = Counter(rec.get("relations", {}))
            rels[kind] += weight
            rec["relations"] = dict(rels)
            sources = Counter(rec.get("sources", {}))
            sources[source] += weight
            rec["sources"] = dict(sources)
            rec["observations"] = float(rec.get("observations", 0.0)) + weight

        self.total_examples += weight
        if source == "inferred":
            self.inferred_examples += weight

    def observe_bootstrap(self, text: str, frame: StructuralFrame) -> int:
        """Learn only from conservative parser-supported relations."""
        if not frame.supported:
            return 0

        clauses = self._clauses(text)
        learned = 0
        relation_index = 0
        all_cues = self._cues(text)

        for clause in clauses:
            known = self._known_clause_match(clause)
            if not known:
                continue
            if known["kind"] == "THRESHOLD":
                # THRESHOLD is handled by the stable parser and is not one of the
                # open-verb relation families in this learner.
                relation_index += 1
                continue
            self._learn_example(
                known["kind"],
                known["left"],
                known["connector"],
                known["right"],
                all_cues,
                weight=1.0,
                source="bootstrap",
            )
            learned += 1
            relation_index += 1
        return learned

    def learn_decision(self, decision: PerceptionDecision) -> int:
        if decision.source != "learned" or not decision.frame.supported:
            return 0
        if decision.confidence < self.cfg.perception_pseudolearn_threshold:
            return 0

        learned = 0
        for detail in decision.details:
            self._learn_example(
                detail["kind"],
                detail["left_raw"],
                detail["connector_raw"],
                detail["right_raw"],
                detail.get("cues", []),
                weight=max(0.20, decision.confidence * self.cfg.perception_pseudolearn_weight),
                source="inferred",
            )
            learned += 1
        return learned

    def _counter_score(self, stems: Iterable[str], counter: Counter[str]) -> float:
        stems = list(dict.fromkeys(stems))
        if not stems or not counter:
            return 0.0

        maximum = max(counter.values()) if counter else 1.0
        contributions = []
        for stem in stems:
            direct = float(counter.get(stem, 0.0)) / maximum
            semantic = 0.0
            for alias, similarity in self.encoder.semantic.similar(stem):
                semantic = max(
                    semantic,
                    similarity * float(counter.get(alias, 0.0)) / maximum,
                )
            contributions.append(max(direct, 0.82 * semantic))

        # A role phrase may contain modifiers never seen before, so reward the
        # strongest evidence and a smaller average-support term.
        return min(1.0, 0.68 * max(contributions) + 0.32 * (sum(contributions) / len(contributions)))

    def _connector_score(self, stems: Iterable[str], kind: str) -> float:
        stems = list(dict.fromkeys(stems))
        if not stems:
            return 0.0

        # Score a learned phrase by how specifically it predicts this relation,
        # not by comparing its raw count to old high-frequency bootstrap verbs.
        # This lets one confident newly learned paraphrase become useful quickly.
        phrase = " ".join(stems)
        phrase_score = 0.0
        if phrase:
            by_kind = {
                k: float(counter.get(phrase, 0.0))
                for k, counter in self.connector_phrase_counts.items()
            }
            total = sum(by_kind.values())
            if total > 0.0:
                purity = by_kind.get(kind, 0.0) / total
                support = min(1.0, total / 0.30)
                phrase_score = purity * support

        token_scores = []
        for stem in stems:
            by_kind = {
                k: float(counter.get(stem, 0.0))
                for k, counter in self.connector_token_counts.items()
            }
            total = sum(by_kind.values())
            direct = 0.0
            if total > 0.0:
                direct = (by_kind.get(kind, 0.0) / total) * min(1.0, total / 0.30)

            semantic = 0.0
            for alias, similarity in self.encoder.semantic.similar(stem):
                alias_by_kind = {
                    k: float(counter.get(alias, 0.0))
                    for k, counter in self.connector_token_counts.items()
                }
                alias_total = sum(alias_by_kind.values())
                if alias_total <= 0.0:
                    continue
                alias_purity = alias_by_kind.get(kind, 0.0) / alias_total
                alias_support = min(1.0, alias_total / 0.30)
                semantic = max(semantic, similarity * alias_purity * alias_support)
            token_scores.append(max(direct, semantic))

        token_score = max(token_scores) if token_scores else 0.0
        if phrase_score > 0.0:
            return min(1.0, 0.72 * phrase_score + 0.28 * token_score)
        return min(1.0, token_score)

    def _cue_score(self, cues: Iterable[str], kind: str) -> float:
        cues = list(dict.fromkeys(cues))
        counter = self.cue_counts[kind]
        if not cues or not counter:
            return 0.0
        maximum = max(counter.values())
        vals = [float(counter.get(c, 0.0)) / maximum for c in cues]
        return max(vals) if vals else 0.0

    def _length_score(self, left_len: int, right_len: int, kind: str) -> float:
        def one(value: int, counter: Counter[int]) -> float:
            if not counter:
                return 0.5
            total = sum(counter.values()) or 1.0
            weighted_mean = sum(k * v for k, v in counter.items()) / total
            return 1.0 / (1.0 + abs(float(value) - weighted_mean))
        return 0.5 * one(left_len, self.left_len_counts[kind]) + 0.5 * one(right_len, self.right_len_counts[kind])

    def _has_direct_connector_evidence(self, stems: Iterable[str]) -> bool:
        stems = list(dict.fromkeys(stems))
        if not stems:
            return False
        phrase = " ".join(stems)
        if any(float(counter.get(phrase, 0.0)) > 0.0 for counter in self.connector_phrase_counts.values()):
            return True
        return any(
            any(float(counter.get(stem, 0.0)) > 0.0 for counter in self.connector_token_counts.values())
            for stem in stems
        )

    def _role_token_usage(self, stem: str) -> float:
        total = 0.0
        for counter in self.left_counts.values():
            total += float(counter.get(stem, 0.0))
        for counter in self.right_counts.values():
            total += float(counter.get(stem, 0.0))
        return total

    def _score_split(
        self,
        left: str,
        connector: str,
        right: str,
        cues: List[str],
    ) -> List[Tuple[str, float, dict]]:
        left_stems = self._stems(left)
        right_stems = self._stems(right)
        conn_stems = self._connector_stems(connector)
        if not left_stems or not right_stems or not conn_stems:
            return []

        # A relation phrase with no learned connector evidence must have been
        # observed previously before role context alone is allowed to assign a
        # meaning. This prevents first-sighting gibberish from being labeled
        # merely because the surrounding nouns resemble a known pattern.
        connector_exposed = all(
            self.encoder.semantic.usage.get(stem, 0)
            >= self.cfg.perception_min_unlabeled_exposures
            for stem in conn_stems
        )
        connector_role_clean = all(
            self._role_token_usage(stem) <= 0.0
            for stem in conn_stems
        )
        direct_connector_known = self._has_direct_connector_evidence(conn_stems)

        # Distributional word similarity is useful for unseen language, but a
        # noun/entity already strongly learned in a relation role must not become
        # a connector solely because bag-of-context semantics happen to resemble
        # a verb. Direct connector evidence can override this once such dual use
        # has actually been observed.
        if not connector_role_clean and not direct_connector_known:
            return []

        rows = []
        total_support = sum(self.support.values()) or 1.0
        for kind in self.SAFE_KINDS:
            if self.support[kind] < self.cfg.perception_min_relation_support:
                continue

            l = self._counter_score(left_stems, self.left_counts[kind])
            r = self._counter_score(right_stems, self.right_counts[kind])
            c = self._connector_score(conn_stems, kind)
            if c <= 0.0 and not connector_exposed:
                continue
            q = self._cue_score(cues, kind)
            length_fit = self._length_score(len(left_stems), len(right_stems), kind)
            prior = float(self.support[kind]) / total_support

            # Connector semantics should dominate once learned, but role context
            # can bootstrap a truly unfamiliar connector in a familiar structure.
            role = 0.5 * l + 0.5 * r
            score = (
                self.cfg.perception_connector_weight * c
                + self.cfg.perception_role_weight * role
                + self.cfg.perception_cue_weight * q
                + self.cfg.perception_length_weight * length_fit
                + self.cfg.perception_prior_weight * prior
            )

            # Do not let a broad prior alone create a relation.
            evidence = max(c, role, q)
            if evidence < self.cfg.perception_min_evidence:
                continue

            rows.append((
                kind,
                min(1.0, score),
                {
                    "left_score": l,
                    "right_score": r,
                    "connector_score": c,
                    "cue_score": q,
                    "length_fit": length_fit,
                    "prior": prior,
                    "connector_stems": conn_stems,
                },
            ))

        rows.sort(key=lambda x: (-x[1], x[0]))
        return rows

    def _candidate_splits(self, clause: str) -> Iterable[Tuple[str, str, str, bool]]:
        tokens = WORDS.findall(clause)
        n = len(tokens)
        max_conn = max(1, int(self.cfg.perception_max_connector_tokens))

        for start in range(1, n - 1):
            for length in range(1, max_conn + 1):
                end = start + length
                if end >= n:
                    break

                connector_tokens = tokens[start:end]
                negated = "not" in connector_tokens or "never" in connector_tokens
                useful = [
                    t for t in connector_tokens
                    if t not in self.AUXILIARY and t not in {"not", "never"}
                ]
                if not useful:
                    continue

                left = " ".join(tokens[:start])
                connector = " ".join(connector_tokens)
                right = " ".join(tokens[end:])
                yield left, connector, right, negated

    def _safety_warnings(self, text: str) -> List[str]:
        raw = self._clean_raw(text)
        warnings = []
        if "?" in raw:
            warnings.append("question: open perception does not assert relations from questions")
        if re.search(r"\b(?:if|when|unless|might|may|could|would|should|perhaps|maybe)\b", raw):
            warnings.append("conditional or modal statement: open perception abstains")
        if re.search(r"\b(?:not only|not always|not necessarily|neither|nor|without|fails? to|unable to)\b", raw):
            warnings.append("complex negation: open perception abstains")
        return warnings

    def infer(self, text: str) -> PerceptionDecision:
        safety = self._safety_warnings(text)
        if safety:
            frame = StructuralFrame(text, [], [], self._cues(text), safety)
            return PerceptionDecision(frame, 0.0, 0.0, "abstain", [])

        clauses = self._clauses(text)
        relations: List[Relation] = []
        details: List[dict] = []
        confidences = []
        margins = []
        warnings = []
        all_cues = self._cues(text)

        for clause in clauses:
            # If this clause is already understood by the stable parser, preserve
            # that exact interpretation rather than competing with it.
            stable = self.parser.parse(clause)
            if stable.supported and len(stable.relations) == 1:
                rel = stable.relations[0]
                relations.append(rel)
                confidences.append(1.0)
                margins.append(1.0)
                continue

            candidates = []
            for left, connector, right, negated in self._candidate_splits(clause):
                rows = self._score_split(left, connector, right, all_cues)
                if not rows:
                    continue
                best_kind, best_score, diagnostics = rows[0]
                second = rows[1][1] if len(rows) > 1 else 0.0
                margin = best_score - second

                # Mild preference for compact connectors prevents swallowing
                # half of the subject or object as the relation phrase.
                conn_len = len(self._connector_stems(connector))
                compact_bonus = 0.08 / max(1, conn_len)
                final = min(1.0, best_score + compact_bonus)

                candidates.append({
                    "kind": best_kind,
                    "score": final,
                    "margin": margin,
                    "left_raw": left,
                    "connector_raw": connector,
                    "right_raw": right,
                    "negated": negated,
                    "diagnostics": diagnostics,
                })

            candidates.sort(
                key=lambda x: (-x["score"], -x["margin"], len(self._connector_stems(x["connector_raw"])))
            )
            if not candidates:
                warnings.append("open perception: no supported interpretation")
                continue

            best = candidates[0]
            # Compare against the strongest genuinely different interpretation,
            # not just another token split yielding the same relation.
            alt_score = 0.0
            for cand in candidates[1:]:
                if cand["kind"] != best["kind"]:
                    alt_score = cand["score"]
                    break
            relation_margin = best["score"] - alt_score

            if (
                best["score"] < self.cfg.perception_min_confidence
                or relation_margin < self.cfg.perception_min_margin
            ):
                warnings.append("open perception: ambiguous learned relation")
                continue

            relation = Relation(
                self.parser.normalize_phrase(best["left_raw"]),
                best["kind"],
                self.parser.normalize_phrase(best["right_raw"]),
                confidence=best["score"],
                negated=best["negated"],
            )
            relations.append(relation)
            best["cues"] = list(all_cues)
            best["relation_margin"] = relation_margin
            details.append(best)
            confidences.append(best["score"])
            margins.append(relation_margin)

        entities = list(dict.fromkeys(
            x for rel in relations for x in (rel.left, rel.right)
        ))
        frame = StructuralFrame(
            text,
            entities,
            relations,
            all_cues,
            list(dict.fromkeys(warnings)),
        )

        confidence = min(confidences) if confidences else 0.0
        margin = min(margins) if margins else 0.0
        source = "learned" if frame.supported and details else (
            "bootstrap" if frame.supported else "abstain"
        )
        return PerceptionDecision(frame, confidence, margin, source, details)

    def stats(self) -> dict:
        phrases = set()
        for counter in self.connector_phrase_counts.values():
            phrases.update(counter)
        inferred_phrases = [
            p for p, rec in self.learned_phrase_sources.items()
            if float(rec.get("sources", {}).get("inferred", 0.0)) > 0.0
        ]
        return {
            "examples": float(self.total_examples),
            "inferred_examples": float(self.inferred_examples),
            "connector_phrases": len(phrases),
            "inferred_connector_phrases": len(inferred_phrases),
            "relation_support": dict(self.support),
        }

    def export_state(self) -> dict:
        return {
            "support": dict(self.support),
            "left_counts": {k: dict(v) for k, v in self.left_counts.items()},
            "right_counts": {k: dict(v) for k, v in self.right_counts.items()},
            "cue_counts": {k: dict(v) for k, v in self.cue_counts.items()},
            "connector_token_counts": {
                k: dict(v) for k, v in self.connector_token_counts.items()
            },
            "connector_phrase_counts": {
                k: dict(v) for k, v in self.connector_phrase_counts.items()
            },
            "left_len_counts": {
                k: {str(kk): vv for kk, vv in v.items()}
                for k, v in self.left_len_counts.items()
            },
            "right_len_counts": {
                k: {str(kk): vv for kk, vv in v.items()}
                for k, v in self.right_len_counts.items()
            },
            "learned_phrase_sources": self.learned_phrase_sources,
            "total_examples": self.total_examples,
            "inferred_examples": self.inferred_examples,
        }

    def import_state(self, payload: dict) -> None:
        self.support = Counter({
            str(k): float(v) for k, v in payload.get("support", {}).items()
        })
        self.left_counts = defaultdict(Counter)
        self.right_counts = defaultdict(Counter)
        self.cue_counts = defaultdict(Counter)
        self.connector_token_counts = defaultdict(Counter)
        self.connector_phrase_counts = defaultdict(Counter)
        self.left_len_counts = defaultdict(Counter)
        self.right_len_counts = defaultdict(Counter)

        for name, target in (
            ("left_counts", self.left_counts),
            ("right_counts", self.right_counts),
            ("cue_counts", self.cue_counts),
            ("connector_token_counts", self.connector_token_counts),
            ("connector_phrase_counts", self.connector_phrase_counts),
        ):
            for kind, values in payload.get(name, {}).items():
                target[str(kind)] = Counter({
                    str(k): float(v) for k, v in values.items()
                })

        for name, target in (
            ("left_len_counts", self.left_len_counts),
            ("right_len_counts", self.right_len_counts),
        ):
            for kind, values in payload.get(name, {}).items():
                target[str(kind)] = Counter({
                    int(k): float(v) for k, v in values.items()
                })

        self.learned_phrase_sources = {
            str(k): dict(v)
            for k, v in payload.get("learned_phrase_sources", {}).items()
        }
        self.total_examples = float(payload.get("total_examples", 0.0))
        self.inferred_examples = float(payload.get("inferred_examples", 0.0))
