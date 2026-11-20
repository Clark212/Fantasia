from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class EvidenceLineageRecord:
    """Immutable provenance for one observed evidence item.

    ``roots`` are the independent upstream evidence units that ultimately
    support this item. A copied/transformed observation inherits its parents'
    roots and therefore contributes no fresh support when those roots have
    already been consumed by a belief state.
    """

    evidence_id: str
    source_id: str
    parent_ids: tuple[str, ...]
    roots: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "source_id": self.source_id,
            "parent_ids": list(self.parent_ids),
            "roots": list(self.roots),
        }


class EvidenceLineageGraph:
    """Bounded, fail-closed evidence provenance graph.

    Alpha.6.2 deliberately does *not* infer hidden correlations. Instead, it
    makes explicit provenance actionable: copied/derived evidence can point to
    upstream evidence IDs (or explicit independent root IDs), letting ASM avoid
    counting the same underlying support multiple times.

    Unknown parents are rejected rather than silently treated as independent.
    This is important because inventing independence would recreate the exact
    overconfidence failure this module is meant to prevent.
    """

    def __init__(self, *, max_nodes: int = 65536, max_roots_per_item: int = 256) -> None:
        self.max_nodes = int(max_nodes)
        self.max_roots_per_item = int(max_roots_per_item)
        if self.max_nodes < 1:
            raise ValueError("max_nodes must be >= 1")
        if self.max_roots_per_item < 1:
            raise ValueError("max_roots_per_item must be >= 1")
        self._records: dict[str, EvidenceLineageRecord] = {}

    @staticmethod
    def _key(value: Any, name: str) -> str:
        key = str(value).strip()
        if not key:
            raise ValueError(f"{name} must be non-empty")
        return key

    @classmethod
    def _keys(cls, values: Iterable[Any] | None, name: str) -> tuple[str, ...]:
        if values is None:
            return ()
        out: list[str] = []
        seen: set[str] = set()
        for value in values:
            key = cls._key(value, name)
            if key not in seen:
                seen.add(key)
                out.append(key)
        return tuple(sorted(out))

    def register(
        self,
        evidence_id: str,
        *,
        source_id: str,
        parent_ids: Iterable[str] | None = None,
        root_ids: Iterable[str] | None = None,
    ) -> EvidenceLineageRecord:
        eid = self._key(evidence_id, "evidence_id")
        sid = self._key(source_id, "source_id")
        parents = self._keys(parent_ids, "parent evidence id")
        explicit_roots = self._keys(root_ids, "lineage root id")
        if eid in parents:
            raise ValueError("evidence cannot be its own parent")

        roots: set[str] = set(explicit_roots)
        for parent_id in parents:
            parent = self._records.get(parent_id)
            if parent is None:
                raise ValueError(f"unknown parent evidence id: {parent_id!r}")
            roots.update(parent.roots)

        # A base observation is itself one independent evidence unit unless the
        # caller explicitly identifies an upstream independent root.
        if not parents and not explicit_roots:
            roots.add(f"evidence:{eid}")
        if not roots:
            raise ValueError("evidence lineage must resolve to at least one root")
        if len(roots) > self.max_roots_per_item:
            raise RuntimeError("evidence lineage root capacity reached for one item")

        record = EvidenceLineageRecord(
            evidence_id=eid,
            source_id=sid,
            parent_ids=parents,
            roots=tuple(sorted(roots)),
        )
        existing = self._records.get(eid)
        if existing is not None:
            if existing != record:
                raise ValueError("evidence_id already registered with conflicting lineage")
            return existing
        if len(self._records) >= self.max_nodes:
            raise RuntimeError("evidence lineage graph capacity reached")
        self._records[eid] = record
        return record

    def get(self, evidence_id: str) -> EvidenceLineageRecord | None:
        return self._records.get(self._key(evidence_id, "evidence_id"))

    def roots(self, evidence_id: str) -> tuple[str, ...]:
        record = self.get(evidence_id)
        if record is None:
            raise KeyError(f"unknown evidence id: {evidence_id!r}")
        return record.roots

    @staticmethod
    def novelty(existing_roots: Iterable[str], incoming_roots: Iterable[str]) -> float:
        existing = {str(x) for x in existing_roots}
        incoming = {str(x) for x in incoming_roots}
        if not incoming:
            raise ValueError("incoming evidence must have at least one lineage root")
        novel = len(incoming - existing)
        return float(novel / len(incoming))

    def stats(self) -> dict[str, Any]:
        root_count = len({root for row in self._records.values() for root in row.roots})
        copied = sum(1 for row in self._records.values() if row.parent_ids)
        return {
            "evidence_nodes": len(self._records),
            "independent_roots": root_count,
            "derived_or_copied_nodes": copied,
            "max_nodes": self.max_nodes,
            "max_roots_per_item": self.max_roots_per_item,
        }

    def export_state(self) -> dict[str, Any]:
        return {
            "schema": 1,
            "max_nodes": self.max_nodes,
            "max_roots_per_item": self.max_roots_per_item,
            "records": [self._records[key].as_dict() for key in sorted(self._records)],
        }

    def import_state(self, payload: dict[str, Any] | None) -> None:
        if not payload:
            return
        if int(payload.get("schema", 1)) != 1:
            raise ValueError("unsupported evidence lineage snapshot schema")
        raw = payload.get("records", [])
        if not isinstance(raw, list):
            raise ValueError("evidence lineage records must be a list")
        if len(raw) > self.max_nodes:
            raise ValueError("evidence lineage snapshot exceeds node capacity")

        # Rebuild in stored order-independent passes so parent references can
        # appear anywhere in the serialized list. Cycles/missing parents fail.
        pending: dict[str, dict[str, Any]] = {}
        for item in raw:
            if not isinstance(item, dict):
                raise ValueError("evidence lineage record must be a mapping")
            eid = self._key(item.get("evidence_id", ""), "evidence_id")
            if eid in pending:
                raise ValueError("duplicate evidence_id in lineage snapshot")
            pending[eid] = item

        restored: dict[str, EvidenceLineageRecord] = {}
        while pending:
            progressed = False
            for eid in list(sorted(pending)):
                item = pending[eid]
                sid = self._key(item.get("source_id", ""), "source_id")
                parents = self._keys(item.get("parent_ids", []), "parent evidence id")
                if any(parent not in restored for parent in parents):
                    continue
                stored_roots = self._keys(item.get("roots", []), "lineage root id")
                if not stored_roots or len(stored_roots) > self.max_roots_per_item:
                    raise ValueError("invalid evidence lineage roots in snapshot")
                derived: set[str] = set()
                for parent in parents:
                    derived.update(restored[parent].roots)
                # Parent-derived records may also carry explicit roots, so the
                # stored roots must include every parent's ancestry.
                if not derived.issubset(set(stored_roots)):
                    raise ValueError("lineage snapshot roots do not preserve parent ancestry")
                restored[eid] = EvidenceLineageRecord(
                    evidence_id=eid,
                    source_id=sid,
                    parent_ids=parents,
                    roots=stored_roots,
                )
                del pending[eid]
                progressed = True
            if not progressed:
                raise ValueError("lineage snapshot contains missing parents or a cycle")
        self._records = restored


# --- Astra donor: explicit evidence ledger (additive; does not replace hidden-dependency learning) ---
import json as _ledger_json
import math as _ledger_math
from .planning import DiscreteBeliefState as _LedgerBeliefState

def bounded_id(value, name='id'):
    if not isinstance(value,str) or not value.strip() or len(value)>256:
        raise ValueError(f'{name} must be a non-empty string of at most 256 characters')
    return value


class EvidenceLedger:
    def __init__(self, prior, *, max_records=4096):
        if type(max_records) is not int or not 1<=max_records<=100000:
            raise ValueError('max_records out of range')
        self.prior=prior if isinstance(prior,_LedgerBeliefState) else _LedgerBeliefState.from_mapping(prior)
        if len(self.prior.hypothesis_names())>32:raise ValueError('lineage supports at most 32 hypotheses')
        self.belief=self.prior
        self.max_records=max_records
        self._records={}
        self._roots={}
        self._counted=set()
        self.suppressed=0

    def add(self, evidence_id, *, source_id, likelihoods=None, parents=(), context='',
            time=None, transformation='observation', source_version=1, confidence=1.0):
        bounded_id(evidence_id,'evidence_id');bounded_id(source_id,'source_id')
        if not isinstance(parents,(list,tuple)) or len(parents)>32 or any(not isinstance(p,str) for p in parents) or len(set(parents))!=len(parents):
            raise ValueError('parents must contain at most 32 distinct prior evidence IDs')
        if any(not isinstance(p,str) or p not in self._records for p in parents):
            raise ValueError('unknown parent; ancestry must precede descendants')
        if not isinstance(context,str) or len(context)>512:
            raise ValueError('invalid context')
        bounded_id(transformation,'transformation')
        if type(source_version) is not int or source_version<1:
            raise ValueError('invalid source version')
        if type(confidence) not in (int,float) or not _ledger_math.isfinite(confidence) or not 0<=confidence<=1:
            raise ValueError('invalid confidence')
        if time is not None and (type(time) not in (float,int) or not _ledger_math.isfinite(time)):
            raise ValueError('invalid time')
        likes=None if likelihoods is None else self.prior._validated_likelihoods(likelihoods)
        record=dict(evidence_id=evidence_id,source_id=source_id,parents=list(parents),
                    likelihoods=likes,context=context,time=time,transformation=transformation,
                    source_version=source_version,confidence=float(confidence))
        if evidence_id in self._records:
            existing=self._records[evidence_id]
            if {k:existing[k] for k in record}!=record:
                raise ValueError('conflicting reuse of evidence ID')
            return {'status':'duplicate','evidence_id':evidence_id,'belief':self.belief.as_dict()}
        if len(self._records)>=self.max_records:
            raise RuntimeError('evidence ledger capacity reached; no evidence was discarded')
        roots=frozenset().union(*(self._roots[p] for p in parents)) if parents else frozenset((evidence_id,))
        if len(roots)>256:
            raise ValueError('ancestry root capacity exceeded')
        overlap=bool(roots & self._counted)
        status='provenance_only' if likes is None else ('dependent_support' if overlap else 'counted')
        # Compute before commit. Invalid/impossible evidence leaves the ledger intact.
        next_belief=self.belief.update(likes) if status=='counted' else self.belief
        record['status']=status
        self._records[evidence_id]=record
        self._roots[evidence_id]=roots
        if status=='counted':self._counted.update(roots)
        if status=='dependent_support':self.suppressed+=1
        self.belief=next_belief
        return {'status':status,'evidence_id':evidence_id,'roots':sorted(roots),'belief':self.belief.as_dict()}

    def record(self,evidence_id):
        return _ledger_json.loads(_ledger_json.dumps(self._records[evidence_id]))

    def export_state(self):
        return {'schema':1,'max_records':self.max_records,
                'prior_logs':self.prior.as_log_dict(),'structural_zeros':list(self.prior.structural_zero_hypotheses()),
                'prior_evidence_count':self.prior.evidence_count,
                'records':[self.record(k) for k in self._records]}

    @classmethod
    def from_state(cls,payload):
        expected={'schema','max_records','prior_logs','structural_zeros','prior_evidence_count','records'}
        if not isinstance(payload,dict) or set(payload)!=expected or payload['schema']!=1:
            raise ValueError('invalid lineage snapshot')
        logs=payload['prior_logs'];zeros=payload['structural_zeros'];count=payload['prior_evidence_count']
        if not isinstance(logs,dict) or not logs or any(not isinstance(k,str) or type(v) not in (int,float) or not _ledger_math.isfinite(v) for k,v in logs.items()):
            raise ValueError('invalid prior logs')
        if not isinstance(zeros,list) or any(not isinstance(x,str) or x in logs for x in zeros) or type(count) is not int or count<0:
            raise ValueError('invalid prior metadata')
        prior=_LedgerBeliefState((),count,tuple(logs.items()),tuple(zeros))
        ledger=cls(prior,max_records=payload['max_records'])
        records=payload['records']
        if not isinstance(records,list) or len(records)>ledger.max_records:
            raise ValueError('invalid lineage records')
        for record in records:
            if not isinstance(record,dict):raise ValueError('invalid lineage record')
            r=dict(record);status=r.pop('status',None)
            result=ledger.add(**r)
            if result['status']!=status:raise ValueError('lineage disposition mismatch')
        return ledger
