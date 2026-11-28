from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path
from typing import Iterable, List, Sequence


class SemanticEpisodicIndex:
    """
    Dependency-free approximate nearest-neighbor index for episodic embeddings.

    It uses several deterministic LSH signatures over the recurrent hidden state
    to retrieve a bounded candidate set, then cosine-reranks only those rows.
    This is approximate retrieval; it does not scan every stored event.
    """

    def __init__(
        self,
        db_path: str | Path,
        *,
        tables: int = 4,
        bits: int = 10,
        min_candidates: int = 24,
        max_candidates: int = 256,
        min_similarity: float = 0.30,
    ):
        self.db=sqlite3.connect(str(db_path))
        self.db.execute("PRAGMA journal_mode=WAL")
        self.tables=max(1,int(tables))
        self.bits=max(4,min(16,int(bits)))
        self.min_candidates=max(1,int(min_candidates))
        self.max_candidates=max(self.min_candidates,int(max_candidates))
        self.min_similarity=float(min_similarity)
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS semantic_vectors(
                event_id INTEGER PRIMARY KEY,
                dims INTEGER NOT NULL,
                vector TEXT NOT NULL,
                tag TEXT NOT NULL DEFAULT 'other'
            );
            CREATE TABLE IF NOT EXISTS semantic_lsh(
                table_id INTEGER NOT NULL,
                bucket INTEGER NOT NULL,
                event_id INTEGER NOT NULL,
                PRIMARY KEY(table_id,bucket,event_id)
            );
            CREATE INDEX IF NOT EXISTS idx_semantic_lsh
            ON semantic_lsh(table_id,bucket,event_id);
            CREATE INDEX IF NOT EXISTS idx_semantic_lsh_event
            ON semantic_lsh(event_id);
            """
        )
        cols={row[1] for row in self.db.execute("PRAGMA table_info(semantic_vectors)").fetchall()}
        if "tag" not in cols:
            self.db.execute(
                "ALTER TABLE semantic_vectors ADD COLUMN tag TEXT NOT NULL DEFAULT 'other'"
            )
        self.db.execute(
            "CREATE INDEX IF NOT EXISTS idx_semantic_tag ON semantic_vectors(tag,event_id)"
        )
        self.db.commit()

    @staticmethod
    def _normalize(vector: Sequence[float]) -> List[float]:
        vals=[float(x) for x in vector]
        norm=math.sqrt(sum(x*x for x in vals))
        return [x/norm for x in vals] if norm>0 else vals

    def _signatures(self, vector: Sequence[float]) -> List[int]:
        v=self._normalize(vector)
        n=len(v)
        if n == 0:
            return [0]*self.tables
        out=[]
        # Deterministic pairwise hyperplane surrogate. Different table constants
        # create independent-ish angular partitions without storing random planes.
        for t in range(self.tables):
            sig=0
            for b in range(self.bits):
                i=(17*t + 13*b + 3) % n
                j=(29*t + 7*b + 11) % n
                if v[i] >= v[j]:
                    sig |= (1 << b)
            out.append(sig)
        return out

    def add(self, event_id: int, vector: Sequence[float], *, tag: str = "other") -> None:
        if not vector:
            return
        vec=self._normalize(vector)
        sigs=self._signatures(vec)
        payload=json.dumps(vec,separators=(",",":"))
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO semantic_vectors(event_id,dims,vector,tag) VALUES(?,?,?,?)",
                (int(event_id),len(vec),payload,str(tag or "other")),
            )
            self.db.execute("DELETE FROM semantic_lsh WHERE event_id=?",(int(event_id),))
            self.db.executemany(
                "INSERT OR REPLACE INTO semantic_lsh(table_id,bucket,event_id) VALUES(?,?,?)",
                [(t,int(bucket),int(event_id)) for t,bucket in enumerate(sigs)],
            )

    def missing_events(self, limit: int = 4096) -> List[tuple[int,str]]:
        rows=self.db.execute(
            """
            SELECT e.id,e.text
            FROM events e
            LEFT JOIN semantic_vectors s ON s.event_id=e.id
            WHERE s.event_id IS NULL
            ORDER BY e.id
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        return [(int(i),str(text)) for i,text in rows]

    def count(self) -> int:
        return int(self.db.execute("SELECT COUNT(*) FROM semantic_vectors").fetchone()[0])

    def _candidate_ids(self, vector: Sequence[float], *, tag: str | None = None) -> List[int]:
        # Typed stores such as beliefs/goals are usually small. If the entire
        # compatible pool is already below the candidate budget, exact candidate
        # enumeration is both cheaper and more reliable than approximate LSH.
        if tag is not None:
            count=int(self.db.execute(
                "SELECT COUNT(*) FROM semantic_vectors WHERE tag=?",
                (str(tag),),
            ).fetchone()[0])
            if 0 < count <= self.max_candidates:
                return [
                    int(r[0])
                    for r in self.db.execute(
                        "SELECT event_id FROM semantic_vectors WHERE tag=? ORDER BY event_id DESC LIMIT ?",
                        (str(tag),self.max_candidates),
                    ).fetchall()
                ]

        sigs=self._signatures(vector)
        ids=set()

        def fetch(table_id,bucket):
            if tag is None:
                rows=self.db.execute(
                    "SELECT event_id FROM semantic_lsh WHERE table_id=? AND bucket=? LIMIT ?",
                    (int(table_id),int(bucket),self.max_candidates),
                ).fetchall()
            else:
                rows=self.db.execute(
                    """
                    SELECT l.event_id
                    FROM semantic_lsh l
                    JOIN semantic_vectors s ON s.event_id=l.event_id
                    WHERE l.table_id=? AND l.bucket=? AND s.tag=?
                    LIMIT ?
                    """,
                    (int(table_id),int(bucket),str(tag),self.max_candidates),
                ).fetchall()
            ids.update(int(r[0]) for r in rows)

        for t,bucket in enumerate(sigs):
            fetch(t,bucket)

        # If exact buckets are sparse, search Hamming-1 neighbors.
        if len(ids) < self.min_candidates:
            for t,bucket in enumerate(sigs):
                for bit in range(self.bits):
                    fetch(t,bucket ^ (1 << bit))
                    if len(ids) >= self.max_candidates:
                        break
                if len(ids) >= self.max_candidates:
                    break

        return list(ids)[:self.max_candidates]

    @staticmethod
    def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
        if not a or not b or len(a)!=len(b):
            return -1.0
        return sum(float(x)*float(y) for x,y in zip(a,b))

    def recall(self, vector: Sequence[float], limit: int = 5, *, tag: str | None = None) -> List[dict]:
        if not vector:
            return []
        q=self._normalize(vector)
        ids=self._candidate_ids(q, tag=tag)
        if not ids:
            return []
        placeholders=",".join("?" for _ in ids)
        rows=self.db.execute(
            f"""
            SELECT e.id,e.ts,e.text,e.concepts,e.workspace,e.surprise,e.magnitude,s.vector,s.tag
            FROM semantic_vectors s
            JOIN events e ON e.id=s.event_id
            WHERE s.event_id IN ({placeholders})
            """,
            ids,
        ).fetchall()
        scored=[]
        for row in rows:
            vec=json.loads(row[7])
            sim=self._cosine(q,vec)
            if sim < self.min_similarity:
                continue
            # map cosine [-1,1] to [0,1], but only positive-ish rows survived above
            semantic=(sim+1.0)/2.0
            importance=0.5*float(row[5])+0.5*float(row[6])
            relevance=0.88*semantic+0.12*importance
            scored.append((relevance,{
                "id":int(row[0]),
                "ts":float(row[1]),
                "text":str(row[2]),
                "concepts":json.loads(row[3]),
                "workspace":json.loads(row[4]),
                "surprise":float(row[5]),
                "magnitude":float(row[6]),
                "relevance":float(relevance),
                "semantic_similarity":float(sim),
                "retrieval_source":"semantic_lsh",
                "semantic_tag":str(row[8]),
            }))
        scored.sort(key=lambda x:x[0],reverse=True)
        return [x[1] for x in scored[:limit]]

    def clear(self) -> None:
        with self.db:
            self.db.execute("DELETE FROM semantic_lsh")
            self.db.execute("DELETE FROM semantic_vectors")

    def close(self) -> None:
        self.db.close()
