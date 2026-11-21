"""DEV17 knowledge base: the learning cycle for repair procedures ASM constructs itself (asm.coding.induction).

  encounter    the workflow's built-in operations fail on a problem (phase 3 is reached)
  search       `retrieve` returns stored procedures whose pattern matches code in the suspect function
  discover     `learn(examples)` extracts and generalizes edits from (before, after) fixes into CANDIDATE procedures
  construct    every candidate is an executable rewrite (induction.Procedure); nothing is hand-coded per operation
  test         `validate(held_out)` applies candidates to examples they were not learned from and scores whether
               they reproduce the real fix (hits), how often they fire, and how many programs they generate (cost)
  preserve     procedures meeting the policy become ACTIVE; the base is saved sealed (SHA-256), with full evidence
  apply        `candidates_for` turns matching active (then candidate) procedures into repair candidates; the tests,
               contract and verification still decide acceptance
  revise       `record_outcome` adds field evidence; `revise` RETIRES procedures that keep failing and marks a procedure
               SUPERSEDED when another one achieves the same successes at lower cost (or more successes at no worse
               precision)

Policy constants are fixed in benchmarks/preregistration/dev17_study.md and must not be tuned on evaluation data.
"""
from __future__ import annotations

import ast
import hashlib
import json
import time
from dataclasses import dataclass, field as dc_field
from pathlib import Path

from .induction import Procedure, induce

# ---- policy (pre-registered)
MIN_SUPPORT_ACTIVE = 2          # independent supporting examples that make a procedure ACTIVE without validation
MIN_VALIDATION_HITS = 1         # held-out hits that make a procedure ACTIVE
MIN_VALIDATION_PRECISION = 0.05  # hits / fires on held-out data required with those hits
RETIRE_MIN_FIRES = 20           # field + validation fires before a procedure with zero hits is retired
MAX_CANDIDATES = 60             # learned candidates offered per suspect function


def _norm(src: str) -> str | None:
    try:
        return ast.unparse(ast.parse(src))
    except (SyntaxError, ValueError):
        return None


@dataclass
class Entry:
    procedure: Procedure
    support: list = dc_field(default_factory=list)      # example ids it was learned from
    sources: list = dc_field(default_factory=list)      # where those examples came from (e.g. "history:toolz")
    status: str = "candidate"                         # candidate | active | retired | superseded
    validation: dict = dc_field(default_factory=lambda: {"fires": 0, "hits": 0, "cost": 0, "hit_ids": []})
    field: dict = dc_field(default_factory=lambda: {"fires": 0, "hits": 0, "problems": []})
    history: list = dc_field(default_factory=list)       # [(time, event, detail)]
    replaced_by: str | None = None

    @property
    def id(self) -> str:
        return self.procedure.id

    def precision(self) -> float | None:
        f = self.validation["fires"] + self.field["fires"]
        return (self.validation["hits"] + self.field["hits"]) / f if f else None

    def to_dict(self) -> dict:
        return {"procedure": self.procedure.to_dict(), "support": self.support, "sources": self.sources,
                "status": self.status, "validation": self.validation, "field": self.field, "history": self.history,
                "replaced_by": self.replaced_by}

    @classmethod
    def from_dict(cls, d) -> "Entry":
        return cls(Procedure.from_dict(d["procedure"]), d["support"], d["sources"], d["status"], d["validation"],
                   d["field"], [tuple(h) for h in d["history"]], d["replaced_by"])


def _canon(x) -> str:
    return json.dumps(x, sort_keys=True, separators=(",", ":"), default=list)


class KnowledgeBase:
    def __init__(self):
        self.entries: dict = {}
        self.examples_seen: set = set()

    # ------------------------------------------------------------------ discover + construct
    def learn(self, examples: list, source: str) -> list:
        """examples: [(before_fn, after_fn, example_id)]. Re-induces over all examples seen so far plus the new ones,
        so a new example can generalize an old procedure. Returns ids of procedures that are new."""
        new_ids = []
        fresh = [e for e in examples if e[2] not in self.examples_seen]
        self._pool = getattr(self, "_pool", []) + fresh
        self._source_of = getattr(self, "_source_of", {})
        for e in fresh:
            self.examples_seen.add(e[2])
            self._source_of[e[2]] = source
        for proc, ids in induce(self._pool):
            ent = self.entries.get(proc.id)
            if ent is None:
                ent = Entry(proc)
                ent.history.append((round(time.time()), "discovered", source))
                self.entries[proc.id] = ent
                new_ids.append(proc.id)
            for i in ids:
                if i not in ent.support:
                    ent.support.append(i)
            ent.sources = sorted({self._source_of.get(i, "unknown") for i in ent.support})
            if ent.status == "candidate" and len(ent.support) >= MIN_SUPPORT_ACTIVE:
                self._set(ent, "active", f"corroborated by {len(ent.support)} independent examples")
        return new_ids

    # ------------------------------------------------------------------ test predictions
    def validate(self, held_out: list) -> dict:
        """Apply every non-retired procedure to held-out examples [(before_fn, after_fn, id)] it was not learned from.
        A hit: one generated program equals the real fix (AST). Updates evidence and status. Returns a summary."""
        targets = [(b, _norm(a), i) for b, a, i in held_out]
        for ent in self.entries.values():
            if ent.status in ("retired", "superseded"):
                continue
            for before, after_n, eid in targets:
                if eid in ent.support or after_n is None:
                    continue
                outs = ent.procedure.apply(before, (1, before.count("\n") + 1))
                if not outs:
                    continue
                ent.validation["fires"] += 1
                ent.validation["cost"] += len(outs)
                if any(_norm(o) == after_n for o in outs):
                    ent.validation["hits"] += 1
                    ent.validation["hit_ids"].append(eid)
            v = ent.validation
            if ent.status == "candidate" and v["hits"] >= MIN_VALIDATION_HITS and v["fires"] and \
                    v["hits"] / v["fires"] >= MIN_VALIDATION_PRECISION:
                self._set(ent, "active", f"validated: {v['hits']} held-out hits in {v['fires']} fires")
        self.revise()
        return self.summary()

    # ------------------------------------------------------------------ search + apply
    def retrieve(self, source: str, span: tuple, include_candidates: bool = True, max_programs: int | None = None) -> list:
        """[(entry, programs)] in trust order. DEV18 A2 (performance; same results): with `max_programs`, stops once that
        many programs are held; the result is then exactly the first `max_programs` programs of the full retrieval."""
        order = sorted((e for e in self.entries.values() if e.status == "active" or
                        (include_candidates and e.status == "candidate")),
                       key=lambda e: (e.status != "active", -(e.validation["hits"] + e.field["hits"]),
                                      -(e.precision() or 0.0), -len(e.support), e.id))
        out, held = [], 0
        for ent in order:
            if max_programs is not None and held >= max_programs:
                break
            left = None if max_programs is None else max_programs - held
            progs = [p for p, _ in ent.procedure.apply_detailed(source, span, max_results=left)]
            if progs:
                out.append((ent, progs))
                held += len(progs)
        return out

    def candidates_for(self, source: str, path: str, span: tuple, limit: int = MAX_CANDIDATES) -> list:
        """At most `limit` candidates (DEV19 A2: the same limit-0 defect as ShapeLibrary.candidates_for; no caller
        passed 0 here)."""
        from .research import Candidate
        if limit <= 0:
            return []
        cands = []
        for ent, progs in self.retrieve(source, span):
            for k, prog in enumerate(progs):
                c = Candidate(path, prog, f"learned: {ent.id} [{ent.status}] {ent.procedure.describe()}"[:200])
                c.meta = {"kind": f"learned_{ent.procedure.kind}", "family": "learned", "line": span[0],
                          "line_score": 0.0, "line_rank": 99, "original": ent.id, "option": ent.status,
                          "procedure": ent.id, "match_index": k}
                cands.append(c)
                if len(cands) >= limit:
                    return cands
        return cands

    # ------------------------------------------------------------------ improve or replace
    def record_outcome(self, procedure_id: str, success: bool, problem_id: str) -> None:
        ent = self.entries[procedure_id]
        ent.field["fires"] += 1
        ent.field["hits"] += int(success)
        ent.field["problems"].append([problem_id, bool(success)])
        ent.history.append((round(time.time()), "outcome", f"{problem_id}: {'success' if success else 'failure'}"))
        if success and ent.status == "candidate":
            self._set(ent, "active", f"confirmed on {problem_id}")
        self.revise()

    def revise(self) -> None:
        live = [e for e in self.entries.values() if e.status in ("candidate", "active")]
        for e in live:
            fires = e.validation["fires"] + e.field["fires"]
            hits = e.validation["hits"] + e.field["hits"]
            if fires >= RETIRE_MIN_FIRES and hits == 0:
                self._set(e, "retired", f"{fires} fires, no success")
        live = [e for e in live if e.status in ("candidate", "active")]
        hitsets = {e.id: set(e.validation["hit_ids"]) | {p for p, ok in e.field["problems"] if ok} for e in live}
        for a in live:
            for b in live:
                if a is b or a.status not in ("candidate", "active") or b.status not in ("candidate", "active"):
                    continue
                ha, hb = hitsets[a.id], hitsets[b.id]
                if not hb or not hb <= ha:
                    continue
                pa, pb = a.precision() or 0.0, b.precision() or 0.0
                cost_a = a.validation["cost"] + a.field["fires"]
                cost_b = b.validation["cost"] + b.field["fires"]
                if (ha == hb and (cost_a, a.id) < (cost_b, b.id)) or (ha > hb and pa >= pb):
                    self._set(b, "superseded", f"replaced by {a.id}")
                    b.replaced_by = a.id

    def _set(self, ent: Entry, status: str, why: str) -> None:
        if ent.status != status:
            ent.history.append((round(time.time()), status, why))
            ent.status = status

    # ------------------------------------------------------------------ preserve
    def summary(self) -> dict:
        by = {}
        for e in self.entries.values():
            by[e.status] = by.get(e.status, 0) + 1
        return {"procedures": len(self.entries), "by_status": dict(sorted(by.items())),
                "examples": len(self.examples_seen),
                "validated_hits": sum(e.validation["hits"] for e in self.entries.values())}

    def body(self) -> dict:
        return {"entries": [self.entries[k].to_dict() for k in sorted(self.entries)],
                "examples_seen": sorted(self.examples_seen),
                "examples": [list(e) for e in getattr(self, "_pool", [])],
                "example_sources": dict(sorted(getattr(self, "_source_of", {}).items()))}  # kept so later learning can re-generalize

    def save(self, path) -> str:
        body = self.body()
        seal = hashlib.sha256(_canon(body).encode()).hexdigest()
        Path(path).write_text(_canon({"body": body, "sha256": seal}) + "\n", encoding="utf-8")
        return seal

    @classmethod
    def load(cls, path) -> "KnowledgeBase":
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        if hashlib.sha256(_canon(d["body"]).encode()).hexdigest() != d.get("sha256"):
            raise ValueError("knowledge file failed its integrity check (edited or corrupted); refusing to load")
        kb = cls()
        for e in d["body"]["entries"]:
            ent = Entry.from_dict(e)
            kb.entries[ent.id] = ent
        kb.examples_seen = set(d["body"]["examples_seen"])
        kb._pool = [tuple(e) for e in d["body"].get("examples", [])]
        kb._source_of = dict(d["body"].get("example_sources", {}))
        return kb
