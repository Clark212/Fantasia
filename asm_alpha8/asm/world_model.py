from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
import sqlite3
import time
from pathlib import Path
from typing import Any

from .encoder import STOPWORDS, light_stem
from .semantic_event import Proposition, SemanticDecision, SemanticEvent


_WORLD_STOP = {
    "what", "which", "who", "when", "where", "why", "how", "does", "do", "did",
    "is", "are", "was", "were", "the", "a", "an", "that", "this", "it", "to",
    "of", "for", "and", "or", "in", "on", "at", "with", "from", "by", "as",
}


@dataclass(slots=True)
class WorldState:
    state_key: str
    holder: str
    event_type: str
    epistemic: str
    proposition_surface: str
    proposition_canonical: str
    truth: bool | None
    confidence: float
    source_event_id: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class WorldTransition:
    state_key: str
    source_event_id: int | None
    target_event_id: int
    transition_kind: str
    before_truth: bool | None
    after_truth: bool | None
    before_epistemic: str | None
    after_epistemic: str
    confidence: float
    causal: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class MechanismCandidate:
    mechanism_key: str
    dependency_type: str
    dependency_value: str
    priority: float
    reason: str
    source_event_id: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class PersistentWorldModel:
    """
    ASM v0.3.0-alpha.1 persistent world-state substrate.

    The world model converts *persistent typed semantic events* into explicit
    current-state records plus immutable state history.  Revisions create
    transition evidence, but alpha.1 deliberately marks every transition as
    non-causal.  Temporal order and contradiction are evidence for later
    mechanism learning, not proof that one state caused another.

    Alpha.1 also maintains a small dependency graph used by the seismic
    mechanism scheduler.  The scheduler selects bounded local mechanism
    candidates; it does not yet execute a learned world mechanism or planner.
    """

    def __init__(self, db_path: str | Path, *, max_schedule_candidates: int = 12):
        self.path = str(db_path)
        self.max_schedule_candidates = max(1, int(max_schedule_candidates))
        self.db = sqlite3.connect(self.path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.execute("PRAGMA temp_store=MEMORY")
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS world_state_history(
                event_id INTEGER NOT NULL,
                state_key TEXT NOT NULL,
                holder TEXT NOT NULL,
                event_type TEXT NOT NULL,
                epistemic TEXT NOT NULL,
                proposition_surface TEXT NOT NULL,
                proposition_canonical TEXT NOT NULL,
                truth INTEGER,
                confidence REAL NOT NULL,
                created_ts REAL NOT NULL,
                PRIMARY KEY(event_id, state_key)
            );

            CREATE INDEX IF NOT EXISTS idx_world_history_holder
            ON world_state_history(holder, event_id DESC);

            CREATE INDEX IF NOT EXISTS idx_world_history_prop
            ON world_state_history(proposition_canonical, event_id DESC);

            CREATE TABLE IF NOT EXISTS world_current_state(
                state_key TEXT PRIMARY KEY,
                holder TEXT NOT NULL,
                event_type TEXT NOT NULL,
                epistemic TEXT NOT NULL,
                proposition_surface TEXT NOT NULL,
                proposition_canonical TEXT NOT NULL,
                truth INTEGER,
                confidence REAL NOT NULL,
                source_event_id INTEGER NOT NULL,
                updated_ts REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_world_current_holder
            ON world_current_state(holder, event_type);

            CREATE TABLE IF NOT EXISTS world_nodes(
                node_key TEXT PRIMARY KEY,
                node_type TEXT NOT NULL,
                label TEXT NOT NULL,
                confidence REAL NOT NULL,
                first_event_id INTEGER NOT NULL,
                last_event_id INTEGER NOT NULL,
                updated_ts REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_world_nodes_type
            ON world_nodes(node_type, last_event_id DESC);

            CREATE TABLE IF NOT EXISTS world_edges(
                source_key TEXT NOT NULL,
                target_key TEXT NOT NULL,
                relation TEXT NOT NULL,
                confidence REAL NOT NULL,
                first_event_id INTEGER NOT NULL,
                last_event_id INTEGER NOT NULL,
                updated_ts REAL NOT NULL,
                PRIMARY KEY(source_key, target_key, relation)
            );

            CREATE INDEX IF NOT EXISTS idx_world_edges_source
            ON world_edges(source_key, relation, last_event_id DESC);

            CREATE INDEX IF NOT EXISTS idx_world_edges_target
            ON world_edges(target_key, relation, last_event_id DESC);

            CREATE TABLE IF NOT EXISTS world_transition_evidence(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                state_key TEXT NOT NULL,
                source_event_id INTEGER,
                target_event_id INTEGER NOT NULL,
                transition_kind TEXT NOT NULL,
                before_truth INTEGER,
                after_truth INTEGER,
                before_epistemic TEXT,
                after_epistemic TEXT NOT NULL,
                confidence REAL NOT NULL,
                causal INTEGER NOT NULL DEFAULT 0,
                created_ts REAL NOT NULL,
                UNIQUE(state_key, source_event_id, target_event_id, transition_kind)
            );

            CREATE INDEX IF NOT EXISTS idx_world_transition_state
            ON world_transition_evidence(state_key, target_event_id DESC);

            CREATE TABLE IF NOT EXISTS world_dependencies(
                dependency_type TEXT NOT NULL,
                dependency_value TEXT NOT NULL,
                state_key TEXT NOT NULL,
                support REAL NOT NULL,
                first_event_id INTEGER NOT NULL,
                last_event_id INTEGER NOT NULL,
                PRIMARY KEY(dependency_type, dependency_value, state_key)
            );

            CREATE INDEX IF NOT EXISTS idx_world_dependency_lookup
            ON world_dependencies(dependency_type, dependency_value, support DESC);
            """
        )
        self.db.commit()

    @staticmethod
    def _truth_db(value: bool | None) -> int | None:
        return None if value is None else (1 if bool(value) else 0)

    @staticmethod
    def _truth_py(value: int | None) -> bool | None:
        return None if value is None else bool(value)

    @staticmethod
    def _norm(value: str) -> str:
        return " ".join(str(value).lower().strip().split())

    @classmethod
    def _terms(cls, text: str) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for token in re.findall(r"[A-Za-z0-9']+", str(text).lower()):
            if token in STOPWORDS or token in _WORLD_STOP or len(token) < 2:
                continue
            stem = light_stem(token)
            if stem and stem not in seen:
                seen.add(stem)
                out.append(stem)
        return out[:16]

    @staticmethod
    def _state_node_key(state_key: str) -> str:
        digest = hashlib.sha1(state_key.encode("utf-8")).hexdigest()[:16]
        return f"state:{digest}"

    @classmethod
    def _state_key(cls, event_type: str, holder: str, proposition_canonical: str) -> str:
        # Event type remains part of the slot.  Alice's belief about P is not the
        # same world state as an asserted observation of P.
        return f"{event_type}|{cls._norm(holder) or '__world__'}|{proposition_canonical}"

    def _upsert_node(self, key: str, node_type: str, label: str, confidence: float, event_id: int, now: float) -> None:
        self.db.execute(
            """
            INSERT INTO world_nodes(node_key,node_type,label,confidence,first_event_id,last_event_id,updated_ts)
            VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(node_key) DO UPDATE SET
                confidence=max(world_nodes.confidence,excluded.confidence),
                last_event_id=excluded.last_event_id,
                updated_ts=excluded.updated_ts
            """,
            (key, node_type, label, float(confidence), int(event_id), int(event_id), now),
        )

    def _upsert_edge(self, source: str, target: str, relation: str, confidence: float, event_id: int, now: float) -> None:
        self.db.execute(
            """
            INSERT INTO world_edges(source_key,target_key,relation,confidence,first_event_id,last_event_id,updated_ts)
            VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(source_key,target_key,relation) DO UPDATE SET
                confidence=max(world_edges.confidence,excluded.confidence),
                last_event_id=excluded.last_event_id,
                updated_ts=excluded.updated_ts
            """,
            (source, target, relation, float(confidence), int(event_id), int(event_id), now),
        )

    def _observe_record(
        self,
        *,
        event_id: int,
        event_type: str,
        epistemic: str,
        confidence: float,
        holders: list[str],
        surface: str,
        canonical: str,
        truth: bool | None,
    ) -> dict[str, Any]:
        if not canonical:
            return {"states": [], "transitions": [], "scheduled": []}
        now = time.time()
        holders = [self._norm(x) for x in holders if self._norm(x)] or ["__world__"]
        # Nested mental state is a perspective path, not independent evidence that
        # every agent in the path personally holds the proposition.  Preserve
        # Alice>Bob as one scoped holder and represent the path in the graph.
        nested_path = list(holders) if str(event_type) == "nested_belief" and len(holders) > 1 else []
        state_holders = [">".join(nested_path)] if nested_path else holders
        states: list[dict[str, Any]] = []
        transitions: list[dict[str, Any]] = []
        scheduled: list[MechanismCandidate] = []

        with self.db:
            if nested_path:
                for agent in nested_path:
                    self._upsert_node(f"agent:{agent}", "agent", agent, confidence, event_id, now)
                for left, right in zip(nested_path, nested_path[1:]):
                    self._upsert_edge(f"agent:{left}", f"agent:{right}", "models_mind", confidence, event_id, now)

            for holder in state_holders:
                state_key = self._state_key(event_type, holder, canonical)
                prior = self.db.execute(
                    """
                    SELECT epistemic,truth,confidence,source_event_id
                    FROM world_current_state WHERE state_key=?
                    """,
                    (state_key,),
                ).fetchone()

                self.db.execute(
                    """
                    INSERT OR REPLACE INTO world_state_history(
                        event_id,state_key,holder,event_type,epistemic,
                        proposition_surface,proposition_canonical,truth,confidence,created_ts
                    ) VALUES(?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        int(event_id), state_key, holder, str(event_type), str(epistemic),
                        str(surface), str(canonical), self._truth_db(truth), float(confidence), now,
                    ),
                )
                self.db.execute(
                    """
                    INSERT INTO world_current_state(
                        state_key,holder,event_type,epistemic,proposition_surface,
                        proposition_canonical,truth,confidence,source_event_id,updated_ts
                    ) VALUES(?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(state_key) DO UPDATE SET
                        epistemic=excluded.epistemic,
                        proposition_surface=excluded.proposition_surface,
                        proposition_canonical=excluded.proposition_canonical,
                        truth=excluded.truth,
                        confidence=excluded.confidence,
                        source_event_id=excluded.source_event_id,
                        updated_ts=excluded.updated_ts
                    """,
                    (
                        state_key, holder, str(event_type), str(epistemic), str(surface),
                        str(canonical), self._truth_db(truth), float(confidence), int(event_id), now,
                    ),
                )

                state_node = self._state_node_key(state_key)
                if nested_path:
                    holder_node = f"mindpath:{holder}"
                    self._upsert_node(holder_node, "agent_path", holder, confidence, event_id, now)
                    self._upsert_edge(f"agent:{nested_path[-1]}", holder_node, "scoped_by_path", confidence, event_id, now)
                    self._upsert_edge(holder_node, state_node, "holds_nested_state", confidence, event_id, now)
                else:
                    holder_node = f"agent:{holder}" if holder != "__world__" else "world:reality"
                    self._upsert_node(holder_node, "agent" if holder != "__world__" else "world", holder, confidence, event_id, now)
                    self._upsert_edge(holder_node, state_node, "holds_state", confidence, event_id, now)
                self._upsert_node(state_node, "state", canonical, confidence, event_id, now)

                term_list = self._terms(surface or canonical)
                for term in term_list:
                    term_node = f"term:{term}"
                    self._upsert_node(term_node, "proposition_term", term, confidence * 0.7, event_id, now)
                    self._upsert_edge(state_node, term_node, "mentions", confidence * 0.7, event_id, now)

                for dep_type, dep_value, weight in [
                    ("state", state_key, 1.0),
                    ("holder", holder, 0.75),
                    ("event_type", str(event_type), 0.65),
                    *[("term", term, 0.45) for term in term_list[:8]],
                ]:
                    self.db.execute(
                        """
                        INSERT INTO world_dependencies(
                            dependency_type,dependency_value,state_key,support,first_event_id,last_event_id
                        ) VALUES(?,?,?,?,?,?)
                        ON CONFLICT(dependency_type,dependency_value,state_key) DO UPDATE SET
                            support=world_dependencies.support+excluded.support,
                            last_event_id=excluded.last_event_id
                        """,
                        (dep_type, dep_value, state_key, float(weight), int(event_id), int(event_id)),
                    )

                transition_kind = "new_state"
                prior_event_id: int | None = None
                before_truth: bool | None = None
                before_epi: str | None = None
                if prior:
                    before_epi = str(prior[0])
                    before_truth = self._truth_py(prior[1])
                    prior_event_id = int(prior[3])
                    if before_truth is not None and truth is not None and before_truth != truth:
                        transition_kind = "truth_revision"
                    elif before_epi != str(epistemic):
                        transition_kind = "epistemic_shift"
                    else:
                        transition_kind = "reaffirm"

                transition_confidence = min(float(confidence), float(prior[2]) if prior else float(confidence))
                self.db.execute(
                    """
                    INSERT OR IGNORE INTO world_transition_evidence(
                        state_key,source_event_id,target_event_id,transition_kind,
                        before_truth,after_truth,before_epistemic,after_epistemic,
                        confidence,causal,created_ts
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        state_key, prior_event_id, int(event_id), transition_kind,
                        self._truth_db(before_truth), self._truth_db(truth), before_epi,
                        str(epistemic), float(transition_confidence), 0, now,
                    ),
                )
                transition = WorldTransition(
                    state_key=state_key,
                    source_event_id=prior_event_id,
                    target_event_id=int(event_id),
                    transition_kind=transition_kind,
                    before_truth=before_truth,
                    after_truth=truth,
                    before_epistemic=before_epi,
                    after_epistemic=str(epistemic),
                    confidence=float(transition_confidence),
                    causal=False,
                )
                transitions.append(transition.as_dict())

                state = WorldState(
                    state_key=state_key,
                    holder=holder,
                    event_type=str(event_type),
                    epistemic=str(epistemic),
                    proposition_surface=str(surface),
                    proposition_canonical=str(canonical),
                    truth=truth,
                    confidence=float(confidence),
                    source_event_id=int(event_id),
                )
                states.append(state.as_dict())
                scheduled.extend(self._schedule_for_state(state, terms=term_list))

        dedup: dict[str, MechanismCandidate] = {}
        for row in scheduled:
            old = dedup.get(row.mechanism_key)
            if old is None or row.priority > old.priority:
                dedup[row.mechanism_key] = row
        selected = sorted(dedup.values(), key=lambda x: (-x.priority, x.mechanism_key))[: self.max_schedule_candidates]
        return {
            "states": states,
            "transitions": transitions,
            "scheduled": [x.as_dict() for x in selected],
        }

    def _schedule_for_state(self, state: WorldState, *, terms: list[str]) -> list[MechanismCandidate]:
        event_id = int(state.source_event_id)
        candidates = [
            MechanismCandidate(
                mechanism_key=f"local-state:{self._state_node_key(state.state_key)}",
                dependency_type="state",
                dependency_value=state.state_key,
                priority=1.0,
                reason="changed_state",
                source_event_id=event_id,
            ),
            MechanismCandidate(
                mechanism_key=f"holder:{state.holder}",
                dependency_type="holder",
                dependency_value=state.holder,
                priority=0.72,
                reason="holder_dependency",
                source_event_id=event_id,
            ),
            MechanismCandidate(
                mechanism_key=f"event-type:{state.event_type}",
                dependency_type="event_type",
                dependency_value=state.event_type,
                priority=0.62,
                reason="event_type_dependency",
                source_event_id=event_id,
            ),
        ]
        for term in terms[:8]:
            candidates.append(MechanismCandidate(
                mechanism_key=f"term:{term}",
                dependency_type="term",
                dependency_value=term,
                priority=0.40,
                reason="proposition_dependency",
                source_event_id=event_id,
            ))
        return candidates

    def observe(self, event_id: int, decision: SemanticDecision, *, raw_text: str) -> dict[str, Any]:
        event = decision.primary
        if decision.abstained or not event.persistent_eligible or event.event_type == "question":
            return {"states": [], "transitions": [], "scheduled": [], "skipped": "non_persistent_semantic_event"}
        proposition = event.proposition or Proposition.from_surface(raw_text)
        return self._observe_record(
            event_id=int(event_id),
            event_type=str(event.event_type),
            epistemic=str(event.epistemic),
            confidence=float(event.confidence),
            holders=list(event.agents),
            surface=proposition.surface,
            canonical=proposition.canonical,
            truth=proposition.truth,
        )

    def backfill_from_semantic_memory(self, *, limit: int = 20000) -> int:
        """Backfill only events not already represented in world-state history."""
        rows = self.db.execute(
            """
            SELECT r.event_id,r.event_type,r.epistemic,r.confidence,r.agents,
                   r.proposition_surface,r.proposition_canonical,r.truth
            FROM semantic_event_records r
            LEFT JOIN world_state_history w ON w.event_id=r.event_id
            WHERE w.event_id IS NULL AND r.persistent_eligible=1
            ORDER BY r.event_id
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        count = 0
        for row in rows:
            try:
                holders = json.loads(row[4]) if row[4] else []
                canonical = str(row[6] or "")
                surface = str(row[5] or "")
                if not canonical:
                    continue
                self._observe_record(
                    event_id=int(row[0]),
                    event_type=str(row[1]),
                    epistemic=str(row[2]),
                    confidence=float(row[3]),
                    holders=[str(x) for x in holders],
                    surface=surface,
                    canonical=canonical,
                    truth=self._truth_py(row[7]),
                )
                count += 1
            except Exception:
                # Historical backfill must never prevent the engine from opening.
                continue
        return count

    def current(self, *, holder: str | None = None, event_type: str | None = None, limit: int = 32) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if holder:
            clauses.append("holder=?")
            params.append(self._norm(holder))
        if event_type:
            clauses.append("event_type=?")
            params.append(str(event_type))
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(max(1, int(limit)))
        rows = self.db.execute(
            f"""
            SELECT state_key,holder,event_type,epistemic,proposition_surface,
                   proposition_canonical,truth,confidence,source_event_id
            FROM world_current_state{where}
            ORDER BY source_event_id DESC LIMIT ?
            """,
            params,
        ).fetchall()
        return [
            WorldState(
                state_key=str(r[0]), holder=str(r[1]), event_type=str(r[2]), epistemic=str(r[3]),
                proposition_surface=str(r[4]), proposition_canonical=str(r[5]), truth=self._truth_py(r[6]),
                confidence=float(r[7]), source_event_id=int(r[8]),
            ).as_dict()
            for r in rows
        ]

    def transitions(self, *, state_key: str | None = None, limit: int = 32) -> list[dict[str, Any]]:
        if state_key:
            rows = self.db.execute(
                """
                SELECT state_key,source_event_id,target_event_id,transition_kind,
                       before_truth,after_truth,before_epistemic,after_epistemic,confidence,causal
                FROM world_transition_evidence WHERE state_key=?
                ORDER BY target_event_id DESC LIMIT ?
                """,
                (state_key, max(1, int(limit))),
            ).fetchall()
        else:
            rows = self.db.execute(
                """
                SELECT state_key,source_event_id,target_event_id,transition_kind,
                       before_truth,after_truth,before_epistemic,after_epistemic,confidence,causal
                FROM world_transition_evidence
                ORDER BY target_event_id DESC LIMIT ?
                """,
                (max(1, int(limit)),),
            ).fetchall()
        return [
            WorldTransition(
                state_key=str(r[0]), source_event_id=(None if r[1] is None else int(r[1])),
                target_event_id=int(r[2]), transition_kind=str(r[3]),
                before_truth=self._truth_py(r[4]), after_truth=self._truth_py(r[5]),
                before_epistemic=(None if r[6] is None else str(r[6])), after_epistemic=str(r[7]),
                confidence=float(r[8]), causal=bool(r[9]),
            ).as_dict()
            for r in rows
        ]

    def graph_neighbors(self, node_key: str, *, limit: int = 24) -> list[dict[str, Any]]:
        rows = self.db.execute(
            """
            SELECT source_key,target_key,relation,confidence,first_event_id,last_event_id
            FROM world_edges
            WHERE source_key=? OR target_key=?
            ORDER BY last_event_id DESC,confidence DESC LIMIT ?
            """,
            (str(node_key), str(node_key), max(1, int(limit))),
        ).fetchall()
        return [
            {
                "source_key": str(r[0]), "target_key": str(r[1]), "relation": str(r[2]),
                "confidence": float(r[3]), "first_event_id": int(r[4]), "last_event_id": int(r[5]),
            }
            for r in rows
        ]

    def stats(self) -> dict[str, int]:
        def n(table: str) -> int:
            return int(self.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        return {
            "current_states": n("world_current_state"),
            "state_history": n("world_state_history"),
            "nodes": n("world_nodes"),
            "edges": n("world_edges"),
            "transitions": n("world_transition_evidence"),
            "dependencies": n("world_dependencies"),
        }

    def close(self) -> None:
        self.db.close()
