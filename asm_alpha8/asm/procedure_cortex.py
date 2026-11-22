from __future__ import annotations

"""Experimental ASM-native procedure cortex.

This module is deliberately NOT wired into ASMEngine in alpha.6.1.  It adapts
useful EPN research ideas (validated executable procedures, version retention,
invalidation, disagreement queries, structural families) while keeping ASM's
cognitive authority.  Promotion into a later capability stage requires separate
benchmarks and integration tests.
"""

from dataclasses import dataclass, field
import hashlib
import math
from typing import Any, Iterable


Expression = tuple


def _finite_number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("expected a numeric value")
    x = float(value)
    if not math.isfinite(x):
        raise ValueError("procedure values must be finite")
    return x


def _validate_expression(expr: Any, *, depth: int = 0) -> Expression:
    if depth > 12 or not isinstance(expr, tuple) or not expr:
        raise ValueError("invalid procedure expression")
    op = expr[0]
    if op == "var":
        if len(expr) != 2 or not isinstance(expr[1], int) or expr[1] < 0 or expr[1] > 31:
            raise ValueError("invalid variable reference")
        return expr
    if op == "const":
        if len(expr) != 2:
            raise ValueError("invalid constant")
        value = expr[1]
        if isinstance(value, bool):
            return expr
        _finite_number(value)
        return expr
    arity = {"not": 1, "add": 2, "sub": 2, "mul": 2, "and": 2, "or": 2, "xor": 2}.get(op)
    if arity is None or len(expr) != arity + 1:
        raise ValueError("unsupported procedure operation")
    for child in expr[1:]:
        _validate_expression(child, depth=depth + 1)
    return expr


def evaluate_expression(expr: Expression, inputs: tuple[Any, ...]) -> Any:
    """Evaluate a tiny safe DSL; no Python eval/exec is used."""
    _validate_expression(expr)

    def ev(node):
        op = node[0]
        if op == "var":
            i = node[1]
            if i >= len(inputs):
                raise ValueError("procedure variable exceeds input arity")
            return inputs[i]
        if op == "const":
            return node[1]
        if op == "not":
            return not bool(ev(node[1]))
        a, b = ev(node[1]), ev(node[2])
        if op == "add":
            return _finite_number(a) + _finite_number(b)
        if op == "sub":
            return _finite_number(a) - _finite_number(b)
        if op == "mul":
            return _finite_number(a) * _finite_number(b)
        if op == "and":
            return bool(a) and bool(b)
        if op == "or":
            return bool(a) or bool(b)
        if op == "xor":
            return bool(a) ^ bool(b)
        raise ValueError("unsupported procedure operation")

    result = ev(expr)
    if isinstance(result, float) and not math.isfinite(result):
        raise ValueError("procedure produced a non-finite value")
    return result


@dataclass(frozen=True, slots=True)
class ProcedureExample:
    inputs: tuple[Any, ...]
    output: Any
    evidence_id: str
    context: str = "default"


@dataclass(slots=True)
class ProcedureVersion:
    name: str
    version: int
    expression: Expression
    input_arity: int
    context: str
    status: str = "provisional"
    support: int = 0
    contradictions: int = 0
    evidence_ids: list[str] = field(default_factory=list)
    created_from: str = "induction"
    family_id: str | None = None

    @property
    def confidence(self) -> float:
        # Beta(1,1) validation posterior; transparent, bounded, not certainty.
        return (1.0 + self.support) / (2.0 + self.support + self.contradictions)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "expression": self.expression,
            "input_arity": self.input_arity,
            "context": self.context,
            "status": self.status,
            "support": self.support,
            "contradictions": self.contradictions,
            "confidence": self.confidence,
            "evidence_ids": list(self.evidence_ids),
            "created_from": self.created_from,
            "family_id": self.family_id,
        }


@dataclass(frozen=True, slots=True)
class ProcedureFamily:
    family_id: str
    template: Expression
    parameter: str
    members: tuple[str, ...]


class ExperimentalProcedureCortex:
    """Bounded native prototype for validated/versioned executable procedures.

    The cortex never writes ASM beliefs.  It only manages procedure hypotheses.
    External backends may propose expressions; promotion depends on supplied
    evidence, and contradictions can suspend an active procedure.
    """

    VALID_STATUS = {"provisional", "active", "suspicious", "suspended"}

    def __init__(self, *, min_support: int = 4, suspend_after: int = 2,
                 max_versions: int = 256, max_evidence_per_task: int = 256):
        if min_support < 1 or suspend_after < 1 or max_versions < 1 or max_evidence_per_task < 2:
            raise ValueError("procedure cortex bounds must be positive")
        self.min_support = int(min_support)
        self.suspend_after = int(suspend_after)
        self.max_versions = int(max_versions)
        self.max_evidence_per_task = int(max_evidence_per_task)
        self.versions: dict[str, list[ProcedureVersion]] = {}
        self.evidence: dict[str, list[ProcedureExample]] = {}

    @staticmethod
    def _name(value: str) -> str:
        name = str(value).strip()
        if not name:
            raise ValueError("procedure name must be non-empty")
        return name

    @staticmethod
    def _context(value: str | None) -> str:
        context = "default" if value is None else str(value).strip()
        if not context:
            raise ValueError("context must be non-empty")
        return context

    def _next_version(self, name: str) -> int:
        return len(self.versions.get(name, ())) + 1

    def _count_versions(self) -> int:
        return sum(len(v) for v in self.versions.values())

    @staticmethod
    def _matches(expr: Expression, examples: Iterable[ProcedureExample]) -> tuple[int, int]:
        support = contradictions = 0
        for example in examples:
            try:
                value = evaluate_expression(expr, example.inputs)
            except (ValueError, OverflowError):
                contradictions += 1
                continue
            if value == example.output:
                support += 1
            else:
                contradictions += 1
        return support, contradictions

    def propose(self, name: str, expression: Expression, *, input_arity: int,
                context: str | None = None, created_from: str = "backend_proposal") -> ProcedureVersion:
        name = self._name(name)
        context = self._context(context)
        expr = _validate_expression(expression)
        if not 1 <= int(input_arity) <= 32:
            raise ValueError("input_arity must be within 1..32")
        if self._count_versions() >= self.max_versions:
            raise RuntimeError("procedure version capacity reached")
        examples = [e for e in self.evidence.get(name, ()) if e.context == context]
        support, contradictions = self._matches(expr, examples)
        version = ProcedureVersion(
            name=name, version=self._next_version(name), expression=expr,
            input_arity=int(input_arity), context=context,
            support=support, contradictions=contradictions,
            evidence_ids=[e.evidence_id for e in examples], created_from=str(created_from),
        )
        if support >= self.min_support and contradictions == 0:
            version.status = "active"
            self._suspend_other_active(name, context=context)
        elif contradictions:
            version.status = "suspicious"
        self.versions.setdefault(name, []).append(version)
        return version

    def record(self, name: str, inputs: Iterable[Any], output: Any, *,
               evidence_id: str, context: str | None = None) -> dict[str, Any]:
        name = self._name(name)
        context = self._context(context)
        eid = str(evidence_id).strip()
        if not eid:
            raise ValueError("evidence_id must be non-empty")
        inp = tuple(inputs)
        if not 1 <= len(inp) <= 32:
            raise ValueError("procedure evidence requires 1..32 inputs")
        bucket = self.evidence.setdefault(name, [])
        if any(e.evidence_id == eid for e in bucket):
            raise ValueError("duplicate procedure evidence_id")
        bucket.append(ProcedureExample(inp, output, eid, context))
        if len(bucket) > self.max_evidence_per_task:
            del bucket[: len(bucket) - self.max_evidence_per_task]

        updates = []
        for version in self.versions.get(name, ()):
            if version.context != context or version.status == "suspended":
                continue
            if version.input_arity != len(inp):
                continue
            predicted = evaluate_expression(version.expression, inp)
            if predicted == output:
                version.support += 1
            else:
                version.contradictions += 1
            version.evidence_ids.append(eid)
            if version.contradictions >= self.suspend_after:
                version.status = "suspended"
            elif version.contradictions:
                version.status = "suspicious"
            elif version.support >= self.min_support:
                version.status = "active"
                self._suspend_other_active(name, context=context, except_version=version.version)
            updates.append(version.as_dict())
        return {"name": name, "context": context, "updated_versions": updates}

    def _suspend_other_active(self, name: str, *, context: str, except_version: int | None = None) -> None:
        for version in self.versions.get(name, ()):
            if (version.context == context and version.status == "active"
                    and version.version != except_version):
                version.status = "suspended"

    def active(self, name: str, *, context: str | None = None) -> ProcedureVersion | None:
        name = self._name(name); context = self._context(context)
        for version in reversed(self.versions.get(name, ())):
            if version.context == context and version.status == "active":
                return version
        return None

    def execute(self, name: str, inputs: Iterable[Any], *, context: str | None = None) -> dict[str, Any]:
        version = self.active(name, context=context)
        if version is None:
            return {"status": "no_active_procedure", "name": self._name(name), "context": self._context(context)}
        inp = tuple(inputs)
        if len(inp) != version.input_arity:
            raise ValueError("procedure input arity mismatch")
        return {
            "status": "executed", "name": version.name, "version": version.version,
            "context": version.context, "value": evaluate_expression(version.expression, inp),
            "confidence": version.confidence,
        }

    def induce_affine(self, name: str, *, context: str | None = None,
                      max_abs_parameter: int = 1000) -> ProcedureVersion | None:
        """Bounded unary affine induction from stored numeric evidence.

        This is intentionally small and transparent: it is a prototype of the
        procedure-validation lifecycle, not a claim of general program synthesis.
        """
        name = self._name(name); context = self._context(context)
        examples = [e for e in self.evidence.get(name, ()) if e.context == context and len(e.inputs) == 1]
        numeric = []
        for e in examples:
            try:
                x = _finite_number(e.inputs[0]); y = _finite_number(e.output)
            except ValueError:
                return None
            numeric.append((x, y))
        if len(numeric) < 2:
            return None
        pair = None
        for i in range(len(numeric)):
            for j in range(i + 1, len(numeric)):
                if numeric[i][0] != numeric[j][0]:
                    pair = (numeric[i], numeric[j]); break
            if pair: break
        if pair is None:
            return None
        (x1, y1), (x2, y2) = pair
        a = (y2 - y1) / (x2 - x1)
        b = y1 - a * x1
        # Keep this first prototype exact/simple: integer affine procedures only.
        if abs(a - round(a)) > 1e-12 or abs(b - round(b)) > 1e-12:
            return None
        a = int(round(a)); b = int(round(b))
        if abs(a) > max_abs_parameter or abs(b) > max_abs_parameter:
            return None
        expr = ("add", ("mul", ("const", a), ("var", 0)), ("const", b))
        support, contradictions = self._matches(expr, examples)
        if contradictions:
            return None
        return self.propose(name, expr, input_arity=1, context=context, created_from="affine_induction")

    def induce_boolean(self, name: str, *, context: str | None = None) -> ProcedureVersion | None:
        name = self._name(name); context = self._context(context)
        examples = [e for e in self.evidence.get(name, ()) if e.context == context]
        if len(examples) < 2:
            return None
        arity = len(examples[0].inputs)
        if not 1 <= arity <= 8 or any(len(e.inputs) != arity for e in examples):
            return None
        if any(any(type(v) is not bool for v in e.inputs) or type(e.output) is not bool for e in examples):
            return None
        candidates: list[Expression] = [("const", False), ("const", True)]
        vars_ = [("var", i) for i in range(arity)]
        candidates += vars_ + [("not", v) for v in vars_]
        for i in range(arity):
            for j in range(i + 1, arity):
                for op in ("and", "or", "xor"):
                    candidates.append((op, vars_[i], vars_[j]))
        for expr in candidates:
            support, contradictions = self._matches(expr, examples)
            if contradictions == 0:
                return self.propose(name, expr, input_arity=arity, context=context, created_from="boolean_induction")
        return None

    def disagreement_probe(self, name: str, probes: Iterable[Iterable[Any]], *,
                           context: str | None = None) -> dict[str, Any]:
        name = self._name(name); context = self._context(context)
        candidates = [v for v in self.versions.get(name, ())
                      if v.context == context and v.status != "suspended"]
        if len(candidates) < 2:
            return {"status": "insufficient_hypotheses", "name": name}
        best = None
        for raw in probes:
            inp = tuple(raw)
            outputs = []
            for v in candidates:
                if len(inp) != v.input_arity:
                    continue
                outputs.append((v.version, evaluate_expression(v.expression, inp)))
            distinct = len({repr(value) for _, value in outputs})
            if distinct > 1 and (best is None or distinct > best[0]):
                best = (distinct, inp, outputs)
        if best is None:
            return {"status": "no_disagreement_found", "name": name,
                    "claim": "Finite probes found no disagreement; this is not proof of equivalence."}
        return {"status": "disagreement", "name": name, "input": best[1],
                "candidate_outputs": best[2], "distinct_outputs": best[0]}

    def affine_families(self) -> list[ProcedureFamily]:
        """Anti-unify active affine procedures that share slope but vary intercept."""
        groups: dict[int, list[tuple[str, int, int]]] = {}
        for name, versions in self.versions.items():
            for v in versions:
                if v.status != "active":
                    continue
                e = v.expression
                try:
                    if not (e[0] == "add" and e[1][0] == "mul" and e[1][1][0] == "const"
                            and e[1][2] == ("var", 0) and e[2][0] == "const"):
                        continue
                    slope = int(e[1][1][1]); intercept = int(e[2][1])
                except (IndexError, TypeError, ValueError):
                    continue
                groups.setdefault(slope, []).append((name, v.version, intercept))
        families = []
        for slope, members in groups.items():
            intercepts = {m[2] for m in members}
            if len(members) < 2 or len(intercepts) < 2:
                continue
            key = repr((slope, sorted((m[0], m[1]) for m in members))).encode()
            fid = "affine_" + hashlib.sha256(key).hexdigest()[:10]
            template = ("add", ("mul", ("const", slope), ("var", 0)), ("const", "$b"))
            families.append(ProcedureFamily(fid, template, "$b",
                                            tuple(f"{n}@{v}" for n, v, _ in sorted(members))))
        return families

    def export_state(self) -> dict[str, Any]:
        return {
            "schema": 1,
            "experimental": True,
            "min_support": self.min_support,
            "suspend_after": self.suspend_after,
            "max_versions": self.max_versions,
            "max_evidence_per_task": self.max_evidence_per_task,
            "versions": {name: [v.as_dict() for v in versions] for name, versions in self.versions.items()},
            "evidence": {name: [{"inputs": e.inputs, "output": e.output, "evidence_id": e.evidence_id,
                                  "context": e.context} for e in examples]
                         for name, examples in self.evidence.items()},
        }

    @classmethod
    def import_state(cls, payload: dict[str, Any]) -> "ExperimentalProcedureCortex":
        if not isinstance(payload, dict) or payload.get("schema") != 1:
            raise ValueError("unsupported procedure cortex snapshot")
        cortex = cls(
            min_support=int(payload.get("min_support", 4)),
            suspend_after=int(payload.get("suspend_after", 2)),
            max_versions=int(payload.get("max_versions", 256)),
            max_evidence_per_task=int(payload.get("max_evidence_per_task", 256)),
        )

        def as_tuple(value):
            if isinstance(value, list):
                return tuple(as_tuple(x) for x in value)
            if isinstance(value, tuple):
                return tuple(as_tuple(x) for x in value)
            return value

        raw_evidence = payload.get("evidence", {})
        if not isinstance(raw_evidence, dict):
            raise ValueError("procedure evidence snapshot must be a mapping")
        for raw_name, rows in raw_evidence.items():
            name = cortex._name(raw_name)
            if not isinstance(rows, list) or len(rows) > cortex.max_evidence_per_task:
                raise ValueError("procedure evidence snapshot exceeds bounds")
            bucket = []
            seen = set()
            for row in rows:
                if not isinstance(row, dict):
                    raise ValueError("procedure evidence row must be a mapping")
                eid = str(row.get("evidence_id", "")).strip()
                if not eid or eid in seen:
                    raise ValueError("invalid/duplicate procedure evidence id")
                seen.add(eid)
                inputs = tuple(as_tuple(row.get("inputs", ())))
                if not 1 <= len(inputs) <= 32:
                    raise ValueError("invalid procedure evidence arity")
                bucket.append(ProcedureExample(inputs, row.get("output"), eid, cortex._context(row.get("context"))))
            cortex.evidence[name] = bucket

        raw_versions = payload.get("versions", {})
        if not isinstance(raw_versions, dict):
            raise ValueError("procedure versions snapshot must be a mapping")
        total = sum(len(v) for v in raw_versions.values() if isinstance(v, list))
        if total > cortex.max_versions:
            raise ValueError("procedure snapshot exceeds version capacity")
        for raw_name, rows in raw_versions.items():
            name = cortex._name(raw_name)
            if not isinstance(rows, list):
                raise ValueError("procedure versions must be lists")
            restored = []
            seen_versions = set()
            for row in rows:
                if not isinstance(row, dict):
                    raise ValueError("procedure version row must be a mapping")
                version = int(row.get("version", 0))
                if version < 1 or version in seen_versions:
                    raise ValueError("invalid/duplicate procedure version")
                seen_versions.add(version)
                expr = _validate_expression(as_tuple(row.get("expression")))
                status = str(row.get("status", "provisional"))
                if status not in cortex.VALID_STATUS:
                    raise ValueError("invalid procedure status")
                restored.append(ProcedureVersion(
                    name=name, version=version, expression=expr,
                    input_arity=int(row.get("input_arity", 0)),
                    context=cortex._context(row.get("context")), status=status,
                    support=int(row.get("support", 0)), contradictions=int(row.get("contradictions", 0)),
                    evidence_ids=[str(x) for x in row.get("evidence_ids", [])],
                    created_from=str(row.get("created_from", "restored")),
                    family_id=row.get("family_id"),
                ))
            cortex.versions[name] = restored
        return cortex


# --- Astra donor: audited typed Procedure Cortex (experimental engine integration) ---
"""ASM-owned, auditable executable hypotheses with held-out validation.

The DSL and generator are supplied inductive biases, not learned universal
intelligence. Evidence and each version are retained in SQLite; compilation is
recoverable from the stored expression, dependencies and evidence links.
"""
import hashlib
import itertools
import json
import sqlite3
from .evidence_lineage import bounded_id
from .procedure_program import Program,anti_unify,substitute,choose_experiment


def pack(value):return json.dumps(value,sort_keys=True,separators=(',',':'))


class ProcedureCortex:
    MAX_MECHANISMS=128
    MAX_VERSIONS=64
    MIN_VALIDATION=8
    TRUST_FLOOR=.8

    EXTRAPOLATION_GUARDS=('off','abstain','discount')
    FAMILY_SHARING=('listing','round_robin')
    FAMILY_SCOPES=('one_input','any_int')
    FAMILY_MAPPINGS=('exact','rename')

    def __init__(self,db_path,*,trust_provider,dependency_provider=None,extrapolation_guard='abstain',extrapolation_confidence_cap=.5,
                 family_sharing='round_robin',family_scope='one_input',family_mapping='exact'):
        # Honesty guard (DEFAULT 'abstain' since DEV3.3; 'off' restores the pre-DEV3.2 behaviour). 'abstain': refuse queries whose integer
        # inputs lie outside the range of the evidence behind the active procedure. 'discount': still answer, but cap confidence at the cap.
        if extrapolation_guard not in self.EXTRAPOLATION_GUARDS:raise ValueError('invalid extrapolation guard')
        if type(extrapolation_confidence_cap) not in (int,float) or not 0<extrapolation_confidence_cap<=1:raise ValueError('invalid extrapolation confidence cap')
        self.extrapolation_guard=extrapolation_guard;self.extrapolation_confidence_cap=float(extrapolation_confidence_cap)
        # How `induce` shares its family budget (at most 64 candidates) between learned families. 'round_robin' (DEFAULT
        # since DEV21's owner-approved change; G21-A passed on held-out structures): every family proposes its next
        # instantiation before any family proposes another. 'listing' (the default before): families in listing order,
        # each until the budget is spent, so a two-parameter family can use all of it (DEV4's T3b interference).
        if family_sharing not in self.FAMILY_SHARING:raise ValueError('invalid family sharing')
        # DEV22 (experimental, opt-in): which integer targets learned families propose for. 'one_input' (default,
        # unchanged): only targets with one integer input. 'any_int': also targets with 2-4 integer inputs.
        if family_scope not in self.FAMILY_SCOPES:raise ValueError('invalid family scope')
        # DEV23 (experimental, opt-in): 'exact' (default, unchanged): a family applies only to targets with its own input
        # names. 'rename': also to targets whose inputs differ only by name, under every renaming (_renamings).
        if family_mapping not in self.FAMILY_MAPPINGS:raise ValueError('invalid family mapping')
        self.family_sharing=family_sharing;self.family_scope=family_scope;self.family_mapping=family_mapping
        self.db=sqlite3.connect(str(db_path))
        self.db.execute('PRAGMA journal_mode=WAL')
        self.trust_provider=trust_provider
        self.dependency_provider=dependency_provider
        self._programs={}
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS procedure_evidence(
          id TEXT PRIMARY KEY, mechanism TEXT NOT NULL, context TEXT NOT NULL,
          root TEXT NOT NULL, source TEXT NOT NULL, source_version INTEGER NOT NULL,
          inputs TEXT NOT NULL, expected TEXT NOT NULL, seq INTEGER NOT NULL UNIQUE);
        CREATE INDEX IF NOT EXISTS procedure_evidence_context ON procedure_evidence(mechanism,context,seq);
        CREATE TABLE IF NOT EXISTS procedure_versions(
          mechanism TEXT NOT NULL, context TEXT NOT NULL, version INTEGER NOT NULL,
          program TEXT NOT NULL, provenance TEXT NOT NULL, created_seq INTEGER NOT NULL,
          state TEXT NOT NULL, support INTEGER NOT NULL DEFAULT 0,
          contradictions INTEGER NOT NULL DEFAULT 0, dependencies TEXT NOT NULL,
          PRIMARY KEY(mechanism,context,version));
        CREATE INDEX IF NOT EXISTS procedure_state ON procedure_versions(mechanism,context,state);
        CREATE TABLE IF NOT EXISTS procedure_support(
          mechanism TEXT NOT NULL, context TEXT NOT NULL, version INTEGER NOT NULL,
          evidence_id TEXT NOT NULL, root TEXT NOT NULL, phase TEXT NOT NULL,
          matched INTEGER NOT NULL, PRIMARY KEY(mechanism,context,version,root));
        CREATE TABLE IF NOT EXISTS procedure_families(
          id TEXT PRIMARY KEY, inputs TEXT NOT NULL, template TEXT NOT NULL, parents TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS procedure_audit(
          seq INTEGER PRIMARY KEY, mechanism TEXT NOT NULL, context TEXT NOT NULL,
          version INTEGER NOT NULL, event TEXT NOT NULL, evidence_id TEXT);
        CREATE TABLE IF NOT EXISTS procedure_auto_state(
          mechanism TEXT NOT NULL, context TEXT NOT NULL, last_attempt_seq INTEGER NOT NULL DEFAULT 0,
          last_signature TEXT NOT NULL DEFAULT '', last_status TEXT NOT NULL DEFAULT '',
          attempts INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY(mechanism,context));
        CREATE TABLE IF NOT EXISTS procedure_route_evidence(
          seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE,
          mechanism TEXT NOT NULL, root TEXT NOT NULL, source TEXT NOT NULL,
          source_version INTEGER NOT NULL, features TEXT NOT NULL,
          target_context TEXT NOT NULL, temporal_index REAL);
        CREATE INDEX IF NOT EXISTS procedure_route_mechanism_seq
          ON procedure_route_evidence(mechanism,seq);
        CREATE UNIQUE INDEX IF NOT EXISTS procedure_route_root
          ON procedure_route_evidence(mechanism,root);
        ''')
        # WIP migration is additive: alpha.7.4 DBs have no route table, while an
        # earlier parallel-router DB may have the table without temporal_index.
        route_cols={r[1] for r in self.db.execute('PRAGMA table_info(procedure_route_evidence)')}
        if route_cols and 'temporal_index' not in route_cols:
            self.db.execute('ALTER TABLE procedure_route_evidence ADD COLUMN temporal_index REAL')
        self.db.execute('CREATE INDEX IF NOT EXISTS procedure_route_temporal ON procedure_route_evidence(mechanism,temporal_index)')
        self.db.commit()
        self._scopes=set(self.db.execute('SELECT DISTINCT mechanism,context FROM procedure_evidence'))

    def _trust(self,source):
        data=self.trust_provider(source)
        r=data['reliability'];v=data.get('version',1)
        import math
        if type(r) not in (int,float) or not math.isfinite(r) or not 0<=r<=1 or type(v) is not int or v<1:
            raise ValueError('invalid core trust response')
        return {'reliability':float(r),'version':v}

    def _program(self,data):
        if data not in self._programs:
            if len(self._programs)>=256:self._programs.pop(next(iter(self._programs)))
            self._programs[data]=Program.from_dict(json.loads(data))
        return self._programs[data]

    def _event(self,mechanism,context,version,event,evidence_id=None):
        self.db.execute('INSERT INTO procedure_audit(mechanism,context,version,event,evidence_id) VALUES(?,?,?,?,?)',
                        (mechanism,context,version,event,evidence_id))

    def _scope(self,mechanism,context):
        bounded_id(mechanism,'mechanism')
        if not isinstance(context,str) or len(context)>256:raise ValueError('invalid procedure context')

    def observe(self,mechanism,values,expected,*,evidence_id,source_id,root_id=None,context='',
                auto_induce=False,induction_budget=512,induction_fit_roots=3):
        self._scope(mechanism,context);bounded_id(evidence_id);bounded_id(source_id)
        if type(auto_induce) is not bool:raise ValueError('auto_induce must be boolean')
        if type(induction_budget) is not int or not 1<=induction_budget<=512:raise ValueError('invalid induction budget')
        if type(induction_fit_roots) is not int or not 3<=induction_fit_roots<=16:raise ValueError('invalid induction fit root count')
        root_id=evidence_id if root_id is None else bounded_id(root_id,'root_id')
        # Apply the same input contract even before a program exists.
        if not isinstance(values,dict) or not 1<=len(values)<=4 or any(type(x) not in (int,bool) for x in values.values()):raise ValueError('invalid procedure observation')
        probe=Program({k:'bool' if type(v) is bool else 'int' for k,v in values.items()},next(iter(values)))
        probe.validate_inputs(values)
        if type(expected) not in (int,bool) or type(expected) is int and abs(expected)>10**12:raise ValueError('invalid expected value')
        trust=self._trust(source_id)
        row=(mechanism,context,root_id,source_id,trust['version'],pack(values),pack(expected))
        old=self.db.execute('SELECT mechanism,context,root,source,source_version,inputs,expected FROM procedure_evidence WHERE id=?',(evidence_id,)).fetchone()
        if old is not None:
            if old!=row:raise ValueError('conflicting procedure evidence ID')
            return {'status':'duplicate'}
        if (mechanism,context) not in self._scopes and len(self._scopes)>=self.MAX_MECHANISMS:raise RuntimeError('procedure mechanism capacity reached')
        versions=self.db.execute("SELECT version,program,state,dependencies,created_seq FROM procedure_versions WHERE mechanism=? AND context=? AND state IN ('proposed','active','suspicious') ORDER BY version",(mechanism,context)).fetchall()
        with self.db:
            seq=self.db.execute('SELECT COALESCE(MAX(seq),0)+1 FROM procedure_evidence').fetchone()[0]
            self.db.execute('INSERT INTO procedure_evidence VALUES(?,?,?,?,?,?,?,?,?)',(evidence_id,*row,seq))
            for version,data,state,deps,_ in versions:
                p=self._program(data)
                try:pred=p.run(values);matched=type(pred)==type(expected) and pred==expected
                except ValueError:matched=False
                # Repeated descendants of one evidence root never add support.
                used=self.db.execute('SELECT 1 FROM procedure_support WHERE mechanism=? AND context=? AND version=? AND root=?',(mechanism,context,version,root_id)).fetchone()
                if used:continue
                dependencies=json.loads(deps)
                if source_id not in dependencies and len(dependencies)>=8:continue
                if source_id in dependencies and dependencies[source_id]!=trust['version']:
                    self._set_state(mechanism,context,version,'suspended','source_regime_changed',evidence_id);continue
                dependencies[source_id]=trust['version']
                self.db.execute('INSERT INTO procedure_support VALUES(?,?,?,?,?,?,?)',(mechanism,context,version,evidence_id,root_id,'validation',int(matched)))
                self.db.execute('UPDATE procedure_versions SET support=support+?,contradictions=contradictions+?,dependencies=? WHERE mechanism=? AND context=? AND version=?',(int(matched),int(not matched),pack(dependencies),mechanism,context,version))
                if not matched:
                    next_state='suspicious' if state=='active' else 'suspended'
                    event=('active_prediction_mismatch' if state=='active' else
                           'proposal_prediction_mismatch' if state=='proposed' else 'prediction_mismatch')
                    self._set_state(mechanism,context,version,next_state,event,evidence_id)
                elif state=='proposed':
                    independent=self.db.execute("SELECT COUNT(DISTINCT e.inputs) FROM procedure_support s JOIN procedure_evidence e ON e.id=s.evidence_id WHERE s.mechanism=? AND s.context=? AND s.version=? AND s.phase='validation' AND s.matched=1",(mechanism,context,version)).fetchone()[0]
                    minimum=min(self.MIN_VALIDATION,2**len(p.inputs)) if all(t=='bool' for _,t in p.inputs) else self.MIN_VALIDATION
                    if independent>=minimum and all(self._trust(s)['reliability']>=self.TRUST_FLOOR and self._trust(s)['version']==v for s,v in dependencies.items()):
                        self.db.execute("UPDATE procedure_versions SET state='retired' WHERE mechanism=? AND context=? AND state='active'",(mechanism,context))
                        self._set_state(mechanism,context,version,'active','validated',evidence_id)
        self._scopes.add((mechanism,context))
        result={'status':'recorded','evidence_id':evidence_id,'sequence':seq}
        if auto_induce:
            result['auto_induction']=self.auto_induce(
                mechanism,context=context,budget=induction_budget,fit_roots=induction_fit_roots
            )
        return result

    def _set_state(self,mechanism,context,version,state,event,evidence_id=None):
        self.db.execute('UPDATE procedure_versions SET state=? WHERE mechanism=? AND context=? AND version=?',(state,mechanism,context,version))
        self._event(mechanism,context,version,event,evidence_id)

    def training(self,mechanism,*,context='',limit=32):
        self._scope(mechanism,context)
        if type(limit) is not int or not 1<=limit<=64:raise ValueError('training limit out of range')
        rows=self.db.execute('SELECT id,root,source,source_version,inputs,expected,seq FROM procedure_evidence WHERE mechanism=? AND context=? ORDER BY seq DESC LIMIT ?',(mechanism,context,limit)).fetchall()
        return [dict(id=r[0],root=r[1],source=r[2],source_version=r[3],inputs=json.loads(r[4]),expected=json.loads(r[5]),seq=r[6]) for r in reversed(rows)]

    def propose(self,mechanism,program,*,context='',provenance='external',training_ids=None):
        self._scope(mechanism,context);bounded_id(provenance,'provenance')
        if not isinstance(program,Program):program=Program.from_dict(program)
        examples=self.training(mechanism,context=context)
        if training_ids is not None:
            if not isinstance(training_ids,list) or len(training_ids)>64:raise ValueError('invalid training IDs')
            wanted=set(training_ids);examples=[x for x in examples if x['id'] in wanted]
            if {x['id'] for x in examples}!=wanted:raise ValueError('unknown/out-of-window training ID')
        if len({e['root'] for e in examples})<3:raise ValueError('at least three independent fit observations required')
        dependencies={}
        for e in examples:
            pred=program.run(e['inputs'])
            if type(pred)!=type(e['expected']) or pred!=e['expected']:return {'status':'rejected','reason':'training_contradiction'}
            current=self._trust(e['source'])
            if current['version']!=e['source_version']:return {'status':'rejected','reason':'stale_training_source'}
            dependencies[e['source']]=e['source_version']
        if len(dependencies)>8:raise ValueError('dependency capacity exceeded')
        version=self.db.execute('SELECT COALESCE(MAX(version),0)+1 FROM procedure_versions WHERE mechanism=? AND context=?',(mechanism,context)).fetchone()[0]
        if version>self.MAX_VERSIONS:raise RuntimeError('procedure version capacity reached; history retained')
        with self.db:
            self.db.execute('INSERT INTO procedure_versions(mechanism,context,version,program,provenance,created_seq,state,dependencies) VALUES(?,?,?,?,?,?,?,?)',(mechanism,context,version,pack(program.as_dict()),provenance,max(e['seq'] for e in examples),'proposed',pack(dependencies)))
            for e in examples:self.db.execute('INSERT OR IGNORE INTO procedure_support VALUES(?,?,?,?,?,?,?)',(mechanism,context,version,e['id'],e['root'],'fit',1))
            self._event(mechanism,context,version,'proposed')
        return {'status':'proposed','version':version,'program':program.as_dict()}

    def predict(self,mechanism,values,*,context='',compiled=True):
        self._scope(mechanism,context)
        row=self.db.execute("SELECT version,program,support,contradictions,dependencies FROM procedure_versions WHERE mechanism=? AND context=? AND state='active' ORDER BY version DESC LIMIT 1",(mechanism,context)).fetchone()
        if row is None:return {'status':'abstained','reason':'no_validated_active_procedure'}
        version,data,support,contradictions,deps=row
        confidence=(support+1)/(support+contradictions+2)
        for source,expected_version in json.loads(deps).items():
            trust=self._trust(source);confidence=min(confidence,trust['reliability'])
            if trust['version']!=expected_version or trust['reliability']<self.TRUST_FLOOR:
                with self.db:self._set_state(mechanism,context,version,'suspended','dependency_invalidated')
                return {'status':'abstained','reason':'dependency_invalidated','version':version}
        where='inside'
        if self.extrapolation_guard!='off':
            where,outside=self._outside_support(mechanism,context,json.loads(deps),data,values)
            if where!='inside':
                if self.extrapolation_guard=='abstain':
                    return {'status':'abstained','reason':'outside_evidence_support' if where=='outside' else 'evidence_support_unknown','version':version,'outside':outside}
                confidence=min(confidence,self.extrapolation_confidence_cap)
        try:value=self._program(data).run(values,compiled=compiled)
        except ValueError as e:return {'status':'abstained','reason':str(e),'version':version}
        result={'status':'predicted','value':value,'version':version,'confidence':confidence,'support':support,'contradictions':contradictions}
        if self.extrapolation_guard!='off':result['extrapolating']=where!='inside'
        return result

    def _outside_support(self,mechanism,context,sources,data,values):
        """Where a query sits relative to the evidence that backs the active procedure.

        Returns ('inside'|'outside'|'unknown', names). Only integer inputs are checked, each against the [min, max] of that variable
        in the evidence rows from the procedure's dependency sources (at the dependency versions). Bool-only procedures are not
        guarded, and a query inside every range can still be a novel combination or fall in a gap: this is a bounding-box check.
        """
        int_names=[k for k,t in self._program(data).inputs if t=='int']
        if not int_names:return 'inside',[]
        if sources:
            rows=[]
            for source,version in sorted(sources.items()):
                rows+=self.db.execute('SELECT inputs FROM procedure_evidence WHERE mechanism=? AND context=? AND source=? AND source_version=?',(mechanism,context,source,version)).fetchall()
        else:rows=self.db.execute('SELECT inputs FROM procedure_evidence WHERE mechanism=? AND context=?',(mechanism,context)).fetchall()
        lo={};hi={}
        for (raw,) in rows:
            seen=json.loads(raw)
            for n in int_names:
                v=seen.get(n)
                if type(v) is int:
                    lo[n]=v if n not in lo else min(lo[n],v);hi[n]=v if n not in hi else max(hi[n],v)
        if not lo:return 'unknown',[]
        outside=[n for n in int_names if n in values and type(values[n]) is int and (n not in lo or not lo[n]<=values[n]<=hi[n])]
        return ('outside',outside) if outside else ('inside',[])

    def versions(self,mechanism,*,context=''):
        self._scope(mechanism,context)
        names=['version','program','provenance','created_seq','state','support','contradictions','dependencies']
        rows=self.db.execute('SELECT '+','.join(names)+' FROM procedure_versions WHERE mechanism=? AND context=? ORDER BY version',(mechanism,context))
        return [{k:(json.loads(v) if k in ('program','dependencies') else v) for k,v in zip(names,r)} for r in rows]

    def _renamings(self,src,dst):
        """Renamings {family input: target input} under which a family applies: the identity when the inputs are equal;
        with family_mapping='rename', every type-preserving bijection otherwise, positional (sorted) order first."""
        if src==dst:return [{}]
        if self.family_mapping!='rename' or len(src)!=len(dst):return []
        maps=(dict(zip(sorted(src),p)) for p in itertools.permutations(sorted(dst)))
        return [m for m in maps if all(src[k]==dst[v] for k,v in m.items())]

    def _family_candidates(self,input_types,budget,ceiling=0):
        """At most `budget` instantiations (parameters -8..8) of the learned families that apply to this schema: 'listing'
        takes the sources one after another (DEV4's interference), 'round_robin' one instantiation from each in turn. With
        family_mapping='rename' each family and renaming is a source, and the budget grows to 17 proposals (one parameter
        range) per source, up to `ceiling`."""
        streams=[[(f,m,v) for v in itertools.product(range(-8,9),repeat=f['parameters'])]
                 for f in self.families() for m in self._renamings(f['inputs'],input_types)]
        if self.family_mapping=='rename':budget=max(budget,min(ceiling,17*len(streams)))
        order=(itertools.chain.from_iterable(streams) if self.family_sharing=='listing' else
               (x for turn in itertools.zip_longest(*streams) for x in turn if x is not None))
        for f,m,values in itertools.islice(order,budget):
            tag='@'+','.join(f'{k}={v}' for k,v in sorted(m.items())) if m else ''
            tree=self._rename_inputs(f['template'],m) if m else f['template']
            yield Program(dict(input_types),substitute(tree,{f'${i}':v for i,v in enumerate(values)})),'family:'+f['id']+tag

    @staticmethod
    def _rename_inputs(tree,m):
        """Rename input leaves only: an input may share an operator's name (e.g. 'min'), which substitute would rename."""
        if isinstance(tree,tuple):return (tree[0],*(ProcedureCortex._rename_inputs(x,m) for x in tree[1:]))
        return m.get(tree,tree) if isinstance(tree,str) else tree

    def families(self):
        rows=self.db.execute("SELECT mechanism,context,version,program FROM procedure_versions WHERE state='active' ORDER BY mechanism,context,version LIMIT 32").fetchall()
        families={}
        for a,b in itertools.combinations(rows,2):
            pa=self._program(a[3]);pb=self._program(b[3])
            if pa.inputs!=pb.inputs:continue
            result=anti_unify(pa.expression,pb.expression)
            if result:
                tree,n=result;key=pack(tree)
                if key not in families:families[key]={'inputs':dict(pa.inputs),'template':tree,'parameters':n,'parents':[a[:3],b[:3]]}
                if len(families)>=16:break
        result=list(families.values())
        with self.db:
            for family in result:
                family['id']=hashlib.sha256(pack(family).encode()).hexdigest()[:24]
                self.db.execute('INSERT OR IGNORE INTO procedure_families VALUES(?,?,?,?)',
                    (family['id'],pack(family['inputs']),pack(family['template']),pack(family['parents'])))
        return result

    @staticmethod
    def _affine_expression(input_names, coefficients, bias):
        """Build a small canonical integer affine expression."""
        terms=[]
        for name,coef in zip(input_names,coefficients):
            coef=int(coef)
            if coef==0:continue
            if coef==1:term=name
            elif coef==-1:term=('sub',0,name)
            else:term=('mul',coef,name)
            terms.append(term)
        if bias or not terms:terms.append(int(bias))
        expr=terms[0]
        for term in terms[1:]:expr=('add',expr,term)
        return expr

    @staticmethod
    def _solve_affine(examples,input_names,*,coefficient_bound=32):
        """Exact rational solve for y=sum(ai*xi)+b; return integer solution only.

        The solve must be full-rank.  We deliberately refuse underdetermined
        fits instead of choosing arbitrary coefficients that happen to explain
        a tiny evidence sample.
        """
        from fractions import Fraction
        n=len(input_names)+1
        matrix=[]
        for e in examples:
            matrix.append([Fraction(e['inputs'][k]) for k in input_names]+[Fraction(1),Fraction(e['expected'])])
        m=len(matrix);row=0;pivots=[]
        for col in range(n):
            pivot=next((r for r in range(row,m) if matrix[r][col]),None)
            if pivot is None:continue
            matrix[row],matrix[pivot]=matrix[pivot],matrix[row]
            scale=matrix[row][col]
            matrix[row]=[v/scale for v in matrix[row]]
            for r in range(m):
                if r==row or not matrix[r][col]:continue
                scale=matrix[r][col]
                matrix[r]=[a-scale*b for a,b in zip(matrix[r],matrix[row])]
            pivots.append(col);row+=1
            if row==m:break
        # Inconsistent row => no affine rule. Rank<n => insufficient evidence.
        for r in range(m):
            if all(matrix[r][c]==0 for c in range(n)) and matrix[r][n]!=0:return None
        if len(pivots)<n:return None
        solution=[Fraction(0) for _ in range(n)]
        for r,col in enumerate(pivots):solution[col]=matrix[r][n]
        if any(v.denominator!=1 or abs(v.numerator)>coefficient_bound for v in solution):return None
        return [int(v) for v in solution[:-1]],int(solution[-1])

    def _composition_seeds(self,input_types,*,limit=24):
        """Return trusted active procedure expressions remapped onto this schema.

        Only already-active procedures whose source-regime dependencies are
        still current may donate structure.  Donor expressions are inlined;
        the new procedure must still earn its own independent fit/validation
        evidence and therefore never inherits donor authority.
        """
        if type(limit) is not int or not 1<=limit<=64:raise ValueError('invalid composition seed limit')
        names=tuple(sorted(input_types))
        rows=self.db.execute("SELECT mechanism,context,version,program,dependencies FROM procedure_versions WHERE state='active' ORDER BY created_seq DESC LIMIT ?",(limit,)).fetchall()
        out=[];seen=set()
        for mechanism,context,version,data,deps in rows:
            try:
                donor=self._program(data);dependencies=json.loads(deps)
                if any(self._trust(src)['reliability']<self.TRUST_FLOOR or self._trust(src)['version']!=ver for src,ver in dependencies.items()):continue
            except (ValueError,RuntimeError):continue
            donor_inputs=dict(donor.inputs)
            if donor.output_type!='int':continue
            # Exact-name donor can be reused directly.
            if donor_inputs==input_types:
                key=pack(donor.expression)
                if key not in seen:
                    seen.add(key);out.append((donor.expression,f'{mechanism}@{context}:v{version}'))
            # Unary int donors can be applied independently to any int input.
            if len(donor_inputs)==1 and next(iter(donor_inputs.values()))=='int':
                old=next(iter(donor_inputs))
                for new in names:
                    if input_types[new]!='int':continue
                    expr=substitute(donor.expression,{old:new})
                    key=pack(expr)
                    if key in seen:continue
                    try:Program(input_types,expr)
                    except ValueError:continue
                    seen.add(key);out.append((expr,f'{mechanism}@{context}:v{version}->{new}'))
                    if len(out)>=limit:return out
        return out

    def _compose_integer(self,examples,input_types,*,budget=512):
        """Bounded signature-deduplicated compositional synthesis.

        Search is intentionally shallow: variables/constants and validated donor
        structures form the base pool; one binary layer is built, then one more
        layer may combine a discovered structure with a base expression.  This
        learns useful products/min/max/nested compositions without exponential
        unbounded enumeration.
        """
        names=tuple(sorted(input_types));target=tuple(e['expected'] for e in examples)
        bases=[]
        for name in names:bases.append((name,'variable'))
        for expr,origin in self._composition_seeds(input_types):bases.append((expr,'donor:'+origin))
        # Cheap nonlinear primitives are seeded explicitly so useful terms like
        # x^2+y do not spend the entire bounded search rediscovering x*x first.
        for name in names:bases.append((('mul',name,name),'self_square:'+name))
        for c in (-3,-2,-1,0,1,2,3):bases.append((c,'constant'))
        seen_program=set();seen_signature={};tested=0;evaluator_calls=0

        def evaluate(expr,origin):
            nonlocal tested,evaluator_calls
            try:p=Program(input_types,expr)
            except ValueError:return None
            if p.key in seen_program:return None
            seen_program.add(p.key)
            values=[]
            try:
                for e in examples:
                    evaluator_calls+=1;values.append(p.run(e['inputs']))
            except (ValueError,OverflowError):return None
            tested+=1;sig=tuple(values)
            if sig==target:return (p,origin)
            # Keep the smallest representative of each observational signature.
            prior=seen_signature.get(sig)
            if prior is None or p.size<prior[0].size:seen_signature[sig]=(p,origin)
            return False

        base_pool=[]
        for expr,origin in bases:
            if tested>=budget:break
            hit=evaluate(expr,origin)
            if hit:return {'program':hit[0],'origin':'composition:'+hit[1],'candidate_count':tested,'evaluator_calls':evaluator_calls}
            try:p=Program(input_types,expr)
            except ValueError:continue
            base_pool.append((p.expression,origin))
        ops=('add','sub','mul','min','max')
        level1=[]
        for i,(a,oa) in enumerate(base_pool):
            for j,(b,ob) in enumerate(base_pool):
                for op in ops:
                    if tested>=budget:return {'program':None,'origin':None,'candidate_count':tested,'evaluator_calls':evaluator_calls,'budget_exhausted':True}
                    if op in ('add','mul','min','max') and j<i:continue
                    expr=(op,a,b);origin=f'{op}({oa},{ob})'
                    hit=evaluate(expr,origin)
                    if hit:return {'program':hit[0],'origin':'composition:'+hit[1],'candidate_count':tested,'evaluator_calls':evaluator_calls}
                    try:p=Program(input_types,expr)
                    except ValueError:continue
                    # Signature dedup controls the second-layer frontier.
                    try:sig=tuple(p.run(e['inputs']) for e in examples)
                    except (ValueError,OverflowError):continue
                    best=seen_signature.get(sig)
                    if best and best[0].key==p.key:level1.append((p.expression,origin))
                if tested>=budget:break
            if tested>=budget:break
        # Prefer smaller first-layer programs; cap frontier hard.
        uniq=[];keys=set()
        for expr,origin in sorted(level1,key=lambda z: Program(input_types,z[0]).size):
            key=pack(expr)
            if key in keys:continue
            keys.add(key);uniq.append((expr,origin))
            if len(uniq)>=64:break
        for a,oa in uniq:
            for b,ob in base_pool:
                for op in ops:
                    if tested>=budget:return {'program':None,'origin':None,'candidate_count':tested,'evaluator_calls':evaluator_calls,'budget_exhausted':True}
                    expr=(op,a,b);origin=f'{op}({oa},{ob})'
                    hit=evaluate(expr,origin)
                    if hit:return {'program':hit[0],'origin':'composition:'+hit[1],'candidate_count':tested,'evaluator_calls':evaluator_calls}
        return {'program':None,'origin':None,'candidate_count':tested,'evaluator_calls':evaluator_calls,'budget_exhausted':tested>=budget}

    @staticmethod
    def _branch_integer_expression(examples, input_names):
        """Fit one conditional branch conservatively.

        Constant branches require at least two independent examples. Nonconstant
        affine branches require a full-rank system. This refuses one-point leaf
        memorization, which was a major source of spurious conditionals in early
        alpha.7.4 prototypes.
        """
        if len(examples) < 2:
            return None
        outputs=[e['expected'] for e in examples]
        if all(type(v) is int and v==outputs[0] for v in outputs):
            return int(outputs[0])
        if not input_names or len(examples) < len(input_names)+1:
            return None
        solved=ProcedureCortex._solve_affine(examples,input_names)
        if solved is None:
            return None
        coeffs,bias=solved
        return ProcedureCortex._affine_expression(input_names,coeffs,bias)

    @staticmethod
    def _condition_expressions(examples,input_types,*,limit=128):
        """Deterministic bounded pool of simple Boolean predicates."""
        out=[];seen=set()
        def add(expr):
            key=pack(expr)
            if key not in seen and len(out)<limit:
                try:
                    p=Program(input_types,expr)
                except ValueError:
                    return
                if p.output_type=='bool':
                    seen.add(key);out.append(expr)
        bool_names=tuple(sorted(k for k,v in input_types.items() if v=='bool'))
        int_names=tuple(sorted(k for k,v in input_types.items() if v=='int'))
        for name in bool_names:
            add(name);add(('not',name))
        for name in int_names:
            vals=sorted({int(e['inputs'][name]) for e in examples})
            constants={-1,0,1}
            for v in vals:
                constants.add(v)
                if v<10**6:constants.add(v+1)
            # Prefer small/central thresholds first while remaining deterministic.
            ordered=sorted(constants,key=lambda x:(abs(x),x))[:24]
            for c in ordered:
                add(('lt',name,int(c)));add(('eq',name,int(c)))
        for i,a in enumerate(int_names):
            for b in int_names[i+1:]:
                add(('lt',a,b));add(('lt',b,a));add(('eq',a,b))
        return out

    def _boolean_search(self,examples,input_types,*,budget=512,collect=False,max_hypotheses=256):
        """Bounded signature-deduplicated synthesis for Boolean outputs."""
        target=tuple(e['expected'] for e in examples)
        tested=0;evaluator_calls=0;seen_keys=set();representatives={};fits=[]

        def evaluate(expr,origin):
            nonlocal tested,evaluator_calls
            if tested>=budget:return None
            try:p=Program(input_types,expr)
            except ValueError:return None
            if p.output_type!='bool' or p.key in seen_keys:return None
            seen_keys.add(p.key);values=[]
            try:
                for e in examples:
                    evaluator_calls+=1;values.append(p.run(e['inputs']))
            except (ValueError,OverflowError):return None
            tested+=1;sig=tuple(values)
            if sig==target and len(fits)<max_hypotheses:fits.append((p,origin))
            old=representatives.get(sig)
            if old is None or p.size<old[0].size:representatives[sig]=(p,origin)
            return p

        bases=[]
        for name,kind in sorted(input_types.items()):
            if kind=='bool':bases.extend([(name,'bool_var'),(('not',name),'not_var')])
        bases.extend([(True,'bool_const'),(False,'bool_const')])
        for expr in self._condition_expressions(examples,input_types,limit=96):bases.append((expr,'predicate'))
        base_programs=[]
        for expr,origin in bases:
            if tested>=budget:break
            p=evaluate(expr,origin)
            if p is not None:base_programs.append((p.expression,origin))
            if fits and not collect:return {'program':fits[0][0],'origin':fits[0][1],'candidate_count':tested,'evaluator_calls':evaluator_calls}

        # Common compact Boolean forms, including XOR via not(eq()).
        pool=list(base_programs)
        for i,(a,oa) in enumerate(base_programs):
            for j,(b,ob) in enumerate(base_programs):
                if tested>=budget:break
                for op in ('and','or','eq'):
                    if op in ('and','or','eq') and j<i:continue
                    expr=(op,a,b);origin=f'{op}({oa},{ob})'
                    p=evaluate(expr,origin)
                    if fits and not collect:return {'program':fits[0][0],'origin':fits[0][1],'candidate_count':tested,'evaluator_calls':evaluator_calls}
                    if p is not None:pool.append((p.expression,origin))
                    if tested>=budget:break
                    # Negated equality is XOR; negated conjunction/disjunction
                    # also makes NAND/NOR available without a separate opcode.
                    nexpr=('not',expr);norigin='not_'+origin
                    np=evaluate(nexpr,norigin)
                    if fits and not collect:return {'program':fits[0][0],'origin':fits[0][1],'candidate_count':tested,'evaluator_calls':evaluator_calls}
                    if np is not None:pool.append((np.expression,norigin))
                if tested>=budget:break
            if tested>=budget:break

        # Direct 3-input majority is useful enough to include as one bounded
        # structural bias instead of requiring a deep brute-force search.
        bool_vars=[k for k,v in sorted(input_types.items()) if v=='bool']
        if len(bool_vars)>=3 and tested<budget:
            for a,b,c in itertools.combinations(bool_vars,3):
                expr=('or',('or',('and',a,b),('and',a,c)),('and',b,c))
                evaluate(expr,'majority3')
                if fits and not collect:return {'program':fits[0][0],'origin':fits[0][1],'candidate_count':tested,'evaluator_calls':evaluator_calls}
                if tested>=budget:break

        # One more shallow layer over signature representatives. This is bounded
        # and heavily compressed by observational signatures.
        frontier=[(p.expression,o) for p,o in sorted(representatives.values(),key=lambda z:z[0].size)[:48]]
        for a,oa in frontier:
            for b,ob in base_programs[:24]:
                for op in ('and','or','eq'):
                    if tested>=budget:break
                    evaluate((op,a,b),f'{op}({oa},{ob})')
                    if fits and not collect:return {'program':fits[0][0],'origin':fits[0][1],'candidate_count':tested,'evaluator_calls':evaluator_calls}
                if tested>=budget:break
            if tested>=budget:break
        return {'program':fits[0][0] if fits else None,'origin':fits[0][1] if fits else None,
                'hypotheses':[p for p,_ in fits],'candidate_count':tested,'evaluator_calls':evaluator_calls,
                'budget_exhausted':tested>=budget}

    def _conditional_integer_search(self,examples,input_types,*,budget=512,collect=False,max_hypotheses=256):
        """Fit simple piecewise-affine integer procedures behind Boolean gates."""
        tested=0;evaluator_calls=0;fits=[];seen=set()
        int_names=tuple(sorted(k for k,v in input_types.items() if v=='int'))
        conditions=self._condition_expressions(examples,input_types,limit=min(128,budget))
        for cond in conditions:
            if tested>=budget:break
            try:cp=Program(input_types,cond)
            except ValueError:continue
            left=[];right=[]
            try:
                for e in examples:(left if cp.run(e['inputs']) else right).append(e)
            except (ValueError,OverflowError):continue
            if len(left)<2 or len(right)<2:continue
            yes=self._branch_integer_expression(left,int_names);no=self._branch_integer_expression(right,int_names)
            if yes is None or no is None:continue
            expr=('if',cond,yes,no)
            try:p=Program(input_types,expr)
            except ValueError:continue
            if p.key in seen:continue
            seen.add(p.key);tested+=1;ok=True
            try:
                for e in examples:
                    evaluator_calls+=1
                    if p.run(e['inputs'])!=e['expected']:ok=False;break
            except (ValueError,OverflowError):ok=False
            if ok:
                fits.append((p,'conditional'))
                if not collect:return {'program':p,'origin':'conditional','candidate_count':tested,'evaluator_calls':evaluator_calls}
                if len(fits)>=max_hypotheses:break
        return {'program':fits[0][0] if fits else None,'origin':fits[0][1] if fits else None,
                'hypotheses':[p for p,_ in fits],'candidate_count':tested,'evaluator_calls':evaluator_calls,
                'budget_exhausted':tested>=budget}

    @staticmethod
    def _query_pool(examples,input_types,*,limit=128):
        """Generate a finite hypothetical input pool; this never queries the world."""
        names=tuple(sorted(input_types));choices=[]
        for name in names:
            if input_types[name]=='bool':vals=[False,True]
            else:
                observed=sorted({int(e['inputs'][name]) for e in examples})
                vals=[]
                # Information gathering should first probe around the evidence
                # frontier, not around arbitrary global constants. Otherwise a
                # threshold near -100 could look falsely resolved because the
                # query pool only explored values near zero.
                anchors=[]
                for v in observed:anchors.extend((v-1,v,v+1))
                for a,b in zip(observed,observed[1:]):
                    if b-a>1:anchors.extend(((a+b)//2,(a+b+1)//2))
                anchors.extend((-2,-1,0,1,2))
                for z in anchors:
                    if abs(z)<=10**6 and z not in vals:vals.append(z)
                vals=vals[:18]
            choices.append(vals)
        out=[];seen=set()
        for combo in itertools.product(*choices):
            row=dict(zip(names,combo));key=pack(row)
            if key in seen:continue
            seen.add(key);out.append(row)
            if len(out)>=limit:break
        return out

    def _query_from_programs(self,programs,examples,input_types,*,candidate_inputs=None):
        """Choose a read-only discriminating input from competitive hypotheses.

        A tiny MDL preference removes gratuitously complex exception rules from
        the disagreement set while still keeping near-simple alternatives such
        as OR versus XOR. This prevents information gathering from chasing
        arbitrary one-off exceptions indefinitely.
        """
        if len(programs)<2:return None
        minimum=min(p.size for p in programs)
        competitive=[p for p in programs if p.size<=minimum+2][:256]
        if len(competitive)<2:return None
        pool=self._query_pool(examples,input_types) if candidate_inputs is None else candidate_inputs
        if not isinstance(pool,list) or not 1<=len(pool)<=256:raise ValueError('candidate input pool must contain 1-256 rows')
        validated=[];schema=dict(input_types)
        probe=Program(schema,next(iter(schema)))
        for row in pool:
            probe.validate_inputs(row);validated.append(dict(row))
        observed={pack(e['inputs']) for e in examples}
        novel=[row for row in validated if pack(row) not in observed]
        if novel:validated=novel
        q=choose_experiment(competitive,validated,strategy='disagreement')
        if q is None:return None
        predictions={}
        for p in competitive:
            value=p.run(q['input']);predictions[pack(value)]=predictions.get(pack(value),0)+1
        return {'status':'query_suggested','input':q['input'],'score':q['score'],
                'distinct_predictions':q['distinct_predictions'],'prediction_groups':predictions,
                'hypotheses':len(competitive),'total_fit_hypotheses':len(programs),'read_only':True}

    def _information_from_examples(self,examples,input_types,expected_type,*,candidate_inputs=None,budget=256):
        if len(examples)<3:return {'status':'unresolved','reason':'insufficient_evidence_for_hypothesis_disagreement'}
        if expected_type=='bool':search=self._boolean_search(examples,input_types,budget=budget,collect=True)
        elif expected_type=='int':search=self._conditional_integer_search(examples,input_types,budget=budget,collect=True)
        else:return {'status':'unsupported','reason':'unsupported_output_type'}
        programs=search.get('hypotheses',[])
        if len(programs)<2:return {'status':'unresolved','reason':'fewer_than_two_plausible_hypotheses','hypotheses':len(programs),'candidate_count':search.get('candidate_count',0)}
        q=self._query_from_programs(programs,examples,input_types,candidate_inputs=candidate_inputs)
        if q is None:return {'status':'unresolved','reason':'hypotheses_do_not_disagree_on_pool','hypotheses':len(programs),'candidate_count':search.get('candidate_count',0)}
        q.update(candidate_count=search.get('candidate_count',0),evaluator_calls=search.get('evaluator_calls',0))
        return q

    def information_query(self,mechanism,*,context='',candidate_inputs=None,budget=256):
        """Suggest one observation that best separates current procedure hypotheses.

        The method is read-only: it neither performs the observation nor writes
        evidence, beliefs, procedure support, or source calibration.
        """
        self._scope(mechanism,context)
        if type(budget) is not int or not 1<=budget<=512:raise ValueError('invalid information-query budget')
        boundary=self._auto_boundary_seq(mechanism,context)
        rows=self.training(mechanism,context=context,limit=64)
        if boundary:rows=[r for r in rows if r['seq']>=boundary]
        examples=[];roots=set()
        for row in reversed(rows):
            if row['root'] in roots:continue
            try:trust=self._trust(row['source'])
            except (ValueError,RuntimeError):continue
            if trust['reliability']<self.TRUST_FLOOR or trust['version']!=row['source_version']:continue
            roots.add(row['root']);examples.append(row)
            if len(examples)>=16:break
        examples.reverse()
        if len(examples)<3:return {'status':'unresolved','reason':'insufficient_trusted_independent_evidence','roots':len(examples),'read_only':True}
        schemas=[{k:'bool' if type(v) is bool else 'int' for k,v in e['inputs'].items()} for e in examples]
        input_types=schemas[0];expected_type='bool' if type(examples[0]['expected']) is bool else 'int'
        if any(x!=input_types for x in schemas) or any(('bool' if type(e['expected']) is bool else 'int')!=expected_type for e in examples):
            return {'status':'unsupported','reason':'mixed procedure schemas are not queried','read_only':True}
        result=self._information_from_examples(examples,input_types,expected_type,candidate_inputs=candidate_inputs,budget=budget)
        result['read_only']=True;result['boundary_seq']=boundary
        return result

    def induce(self,mechanism,*,context='',use_families=True,budget=512,training_ids=None):
        if type(budget) is not int or not 1<=budget<=512:raise ValueError('invalid induction budget')
        examples=self.training(mechanism,context=context,limit=64)
        selected_ids=None
        if training_ids is not None:
            if not isinstance(training_ids,list) or not 3<=len(training_ids)<=16 or len(set(training_ids))!=len(training_ids):
                raise ValueError('invalid induction training IDs')
            wanted=set(training_ids);examples=[x for x in examples if x['id'] in wanted]
            if {x['id'] for x in examples}!=wanted:raise ValueError('unknown/out-of-window induction training ID')
            selected_ids=list(training_ids)
        if len({e['root'] for e in examples})<3:raise ValueError('more independent fit evidence required')
        if not examples:return {'status':'unresolved','candidate_count':0,'evaluator_calls':0,'budget':budget}
        schemas=[{k:'bool' if type(v) is bool else 'int' for k,v in e['inputs'].items()} for e in examples]
        input_types=schemas[0]
        expected_type='bool' if type(examples[0]['expected']) is bool else 'int'
        if any(schema!=input_types for schema in schemas) or any(('bool' if type(e['expected']) is bool else 'int')!=expected_type for e in examples):
            return {'status':'unsupported','reason':'mixed procedure schemas are not synthesized'}

        # Alpha.7.4: Boolean procedures are synthesized by a bounded typed
        # search. They are still only hypotheses until held-out validation.
        if expected_type=='bool':
            found=self._boolean_search(examples,input_types,budget=budget,collect=True)
            programs=found.get('hypotheses',[])
            if programs:
                q=self._query_from_programs(programs,examples,input_types)
                if q is not None:
                    q.update(candidate_count=found.get('candidate_count',0),evaluator_calls=found.get('evaluator_calls',0))
                    return {'status':'needs_information','information_query':q,'candidate_count':found.get('candidate_count',0),
                            'evaluator_calls':found.get('evaluator_calls',0),'budget':budget}
                program=programs[0];origin=found.get('origin') or 'equivalent_boolean_hypothesis'
                result=self.propose(mechanism,program,context=context,provenance='asm_induction:boolean:'+origin,training_ids=selected_ids)
                result.update(origin='boolean:'+origin,candidate_count=found.get('candidate_count',0),
                              evaluator_calls=found.get('evaluator_calls',0),budget_exhausted=found.get('budget_exhausted',False));return result
            return {'status':'unresolved','candidate_count':found.get('candidate_count',0),
                    'evaluator_calls':found.get('evaluator_calls',0),'budget':budget,
                    'budget_exhausted':found.get('budget_exhausted',False)}

        # Preserve alpha.7.2 unary integer grammar exactly for backward compatibility.
        if input_types=={'x':'int'} and expected_type=='int':
            def candidates():
                yield Program({'x':'int'},'x'),'grammar'
                yield Program({'x':'int'},('mul','x','x')),'grammar'
                family_budget=min(64,max(0,budget-291))
                if use_families and family_budget:yield from self._family_candidates({'x':'int'},family_budget,max(0,budget-291))
                for a in range(-8,9):
                    for b in range(-8,9):yield Program({'x':'int'},('add',('mul',a,'x'),b)),'grammar'
            seen=set();evaluations=0;count=0
            for program,origin in candidates():
                if program.key in seen:continue
                seen.add(program.key);count+=1
                valid=True
                for e in examples:
                    evaluations+=1
                    if program.run(e['inputs'])!=e['expected']:valid=False;break
                if valid:
                    result=self.propose(mechanism,program,context=context,provenance='asm_induction:'+origin,training_ids=selected_ids)
                    result.update(candidate_count=count,evaluator_calls=evaluations,origin=origin);return result
                if count>=budget:break
            remaining=max(1,budget-count)
            conditional=self._conditional_integer_search(examples,input_types,budget=remaining,collect=True)
            total=count+conditional.get('candidate_count',0)
            total_evals=evaluations+conditional.get('evaluator_calls',0)
            programs=conditional.get('hypotheses',[])
            if programs:
                q=self._query_from_programs(programs,examples,input_types)
                if q is not None:
                    q.update(candidate_count=total,evaluator_calls=total_evals)
                    return {'status':'needs_information','information_query':q,'candidate_count':total,
                            'evaluator_calls':total_evals,'budget':budget}
                program=programs[0];origin=conditional.get('origin') or 'conditional'
                result=self.propose(mechanism,program,context=context,provenance='asm_induction:'+origin,training_ids=selected_ids)
                result.update(origin=origin,candidate_count=total,evaluator_calls=total_evals,
                              budget_exhausted=total>=budget);return result
            return {'status':'unresolved','candidate_count':total,'evaluator_calls':total_evals,'budget':budget,
                    'budget_exhausted':total>=budget}

        # Alpha.7.3/7.4: bounded multi-input integer synthesis. Mixed
        # bool/int schemas are allowed only through explicit conditionals.
        if expected_type!='int' or not 1<=len(input_types)<=4 or any(t not in ('int','bool') for t in input_types.values()):
            return {'status':'unsupported','reason':'built-in synthesis supports bool/int outputs over 1-4 typed inputs'}
        all_int=all(t=='int' for t in input_types.values())
        names=tuple(sorted(k for k,v in input_types.items() if v=='int'))
        fam_count=fam_evals=0
        if all_int and len(input_types)>=2 and use_families and self.family_scope=='any_int':
            # DEV22: learned families with this input schema first (as for one-input targets), inside the same
            # budget; three fit points almost always admit an exact integer affine fit, which would pre-empt them
            for program,origin in self._family_candidates(input_types,min(64,budget),budget//2):
                fam_count+=1
                try:
                    for e in examples:
                        fam_evals+=1
                        if program.run(e['inputs'])!=e['expected']:break
                    else:
                        result=self.propose(mechanism,program,context=context,provenance='asm_induction:'+origin,training_ids=selected_ids)
                        result.update(candidate_count=fam_count,evaluator_calls=fam_evals,origin=origin);return result
                except (ValueError,OverflowError):pass
        if all_int and len(input_types)>=2:
            affine=self._solve_affine(examples,names)
            if affine is not None:
                coeffs,bias=affine
                program=Program(input_types,self._affine_expression(names,coeffs,bias))
                if all(program.run(e['inputs'])==e['expected'] for e in examples):
                    result=self.propose(mechanism,program,context=context,provenance='asm_induction:multi_affine',training_ids=selected_ids)
                    result.update(candidate_count=1+fam_count,evaluator_calls=len(examples)+fam_evals,origin='multi_affine');return result

        # Test a small conditional gate pool before general composition. The
        # remaining budget stays available to alpha.7.3's integer composer.
        conditional_budget=min(budget,128 if all_int else budget)
        conditional=self._conditional_integer_search(examples,input_types,budget=conditional_budget,collect=True)
        if fam_count:  # DEV22: the family proposals' cost is part of this search's cost
            conditional['candidate_count']=conditional.get('candidate_count',0)+fam_count
            conditional['evaluator_calls']=conditional.get('evaluator_calls',0)+fam_evals
        conditional_programs=conditional.get('hypotheses',[])
        if conditional_programs:
            q=self._query_from_programs(conditional_programs,examples,input_types)
            if q is not None:
                q.update(candidate_count=conditional.get('candidate_count',0),evaluator_calls=conditional.get('evaluator_calls',0))
                return {'status':'needs_information','information_query':q,
                        'candidate_count':conditional.get('candidate_count',0),
                        'evaluator_calls':conditional.get('evaluator_calls',0),'budget':budget}
            program=conditional_programs[0];origin=conditional.get('origin') or 'conditional'
            result=self.propose(mechanism,program,context=context,provenance='asm_induction:'+origin,training_ids=selected_ids)
            result.update(origin=origin,candidate_count=conditional.get('candidate_count',0),
                          evaluator_calls=conditional.get('evaluator_calls',0),
                          budget_exhausted=conditional.get('budget_exhausted',False));return result
        if not all_int:
            return {'status':'unresolved','candidate_count':conditional.get('candidate_count',0),
                    'evaluator_calls':conditional.get('evaluator_calls',0),'budget':budget,
                    'budget_exhausted':conditional.get('budget_exhausted',False)}

        spent=min(budget,conditional.get('candidate_count',0))
        remaining=max(1,budget-spent)
        composed=self._compose_integer(examples,input_types,budget=remaining)
        total_candidates=spent+composed.get('candidate_count',0)
        total_evals=conditional.get('evaluator_calls',0)+composed.get('evaluator_calls',0)
        if composed.get('program') is not None:
            program=composed.pop('program');origin=composed.pop('origin')
            result=self.propose(mechanism,program,context=context,provenance='asm_induction:'+origin,training_ids=selected_ids)
            result.update(origin=origin,candidate_count=total_candidates,evaluator_calls=total_evals,
                          budget_exhausted=total_candidates>=budget);return result
        return {'status':'unresolved','candidate_count':total_candidates,
                'evaluator_calls':total_evals,'budget':budget,
                'budget_exhausted':total_candidates>=budget}

    def _auto_boundary_seq(self,mechanism,context):
        """Return the beginning of the newest procedure regime candidate.

        Only the first mismatch of an active/proposed hypothesis becomes a
        boundary. Repeated failures of an already-suspicious version do not keep
        moving the boundary forward, allowing fresh evidence to accumulate.
        """
        row=self.db.execute('''
            SELECT MAX(e.seq)
            FROM procedure_audit a
            JOIN procedure_evidence e ON e.id=a.evidence_id
            WHERE a.mechanism=? AND a.context=?
              AND a.event IN ('active_prediction_mismatch','proposal_prediction_mismatch','source_regime_changed')
        ''',(mechanism,context)).fetchone()
        return int(row[0] or 0)

    def _trusted_recent_fit(self,mechanism,*,context='',fit_roots=3):
        if type(fit_roots) is not int or not 3<=fit_roots<=16:raise ValueError('invalid induction fit root count')
        boundary=self._auto_boundary_seq(mechanism,context)
        rows=self.training(mechanism,context=context,limit=64)
        if boundary:
            rows=[r for r in rows if r['seq']>=boundary]
        chosen=[];seen=set()
        for row in reversed(rows):
            if row['root'] in seen:continue
            try:trust=self._trust(row['source'])
            except (ValueError,RuntimeError):continue
            if trust['reliability']<self.TRUST_FLOOR or trust['version']!=row['source_version']:continue
            seen.add(row['root']);chosen.append(row)
            if len(chosen)>=fit_roots:break
        chosen.reverse()
        return chosen,boundary

    def _remember_auto_attempt(self,mechanism,context,examples,status):
        signature=hashlib.sha256(pack([
            (e['id'],e['root'],e['source'],e['source_version'],e['inputs'],e['expected']) for e in examples
        ]).encode()).hexdigest()
        last_seq=max((e['seq'] for e in examples),default=0)
        with self.db:
            self.db.execute('''
                INSERT INTO procedure_auto_state(mechanism,context,last_attempt_seq,last_signature,last_status,attempts)
                VALUES(?,?,?,?,?,1)
                ON CONFLICT(mechanism,context) DO UPDATE SET
                    last_attempt_seq=excluded.last_attempt_seq,
                    last_signature=excluded.last_signature,
                    last_status=excluded.last_status,
                    attempts=procedure_auto_state.attempts+1
            ''',(mechanism,context,last_seq,signature,str(status)))
        return signature

    def auto_induce(self,mechanism,*,context='',budget=512,fit_roots=3,use_families=True):
        """Bounded autonomous induction from externally resolved experience.

        This never invents labels and never promotes directly to active. It only
        proposes a hypothesis after >=3 independent, currently trusted roots.
        Later held-out observations must still validate it through ``observe``.
        """
        self._scope(mechanism,context)
        if type(budget) is not int or not 1<=budget<=512:raise ValueError('invalid induction budget')
        active=self.db.execute("SELECT version FROM procedure_versions WHERE mechanism=? AND context=? AND state='active' ORDER BY version DESC LIMIT 1",(mechanism,context)).fetchone()
        if active:return {'status':'stable','reason':'active_procedure_exists','version':active[0]}
        proposed=self.db.execute("SELECT version FROM procedure_versions WHERE mechanism=? AND context=? AND state='proposed' ORDER BY version DESC LIMIT 1",(mechanism,context)).fetchone()
        if proposed:return {'status':'validating','reason':'heldout_validation_required','version':proposed[0]}
        # Multi-input hypotheses need enough independent equations to avoid
        # arbitrary underdetermined affine fits. Unary behavior stays at 3.
        recent=self.training(mechanism,context=context,limit=1)
        required=fit_roots
        prior_auto=self.db.execute('SELECT last_status,last_attempt_seq FROM procedure_auto_state WHERE mechanism=? AND context=?',(mechanism,context)).fetchone()
        if recent:
            arity=len(recent[-1]['inputs'])
            # Multi-input synthesis gets one extra independent root beyond the
            # minimum affine equation count. This reduces spurious nonlinear
            # fits while unary alpha.7.2 behavior remains exactly three roots.
            required=max(required,min(16,arity+1+(1 if arity>1 else 0)))
            base_required=required
            # If the compact alpha.7.2/7.3 grammar already failed on this
            # regime, gather enough roots for a conservative two-branch
            # conditional instead of repeatedly fitting only the latest small
            # window. The first legacy induction attempt is unchanged.
            if prior_auto and prior_auto[0]=='unresolved' and type(recent[-1]['expected']) is int:
                schema={k:'bool' if type(v) is bool else 'int' for k,v in recent[-1]['inputs'].items()}
                n_int=sum(v=='int' for v in schema.values())
                conditional_required=max(4,2*(n_int+1)) if n_int else 4
                required=max(required,min(16,conditional_required))
        if not recent:base_required=required
        available,boundary=self._trusted_recent_fit(mechanism,context=context,fit_roots=16)
        # Before learning a replacement, give an older validated structure a
        # fair chance on clean post-boundary evidence. This preserves the
        # alpha.7.2 single-outlier recovery contract without letting the
        # mismatch that opened the boundary vote against revalidation.
        if boundary:
            fresh_for_revalidation=[e for e in available if e['seq']>boundary]
            if len(fresh_for_revalidation)>=base_required:
                reval_examples=fresh_for_revalidation[-base_required:]
                reval_ids=[e['id'] for e in reval_examples]
                for version in reversed(self.versions(mechanism,context=context)):
                    if version['state'] in ('active','proposed'):continue
                    program=Program.from_dict(version['program'])
                    try:fits=all(type(program.run(e['inputs']))==type(e['expected']) and program.run(e['inputs'])==e['expected'] for e in reval_examples)
                    except ValueError:fits=False
                    if fits:
                        try:
                            result=self.propose(mechanism,program,context=context,
                                provenance=f"asm_auto_revalidation:version{version['version']}",training_ids=reval_ids)
                        except RuntimeError as exc:
                            result={'status':'blocked','reason':str(exc)}
                        self._remember_auto_attempt(mechanism,context,reval_examples,result['status'])
                        result.update(automatic=True,mode='revalidation',fit_evidence_ids=reval_ids,boundary_seq=boundary)
                        return result
        # Once enough post-boundary evidence exists, stop treating the mismatch
        # observation that *created* the boundary as training data for the new
        # regime. This preserves alpha.7.2 single-outlier recovery while still
        # allowing that first mismatch to bootstrap collection when evidence is
        # otherwise scarce.
        if boundary:
            fresh=[e for e in available if e['seq']>boundary]
            if len(fresh)>=required:available=fresh
        if len(available)<required:
            examples=available
            out={'status':'collecting','trusted_independent_roots':len(examples),'required':required,'boundary_seq':boundary}
            if len(examples)>=3:
                schemas=[{k:'bool' if type(v) is bool else 'int' for k,v in e['inputs'].items()} for e in examples]
                input_types=schemas[0];expected_type='bool' if type(examples[0]['expected']) is bool else 'int'
                if all(x==input_types for x in schemas) and all(('bool' if type(e['expected']) is bool else 'int')==expected_type for e in examples):
                    try:q=self._information_from_examples(examples,input_types,expected_type,budget=min(256,budget))
                    except ValueError:q={'status':'unresolved'}
                    if q.get('status')=='query_suggested':out['information_query']=q
            return out
        # After an ambiguity/unresolved result, retain all trusted roots in the
        # bounded 16-example window so the requested answer actually narrows the
        # hypothesis set instead of being dropped by a fixed-size sliding fit.
        examples=available if prior_auto and prior_auto[0] in ('needs_information','unresolved') else available[-required:]
        signature=hashlib.sha256(pack([
            (e['id'],e['root'],e['source'],e['source_version'],e['inputs'],e['expected']) for e in examples
        ]).encode()).hexdigest()
        prior=self.db.execute('SELECT last_signature,last_status,attempts FROM procedure_auto_state WHERE mechanism=? AND context=?',(mechanism,context)).fetchone()
        if prior and prior[0]==signature:
            return {'status':'unchanged','reason':'same_evidence_already_attempted','previous_status':prior[1],'attempts':prior[2]}
        ids=[e['id'] for e in examples]
        for version in reversed(self.versions(mechanism,context=context)):
            if version['state'] in ('active','proposed'):continue
            program=Program.from_dict(version['program'])
            try:fits=all(type(program.run(e['inputs']))==type(e['expected']) and program.run(e['inputs'])==e['expected'] for e in examples)
            except ValueError:fits=False
            if fits:
                try:
                    result=self.propose(mechanism,program,context=context,
                        provenance=f"asm_auto_revalidation:version{version['version']}",training_ids=ids)
                except RuntimeError as exc:
                    result={'status':'blocked','reason':str(exc)}
                self._remember_auto_attempt(mechanism,context,examples,result['status'])
                result.update(automatic=True,mode='revalidation',fit_evidence_ids=ids,boundary_seq=boundary)
                return result
        try:
            result=self.induce(mechanism,context=context,use_families=use_families,budget=budget,training_ids=ids)
        except ValueError as exc:
            result={'status':'unsupported','reason':str(exc)}
        except RuntimeError as exc:
            result={'status':'blocked','reason':str(exc)}
        self._remember_auto_attempt(mechanism,context,examples,result['status'])
        result.update(automatic=True,mode='induction',fit_evidence_ids=ids,boundary_seq=boundary)
        if result.get('status')=='unresolved':
            schemas=[{k:'bool' if type(v) is bool else 'int' for k,v in e['inputs'].items()} for e in examples]
            input_types=schemas[0];expected_type='bool' if type(examples[0]['expected']) is bool else 'int'
            if all(x==input_types for x in schemas):
                try:q=self._information_from_examples(examples,input_types,expected_type,budget=min(256,budget))
                except ValueError:q={'status':'unresolved'}
                if q.get('status')=='query_suggested':result['information_query']=q
        return result

    def auto_status(self,mechanism,*,context=''):
        self._scope(mechanism,context)
        row=self.db.execute('SELECT last_attempt_seq,last_signature,last_status,attempts FROM procedure_auto_state WHERE mechanism=? AND context=?',(mechanism,context)).fetchone()
        if row is None:return {'attempts':0,'last_attempt_seq':0,'last_status':None}
        return {'last_attempt_seq':row[0],'last_signature':row[1],'last_status':row[2],'attempts':row[3]}

    def reconsider(self, mechanism, *, context=""):
        """Reopen an old expression as a NEW hypothesis, never as trusted truth."""
        examples = self.training(mechanism, context=context, limit=3)
        if len({e['root'] for e in examples}) < 3:
            return {'status': 'unresolved', 'reason': 'insufficient_independent_recent_evidence'}
        for version in reversed(self.versions(mechanism, context=context)):
            if version['state'] == 'active':
                continue
            program = Program.from_dict(version['program'])
            try:
                fits = all(type(program.run(e['inputs'])) == type(e['expected']) and program.run(e['inputs']) == e['expected'] for e in examples)
            except ValueError:
                fits = False
            if fits:
                return self.propose(mechanism, program, context=context,
                    provenance=f"asm_revalidation:version{version['version']}",
                    training_ids=[e['id'] for e in examples])
        return {'status': 'unresolved', 'reason': 'no_old_version_fits_recent_evidence'}

    # --- alpha.7.5-parallel WIP: evidence-aware contextual procedure routing ---
    ROUTE_MAX_EVIDENCE = 2048
    ROUTE_MAX_CONTEXTS = 32
    ROUTE_MAX_FEATURES = 16
    ROUTE_MIN_SUPPORT = 3

    @classmethod
    def _route_features(cls, values):
        if not isinstance(values, dict) or not 0 <= len(values) <= cls.ROUTE_MAX_FEATURES:
            raise ValueError('route features must be a mapping with <=16 entries')
        out = {}
        for key, value in values.items():
            if not isinstance(key, str) or not key.isidentifier() or len(key) > 32:
                raise ValueError('invalid route feature name')
            if type(value) is bool:
                out[key] = value
            elif type(value) is int:
                if abs(value) > 10**6:
                    raise ValueError('route integer feature bound exceeded')
                out[key] = value
            elif isinstance(value, str):
                if not value or len(value) > 64:
                    raise ValueError('invalid route string feature')
                out[key] = value
            else:
                raise ValueError('route features support bool/int/string values only')
        return out

    def _active_route_contexts(self, mechanism):
        rows = self.db.execute(
            "SELECT DISTINCT context FROM procedure_versions WHERE mechanism=? AND state='active' ORDER BY context",
            (mechanism,),
        ).fetchall()
        return [r[0] for r in rows][:self.ROUTE_MAX_CONTEXTS]

    def observe_route(self, mechanism, features, target_context, *, evidence_id, source_id, root_id=None, temporal_index=None):
        """Learn one externally resolved context->procedure applicability datum.

        Routing evidence is deliberately separate from procedure correctness.
        Only currently trusted external sources may add applicability evidence,
        and duplicate ancestry roots never multiply support.
        """
        self._scope(mechanism, target_context)
        bounded_id(evidence_id); bounded_id(source_id)
        root_id = evidence_id if root_id is None else bounded_id(root_id, 'root_id')
        features = self._route_features(features)
        if temporal_index is not None:
            import math
            if type(temporal_index) is bool or type(temporal_index) not in (int,float) or not math.isfinite(float(temporal_index)):
                raise ValueError('temporal_index must be a finite number')
            temporal_index=float(temporal_index)
            previous=self.db.execute('SELECT MAX(temporal_index) FROM procedure_route_evidence WHERE mechanism=? AND temporal_index IS NOT NULL',(mechanism,)).fetchone()[0]
            if previous is not None and temporal_index<=float(previous):
                raise ValueError('temporal_index must increase strictly for a routing mechanism')
        active = self.db.execute(
            "SELECT version FROM procedure_versions WHERE mechanism=? AND context=? AND state='active' ORDER BY version DESC LIMIT 1",
            (mechanism, target_context),
        ).fetchone()
        if active is None:
            return {'status':'blocked','reason':'target_context_has_no_active_procedure','target_context':target_context}
        trust = self._trust(source_id)
        if trust['reliability'] < self.TRUST_FLOOR:
            return {'status':'blocked','reason':'routing_source_below_trust_floor','reliability':trust['reliability']}
        row = self.db.execute(
            'SELECT mechanism,root,source,source_version,features,target_context,temporal_index FROM procedure_route_evidence WHERE id=?',
            (evidence_id,),
        ).fetchone()
        expected = (mechanism, root_id, source_id, trust['version'], pack(features), target_context, temporal_index)
        if row is not None:
            if row != expected:
                raise ValueError('conflicting route evidence ID')
            return {'status':'duplicate','evidence_id':evidence_id}
        if self.db.execute(
            'SELECT 1 FROM procedure_route_evidence WHERE mechanism=? AND root=?', (mechanism, root_id)
        ).fetchone():
            return {'status':'duplicate_root','root_id':root_id}
        count = self.db.execute('SELECT COUNT(*) FROM procedure_route_evidence').fetchone()[0]
        if count >= self.ROUTE_MAX_EVIDENCE:
            raise RuntimeError('procedure routing evidence capacity reached')
        with self.db:
            self.db.execute(
                'INSERT INTO procedure_route_evidence(id,mechanism,root,source,source_version,features,target_context,temporal_index) VALUES(?,?,?,?,?,?,?,?)',
                (evidence_id, mechanism, root_id, source_id, trust['version'], pack(features), target_context, temporal_index),
            )
            seq = self.db.execute('SELECT seq FROM procedure_route_evidence WHERE id=?',(evidence_id,)).fetchone()[0]
        return {'status':'recorded','sequence':seq,'target_context':target_context,'procedure_version':active[0]}

    def _effective_route_rows(self, mechanism, *, limit=512):
        if type(limit) is not int or not 1 <= limit <= 2048:
            raise ValueError('invalid route evidence limit')
        rows = self.db.execute(
            'SELECT root,source,source_version,features,target_context,seq,temporal_index FROM procedure_route_evidence '
            'WHERE mechanism=? ORDER BY seq DESC LIMIT ?', (mechanism, limit)
        ).fetchall()
        out=[]; seen=set(); trust_cache={}
        for root, source, source_version, features, context, seq, temporal_index in rows:
            if root in seen: continue
            seen.add(root)
            try:
                if source not in trust_cache: trust_cache[source]=self._trust(source)
                trust=trust_cache[source]
            except (ValueError,RuntimeError): continue
            if trust['reliability'] < self.TRUST_FLOOR or trust['version'] != source_version:
                continue
            try: parsed=json.loads(features)
            except Exception: continue
            if not isinstance(parsed,dict): continue
            out.append({'root':root,'source':source,'source_version':source_version,
                        'reliability':float(trust['reliability']),
                        'features':parsed,'context':context,'seq':seq,'temporal_index':temporal_index})
        out.reverse()
        return out

    @staticmethod
    def _entropy(distribution):
        import math
        return -sum(p*math.log2(p) for p in distribution if p>0)

    @staticmethod
    def _route_solve_linear(matrix, rhs):
        """Bounded dense solve for tiny routing covariance components.

        Returns ``None`` instead of regularizing or inventing confidence when
        the system is singular/ill-conditioned.  alpha.7.7 intentionally
        falls back to alpha.7.6 local graph weights in those cases.
        """
        import math
        n=len(rhs)
        if n<1 or len(matrix)!=n or any(len(row)!=n for row in matrix):
            return None
        a=[[float(matrix[i][j]) for j in range(n)]+[float(rhs[i])] for i in range(n)]
        scale=max(1.0,max(abs(v) for row in matrix for v in row))
        pivot_floor=1e-12*scale
        for col in range(n):
            pivot=max(range(col,n),key=lambda r:abs(a[r][col]))
            if not math.isfinite(a[pivot][col]) or abs(a[pivot][col])<=pivot_floor:
                return None
            if pivot!=col:a[col],a[pivot]=a[pivot],a[col]
            pv=a[col][col]
            for j in range(col,n+1):a[col][j]/=pv
            for r in range(n):
                if r==col:continue
                factor=a[r][col]
                if factor==0.0:continue
                for j in range(col,n+1):a[r][j]-=factor*a[col][j]
        out=[a[i][n] for i in range(n)]
        if not all(math.isfinite(v) for v in out):return None
        residual=max(abs(sum(float(matrix[i][j])*out[j] for j in range(n))-float(rhs[i])) for i in range(n))
        if residual>1e-9*max(1.0,max(abs(float(v)) for v in rhs)):return None
        return out

    @staticmethod
    def _route_positive_definite(matrix):
        """Conservative Cholesky check for a valid covariance component."""
        import math
        n=len(matrix);l=[[0.0]*n for _ in range(n)]
        for i in range(n):
            for j in range(i+1):
                val=float(matrix[i][j])-sum(l[i][k]*l[j][k] for k in range(j))
                if i==j:
                    if not math.isfinite(val) or val<=1e-12:return False
                    l[i][j]=math.sqrt(val)
                else:
                    if l[j][j]==0.0:return False
                    l[i][j]=val/l[j][j]
        return True

    @staticmethod
    def _route_local_dependency_weights(unique, pairs):
        source_weight={}
        for source in unique:
            redundancy=0.0
            for other in unique:
                if source==other:continue
                key=(source+"\t"+other) if source<other else (other+"\t"+source)
                try:rho=float(pairs.get(key,0.0))
                except Exception:rho=0.0
                if not (rho==rho):rho=0.0
                rho=max(-1.0,min(1.0,rho))
                redundancy+=max(0.0,rho)
            source_weight[source]=1.0/(1.0+redundancy)
        return source_weight

    def _route_covariance_dependency_weights(self, unique, pairs, *, max_component=16):
        """alpha.7.7 bounded inverse-covariance information weights.

        Connected dependency components are solved independently using
        ``R w = 1``.  The sum of ``w`` is the covariance-theoretic effective
        independent support.  The solve is accepted only for a positive-
        definite component with finite weights inside [0,1].  Singular,
        inconsistent, oversized, negative-weight, or amplifying solutions
        fall back *component-wise* to alpha.7.6 local graph weighting.
        """
        import math
        local=self._route_local_dependency_weights(unique,pairs)
        adjacency={s:set() for s in unique}
        for i,a in enumerate(unique):
            for b in unique[i+1:]:
                key=(a+"\t"+b) if a<b else (b+"\t"+a)
                try:rho=float(pairs.get(key,0.0))
                except Exception:rho=0.0
                if math.isfinite(rho) and rho>0.0:
                    adjacency[a].add(b);adjacency[b].add(a)
        out={s:1.0 for s in unique};seen=set()
        for root in unique:
            if root in seen:continue
            stack=[root];component=[];seen.add(root)
            while stack:
                s=stack.pop();component.append(s)
                for other in sorted(adjacency[s]):
                    if other not in seen:
                        seen.add(other);stack.append(other)
            component=sorted(component)
            if len(component)==1:
                out[component[0]]=1.0;continue
            if len(component)>max_component:
                for s in component:out[s]=local[s]
                continue
            matrix=[]
            for a in component:
                row=[]
                for b in component:
                    if a==b:rho=1.0
                    else:
                        key=(a+"\t"+b) if a<b else (b+"\t"+a)
                        try:rho=float(pairs.get(key,0.0))
                        except Exception:rho=0.0
                        if not math.isfinite(rho):rho=0.0
                        rho=max(0.0,min(1.0,rho))
                    row.append(rho)
                matrix.append(row)
            if not self._route_positive_definite(matrix):
                for s in component:out[s]=local[s]
                continue
            solved=self._route_solve_linear(matrix,[1.0]*len(component))
            if solved is None or any((not math.isfinite(w)) or w<-1e-12 or w>1.0+1e-12 for w in solved):
                for s in component:out[s]=local[s]
                continue
            solved=[max(0.0,min(1.0,w)) for w in solved]
            for s,w in zip(component,solved):out[s]=w
        return out

    @staticmethod
    def _route_latent_factor_fit(unique, pair_stats, *, max_rank=2):
        """Bounded non-negative factor fit over weak raw dependency structure.

        This is redundancy-only: it never sees route labels and cannot generate
        positive evidence. The fit is limited to 8..16 sources and two factors.
        """
        import math
        from statistics import median
        n=len(unique)
        if not (8 <= n <= 16) or not isinstance(pair_stats,dict):return None
        target=[[0.0]*n for _ in range(n)];vals=[];strong=0
        for i,a in enumerate(unique):
            for j in range(i+1,n):
                b=unique[j];key=(a+"\t"+b) if a<b else (b+"\t"+a)
                st=pair_stats.get(key)
                if not isinstance(st,dict):raw=0.0;trials=0
                else:
                    try:raw=float(st.get("raw",0.0));trials=int(st.get("trials",0))
                    except Exception:raw=0.0;trials=0
                if not math.isfinite(raw) or trials<64:raw=0.0
                raw=max(0.0,min(0.95,raw));target[i][j]=target[j][i]=raw;vals.append(raw)
                if raw>=0.10:strong+=1
        if not vals:return None
        mean_positive=sum(vals)/len(vals);density=float(strong)/float(len(vals));med=median(vals)
        if mean_positive<0.08 or density<0.35 or med<0.05:return None
        residual=[row[:] for row in target];factors=[];cap2=0.90
        for _factor in range(max_rank):
            rowsums=[sum(residual[i][j] for j in range(n) if j!=i) for i in range(n)]
            if max(rowsums,default=0.0)<=1e-12:break
            load=[min(math.sqrt(cap2),math.sqrt(max(0.0,rowsums[i]/float(max(1,n-1))))) for i in range(n)]
            for _ in range(64):
                old=list(load)
                for i in range(n):
                    num=sum(residual[i][j]*load[j] for j in range(n) if j!=i)
                    den=sum(load[j]*load[j] for j in range(n) if j!=i)
                    used=sum(f[i]*f[i] for f in factors);cap=math.sqrt(max(0.0,cap2-used))
                    load[i]=min(cap,max(0.0,num/den if den>1e-15 else 0.0))
                if max(abs(load[i]-old[i]) for i in range(n))<1e-10:break
            if sum(x*x for x in load)<=1e-10:break
            factors.append(load)
            for i in range(n):
                for j in range(i+1,n):residual[i][j]=residual[j][i]=max(0.0,residual[i][j]-load[i]*load[j])
        if not factors:return None
        pred=[[0.0]*n for _ in range(n)];errors=[];sq_target=0.0;sq_error=0.0
        for i in range(n):
            for j in range(i+1,n):
                value=min(0.95,max(0.0,sum(f[i]*f[j] for f in factors)));pred[i][j]=pred[j][i]=value
                err=target[i][j]-value;errors.append(abs(err));sq_target+=target[i][j]*target[i][j];sq_error+=err*err
        mae=sum(errors)/len(errors);explained=0.0 if sq_target<=1e-15 else max(0.0,1.0-sq_error/sq_target)
        strength=[sum(f[i]*f[i] for f in factors) for i in range(n)];loaded=sum(v>=0.04 for v in strength)
        if loaded<4 or explained<0.65 or mae>max(0.05,0.60*mean_positive):return None
        return {"factors":tuple(tuple(float(x) for x in f) for f in factors),"predicted":pred,
                "mean_positive":float(mean_positive),"density_ge_0_10":float(density),"median_positive_field":float(med),
                "mae":float(mae),"explained_energy":float(explained),"loaded_sources":int(loaded)}

    def _route_factor_information_weights(self, unique, fit, *, redundancy_scale=0.85):
        """Bounded Woodbury information weights for a fitted rank<=2 factor covariance."""
        import math
        factors=fit.get("factors") if isinstance(fit,dict) else None
        if not factors:return None
        k=len(factors);n=len(unique)
        if not (1<=k<=2) or any(len(f)!=n for f in factors):return None
        scale=math.sqrt(max(0.0,min(1.0,float(redundancy_scale))))
        load=[[float(factors[j][i])*scale for j in range(k)] for i in range(n)];invpsi=[]
        for i in range(n):
            psi=1.0-sum(x*x for x in load[i])
            if not math.isfinite(psi) or psi<=1e-9:return None
            invpsi.append(1.0/psi)
        small=[[0.0]*k for _ in range(k)];rhs=[0.0]*k
        for a in range(k):
            for b in range(k):small[a][b]=(1.0 if a==b else 0.0)+sum(invpsi[i]*load[i][a]*load[i][b] for i in range(n))
            rhs[a]=sum(invpsi[i]*load[i][a] for i in range(n))
        z=self._route_solve_linear(small,rhs)
        if z is None:return None
        out={}
        for i,src in enumerate(unique):
            w=invpsi[i]*(1.0-sum(load[i][a]*z[a] for a in range(k)))
            if not math.isfinite(w) or w<-1e-12 or w>1.0+1e-12:return None
            out[src]=max(0.0,min(1.0,w))
        return out

    def _route_latent_dependency_weights(self, unique, dep, *, max_component=64):
        """Wide covariance baseline plus monotone PSD latent redundancy."""
        import math
        pairs=dep.get("pairwise") if isinstance(dep,dict) else None
        if not isinstance(pairs,dict):return {src:1.0 for src in unique}
        base=self._route_covariance_dependency_weights(unique,pairs,max_component=max_component)
        fit=self._route_latent_factor_fit(unique,dep.get("pairwise_stats"))
        if fit is None:return base
        factor=self._route_factor_information_weights(unique,fit,redundancy_scale=0.85)
        if factor is None:return base
        out={src:min(float(base.get(src,1.0)),float(factor.get(src,1.0))) for src in unique}
        return out if all(math.isfinite(v) and 0.0<=v<=1.0 for v in out.values()) else base

    @staticmethod
    def _route_signed_component_core(component, edge_map, *, min_size=8, max_size=32,
                                     target_density=0.35):
        """Return a bounded dense core without over-pruning already-coherent groups.

        alpha.7.9 only prunes when a connected component is oversized or too sparse.
        One weakest bridge/passenger is removed at a time.  This avoids the earlier
        failure mode where a blanket k-core rule removed legitimate low-degree
        members of a noisy hidden factor.
        """
        nodes=list(sorted(component))
        def degree_stats(cur):
            cset=set(cur);deg={s:0 for s in cur};strength={s:0.0 for s in cur};edges=0
            for (a,b),raw in edge_map.items():
                if a in cset and b in cset:
                    deg[a]+=1;deg[b]+=1;strength[a]+=abs(raw);strength[b]+=abs(raw);edges+=1
            possible=max(1,len(cur)*(len(cur)-1)//2)
            return deg,strength,float(edges)/float(possible)
        while len(nodes)>=min_size:
            deg,strength,density=degree_stats(nodes)
            if len(nodes)<=max_size and density>=target_density:
                return tuple(nodes)
            weakest=min(nodes,key=lambda x:(deg[x],strength[x],x))
            nodes.remove(weakest)
        return None

    @staticmethod
    def _route_signed_polarities(component, edge_map, *, coherence_floor=0.86):
        """Infer a balanced signed gauge and reject frustrated/inconsistent graphs."""
        import math
        cset=set(component);adj={s:[] for s in component}
        for (a,b),raw in edge_map.items():
            if a not in cset or b not in cset or raw==0.0:continue
            sign=1 if raw>0.0 else -1;weight=abs(float(raw))
            adj[a].append((b,sign,weight));adj[b].append((a,sign,weight))
        if not any(adj.values()):return None
        root=max(component,key=lambda s:(sum(w for _,_,w in adj[s]),len(adj[s]),s))
        polarity={root:1};stack=[root]
        while stack:
            a=stack.pop()
            for b,sign,_w in adj[a]:
                want=polarity[a]*sign
                if b not in polarity:
                    polarity[b]=want;stack.append(b)
        if len(polarity)!=len(component):return None
        total=0.0;agree=0.0
        for (a,b),raw in edge_map.items():
            if a not in cset or b not in cset:continue
            w=abs(float(raw));total+=w
            if polarity[a]*polarity[b]*(1 if raw>0.0 else -1)>0:agree+=w
        if total<=1e-15:return None
        coherence=agree/total
        if not math.isfinite(coherence) or coherence<coherence_floor:return None
        return polarity,float(coherence)

    def _route_signed_latent_dependency_weights(self, unique, dep, *, max_component=32,
                                                edge_floor=0.10, coherence_floor=0.86,
                                                collective_floor=0.085,
                                                material_loading=0.04):
        """alpha.7.9 component-wise signed latent redundancy guard.

        Starts from alpha.7.8 ``full_latent`` dependency weights.  Raw signed
        correlations are used only to discover coherent hidden redundancy inside
        local components.  The result is monotone: every returned source weight is
        <= its alpha.7.8 weight.  Frustrated, weak, sparse, undersampled, oversized,
        non-finite, or numerically invalid components fall back locally to alpha.7.8.
        """
        import math
        pairs=dep.get("pairwise") if isinstance(dep,dict) else None
        stats=dep.get("pairwise_stats") if isinstance(dep,dict) else None
        if not isinstance(pairs,dict) or not isinstance(stats,dict):
            return self._route_latent_dependency_weights(unique,dep,max_component=64)
        base=self._route_latent_dependency_weights(unique,dep,max_component=64)
        canonical=tuple(sorted(unique));edge_map={};raw_map={}
        for i,a in enumerate(canonical):
            for b in canonical[i+1:]:
                key=(a+"\t"+b) if a<b else (b+"\t"+a)
                st=stats.get(key,{})
                try:raw=float(st.get("raw",0.0));trials=int(st.get("trials",0))
                except Exception:raw=0.0;trials=0
                if not math.isfinite(raw) or trials<64:raw=0.0
                raw=max(-0.95,min(0.95,raw));raw_map[(a,b)]=raw
                if abs(raw)>=edge_floor:edge_map[(a,b)]=raw
        adjacency={s:set() for s in canonical}
        for (a,b),_raw in edge_map.items():adjacency[a].add(b);adjacency[b].add(a)
        out=dict(base);seen=set()
        for root in canonical:
            if root in seen:continue
            stack=[root];seen.add(root);component=[]
            while stack:
                s=stack.pop();component.append(s)
                for other in sorted(adjacency[s]):
                    if other not in seen:seen.add(other);stack.append(other)
            if len(component)<8:continue
            core=self._route_signed_component_core(component,edge_map,min_size=8,max_size=max_component,target_density=0.35)
            if core is None:continue
            # Chance edges can attach low-degree passengers to a genuine latent
            # group.  If the whole candidate fails the collective gate, prune
            # only the weakest bridge one-at-a-time and retry; never prune below
            # the minimum 8-source evidence unit.
            candidate=list(core);accepted=None
            while len(candidate)>=8:
                signed=self._route_signed_polarities(tuple(candidate),edge_map,coherence_floor=coherence_floor)
                if signed is not None:
                    polarity,coherence=signed
                    vals=[]
                    for i,a in enumerate(candidate):
                        for b in candidate[i+1:]:
                            raw=raw_map.get((a,b) if a<b else (b,a),0.0)
                            vals.append(max(0.0,float(raw)*float(polarity[a])*float(polarity[b])))
                    if vals and sum(vals)/len(vals)>=collective_floor:
                        accepted=(tuple(candidate),polarity,coherence);break
                if len(candidate)==8:break
                cset=set(candidate);deg={s:0 for s in candidate};strength={s:0.0 for s in candidate}
                for (a,b),raw in edge_map.items():
                    if a in cset and b in cset:
                        deg[a]+=1;deg[b]+=1;strength[a]+=abs(raw);strength[b]+=abs(raw)
                weakest=min(candidate,key=lambda x:(deg[x],strength[x],x));candidate.remove(weakest)
            if accepted is None:continue
            core,polarity,coherence=accepted
            transformed={}
            for i,a in enumerate(core):
                for b in core[i+1:]:
                    key=(a+"\t"+b) if a<b else (b+"\t"+a)
                    st=stats.get(key,{})
                    try:trials=int(st.get("trials",0))
                    except Exception:trials=0
                    raw=raw_map.get((a,b) if a<b else (b,a),0.0)
                    gauged=max(0.0,min(0.95,raw*polarity[a]*polarity[b]))
                    transformed[key]={"raw":gauged,"active":0.0,"trials":trials,"p":1.0,"fdr_accepted":False}
            # Reuse the alpha.7.8 non-negative rank<=2 fitter, but permit a
            # bounded 32-source component for stage-closure tests.
            fit=self._route_latent_factor_fit_extended(core,transformed,max_rank=2,max_sources=max_component,
                                                       mean_floor=collective_floor)
            if fit is None:continue
            factor=self._route_factor_information_weights(core,fit,redundancy_scale=0.85)
            if factor is None:continue
            factors=fit.get("factors",())
            strength={s:sum(float(f[i])**2 for f in factors) for i,s in enumerate(core)}
            for src in core:
                # Low-loading passengers retain the alpha.7.8 baseline exactly.
                if strength.get(src,0.0)<material_loading:continue
                cand=float(factor.get(src,base.get(src,1.0)))
                if math.isfinite(cand) and 0.0<=cand<=1.0:
                    out[src]=min(float(base.get(src,1.0)),cand)
        if not all(math.isfinite(v) and 0.0<=v<=float(base.get(s,1.0))+1e-12 for s,v in out.items()):
            return base
        return out

    @staticmethod
    def _route_latent_factor_fit_extended(unique, pair_stats, *, max_rank=2, max_sources=32,
                                          mean_floor=0.085):
        """alpha.7.9 bounded rank<=2 non-negative fit for a signed-gauged core."""
        import math
        from statistics import median
        n=len(unique)
        if not (8<=n<=max_sources) or not isinstance(pair_stats,dict):return None
        target=[[0.0]*n for _ in range(n)];vals=[];strong=0
        for i,a in enumerate(unique):
            for j in range(i+1,n):
                b=unique[j];key=(a+"\t"+b) if a<b else (b+"\t"+a)
                st=pair_stats.get(key)
                if not isinstance(st,dict):raw=0.0;trials=0
                else:
                    try:raw=float(st.get("raw",0.0));trials=int(st.get("trials",0))
                    except Exception:raw=0.0;trials=0
                if not math.isfinite(raw) or trials<64:raw=0.0
                raw=max(0.0,min(0.95,raw));target[i][j]=target[j][i]=raw;vals.append(raw)
                if raw>=0.10:strong+=1
        if not vals:return None
        mean_positive=sum(vals)/len(vals);density=float(strong)/float(len(vals));med=median(vals)
        if mean_positive<mean_floor or density<0.35 or med<0.04:return None
        residual=[row[:] for row in target];factors=[];cap2=0.90
        for _factor in range(max_rank):
            rowsums=[sum(residual[i][j] for j in range(n) if j!=i) for i in range(n)]
            if max(rowsums,default=0.0)<=1e-12:break
            load=[min(math.sqrt(cap2),math.sqrt(max(0.0,rowsums[i]/float(max(1,n-1))))) for i in range(n)]
            for _ in range(64):
                old=list(load)
                for i in range(n):
                    num=sum(residual[i][j]*load[j] for j in range(n) if j!=i)
                    den=sum(load[j]*load[j] for j in range(n) if j!=i)
                    used=sum(f[i]*f[i] for f in factors);cap=math.sqrt(max(0.0,cap2-used))
                    load[i]=min(cap,max(0.0,num/den if den>1e-15 else 0.0))
                if max(abs(load[i]-old[i]) for i in range(n))<1e-10:break
            if sum(x*x for x in load)<=1e-10:break
            factors.append(load)
            for i in range(n):
                for j in range(i+1,n):residual[i][j]=residual[j][i]=max(0.0,residual[i][j]-load[i]*load[j])
        if not factors:return None
        errors=[];sq_target=0.0;sq_error=0.0
        for i in range(n):
            for j in range(i+1,n):
                value=min(0.95,max(0.0,sum(f[i]*f[j] for f in factors)))
                err=target[i][j]-value;errors.append(abs(err));sq_target+=target[i][j]*target[i][j];sq_error+=err*err
        mae=sum(errors)/len(errors);explained=0.0 if sq_target<=1e-15 else max(0.0,1.0-sq_error/sq_target)
        strength=[sum(f[i]*f[i] for f in factors) for i in range(n)];loaded=sum(v>=0.04 for v in strength)
        if loaded<4 or explained<0.60 or mae>max(0.055,0.65*mean_positive):return None
        return {"factors":tuple(tuple(float(x) for x in f) for f in factors),
                "mean_positive":float(mean_positive),"density_ge_0_10":float(density),
                "median_positive_field":float(med),"mae":float(mae),
                "explained_energy":float(explained),"loaded_sources":int(loaded)}

    def _route_support_weights(self, rows, mode="full"):
        """Per-row epistemic weights for alpha.7.6/7.7/7.8 experiments."""
        valid={"frequency","reliability","dependency","full","covariance","full_covariance",
               "wide_covariance","full_wide_covariance","latent","full_latent",
               "signed_latent","full_signed_latent"}
        if mode not in valid:raise ValueError("invalid routing epistemic mode")
        if not rows:return []
        reliability=[max(0.0,min(1.0,float(r.get("reliability",1.0)))) for r in rows]
        dependency=[1.0]*len(rows);covariance=[1.0]*len(rows);wide=[1.0]*len(rows);latent=[1.0]*len(rows);signed_latent=[1.0]*len(rows)
        if mode in valid-{"frequency","reliability"} and self.dependency_provider is not None:
            unique=[]
            for row in rows:
                if row["source"] not in unique:unique.append(row["source"])
            try:
                dep=self.dependency_provider(unique);pairs=dep.get("pairwise") if isinstance(dep,dict) else None
                if isinstance(pairs,dict):
                    local=self._route_local_dependency_weights(unique,pairs);dependency=[local.get(r["source"],1.0) for r in rows]
                    if mode in {"covariance","full_covariance","wide_covariance","full_wide_covariance","latent","full_latent","signed_latent","full_signed_latent"}:
                        version=dep.get("version") if isinstance(dep,dict) else None;canonical=tuple(sorted(unique))
                        psig=tuple(sorted((str(k),round(float(v),12)) for k,v in pairs.items()))
                        cache=getattr(self,"_route_covariance_cache",None)
                        if cache is None:cache={};self._route_covariance_cache=cache
                        def solve(limit):
                            k=(version,canonical,psig,int(limit));v=cache.get(k)
                            if v is None:
                                v=self._route_covariance_dependency_weights(canonical,pairs,max_component=limit)
                                if len(cache)>=128:cache.pop(next(iter(cache)))
                                cache[k]=dict(v)
                            return v
                        if mode in {"covariance","full_covariance"}:
                            m=solve(16);covariance=[m.get(r["source"],1.0) for r in rows]
                        elif mode in {"wide_covariance","full_wide_covariance"}:
                            m=solve(64);wide=[m.get(r["source"],1.0) for r in rows]
                        else:
                            stats=dep.get("pairwise_stats") if isinstance(dep,dict) else None
                            ssig=tuple(sorted((str(k),round(float(v.get("raw",0.0)),12),int(v.get("trials",0))) for k,v in stats.items())) if isinstance(stats,dict) else ()
                            lc=getattr(self,"_route_latent_cache",None)
                            if lc is None:lc={};self._route_latent_cache=lc
                            lk=(version,canonical,psig,ssig,64);m=lc.get(lk)
                            if m is None:
                                m=self._route_latent_dependency_weights(canonical,dep,max_component=64)
                                if len(lc)>=128:lc.pop(next(iter(lc)))
                                lc[lk]=dict(m)
                            latent=[m.get(r["source"],1.0) for r in rows]
                            if mode in {"signed_latent","full_signed_latent"}:
                                sc=getattr(self,"_route_signed_latent_cache",None)
                                if sc is None:sc={};self._route_signed_latent_cache=sc
                                sk=(version,canonical,psig,ssig,32);sm=sc.get(sk)
                                if sm is None:
                                    sm=self._route_signed_latent_dependency_weights(canonical,dep,max_component=32)
                                    if len(sc)>=128:sc.pop(next(iter(sc)))
                                    sc[sk]=dict(sm)
                                signed_latent=[sm.get(r["source"],1.0) for r in rows]
                else:
                    target=max(0.0,min(float(len(unique)),float(dep.get("effective_count",len(unique)))))
                    scale=target/float(len(unique));dependency=[scale]*len(rows);covariance=list(dependency);wide=list(dependency);latent=list(dependency);signed_latent=list(dependency)
            except Exception:
                dependency=[1.0]*len(rows);covariance=[1.0]*len(rows);wide=[1.0]*len(rows);latent=[1.0]*len(rows);signed_latent=[1.0]*len(rows)
        if mode=="frequency":return [1.0]*len(rows)
        if mode=="reliability":return reliability
        if mode=="dependency":return dependency
        if mode=="covariance":return covariance
        if mode=="wide_covariance":return wide
        if mode=="latent":return latent
        if mode=="signed_latent":return signed_latent
        if mode=="full_covariance":return [r*d for r,d in zip(reliability,covariance)]
        if mode=="full_wide_covariance":return [r*d for r,d in zip(reliability,wide)]
        if mode=="full_latent":return [r*d for r,d in zip(reliability,latent)]
        if mode=="full_signed_latent":return [r*d for r,d in zip(reliability,signed_latent)]
        return [r*d for r,d in zip(reliability,dependency)]

    def _route_model(self, mechanism, observed_features, *, candidate_contexts=None, epistemic_mode="full_signed_latent"):
        import math
        observed_features=self._route_features(observed_features)
        active=self._active_route_contexts(mechanism)
        if candidate_contexts is not None:
            if not isinstance(candidate_contexts,(list,tuple)) or not 1<=len(candidate_contexts)<=self.ROUTE_MAX_CONTEXTS:
                raise ValueError('invalid routing candidate contexts')
            requested=[]
            for c in candidate_contexts:
                self._scope(mechanism,c)
                if c in active and c not in requested: requested.append(c)
            active=requested
        if not active:
            return {'status':'unresolved','reason':'no_active_procedure_contexts','observed_features':observed_features,'epistemic_mode':epistemic_mode}
        if len(active)==1:
            return {'status':'model','contexts':active,'posterior':{active[0]:1.0},'support':{active[0]:0},
                    'rows':[],'observed_features':observed_features}
        rows=[r for r in self._effective_route_rows(mechanism) if r['context'] in active]
        if not rows:
            return {'status':'unresolved','reason':'no_trusted_route_evidence','contexts':active,'observed_features':observed_features}
        weights=self._route_support_weights(rows,epistemic_mode)
        support={c:0.0 for c in active}
        for r,w in zip(rows,weights):support[r['context']]+=w
        total=sum(support.values()); k=len(active)
        logs={}
        for c in active:
            logs[c]=math.log((support[c]+1)/(total+k))
            crows=[r for r in rows if r['context']==c]
            for feature,value in observed_features.items():
                domain={pack(r['features'][feature]) for r in rows if feature in r['features']}
                # One explicit unseen bucket prevents false certainty on novel values.
                vcount=max(2,len(domain)+1)
                present=[r for r in crows if feature in r['features']]
                matches=sum(w for r,w in zip(rows,weights) if r['context']==c and feature in r['features'] and r['features'][feature]==value)
                present_weight=sum(w for r,w in zip(rows,weights) if r['context']==c and feature in r['features'])
                logs[c]+=math.log((matches+1)/(present_weight+vcount))
        m=max(logs.values()); exps={c:math.exp(v-m) for c,v in logs.items()}; z=sum(exps.values())
        posterior={c:exps[c]/z for c in active}
        return {'status':'model','contexts':active,'posterior':posterior,'support':support,'rows':rows,
                'weights':weights,'observed_features':observed_features}

    def _route_information_query(self, model):
        import math
        rows=model.get('rows',[]); contexts=model.get('contexts',[]); posterior=model.get('posterior',{})
        observed=model.get('observed_features',{})
        if len(contexts)<2 or not rows:return None
        current_h=self._entropy(posterior.values())
        feature_names=sorted({k for r in rows for k in r['features']} - set(observed))[:self.ROUTE_MAX_FEATURES]
        best=None
        for feature in feature_names:
            domain=[]
            for r in rows:
                if feature in r['features'] and r['features'][feature] not in domain:domain.append(r['features'][feature])
            if len(domain)<2 or len(domain)>32:continue
            cond={}
            weights=model.get('weights') or [1.0]*len(rows)
            for c in contexts:
                vcount=len(domain)
                present_weight=sum(w for r,w in zip(rows,weights) if r['context']==c and feature in r['features'])
                cond[c]={pack(v):(sum(w for r,w in zip(rows,weights) if r['context']==c and feature in r['features'] and r['features'][feature]==v)+1)/(present_weight+vcount) for v in domain}
            expected_h=0.0; value_dist={}
            for value in domain:
                key=pack(value)
                pv=sum(posterior[c]*cond[c][key] for c in contexts)
                if pv<=0:continue
                post={c:(posterior[c]*cond[c][key])/pv for c in contexts}
                expected_h+=pv*self._entropy(post.values());value_dist[key]=pv
            gain=current_h-expected_h
            candidate={'feature':feature,'expected_information_gain':gain,'possible_values':domain,
                       'value_distribution':value_dist,'read_only':True}
            if best is None or gain>best['expected_information_gain']+1e-12 or (
                abs(gain-best['expected_information_gain'])<=1e-12 and feature<best['feature']):best=candidate
        return best if best is not None and best['expected_information_gain']>1e-12 else None

    def route(self, mechanism, observed_features, *, candidate_contexts=None, confidence_threshold=.8, min_support=None, epistemic_mode="full_signed_latent"):
        """Route among validated procedure contexts without changing learned state."""
        self._scope(mechanism,'')
        if type(confidence_threshold) not in (int,float) or not .5 <= float(confidence_threshold) <= 1:
            raise ValueError('routing confidence threshold must be within .5..1')
        min_support=self.ROUTE_MIN_SUPPORT if min_support is None else min_support
        if type(min_support) is not int or not 1<=min_support<=32:raise ValueError('invalid routing support threshold')
        model=self._route_model(mechanism,observed_features,candidate_contexts=candidate_contexts,epistemic_mode=epistemic_mode)
        if model.get('status')!='model':
            model['read_only']=True;return model
        posterior=model['posterior'];top=max(posterior,key=posterior.get);p=float(posterior[top]);support=model['support'].get(top,0)
        base={'posterior':posterior,'candidate_contexts':model['contexts'],'support':model['support'],
              'observed_features':model['observed_features'],'read_only':True}
        if len(model['contexts'])==1:
            return dict(base,status='routed',context=top,confidence=1.0,reason='only_active_context')
        # Direct empirical applicability evidence is stronger than the smoothed
        # Naive-Bayes fallback: if every trusted row matching the observed
        # context points to one active procedure context, route once that exact
        # signature has enough independent support. Partial signatures that
        # still match multiple contexts remain ambiguous and request information.
        if model['observed_features']:
            exact={}
            route_weights=model.get('weights') or self._route_support_weights(model['rows'],epistemic_mode)
            for row,w in zip(model['rows'],route_weights):
                if all(k in row['features'] and row['features'][k]==v for k,v in model['observed_features'].items()):
                    exact[row['context']]=exact.get(row['context'],0.0)+w
            timed=[(row,w) for row,w in zip(model['rows'],route_weights) if row.get('temporal_index') is not None and
                   all(k in row['features'] and row['features'][k]==v for k,v in model['observed_features'].items())]
            if timed:
                latest=timed[-1][0]['context'];run_support=0.0;run_rows=0
                for row,w in reversed(timed):
                    if row['context']!=latest:break
                    run_support+=w;run_rows+=1
                # Four recent trusted observations remain the temporal-regime
                # persistence target, expressed in effective-support units. A
                # source at the admission trust floor contributes TRUST_FLOOR,
                # while dependency/reliability penalties can still delay a
                # regime switch when those four rows are epistemically weaker.
                temporal_required=max(float(min_support),4.0*self.TRUST_FLOOR)
                if run_support>=temporal_required:
                    return dict(base,status='routed',context=latest,confidence=1.0,
                                reason='recent_temporal_signature_regime',recent_run_support=run_support,
                                recent_run_rows=run_rows,exact_support=exact)
            if len(exact)==1:
                exact_context=next(iter(exact))
                if exact[exact_context]>=min_support:
                    return dict(base,status='routed',context=exact_context,confidence=1.0,
                                reason='unique_empirical_context_signature',exact_support=exact)
        if p>=float(confidence_threshold) and support>=min_support:
            return dict(base,status='routed',context=top,confidence=p)
        query=self._route_information_query(model)
        if query is not None:
            return dict(base,status='needs_information',confidence=p,leading_context=top,information_query=query)
        return dict(base,status='abstain',confidence=p,leading_context=top,reason='routing_uncertainty_not_resolved')

    def route_query_plan(self, mechanism, observed_features, *, candidate_contexts=None,
                         confidence_threshold=.8, min_support=None, max_depth=3, max_branches=8,
                         epistemic_mode="full_signed_latent"):
        """Build a bounded hypothetical information-gathering tree, read-only.

        Branches are simulations only. They never become evidence and never
        mutate procedure/routing state. A caller must externally resolve the
        recommended feature before using the next real routing decision.
        """
        if type(max_depth) is not int or not 0 <= max_depth <= 4:
            raise ValueError('routing query depth must be within 0..4')
        if type(max_branches) is not int or not 1 <= max_branches <= 8:
            raise ValueError('routing branch limit must be within 1..8')
        root_features=self._route_features(observed_features)
        nodes=[0]
        def build(features, depth):
            nodes[0]+=1
            if nodes[0] > 128:
                return {'status':'budget_exhausted','observed_features':dict(features),'read_only':True}
            decision=self.route(mechanism,features,candidate_contexts=candidate_contexts,
                                confidence_threshold=confidence_threshold,min_support=min_support,
                                epistemic_mode=epistemic_mode)
            node={'status':decision.get('status'),'observed_features':dict(features),
                  'posterior':decision.get('posterior',{}),'read_only':True}
            if decision.get('status')=='routed':
                node.update(context=decision['context'],confidence=decision['confidence']);return node
            query=decision.get('information_query')
            if depth>=max_depth or not query:
                node['reason']=decision.get('reason','depth_or_information_limit');return node
            values=list(query.get('possible_values',[]))
            if not 1<=len(values)<=max_branches:
                node['reason']='branch_limit';node['information_query']=query;return node
            node['information_query']={k:v for k,v in query.items() if k!='value_distribution'}
            node['branches']=[]
            for value in values:
                child=dict(features);child[query['feature']]=value
                node['branches'].append({'value':value,'next':build(child,depth+1)})
            return node
        tree=build(root_features,0)
        return {'status':'planned','tree':tree,'nodes':nodes[0],'max_depth':max_depth,'epistemic_mode':epistemic_mode,'read_only':True}

    def predict_routed(self, mechanism, procedure_inputs, observed_features, *, candidate_contexts=None,
                       confidence_threshold=.8, min_support=None, epistemic_mode="full_signed_latent"):
        decision=self.route(mechanism,observed_features,candidate_contexts=candidate_contexts,
                            confidence_threshold=confidence_threshold,min_support=min_support,
                            epistemic_mode=epistemic_mode)
        if decision.get('status')!='routed':
            return {'status':decision.get('status','abstain'),'routing':decision}
        prediction=self.predict(mechanism,procedure_inputs,context=decision['context'])
        return {'status':prediction.get('status'),'routing':decision,'prediction':prediction,
                'value':prediction.get('value')}

    def route_evidence_status(self, mechanism):
        bounded_id(mechanism,'mechanism')
        total=self.db.execute('SELECT COUNT(*) FROM procedure_route_evidence WHERE mechanism=?',(mechanism,)).fetchone()[0]
        effective=self._effective_route_rows(mechanism,limit=min(2048,max(1,total))) if total else []
        contexts={}
        for r in effective:contexts[r['context']]=contexts.get(r['context'],0)+1
        return {'total_records':total,'effective_records':len(effective),'effective_context_support':contexts}

    def close(self):self.db.close()
