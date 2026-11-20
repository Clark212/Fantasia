from __future__ import annotations

import json
import sqlite3
import time
from math import log, sqrt
from pathlib import Path
from typing import Dict, Iterable, List


class EpisodicMemory:
    """
    ASM v0.1.1.1 episodic memory.

    Main change:
    recall is now frequency-aware and candidate-bounded.

    Extremely common concepts are poor retrieval keys, so ASM measures concept
    document frequency and gives rare/informative concepts more influence.
    This prevents concepts such as LEN_BUCKET or repeated filler words from
    exploding the candidate set as memory grows.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        max_concepts: int = 10,
        per_concept_limit: int = 96,
        max_candidates: int = 256,
        common_ratio_cutoff: float = 0.18,
        common_absolute_cutoff: int = 220,
    ):
        self.path = str(path)
        self.max_concepts = max_concepts
        self.per_concept_limit = per_concept_limit
        self.max_candidates = max_candidates
        self.common_ratio_cutoff = common_ratio_cutoff
        self.common_absolute_cutoff = common_absolute_cutoff

        self.db = sqlite3.connect(self.path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.execute("PRAGMA temp_store=MEMORY")
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS events(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                text TEXT NOT NULL,
                concepts TEXT NOT NULL,
                workspace TEXT NOT NULL,
                surprise REAL NOT NULL,
                magnitude REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS concept_index(
                concept TEXT NOT NULL,
                event_id INTEGER NOT NULL,
                weight REAL NOT NULL,
                PRIMARY KEY(concept, event_id)
            );

            CREATE INDEX IF NOT EXISTS idx_concept_lookup
            ON concept_index(concept, event_id DESC);

            CREATE INDEX IF NOT EXISTS idx_event_lookup
            ON concept_index(event_id);

            CREATE TABLE IF NOT EXISTS concept_stats(
                concept TEXT PRIMARY KEY,
                document_frequency INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS kv(
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        self.db.commit()
        self._backfill_index_and_stats_if_needed()

    def _backfill_index_and_stats_if_needed(self) -> None:
        events = self.count_events()
        if events == 0:
            return

        indexed = int(
            self.db.execute(
                "SELECT COUNT(DISTINCT event_id) FROM concept_index"
            ).fetchone()[0]
        )

        if indexed < events:
            rows = self.db.execute("SELECT id, concepts FROM events").fetchall()
            with self.db:
                for event_id, payload in rows:
                    concepts = json.loads(payload)
                    self.db.executemany(
                        "INSERT OR REPLACE INTO concept_index(concept,event_id,weight) "
                        "VALUES(?,?,?)",
                        [
                            (str(concept), int(event_id), float(weight))
                            for concept, weight in concepts.items()
                        ],
                    )

        stats_count = int(
            self.db.execute("SELECT COUNT(*) FROM concept_stats").fetchone()[0]
        )
        if stats_count == 0:
            with self.db:
                self.db.execute("DELETE FROM concept_stats")
                self.db.execute(
                    """
                    INSERT INTO concept_stats(concept, document_frequency)
                    SELECT concept, COUNT(*)
                    FROM concept_index
                    GROUP BY concept
                    """
                )

    def add_event(
        self,
        text: str,
        concepts: Dict[str, float],
        workspace,
        surprise: float,
        magnitude: float,
    ) -> int:
        unique = {
            str(concept): float(weight)
            for concept, weight in concepts.items()
        }

        with self.db:
            cur = self.db.execute(
                "INSERT INTO events(ts,text,concepts,workspace,surprise,magnitude) "
                "VALUES(?,?,?,?,?,?)",
                (
                    time.time(),
                    text,
                    json.dumps(unique, separators=(",", ":")),
                    json.dumps(workspace, separators=(",", ":")),
                    float(surprise),
                    float(magnitude),
                ),
            )
            event_id = int(cur.lastrowid)

            self.db.executemany(
                "INSERT OR REPLACE INTO concept_index(concept,event_id,weight) "
                "VALUES(?,?,?)",
                [
                    (concept, event_id, weight)
                    for concept, weight in unique.items()
                ],
            )

            self.db.executemany(
                """
                INSERT INTO concept_stats(concept,document_frequency)
                VALUES(?,1)
                ON CONFLICT(concept)
                DO UPDATE SET document_frequency=document_frequency+1
                """,
                [(concept,) for concept in unique],
            )

        return event_id

    def _concept_frequencies(self, concepts: List[str]) -> Dict[str, int]:
        if not concepts:
            return {}
        result: Dict[str, int] = {}
        chunk_size = 200
        for i in range(0, len(concepts), chunk_size):
            chunk = concepts[i:i + chunk_size]
            placeholders = ",".join("?" for _ in chunk)
            rows = self.db.execute(
                f"SELECT concept,document_frequency FROM concept_stats "
                f"WHERE concept IN ({placeholders})",
                chunk,
            ).fetchall()
            result.update({str(c): int(df) for c, df in rows})
        return result

    def recall(
        self,
        query_concepts: Dict[str, float] | Iterable[str],
        limit: int = 5,
    ) -> List[dict]:
        if isinstance(query_concepts, dict):
            raw = {
                str(k): abs(float(v))
                for k, v in query_concepts.items()
                if abs(float(v)) > 0.0
            }
        else:
            raw = {str(k): 1.0 for k in query_concepts}

        if not raw:
            return []

        total_events = max(1, self.count_events())
        dfs = self._concept_frequencies(list(raw))

        # Information value ~= smoothed IDF. Structural helper concepts get
        # naturally suppressed when they occur almost everywhere.
        weighted = []
        for concept, base_weight in raw.items():
            df = max(1, dfs.get(concept, 1))
            ratio = df / total_events

            too_common = (
                df >= self.common_absolute_cutoff
                and ratio >= self.common_ratio_cutoff
            )
            if too_common:
                continue

            idf = log((total_events + 1.0) / (df + 1.0)) + 1.0
            weighted.append((concept, base_weight * idf, df))

        # If every key was common, retain the two least-common keys so recall
        # still works rather than becoming empty.
        if not weighted:
            fallback = sorted(
                (
                    (concept, weight, max(1, dfs.get(concept, 1)))
                    for concept, weight in raw.items()
                ),
                key=lambda x: x[2],
            )[:2]
            weighted = [
                (
                    concept,
                    weight * (log((total_events + 1.0) / (df + 1.0)) + 1.0),
                    df,
                )
                for concept, weight, df in fallback
            ]

        weighted.sort(key=lambda x: x[1], reverse=True)
        weighted = weighted[: self.max_concepts]
        qweights = {c: w for c, w, _ in weighted}

        candidates: Dict[int, float] = {}

        # Each informative concept contributes only a bounded number of event
        # candidates. Rare keys still retrieve very old events because their
        # full posting list is usually below the cap.
        for concept, qweight, df in weighted:
            rows = self.db.execute(
                """
                SELECT event_id, weight
                FROM concept_index
                WHERE concept=?
                ORDER BY event_id DESC
                LIMIT ?
                """,
                (concept, self.per_concept_limit),
            ).fetchall()

            for event_id, stored_weight in rows:
                eid = int(event_id)
                candidates[eid] = (
                    candidates.get(eid, 0.0)
                    + qweight * abs(float(stored_weight))
                )

        if not candidates:
            return []

        top_ids = [
            eid
            for eid, _ in sorted(
                candidates.items(),
                key=lambda kv: kv[1],
                reverse=True,
            )[: self.max_candidates]
        ]

        placeholders = ",".join("?" for _ in top_ids)
        rows = self.db.execute(
            f"SELECT id,ts,text,concepts,workspace,surprise,magnitude "
            f"FROM events WHERE id IN ({placeholders})",
            top_ids,
        ).fetchall()

        qnorm = sqrt(sum(v * v for v in qweights.values())) or 1.0
        now = time.time()
        scored = []

        for row in rows:
            event_concepts = json.loads(row[3])

            # Apply the same information weights to event-side overlap only.
            dot = 0.0
            enorm_sq = 0.0
            for concept, qweight in qweights.items():
                eweight = abs(float(event_concepts.get(concept, 0.0)))
                if eweight:
                    dot += qweight * eweight
                    enorm_sq += eweight * eweight

            if dot <= 0.0:
                continue

            enorm = sqrt(enorm_sq) or 1.0
            cosine = dot / (qnorm * enorm)

            age_days = max(0.0, (now - float(row[1])) / 86400.0)
            recency = 1.0 / (1.0 + 0.02 * age_days)
            importance = 0.5 * float(row[5]) + 0.5 * float(row[6])

            relevance = 0.88 * cosine + 0.08 * importance + 0.04 * recency

            scored.append(
                (
                    relevance,
                    {
                        "id": int(row[0]),
                        "ts": float(row[1]),
                        "text": row[2],
                        "concepts": event_concepts,
                        "workspace": json.loads(row[4]),
                        "surprise": float(row[5]),
                        "magnitude": float(row[6]),
                        "relevance": relevance,
                    },
                )
            )

        scored.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in scored[:limit]]

    def concept_frequency(self, concept: str) -> int:
        row = self.db.execute(
            "SELECT document_frequency FROM concept_stats WHERE concept=?",
            (concept,),
        ).fetchone()
        return 0 if row is None else int(row[0])

    def set_kv(self, key: str, value) -> None:
        payload = json.dumps(value, separators=(",", ":"))
        self.db.execute(
            "INSERT INTO kv(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, payload),
        )
        self.db.commit()

    def get_kv(self, key: str, default=None):
        row = self.db.execute(
            "SELECT value FROM kv WHERE key=?",
            (key,),
        ).fetchone()
        return default if row is None else json.loads(row[0])

    def count_events(self) -> int:
        return int(
            self.db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        )

    def close(self) -> None:
        self.db.close()
