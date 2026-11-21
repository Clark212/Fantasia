from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
import re
import sqlite3
import time
from pathlib import Path
from typing import Any

from .encoder import STOPWORDS, light_stem
from .semantic_event import Proposition, SemanticDecision, SemanticEvent


_QUERY_CONTROL = {
    "what", "which", "who", "when", "where", "why", "how", "does", "do", "did",
    "is", "are", "was", "were", "tell", "said", "say", "remember", "recall", "about",
    "think", "thinks", "believe", "believes", "belief", "expect", "expects", "expected",
    "fear", "fears", "afraid", "want", "wants", "goal", "happen", "happened", "event",
    "me", "you", "i", "my", "your", "the", "a", "an", "that", "this", "it",
}


@dataclass(slots=True)
class EventMemoryQuery:
    event_types: list[str] = field(default_factory=list)
    epistemic: list[str] = field(default_factory=list)
    agents: list[str] = field(default_factory=list)
    terms: list[str] = field(default_factory=list)
    latest_only: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_types": list(self.event_types),
            "epistemic": list(self.epistemic),
            "agents": list(self.agents),
            "terms": list(self.terms),
            "latest_only": bool(self.latest_only),
        }


class SemanticEventMemory:
    """
    Alpha.7 structured event memory.

    This index stores the typed SemanticEvent next to the existing episodic row.
    It does not replace episodic memory or the recurrent ANN.  Retrieval merges
    event type, epistemic state, agent/entity and proposition-term evidence.

    The store also records revision/temporal links.  These links are deliberately
    descriptive rather than causal: alpha.7 prepares transitions for v0.3 but
    does not claim that temporal succession proves causation.
    """

    def __init__(self, db_path: str | Path):
        self.path = str(db_path)
        self.db = sqlite3.connect(self.path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.execute("PRAGMA temp_store=MEMORY")
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS semantic_event_records(
                event_id INTEGER PRIMARY KEY,
                event_type TEXT NOT NULL,
                epistemic TEXT NOT NULL,
                confidence REAL NOT NULL,
                source TEXT NOT NULL,
                agents TEXT NOT NULL,
                proposition_surface TEXT NOT NULL DEFAULT '',
                proposition_canonical TEXT NOT NULL DEFAULT '',
                truth INTEGER,
                persistent_eligible INTEGER NOT NULL DEFAULT 1,
                created_ts REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_sem_event_type
            ON semantic_event_records(event_type, event_id DESC);

            CREATE INDEX IF NOT EXISTS idx_sem_event_epi
            ON semantic_event_records(epistemic, event_id DESC);

            CREATE INDEX IF NOT EXISTS idx_sem_event_prop
            ON semantic_event_records(proposition_canonical, event_id DESC);

            CREATE TABLE IF NOT EXISTS semantic_event_entities(
                entity TEXT NOT NULL,
                role TEXT NOT NULL,
                event_id INTEGER NOT NULL,
                weight REAL NOT NULL,
                PRIMARY KEY(entity, role, event_id)
            );

            CREATE INDEX IF NOT EXISTS idx_sem_event_entity
            ON semantic_event_entities(entity, event_id DESC);

            CREATE TABLE IF NOT EXISTS semantic_event_terms(
                term TEXT NOT NULL,
                event_id INTEGER NOT NULL,
                weight REAL NOT NULL,
                PRIMARY KEY(term, event_id)
            );

            CREATE INDEX IF NOT EXISTS idx_sem_event_term
            ON semantic_event_terms(term, event_id DESC);

            CREATE TABLE IF NOT EXISTS semantic_event_links(
                source_event_id INTEGER NOT NULL,
                target_event_id INTEGER NOT NULL,
                relation TEXT NOT NULL,
                score REAL NOT NULL,
                created_ts REAL NOT NULL,
                PRIMARY KEY(source_event_id, target_event_id, relation)
            );

            CREATE INDEX IF NOT EXISTS idx_sem_event_links_target
            ON semantic_event_links(target_event_id, relation, source_event_id);

            CREATE TABLE IF NOT EXISTS semantic_event_latest(
                state_key TEXT PRIMARY KEY,
                event_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                epistemic TEXT NOT NULL,
                agent_key TEXT NOT NULL,
                proposition_canonical TEXT NOT NULL,
                truth INTEGER,
                updated_ts REAL NOT NULL
            );
            """
        )
        self.db.commit()

    @staticmethod
    def _norm_entity(value: str) -> str:
        return " ".join(str(value).lower().strip().split())

    @staticmethod
    def _terms(text: str) -> list[str]:
        words = re.findall(r"[A-Za-z0-9']+", str(text).lower())
        out: list[str] = []
        seen = set()
        for word in words:
            if word in STOPWORDS or word in _QUERY_CONTROL or len(word) < 2:
                continue
            stem = light_stem(word)
            if stem and stem not in seen:
                out.append(stem)
                seen.add(stem)
        return out[:24]

    @staticmethod
    def _state_key(event: SemanticEvent, proposition: Proposition | None) -> str | None:
        if proposition is None or not proposition.canonical:
            return None
        agents = ">".join(x for x in event.agents if x) or "__world__"
        return f"{event.event_type}|{agents}|{proposition.canonical}"

    @staticmethod
    def _truth_db(value: bool | None) -> int | None:
        if value is None:
            return None
        return 1 if bool(value) else 0

    def count(self) -> int:
        return int(self.db.execute("SELECT COUNT(*) FROM semantic_event_records").fetchone()[0])

    def link_count(self) -> int:
        return int(self.db.execute("SELECT COUNT(*) FROM semantic_event_links").fetchone()[0])

    def missing_events(self, limit: int = 4096) -> list[tuple[int, str]]:
        rows = self.db.execute(
            """
            SELECT e.id, e.text
            FROM events e
            LEFT JOIN semantic_event_records s ON s.event_id=e.id
            WHERE s.event_id IS NULL
            ORDER BY e.id
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        return [(int(i), str(text)) for i, text in rows]

    def _latest_for_agent(self, agent: str, before_event: int) -> int | None:
        row = self.db.execute(
            """
            SELECT x.event_id
            FROM semantic_event_entities x
            WHERE x.entity=? AND x.role='agent' AND x.event_id<?
            ORDER BY x.event_id DESC LIMIT 1
            """,
            (agent, int(before_event)),
        ).fetchone()
        return int(row[0]) if row else None

    def _latest_for_prop(self, canonical: str, before_event: int) -> tuple[int, str, str, int | None] | None:
        row = self.db.execute(
            """
            SELECT event_id,event_type,epistemic,truth
            FROM semantic_event_records
            WHERE proposition_canonical=? AND event_id<?
            ORDER BY event_id DESC LIMIT 1
            """,
            (canonical, int(before_event)),
        ).fetchone()
        if not row:
            return None
        return int(row[0]), str(row[1]), str(row[2]), (None if row[3] is None else int(row[3]))

    def add(self, event_id: int, decision: SemanticDecision, *, raw_text: str) -> dict[str, Any]:
        event = decision.primary
        proposition = event.proposition
        if proposition is None:
            # Unknown/general persistent observations still receive a searchable
            # proposition, but their event type remains "other" rather than being
            # falsely upgraded to an observation.
            proposition = Proposition.from_surface(raw_text)

        agents = [self._norm_entity(x) for x in event.agents if self._norm_entity(x)]
        surface = proposition.surface
        canonical = proposition.canonical
        truth = self._truth_db(proposition.truth)
        now = time.time()
        state_key = self._state_key(event, proposition)
        links: list[dict[str, Any]] = []

        with self.db:
            self.db.execute(
                """
                INSERT OR REPLACE INTO semantic_event_records(
                    event_id,event_type,epistemic,confidence,source,agents,
                    proposition_surface,proposition_canonical,truth,
                    persistent_eligible,created_ts
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    int(event_id), str(event.event_type), str(event.epistemic),
                    float(event.confidence), str(event.source),
                    json.dumps(agents, separators=(",", ":")),
                    str(surface), str(canonical), truth,
                    1 if event.persistent_eligible else 0, now,
                ),
            )
            self.db.execute("DELETE FROM semantic_event_entities WHERE event_id=?", (int(event_id),))
            self.db.execute("DELETE FROM semantic_event_terms WHERE event_id=?", (int(event_id),))

            for agent in agents:
                self.db.execute(
                    "INSERT OR REPLACE INTO semantic_event_entities(entity,role,event_id,weight) VALUES(?,?,?,?)",
                    (agent, "agent", int(event_id), 1.0),
                )

            # Proposition terms are indexed as entity-like anchors too.  Alpha.7
            # intentionally calls these proposition terms, not discovered world
            # entities; true entity induction remains a later research problem.
            for term in self._terms(surface):
                self.db.execute(
                    "INSERT OR REPLACE INTO semantic_event_terms(term,event_id,weight) VALUES(?,?,?)",
                    (term, int(event_id), 1.0),
                )
                self.db.execute(
                    "INSERT OR REPLACE INTO semantic_event_entities(entity,role,event_id,weight) VALUES(?,?,?,?)",
                    (term, "proposition_term", int(event_id), 0.55),
                )

            def add_link(src: int | None, relation: str, score: float) -> None:
                if src is None or int(src) == int(event_id):
                    return
                self.db.execute(
                    "INSERT OR REPLACE INTO semantic_event_links(source_event_id,target_event_id,relation,score,created_ts) VALUES(?,?,?,?,?)",
                    (int(src), int(event_id), str(relation), float(score), now),
                )
                links.append({"source_event_id": int(src), "target_event_id": int(event_id), "relation": relation, "score": float(score)})

            for agent in agents[:3]:
                add_link(self._latest_for_agent(agent, int(event_id)), "agent_next", 0.45)

            previous_prop = self._latest_for_prop(canonical, int(event_id)) if canonical else None
            if previous_prop:
                prev_id, prev_type, prev_epi, prev_truth = previous_prop
                add_link(prev_id, "proposition_next", 0.50)
                if prev_type != event.event_type or prev_epi != event.epistemic:
                    add_link(prev_id, "epistemic_shift", 0.75)

            if state_key:
                old = self.db.execute(
                    "SELECT event_id,truth,epistemic FROM semantic_event_latest WHERE state_key=?",
                    (state_key,),
                ).fetchone()
                if old:
                    old_id = int(old[0])
                    old_truth = None if old[1] is None else int(old[1])
                    old_epi = str(old[2])
                    if old_truth is not None and truth is not None and old_truth != truth:
                        add_link(old_id, "revises", 1.0)
                        add_link(old_id, "contradicts", 1.0)
                    elif old_epi != event.epistemic:
                        add_link(old_id, "revises", 0.85)
                    else:
                        add_link(old_id, "reaffirms", 0.60)
                self.db.execute(
                    """
                    INSERT INTO semantic_event_latest(
                        state_key,event_id,event_type,epistemic,agent_key,
                        proposition_canonical,truth,updated_ts
                    ) VALUES(?,?,?,?,?,?,?,?)
                    ON CONFLICT(state_key) DO UPDATE SET
                        event_id=excluded.event_id,
                        event_type=excluded.event_type,
                        epistemic=excluded.epistemic,
                        agent_key=excluded.agent_key,
                        proposition_canonical=excluded.proposition_canonical,
                        truth=excluded.truth,
                        updated_ts=excluded.updated_ts
                    """,
                    (
                        state_key, int(event_id), event.event_type, event.epistemic,
                        ">".join(agents) or "__world__", canonical, truth, now,
                    ),
                )

        return {"event_id": int(event_id), "state_key": state_key, "links": links}

    @classmethod
    def query_from_text(cls, text: str) -> EventMemoryQuery:
        t = " ".join(str(text).lower().replace("’", "'").split())
        q = EventMemoryQuery()

        patterns = [
            ("nested_belief", r"what does\s+([a-z][a-z0-9_-]*)\s+think\s+([a-z][a-z0-9_-]*)\s+(?:believes?|thinks?)"),
            ("belief", r"(?:what does|does|did)\s+([a-z][a-z0-9_-]*)\s+(?:believe|think|assume|suspect)"),
            ("expectation", r"(?:what does|does|did)\s+([a-z][a-z0-9_-]*)\s+(?:expect|anticipate)"),
            ("fear", r"(?:what does|does|did)\s+([a-z][a-z0-9_-]*)\s+(?:fear|worry)"),
            ("goal", r"(?:what does|does|did)\s+([a-z][a-z0-9_-]*)\s+(?:want|hope|intend|plan)"),
        ]
        for event_type, pattern in patterns:
            m = re.search(pattern, t, re.I)
            if m:
                q.event_types = [event_type]
                q.agents = [cls._norm_entity(x) for x in m.groups() if x]
                q.latest_only = True
                break

        if not q.event_types:
            if re.search(r"\b(?:belief|believes|think|thinks)\b", t):
                q.event_types = ["belief", "nested_belief"]
            elif re.search(r"\b(?:expect|expects|expected|anticipate)\b", t):
                q.event_types = ["expectation"]
            elif re.search(r"\b(?:fear|fears|afraid|worried|worry)\b", t):
                q.event_types = ["fear"]
            elif re.search(r"\b(?:want|wants|goal|hope|intends?)\b", t):
                q.event_types = ["goal"]

        q.terms = cls._terms(t)
        # Names caught as agents should not be double-counted as generic topic terms.
        q.terms = [term for term in q.terms if term not in set(q.agents)]
        return q

    @classmethod
    def query_from_event(cls, decision: SemanticDecision, *, raw_text: str) -> EventMemoryQuery:
        event = decision.primary
        if event.event_type == "question":
            return cls.query_from_text(raw_text)
        q = EventMemoryQuery(
            event_types=[] if event.event_type in {"other", "question"} else [event.event_type],
            epistemic=[] if event.epistemic in {"unknown", "queried"} else [event.epistemic],
            agents=[cls._norm_entity(x) for x in event.agents if cls._norm_entity(x)],
            terms=cls._terms(event.proposition.surface if event.proposition else raw_text),
            latest_only=False,
        )
        return q

    def _candidate_ids(self, query: EventMemoryQuery, *, max_candidates: int = 256) -> dict[int, dict[str, Any]]:
        candidates: dict[int, dict[str, Any]] = {}

        def add(event_id: int, kind: str, value: float) -> None:
            rec = candidates.setdefault(int(event_id), {"score": 0.0, "matched_by": []})
            rec["score"] += float(value)
            if kind not in rec["matched_by"]:
                rec["matched_by"].append(kind)

        for event_type in query.event_types[:3]:
            rows = self.db.execute(
                "SELECT event_id FROM semantic_event_records WHERE event_type=? ORDER BY event_id DESC LIMIT ?",
                (event_type, max_candidates),
            ).fetchall()
            for (event_id,) in rows:
                add(int(event_id), f"type:{event_type}", 3.0)

        for epi in query.epistemic[:3]:
            rows = self.db.execute(
                "SELECT event_id FROM semantic_event_records WHERE epistemic=? ORDER BY event_id DESC LIMIT ?",
                (epi, max_candidates),
            ).fetchall()
            for (event_id,) in rows:
                add(int(event_id), f"epistemic:{epi}", 1.3)

        for agent in query.agents[:3]:
            rows = self.db.execute(
                "SELECT event_id FROM semantic_event_entities WHERE entity=? AND role='agent' ORDER BY event_id DESC LIMIT ?",
                (agent, max_candidates),
            ).fetchall()
            for (event_id,) in rows:
                add(int(event_id), f"agent:{agent}", 3.5)

        for term in query.terms[:10]:
            rows = self.db.execute(
                "SELECT event_id,weight FROM semantic_event_terms WHERE term=? ORDER BY event_id DESC LIMIT ?",
                (term, max_candidates),
            ).fetchall()
            for event_id, weight in rows:
                add(int(event_id), f"term:{term}", 0.85 * float(weight))

        if not candidates:
            rows = self.db.execute(
                "SELECT event_id FROM semantic_event_records ORDER BY event_id DESC LIMIT ?",
                (min(32, max_candidates),),
            ).fetchall()
            for (event_id,) in rows:
                add(int(event_id), "recent", 0.05)

        if len(candidates) > max_candidates:
            keep = sorted(candidates.items(), key=lambda kv: (kv[1]["score"], kv[0]), reverse=True)[:max_candidates]
            candidates = dict(keep)
        return candidates

    def recall(self, text: str, *, decision: SemanticDecision | None = None, limit: int = 5) -> list[dict[str, Any]]:
        query = self.query_from_event(decision, raw_text=text) if decision is not None else self.query_from_text(text)
        candidates = self._candidate_ids(query, max_candidates=max(64, int(limit) * 32))
        if not candidates:
            return []

        ids = list(candidates)
        placeholders = ",".join("?" for _ in ids)
        rows = self.db.execute(
            f"""
            SELECT r.event_id,r.event_type,r.epistemic,r.confidence,r.source,r.agents,
                   r.proposition_surface,r.proposition_canonical,r.truth,
                   e.ts,e.text,e.concepts,e.workspace,e.surprise,e.magnitude
            FROM semantic_event_records r
            JOIN events e ON e.id=r.event_id
            WHERE r.event_id IN ({placeholders})
            """,
            ids,
        ).fetchall()

        latest_ids: set[int] = set()
        if query.latest_only:
            for agent in query.agents:
                if query.event_types:
                    for event_type in query.event_types:
                        rows_latest = self.db.execute(
                            """
                            SELECT event_id FROM semantic_event_records
                            WHERE event_type=? AND agents LIKE ?
                            ORDER BY event_id DESC LIMIT 1
                            """,
                            (event_type, f'%"{agent}"%'),
                        ).fetchall()
                        latest_ids.update(int(x[0]) for x in rows_latest)

        scored: list[tuple[float, dict[str, Any]]] = []
        for row in rows:
            event_id = int(row[0])
            row_type = str(row[1])
            row_epistemic = str(row[2])
            row_agents = [self._norm_entity(x) for x in json.loads(row[5])]

            # Explicit semantic constraints are filters, not merely bonuses.
            # A query about Mina must never return Tessa just because the
            # proposition terms happen to match.
            if query.event_types and row_type not in set(query.event_types):
                continue
            if query.epistemic and row_epistemic not in set(query.epistemic):
                continue
            if query.agents and not all(agent in row_agents for agent in query.agents):
                continue

            evidence = candidates[event_id]
            score = float(evidence["score"])
            if event_id in latest_ids:
                score += 1.0
            # bounded recency tie-breaker only; semantic evidence dominates.
            recency = min(1.0, event_id / max(1, max(ids)))
            score += 0.08 * recency
            relevance = 1.0 - math.exp(-score / 4.0)
            truth = None if row[8] is None else bool(row[8])
            record = {
                "id": event_id,
                "event_id": event_id,
                "event_type": str(row[1]),
                "epistemic": str(row[2]),
                "event_confidence": float(row[3]),
                "event_source": str(row[4]),
                "agents": row_agents,
                "proposition_surface": str(row[6]),
                "proposition_canonical": str(row[7]),
                "truth": truth,
                "ts": float(row[9]),
                "text": str(row[10]),
                "concepts": json.loads(row[11]),
                "workspace": json.loads(row[12]),
                "surprise": float(row[13]),
                "magnitude": float(row[14]),
                "relevance": float(relevance),
                "event_relevance": float(relevance),
                "retrieval_source": "event_structured",
                "matched_by": list(evidence["matched_by"]),
                "query": query.as_dict(),
            }
            scored.append((relevance, record))

        scored.sort(key=lambda item: (item[0], item[1]["id"]), reverse=True)
        return [row for _, row in scored[: max(1, int(limit))]]

    def links_for(self, event_id: int, *, incoming: bool = True) -> list[dict[str, Any]]:
        if incoming:
            rows = self.db.execute(
                "SELECT source_event_id,target_event_id,relation,score FROM semantic_event_links WHERE target_event_id=? ORDER BY score DESC",
                (int(event_id),),
            ).fetchall()
        else:
            rows = self.db.execute(
                "SELECT source_event_id,target_event_id,relation,score FROM semantic_event_links WHERE source_event_id=? ORDER BY score DESC",
                (int(event_id),),
            ).fetchall()
        return [
            {"source_event_id": int(a), "target_event_id": int(b), "relation": str(r), "score": float(s)}
            for a, b, r, s in rows
        ]

    def latest_state(self, event_type: str, agent: str, proposition_canonical: str) -> dict[str, Any] | None:
        agent_key = self._norm_entity(agent) or "__world__"
        state_key = f"{event_type}|{agent_key}|{proposition_canonical}"
        row = self.db.execute(
            "SELECT event_id,event_type,epistemic,agent_key,proposition_canonical,truth,updated_ts FROM semantic_event_latest WHERE state_key=?",
            (state_key,),
        ).fetchone()
        if not row:
            return None
        return {
            "event_id": int(row[0]),
            "event_type": str(row[1]),
            "epistemic": str(row[2]),
            "agent_key": str(row[3]),
            "proposition_canonical": str(row[4]),
            "truth": None if row[5] is None else bool(row[5]),
            "updated_ts": float(row[6]),
        }

    def stats(self) -> dict[str, Any]:
        by_type = {
            str(k): int(v)
            for k, v in self.db.execute(
                "SELECT event_type,COUNT(*) FROM semantic_event_records GROUP BY event_type"
            ).fetchall()
        }
        by_link = {
            str(k): int(v)
            for k, v in self.db.execute(
                "SELECT relation,COUNT(*) FROM semantic_event_links GROUP BY relation"
            ).fetchall()
        }
        return {
            "records": self.count(),
            "links": self.link_count(),
            "by_type": by_type,
            "by_link": by_link,
            "latest_states": int(self.db.execute("SELECT COUNT(*) FROM semantic_event_latest").fetchone()[0]),
        }

    def clear(self) -> None:
        with self.db:
            self.db.execute("DELETE FROM semantic_event_latest")
            self.db.execute("DELETE FROM semantic_event_links")
            self.db.execute("DELETE FROM semantic_event_terms")
            self.db.execute("DELETE FROM semantic_event_entities")
            self.db.execute("DELETE FROM semantic_event_records")

    def close(self) -> None:
        self.db.close()
