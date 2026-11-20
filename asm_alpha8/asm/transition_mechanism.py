from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import io
import json
import math
import sqlite3
from itertools import combinations
import time
from pathlib import Path
from typing import Any
from array import array

try:  # The rest of ASM can still open if PyTorch is unavailable.
    import torch
    from torch import nn
except Exception:  # pragma: no cover - exercised only on minimal installs
    torch = None
    nn = None


@dataclass(slots=True)
class TransitionPrediction:
    mechanism_type: str
    entity_id: str
    predicted_state: dict[str, Any] | None
    confidence: float
    uncertainty: float
    outcome_slot: int | None
    known_outcomes: int
    support: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


if nn is not None:
    class _RecurrentTransitionNet(nn.Module):
        def __init__(self, input_dim: int, hidden_dim: int, max_outcomes: int):
            super().__init__()
            self.input_proj = nn.Linear(input_dim, hidden_dim)
            self.gru = nn.GRUCell(hidden_dim, hidden_dim)
            self.head = nn.Linear(hidden_dim, max_outcomes)

        def forward(self, x, hidden):
            x = torch.tanh(self.input_proj(x))
            h = self.gru(x, hidden)
            return self.head(h), h
else:
    class _RecurrentTransitionNet:
        """Import-safe placeholder used only when PyTorch is unavailable."""

        def __init__(self, *args, **kwargs):
            raise RuntimeError("PyTorch is required for recurrent transition mechanisms")


class LocalRecurrentTransitionMechanism:
    """Small action-conditioned recurrent predictor shared across entity instances.

    The network never receives the entity identifier as an input feature.  That is
    deliberate: learned weights describe a *mechanism type* and can transfer to a
    new compatible entity.  Entity identity only selects a persistent recurrent
    context vector, allowing local history without baking instance names into the
    shared rule.
    """

    def __init__(
        self,
        mechanism_type: str,
        *,
        input_dim: int = 128,
        hidden_dim: int = 64,
        max_outcomes: int = 32,
        learning_rate: float = 0.012,
        train_steps: int = 6,
        seed: int = 17,
        retention_anchor_limit: int = 96,
        retention_anchor_batch_limit: int = 6,
        outcome_capacity_limit: int = 4096,
        outcome_growth_factor: float = 2.0,
        consolidation_table_size: int = 1024,
        consolidation_hashes: int = 3,
        consolidation_min_support: int = 4,
        consolidation_max_displacements: int = 24,
        consolidation_enabled: bool = True,
        abstraction_enabled: bool = True,
        abstraction_min_support: int = 8,
        abstraction_min_precision: float = 0.95,
        abstraction_min_diversity: int = 4,
        abstraction_max_dropped_features: int = 2,
        abstraction_sparse_enabled: bool = True,
        abstraction_pending_enabled: bool = True,
        abstraction_sparse_max_retained_features: int = 2,
        abstraction_candidates_per_observation: int = 48,
        abstraction_max_candidates: int = 2048,
        abstraction_exception_limit: int = 512,
    ):
        if torch is None:
            raise RuntimeError("PyTorch is required for recurrent transition mechanisms")
        self.mechanism_type = str(mechanism_type)
        self.input_dim = int(input_dim)
        self.hidden_dim = int(hidden_dim)
        self.max_outcomes = int(max_outcomes)
        self.learning_rate = float(learning_rate)
        self.train_steps = max(1, int(train_steps))
        digest = int(hashlib.sha256(self.mechanism_type.encode("utf-8")).hexdigest()[:8], 16)
        torch.manual_seed((int(seed) + digest) % (2**31 - 1))
        self.net = _RecurrentTransitionNet(self.input_dim, self.hidden_dim, self.max_outcomes)
        self.optimizer = torch.optim.Adam(self.net.parameters(), lr=self.learning_rate)
        self.outcome_to_slot: dict[str, int] = {}
        self.slot_to_outcome: dict[int, dict[str, Any]] = {}
        self.outcome_support: dict[int, int] = {}
        self.context_hidden: dict[str, torch.Tensor] = {}
        self.context_surprise: dict[str, float] = {}
        self.context_trace: dict[str, list[dict[str, Any]]] = {}
        self.context_trace_limit = 4
        # Shared, bounded history-conditioned empirical fallback. The GRU remains
        # primary; this table is consulted only when neural confidence is weak.
        # It stabilizes repeated local sequences across entity instances without
        # using entity IDs as predictive features.
        self.trace_outcome_support: dict[str, dict[int, int]] = {}
        self.trace_table_limit = 512
        self.trace_min_support = 3
        self.trace_max_neural_confidence = 0.75
        self.trace_fallback_hits = 0
        # v0.4-alpha.3: bounded empirical outcome distributions for stochastic
        # planning. Unlike the consolidation map, this deliberately retains
        # multiple outcomes for the same visible input so modal predictions do
        # not erase tail risk. Counts are exact observations, not neural
        # softmax scores.
        self.conditional_outcome_support: dict[str, dict[int, int]] = {}
        self.conditional_outcome_limit = 2048
        self.conditional_outcome_min_support = 6
        self.replay: list[dict[str, Any]] = []
        self.replay_limit = 256
        self.replay_batch_limit = 14
        # Alpha.6: a tiny long-horizon rehearsal set survives even when the
        # ordinary recency replay buffer is flooded by later experience. One
        # representative is retained per visible-input/outcome pair, with a
        # rotating bounded rehearsal budget so compute remains constant.
        self.retention_anchors: dict[str, dict[str, Any]] = {}
        self.retention_ambiguous_signatures: set[str] = set()
        self.retention_anchor_limit = max(1, int(retention_anchor_limit))
        self.retention_anchor_batch_limit = max(0, int(retention_anchor_batch_limit))
        self.retention_anchor_cursor = 0
        # Alpha.7: the output head can grow when a mechanism discovers more
        # outcomes than its initial allocation. Growth is bounded by a configured
        # ceiling; old rows and optimizer moments are preserved.
        self.outcome_capacity_limit = max(self.max_outcomes, int(outcome_capacity_limit))
        self.outcome_growth_factor = max(1.25, float(outcome_growth_factor))
        self.capacity_expansions = 0
        self.capacity_history = [self.max_outcomes]
        # Alpha.10: packed high-load consolidation. Alpha.9 already stores one
        # mapping per cell, but each cell used 14 logical bytes: uint64 fingerprint
        # + int32 slot + uint16 support. Alpha.10 packs slot+support into one uint32
        # (20 slot bits, 12 support bits), preserving the 64-bit exact fingerprint
        # while increasing usable cells under the *same* logical byte budget.
        # Default: 43,008 bytes -> 3,584 cells instead of alpha.9's 3,072.
        self.consolidation_enabled = bool(consolidation_enabled)
        self.consolidation_table_size = max(64, int(consolidation_table_size))
        self.consolidation_hashes = max(1, min(8, int(consolidation_hashes)))
        self.consolidation_min_support = max(1, int(consolidation_min_support))
        self.consolidation_max_displacements = max(1, int(consolidation_max_displacements))
        self.consolidation_layout_version = 3
        self.consolidation_slot_bits = 20
        self.consolidation_support_bits = 12
        self.consolidation_slot_mask = (1 << self.consolidation_slot_bits) - 1
        self.consolidation_support_max = (1 << self.consolidation_support_bits) - 1
        # Preserve alpha.8/alpha.9's configured logical byte budget rather than
        # silently allocating more memory. Old cells cost 8+4+2 = 14 bytes.
        self.consolidation_byte_budget = (
            self.consolidation_table_size * self.consolidation_hashes * 14
            if self.consolidation_enabled else 0
        )
        cells = self.consolidation_byte_budget // 12 if self.consolidation_enabled else 0
        self.consolidation_fingerprints = array("Q", [0]) * cells
        self.consolidation_meta = array("I", [0]) * cells
        self.consolidation_hits = 0
        self.consolidation_misses = 0
        self.consolidation_collisions = 0
        self.consolidation_displacements = 0
        self.consolidation_placement_failures = 0
        # Alpha.11: validated feature-projection abstractions. Exact entity IDs are
        # already excluded from the recurrent network, so this layer targets a
        # harder problem: repeated transition structure that remains stable while
        # *visible* nuisance features vary. Candidate projections are promoted only
        # after repeated, diverse, high-precision evidence. Exact late exceptions
        # are retained separately and override a generalized rule.
        self.abstraction_enabled = bool(abstraction_enabled)
        self.abstraction_min_support = max(2, int(abstraction_min_support))
        self.abstraction_min_precision = max(0.5, min(1.0, float(abstraction_min_precision)))
        self.abstraction_min_diversity = max(2, int(abstraction_min_diversity))
        self.abstraction_max_dropped_features = max(1, min(4, int(abstraction_max_dropped_features)))
        self.abstraction_sparse_enabled = bool(abstraction_sparse_enabled)
        self.abstraction_pending_enabled = bool(abstraction_pending_enabled)
        # Alpha.12: high-dimensional nuisance hardening. Alpha.11 could only
        # discover rules reachable by dropping a few visible features. With many
        # independently varying nuisance dimensions, the useful low-dimensional
        # projection might never be proposed. Alpha.12 also proposes bounded
        # sparse projections that retain only one or two visible features while
        # always retaining action and dt. Empirical precision/diversity gates are
        # unchanged, so a sparse candidate is not trusted merely because it exists.
        self.abstraction_sparse_max_retained_features = max(1, min(3, int(abstraction_sparse_max_retained_features)))
        self.abstraction_candidates_per_observation = max(16, min(128, int(abstraction_candidates_per_observation)))
        self.abstraction_max_candidates = max(64, int(abstraction_max_candidates))
        self.abstraction_exception_limit = max(16, int(abstraction_exception_limit))
        self.abstraction_stats: dict[str, dict[str, Any]] = {}
        # Alpha.12 candidate-pressure hardening. Once the validated-candidate
        # table is full, unseen one-off projections enter a tiny FIFO pending
        # pool instead of causing expensive full-table eviction scans. A pending
        # candidate must repeat before it may evict a weak unpromoted main entry.
        self.abstraction_pending_limit = max(16, min(256, self.abstraction_max_candidates // 8))
        self.abstraction_pending_min_support = 2
        self.abstraction_pending: dict[str, dict[str, Any]] = {}
        self.abstraction_pending_promotions = 0
        self.abstraction_candidate_evictions = 0
        self.abstraction_exceptions: dict[str, dict[str, int]] = {}
        self.abstraction_hits = 0
        self.abstraction_misses = 0
        self.abstraction_exception_hits = 0
        self.abstraction_promotions = 0
        self.total_observations = 0
        self.correct_before_learning = 0
        self.ema_error = 1.0

    @staticmethod
    def _canonical_state(state: dict[str, Any]) -> str:
        return json.dumps(state, sort_keys=True, separators=(",", ":"), ensure_ascii=True)

    @staticmethod
    def _scalar(value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if value is None:
            return "null"
        if isinstance(value, float):
            return f"{value:.6g}"
        return str(value).strip().lower()

    @classmethod
    def _features(
        cls,
        state: dict[str, Any],
        action: str,
        neighborhood: dict[str, Any] | None,
        dt: float,
    ) -> list[str]:
        features = [f"action={str(action).strip().lower()}"]
        for key, value in sorted(state.items()):
            features.append(f"state:{str(key).lower()}={cls._scalar(value)}")
        for key, value in sorted((neighborhood or {}).items()):
            features.append(f"neighbor:{str(key).lower()}={cls._scalar(value)}")
        if dt <= 0:
            bucket = "zero"
        elif dt < 0.5:
            bucket = "short"
        elif dt < 2.0:
            bucket = "unit"
        elif dt < 10.0:
            bucket = "medium"
        else:
            bucket = "long"
        features.append(f"dt={bucket}")
        return features


    @classmethod
    def _input_signature(
        cls,
        state: dict[str, Any],
        action: str,
        neighborhood: dict[str, Any] | None,
        dt: float,
    ) -> str:
        return "|".join(cls._features(state, action, neighborhood, dt))

    @staticmethod
    def _replay_stratum(
        state: dict[str, Any], neighborhood: dict[str, Any] | None
    ) -> str:
        # Structural rather than task-name replay strata. Different visible state
        # schemas retain a bounded foothold in replay even when one domain becomes
        # temporarily dominant. This is deliberately generic: no door/switch/etc.
        # knowledge is encoded here.
        state_keys = ",".join(sorted(str(k).lower() for k in state))
        neighbor_keys = ",".join(sorted(str(k).lower() for k in (neighborhood or {})))
        return f"state[{state_keys}]::neighbor[{neighbor_keys}]"

    def _record_conditional_outcome(self, signature: str, slot: int) -> None:
        signature = str(signature)
        slot = int(slot)
        counts = self.conditional_outcome_support.get(signature)
        if counts is None:
            if len(self.conditional_outcome_support) >= self.conditional_outcome_limit:
                victim = min(
                    self.conditional_outcome_support,
                    key=lambda k: (sum(self.conditional_outcome_support[k].values()), k),
                )
                self.conditional_outcome_support.pop(victim, None)
            counts = {}
            self.conditional_outcome_support[signature] = counts
        counts[slot] = int(counts.get(slot, 0)) + 1

    def _conditional_distribution(
        self, signature: str, *, top_k: int = 4, min_support: int | None = None,
    ) -> tuple[list[tuple[int, float, int]], float, int]:
        """Return observed outcome probabilities + residual unknown mass.

        A single unit pseudo-count is reserved for not-yet-observed outcomes.
        Observed relative frequencies therefore stay empirical while finite-data
        uncertainty remains explicit instead of being hidden inside a modal
        softmax confidence.
        """
        counts = {
            int(slot): int(count) for slot, count in
            self.conditional_outcome_support.get(str(signature), {}).items()
            if int(count) > 0 and int(slot) in self.slot_to_outcome
        }
        support = sum(counts.values())
        required = self.conditional_outcome_min_support if min_support is None else max(1, int(min_support))
        if support < required or not counts:
            return [], 1.0, support
        denom = float(support + 1)
        ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        take = max(1, int(top_k))
        kept = ranked[:take]
        outcomes = [(slot, count / denom, count) for slot, count in kept]
        omitted = sum(count for _, count in ranked[take:]) / denom
        unknown = min(1.0, max(0.0, (1.0 / denom) + omitted))
        return outcomes, unknown, support

    def _balanced_replay_trim(self) -> None:
        if len(self.replay) <= self.replay_limit:
            return
        # Evict from the most over-represented structural stratum, preferring the
        # oldest example there. This prevents a long run in one domain from
        # erasing all rehearsal evidence for earlier domains.
        while len(self.replay) > self.replay_limit:
            counts: dict[str, int] = {}
            for item in self.replay:
                key = str(item.get("stratum", "legacy"))
                counts[key] = counts.get(key, 0) + 1
            largest = max(counts, key=lambda k: (counts[k], k))
            drop = next(
                (i for i, item in enumerate(self.replay) if str(item.get("stratum", "legacy")) == largest),
                0,
            )
            self.replay.pop(drop)

    @staticmethod
    def _retention_anchor_key(item: dict[str, Any]) -> str:
        signature = str(item.get("input_signature", ""))
        return f"{signature}::slot={int(item.get('slot', -1))}"

    def _update_retention_anchor(self, item: dict[str, Any]) -> None:
        signature = str(item.get("input_signature", ""))
        if signature in self.retention_ambiguous_signatures:
            return
        # A visible input with multiple observed outcomes requires recurrent or
        # contextual disambiguation. Rehearsing it as a zero-context anchor would
        # flatten the very history signal alpha.3 introduced.
        if self._visible_input_is_ambiguous(signature):
            self.retention_ambiguous_signatures.add(signature)
            for key in [k for k,v in self.retention_anchors.items() if str(v.get("input_signature", "")) == signature]:
                self.retention_anchors.pop(key, None)
            self._clear_consolidated_signature(signature)
            return
        key = self._retention_anchor_key(item)
        if key in self.retention_anchors:
            return
        if len(self.retention_anchors) >= self.retention_anchor_limit:
            # Preserve broad outcome coverage first. Evict from an outcome that
            # already has the most anchors; deterministic ties keep releases
            # reproducible. This is generic and contains no domain labels.
            counts: dict[int, int] = {}
            for anchor in self.retention_anchors.values():
                slot = int(anchor.get("slot", -1))
                counts[slot] = counts.get(slot, 0) + 1
            victim = max(
                self.retention_anchors,
                key=lambda k: (counts.get(int(self.retention_anchors[k].get("slot", -1)), 0), k),
            )
            self.retention_anchors.pop(victim, None)
        self.retention_anchors[key] = dict(item)

    def _retention_anchor_batch(self, budget: int) -> list[dict[str, Any]]:
        if budget <= 0 or not self.retention_anchors:
            return []
        keys = sorted(self.retention_anchors)
        take = min(int(budget), len(keys))
        start = self.retention_anchor_cursor % len(keys)
        selected = [self.retention_anchors[keys[(start + i) % len(keys)]] for i in range(take)]
        self.retention_anchor_cursor = (start + take) % len(keys)
        return [dict(x) for x in selected]

    def _replay_batch(self, current: dict[str, Any]) -> list[dict[str, Any]]:
        # A zero anchor budget is the explicit alpha.5 replay ablation used by the
        # frozen alpha.6 benchmark. Keep the historical selection path exact.
        current_signature = str(current.get("input_signature", ""))
        if (
            self.retention_anchor_batch_limit <= 0
            or len(self.replay) < self.replay_limit
            or self._visible_input_is_ambiguous(current_signature)
        ):
            # Before the recency buffer is full there is no long-horizon eviction
            # problem to solve, so preserve the inherited alpha.3 learning path.
            # Ambiguous inputs likewise keep the full recurrent-learning budget.
            by_stratum: dict[str, list[dict[str, Any]]] = {}
            for item in self.replay[:-1]:
                by_stratum.setdefault(str(item.get("stratum", "legacy")), []).append(item)
            chosen: list[dict[str, Any]] = []
            for key in sorted(by_stratum):
                if len(chosen) >= self.replay_batch_limit - 1:
                    break
                chosen.append(by_stratum[key][-1])
            if len(chosen) < self.replay_batch_limit - 1:
                pool = self.replay[:-1]
                stride = max(1, len(pool) // max(1, self.replay_batch_limit - 1))
                for item in pool[::stride]:
                    if len(chosen) >= self.replay_batch_limit - 1:
                        break
                    if item not in chosen:
                        chosen.append(item)
            return chosen + [current]

        # Alpha.6 reserves part of the fixed replay budget for rotating long-horizon
        # anchors, then uses the remaining budget for recent cross-stratum evidence.
        budget = max(1, self.replay_batch_limit - 1)
        anchors = self._retention_anchor_batch(min(self.retention_anchor_batch_limit, budget))
        chosen: list[dict[str, Any]] = []
        seen = set()
        current_key = self._retention_anchor_key(current)
        for item in anchors:
            key = self._retention_anchor_key(item)
            if key == current_key or key in seen:
                continue
            chosen.append(item); seen.add(key)
        by_stratum: dict[str, list[dict[str, Any]]] = {}
        for item in self.replay[:-1]:
            by_stratum.setdefault(str(item.get("stratum", "legacy")), []).append(item)
        for key in sorted(by_stratum):
            if len(chosen) >= budget:
                break
            item = by_stratum[key][-1]
            ikey = self._retention_anchor_key(item)
            if ikey != current_key and ikey not in seen:
                chosen.append(item); seen.add(ikey)
        if len(chosen) < budget:
            pool = self.replay[:-1]
            stride = max(1, len(pool) // max(1, budget))
            for item in pool[::stride]:
                if len(chosen) >= budget:
                    break
                ikey = self._retention_anchor_key(item)
                if ikey != current_key and ikey not in seen:
                    chosen.append(item); seen.add(ikey)
        return chosen + [current]

    @staticmethod
    def _abstraction_signature_hash(signature: str) -> int:
        return int.from_bytes(hashlib.sha256(("abs-sig|" + signature).encode("utf-8")).digest()[:8], "big")

    def _abstraction_candidates(
        self, state: dict[str, Any], action: str,
        neighborhood: dict[str, Any] | None, dt: float,
    ) -> list[tuple[str, int]]:
        """Return generic feature projections, never dropping action or dt.

        No domain labels or entity-name heuristics are used. Only visible state/
        neighborhood features may be omitted, up to a small bounded number. A
        projection becomes behaviorally active only after empirical validation.
        """
        if not self.abstraction_enabled:
            return []
        features = self._features(state, action, neighborhood, dt)
        visible = [f for f in features if f.startswith("state:") or f.startswith("neighbor:")]
        mandatory = [f for f in features if not (f.startswith("state:") or f.startswith("neighbor:"))]
        removable = [i for i, f in enumerate(features) if f.startswith("state:") or f.startswith("neighbor:")]
        out: list[tuple[str, int]] = []
        seen: set[str] = set()
        limit = self.abstraction_candidates_per_observation

        # Alpha.12 sparse-retention search. This directly reaches low-dimensional
        # rules even when many nuisance features vary. Keep at least one visible
        # contextual feature; action and dt are always mandatory.
        max_keep = min(self.abstraction_sparse_max_retained_features, len(visible)) if self.abstraction_sparse_enabled else 0
        for kept in range(1, max_keep + 1):
            for combo in combinations(visible, kept):
                retained = list(mandatory) + list(combo)
                key = f"keep={kept}|" + "|".join(sorted(retained))
                if key not in seen:
                    out.append((key, max(0, len(visible) - kept)))
                    seen.add(key)
                if len(out) >= limit:
                    return out

        # Preserve alpha.11's local drop-search as a complementary path for rules
        # that depend on most visible features rather than only a sparse subset.
        max_drop = min(self.abstraction_max_dropped_features, len(removable))
        for dropped in range(1, max_drop + 1):
            for combo in combinations(removable, dropped):
                omit = set(combo)
                retained = [f for i, f in enumerate(features) if i not in omit]
                if len(retained) < 3:
                    continue
                key = f"drop={dropped}|" + "|".join(retained)
                if key not in seen:
                    out.append((key, dropped)); seen.add(key)
                if len(out) >= limit:
                    return out
        return out

    @staticmethod
    def _abstraction_best_slot(record: dict[str, Any]) -> tuple[int | None, int, int, float]:
        counts = {int(k): int(v) for k, v in dict(record.get("counts", {})).items()}
        if not counts:
            return None, 0, 0, 0.0
        slot, best = max(counts.items(), key=lambda kv: (kv[1], -kv[0]))
        total = sum(counts.values())
        return int(slot), int(best), int(total), float(best / max(1, total))

    def _abstraction_record_qualifies(self, record: dict[str, Any]) -> bool:
        _, best, total, precision = self._abstraction_best_slot(record)
        diversity = len(record.get("signatures", set()))
        return (
            total >= self.abstraction_min_support
            and best >= self.abstraction_min_support
            and diversity >= self.abstraction_min_diversity
            and precision >= self.abstraction_min_precision
        )

    def _new_abstraction_record(self, dropped: int) -> dict[str, Any]:
        return {
            "counts": {}, "signatures": set(), "support": 0,
            "dropped": int(dropped), "last_seen": int(self.total_observations),
            "promoted": False, "contradictions": set(),
        }

    def _pending_abstraction_record(self, key: str, dropped: int) -> dict[str, Any]:
        record = self.abstraction_pending.get(key)
        if record is None:
            record = self._new_abstraction_record(dropped)
            self.abstraction_pending[key] = record
            while len(self.abstraction_pending) > self.abstraction_pending_limit:
                # FIFO eviction is deliberate: pending entries are unvalidated
                # one-offs, so avoid O(N) ranking work under nuisance explosions.
                oldest = next(iter(self.abstraction_pending))
                if oldest == key and len(self.abstraction_pending) > 1:
                    oldest = next(k for k in self.abstraction_pending if k != key)
                self.abstraction_pending.pop(oldest, None)
        return record

    def _admit_pending_abstraction(self, key: str) -> bool:
        record = self.abstraction_pending.get(key)
        if record is None or int(record.get("support", 0)) < self.abstraction_pending_min_support:
            return False
        if len(self.abstraction_stats) < self.abstraction_max_candidates:
            self.abstraction_stats[key] = record
            self.abstraction_pending.pop(key, None)
            self.abstraction_pending_promotions += 1
            return True
        # Protect currently validated rules. Repeated new evidence may replace
        # only the weakest unpromoted candidate. This makes admission pressure
        # adaptive without letting one-off nuisance keys churn the whole table.
        pool = [k for k, r in self.abstraction_stats.items() if not self._abstraction_record_qualifies(r)]
        if not pool:
            return False
        victim = min(
            pool,
            key=lambda k: (
                int(self.abstraction_stats[k].get("support", 0)),
                len(self.abstraction_stats[k].get("signatures", set())),
                int(self.abstraction_stats[k].get("last_seen", 0)),
                k,
            ),
        )
        victim_record = self.abstraction_stats[victim]
        incoming_rank = (int(record.get("support", 0)), len(record.get("signatures", set())))
        victim_rank = (int(victim_record.get("support", 0)), len(victim_record.get("signatures", set())))
        if incoming_rank <= victim_rank:
            return False
        self.abstraction_stats.pop(victim, None)
        self.abstraction_stats[key] = record
        self.abstraction_pending.pop(key, None)
        self.abstraction_pending_promotions += 1
        self.abstraction_candidate_evictions += 1
        return True

    def _trim_abstraction_candidates(self) -> None:
        while len(self.abstraction_stats) > self.abstraction_max_candidates:
            # Weak, low-diversity, old candidates are discarded first. Promoted
            # high-support candidates naturally survive without a hand-authored
            # domain priority list.
            victim = min(
                self.abstraction_stats,
                key=lambda k: (
                    int(self.abstraction_stats[k].get("support", 0)),
                    len(self.abstraction_stats[k].get("signatures", set())),
                    int(self.abstraction_stats[k].get("last_seen", 0)),
                    k,
                ),
            )
            self.abstraction_stats.pop(victim, None)

    def _query_abstraction(
        self, state: dict[str, Any], action: str,
        neighborhood: dict[str, Any] | None, dt: float, *, track_stats: bool = True,
    ) -> tuple[int | None, float, int, str | None]:
        if not self.abstraction_enabled:
            return None, 0.0, 0, None
        signature = self._input_signature(state, action, neighborhood, dt)
        if signature in self.retention_ambiguous_signatures or self._visible_input_is_ambiguous(signature):
            return None, 0.0, 0, None
        candidates: list[tuple[float, int, int, str, int]] = []
        for key, dropped in self._abstraction_candidates(state, action, neighborhood, dt):
            record = self.abstraction_stats.get(key)
            if not record or not self._abstraction_record_qualifies(record):
                continue
            slot, _, total, precision = self._abstraction_best_slot(record)
            if slot is None or slot >= len(self.outcome_to_slot):
                continue
            diversity = len(record.get("signatures", set()))
            # Prefer precise, diverse evidence; on ties prefer more-specific rules.
            score = precision + min(0.10, math.log2(total + 1) / 100.0) + min(0.05, diversity / 1000.0)
            candidates.append((score, -dropped, total, key, slot))
        if not candidates:
            if track_stats:
                self.abstraction_misses += 1
            return None, 0.0, 0, None
        _, _, total, key, slot = max(candidates)
        record = self.abstraction_stats[key]
        _, _, _, precision = self._abstraction_best_slot(record)
        if track_stats:
            self.abstraction_hits += 1
        return int(slot), float(precision), int(total), key

    def _remember_abstraction_exception(self, signature: str, slot: int) -> None:
        if signature in self.retention_ambiguous_signatures:
            self.abstraction_exceptions.pop(signature, None)
            return
        rec = self.abstraction_exceptions.get(signature)
        if rec and int(rec.get("slot", -1)) == int(slot):
            rec["support"] = int(rec.get("support", 0)) + 1
            return
        self.abstraction_exceptions[signature] = {"slot": int(slot), "support": 1}
        while len(self.abstraction_exceptions) > self.abstraction_exception_limit:
            victim = min(
                self.abstraction_exceptions,
                key=lambda k: (int(self.abstraction_exceptions[k].get("support", 0)), k),
            )
            self.abstraction_exceptions.pop(victim, None)

    def _update_abstractions(
        self, *, state: dict[str, Any], action: str, neighborhood: dict[str, Any] | None,
        dt: float, target_slot: int,
    ) -> None:
        if not self.abstraction_enabled:
            return
        signature = self._input_signature(state, action, neighborhood, dt)
        if self._visible_input_is_ambiguous(signature):
            self.abstraction_exceptions.pop(signature, None)
            return
        sig_hash = self._abstraction_signature_hash(signature)
        before_slot, _, _, _ = self._query_abstraction(state, action, neighborhood, dt)
        if before_slot is not None and int(before_slot) != int(target_slot):
            self._remember_abstraction_exception(signature, target_slot)
        for key, dropped in self._abstraction_candidates(state, action, neighborhood, dt):
            record = self.abstraction_stats.get(key)
            pending = False
            if record is None:
                if self.abstraction_pending_enabled and len(self.abstraction_stats) >= self.abstraction_max_candidates:
                    record = self._pending_abstraction_record(key, dropped)
                    pending = True
                else:
                    record = self._new_abstraction_record(dropped)
                    self.abstraction_stats[key] = record
            counts = record.setdefault("counts", {})
            signatures = record.setdefault("signatures", set())
            if not isinstance(signatures, set):
                signatures = set(signatures); record["signatures"] = signatures
            contradictions = record.setdefault("contradictions", set())
            if not isinstance(contradictions, set):
                contradictions = set(contradictions); record["contradictions"] = contradictions
            qualified_before = self._abstraction_record_qualifies(record)
            best_before, _, _, _ = self._abstraction_best_slot(record)
            if (not pending) and qualified_before and best_before is not None and int(best_before) != int(target_slot):
                # A stable rule meeting a rare exact exception should not be
                # destroyed by repeatedly seeing that same exceptional case. Only
                # diverse contradictory signatures constitute evidence that the
                # abstraction itself is wrong or the dynamics changed broadly.
                if len(contradictions) < 128:
                    contradictions.add(int(sig_hash))
                if len(contradictions) < self.abstraction_min_diversity:
                    record["last_seen"] = int(self.total_observations)
                    continue
            counts[int(target_slot)] = int(counts.get(int(target_slot), 0)) + 1
            if len(signatures) < 128:
                signatures.add(int(sig_hash))
            record["support"] = int(record.get("support", 0)) + 1
            record["last_seen"] = int(self.total_observations)
            if pending:
                if not self._admit_pending_abstraction(key):
                    continue
                record = self.abstraction_stats[key]
            qualifies = self._abstraction_record_qualifies(record)
            if qualifies and not bool(record.get("promoted", False)):
                record["promoted"] = True
                self.abstraction_promotions += 1
        self._trim_abstraction_candidates()
        after_slot, _, _, _ = self._query_abstraction(state, action, neighborhood, dt)
        if after_slot is not None and int(after_slot) != int(target_slot):
            self._remember_abstraction_exception(signature, target_slot)

    @staticmethod
    def _consolidation_fingerprint(signature: str) -> int:
        # 64-bit non-zero fingerprint. Zero is reserved for an empty cell.
        fp = int.from_bytes(hashlib.sha256(("fp|" + signature).encode("utf-8")).digest()[:8], "big")
        return fp or 1

    def _consolidation_indices_from_fp(self, fp: int) -> list[int]:
        """Candidate cells for packed one-copy alpha.10 consolidation."""
        cells = len(self.consolidation_fingerprints)
        if cells <= 0:
            return []
        raw_fp = int(fp).to_bytes(8, "big", signed=False)
        out: list[int] = []
        for choice in range(self.consolidation_hashes):
            person = f"asm-a10-{choice}".encode("ascii")[:16]
            raw = hashlib.blake2b(raw_fp, digest_size=8, person=person).digest()
            idx = int.from_bytes(raw, "big") % cells
            if idx not in out:
                out.append(idx)
        return out

    def _consolidation_indices(self, signature: str) -> list[int]:
        return self._consolidation_indices_from_fp(self._consolidation_fingerprint(signature))

    def _pack_consolidation_meta(self, slot: int, support: int) -> int:
        slot = int(slot)
        if slot < 0 or slot >= self.consolidation_slot_mask:
            raise RuntimeError(
                f"consolidation slot {slot} exceeds packed layout limit {self.consolidation_slot_mask - 1}"
            )
        support = max(1, min(self.consolidation_support_max, int(support)))
        # Store slot+1 so zero meta remains a natural empty/default value.
        return (support << self.consolidation_slot_bits) | (slot + 1)

    def _unpack_consolidation_meta(self, meta: int) -> tuple[int, int]:
        meta = int(meta)
        if meta <= 0:
            return -1, 0
        stored_slot = meta & self.consolidation_slot_mask
        support = (meta >> self.consolidation_slot_bits) & self.consolidation_support_max
        return int(stored_slot - 1), int(support)

    def _cell_slot_support(self, idx: int) -> tuple[int, int]:
        return self._unpack_consolidation_meta(self.consolidation_meta[idx])

    def _set_consolidation_cell(self, idx: int, fp: int, slot: int, support: int) -> None:
        self.consolidation_fingerprints[idx] = int(fp)
        self.consolidation_meta[idx] = self._pack_consolidation_meta(slot, support)

    def _clear_consolidated_signature(self, signature: str) -> None:
        if not self.consolidation_enabled:
            return
        fp = self._consolidation_fingerprint(signature)
        for idx in self._consolidation_indices_from_fp(fp):
            if int(self.consolidation_fingerprints[idx]) == fp:
                self.consolidation_fingerprints[idx] = 0
                self.consolidation_meta[idx] = 0

    def _place_consolidation_record(self, fp: int, slot: int, support: int = 1) -> bool:
        """Place/update one record with bounded augmenting-path relocation.

        Alpha.9 used a greedy cuckoo walk. Alpha.10 searches a bounded graph of
        legal alternate cells first; if a free cell is reachable, entries are
        shifted along that path without dropping any record. Search work is
        capped by consolidation_max_displacements.
        """
        if not self.consolidation_enabled or not self.consolidation_fingerprints:
            return False
        fp = int(fp) or 1
        slot = int(slot)
        support = max(1, min(self.consolidation_support_max, int(support)))
        candidates = self._consolidation_indices_from_fp(fp)
        for idx in candidates:
            if int(self.consolidation_fingerprints[idx]) == fp:
                old_slot, old_support = self._cell_slot_support(idx)
                if old_slot == slot:
                    self._set_consolidation_cell(idx, fp, slot, min(self.consolidation_support_max, old_support + support))
                    return True
        for idx in candidates:
            if int(self.consolidation_fingerprints[idx]) == 0:
                self._set_consolidation_cell(idx, fp, slot, support)
                return True

        self.consolidation_collisions += 1
        # Breadth-first search across occupied candidate cells. parent[x] is the
        # cell whose resident record can legally move into x. A None parent marks
        # a root candidate for the new record.
        from collections import deque
        queue = deque()
        parent: dict[int, int | None] = {}
        for root in sorted(candidates):
            if root not in parent:
                parent[root] = None
                queue.append(root)
        expanded = 0
        found_empty: int | None = None
        while queue and expanded < self.consolidation_max_displacements:
            cell = queue.popleft()
            expanded += 1
            resident_fp = int(self.consolidation_fingerprints[cell])
            if resident_fp == 0:
                found_empty = cell
                break
            for alt in self._consolidation_indices_from_fp(resident_fp):
                if alt == cell:
                    continue
                if int(self.consolidation_fingerprints[alt]) == 0:
                    parent[alt] = cell
                    found_empty = alt
                    queue.clear()
                    break
                if alt not in parent and len(parent) < self.consolidation_max_displacements + len(candidates):
                    parent[alt] = cell
                    queue.append(alt)
            if found_empty is not None:
                break

        if found_empty is not None:
            # Shift resident records toward the empty cell, leaving a root free.
            dst = found_empty
            moves = 0
            while parent.get(dst) is not None:
                src = int(parent[dst])
                src_fp = int(self.consolidation_fingerprints[src])
                src_slot, src_support = self._cell_slot_support(src)
                self._set_consolidation_cell(dst, src_fp, src_slot, src_support)
                dst = src
                moves += 1
            self._set_consolidation_cell(dst, fp, slot, support)
            self.consolidation_displacements += moves
            return True

        # No bounded augmenting path was found. Admit the new mapping by replacing
        # the weakest direct candidate; the evicted key becomes a future miss, not
        # a false recall because fingerprints are exact-match checked.
        def weakness(j: int) -> tuple[int, int]:
            return (self._cell_slot_support(j)[1], j)
        victim = min(candidates, key=weakness)
        self._set_consolidation_cell(victim, fp, slot, support)
        self.consolidation_placement_failures += 1
        return False

    def _update_consolidation(self, item: dict[str, Any]) -> None:
        if not self.consolidation_enabled:
            return
        signature = str(item.get("input_signature", ""))
        if not signature:
            return
        if signature in self.retention_ambiguous_signatures or self._visible_input_is_ambiguous(signature):
            self.retention_ambiguous_signatures.add(signature)
            self._clear_consolidated_signature(signature)
            return
        slot = int(item.get("slot", -1))
        if slot < 0:
            return
        self._place_consolidation_record(self._consolidation_fingerprint(signature), slot, 1)

    def _query_consolidation(
        self, signature: str, *, track_stats: bool = True
    ) -> tuple[int | None, float, int]:
        if (
            not self.consolidation_enabled
            or self.total_observations < self.replay_limit
            or len(self.outcome_to_slot) <= self.retention_anchor_limit
        ):
            return None, 0.0, 0
        if signature in self.retention_ambiguous_signatures:
            return None, 0.0, 0
        fp = self._consolidation_fingerprint(signature)
        best: tuple[int, int] | None = None
        for idx in self._consolidation_indices_from_fp(fp):
            if int(self.consolidation_fingerprints[idx]) != fp:
                continue
            slot, support = self._cell_slot_support(idx)
            if support < self.consolidation_min_support:
                continue
            if best is None or support > best[1] or (support == best[1] and slot < best[0]):
                best = (slot, support)
        if best is None:
            if track_stats:
                self.consolidation_misses += 1
            return None, 0.0, 0
        slot, support = best
        if track_stats:
            self.consolidation_hits += 1
        confidence = min(0.995, 0.93 + 0.0065 * min(10, support))
        return int(slot), float(confidence), int(support)

    def _consolidation_bytes(self) -> int:
        return (
            len(self.consolidation_fingerprints) * self.consolidation_fingerprints.itemsize
            + len(self.consolidation_meta) * self.consolidation_meta.itemsize
        )

    def _visible_input_is_ambiguous(self, signature: str) -> bool:
        outcomes = {
            int(item["slot"]) for item in self.replay
            if str(item.get("input_signature", "")) == signature
        }
        return len(outcomes) > 1

    def _trace_signature_from_trace(
        self, trace: list[dict[str, Any]], *, state: dict[str, Any], action: str,
        neighborhood: dict[str, Any] | None, dt: float,
    ) -> str | None:
        if not trace:
            return None
        parts: list[str] = []
        for item in trace[-1:]:
            parts.append(self._input_signature(
                item.get("state", {}), item.get("action", ""),
                item.get("neighborhood", {}), float(item.get("dt", 1.0)),
            ))
        parts.append(self._input_signature(state, action, neighborhood, dt))
        return ">>".join(parts)

    def _trace_signature(
        self, entity_id: str, *, state: dict[str, Any], action: str,
        neighborhood: dict[str, Any] | None, dt: float,
    ) -> str | None:
        return self._trace_signature_from_trace(
            list(self.context_trace.get(str(entity_id), [])),
            state=state, action=action, neighborhood=neighborhood, dt=dt,
        )

    def _record_trace_outcome(self, signature: str | None, slot: int) -> None:
        if not signature:
            return
        if signature not in self.trace_outcome_support and len(self.trace_outcome_support) >= self.trace_table_limit:
            # Evict the least-supported entry; deterministic tie break by key.
            victim = min(
                self.trace_outcome_support,
                key=lambda k: (sum(self.trace_outcome_support[k].values()), k),
            )
            self.trace_outcome_support.pop(victim, None)
        counts = self.trace_outcome_support.setdefault(signature, {})
        counts[int(slot)] = int(counts.get(int(slot), 0)) + 1

    def _vectorize(self, features: list[str]) -> torch.Tensor:
        vec = torch.zeros(self.input_dim, dtype=torch.float32)
        for feature in features:
            raw = hashlib.sha256(feature.encode("utf-8")).digest()
            idx = int.from_bytes(raw[:4], "big") % self.input_dim
            sign = 1.0 if raw[4] & 1 else -1.0
            vec[idx] += sign
        norm = torch.linalg.vector_norm(vec)
        if float(norm) > 0:
            vec = vec / norm
        return vec.unsqueeze(0)

    def _hidden(self, entity_id: str) -> torch.Tensor:
        hidden = self.context_hidden.get(str(entity_id))
        if hidden is None:
            return torch.zeros((1, self.hidden_dim), dtype=torch.float32)
        return hidden.detach().clone()

    @staticmethod
    def _clone_optimizer_value(value: Any) -> Any:
        if torch is not None and torch.is_tensor(value):
            return value.detach().clone()
        return value

    def _expand_adam_state(self, old_param, new_param, old_rows: int) -> dict[str, Any]:
        state = self.optimizer.state.get(old_param, {})
        expanded: dict[str, Any] = {}
        for key, value in state.items():
            if torch.is_tensor(value) and value.ndim >= 1 and tuple(value.shape) == tuple(old_param.shape):
                target = torch.zeros_like(new_param.data)
                target[:old_rows].copy_(value[:old_rows])
                expanded[key] = target
            else:
                expanded[key] = self._clone_optimizer_value(value)
        return expanded

    def _resize_output_head(self, new_capacity: int, *, count_expansion: bool = True) -> None:
        new_capacity = int(new_capacity)
        old_capacity = int(self.max_outcomes)
        if new_capacity <= old_capacity:
            return
        if new_capacity > self.outcome_capacity_limit:
            raise RuntimeError(
                f"mechanism {self.mechanism_type!r} requested outcome capacity {new_capacity} "
                f"above configured limit={self.outcome_capacity_limit}"
            )
        old_head = self.net.head
        old_weight = old_head.weight
        old_bias = old_head.bias
        # Deterministic initialization for new rows without perturbing global RNG.
        digest = int(hashlib.sha256(
            f"{self.mechanism_type}|capacity|{new_capacity}".encode("utf-8")
        ).hexdigest()[:8], 16)
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(digest % (2**31 - 1))
            replacement = nn.Linear(self.hidden_dim, new_capacity)
        with torch.no_grad():
            replacement.weight[:old_capacity].copy_(old_weight.data)
            replacement.bias[:old_capacity].copy_(old_bias.data)
        self.net.head = replacement

        # Preserve Adam history for unchanged layers and the existing output rows.
        old_optimizer = self.optimizer
        new_optimizer = torch.optim.Adam(self.net.parameters(), lr=self.learning_rate)
        for param in (self.net.input_proj.weight, self.net.input_proj.bias,
                      self.net.gru.weight_ih, self.net.gru.weight_hh,
                      self.net.gru.bias_ih, self.net.gru.bias_hh):
            if param in old_optimizer.state:
                new_optimizer.state[param] = {
                    k: self._clone_optimizer_value(v) for k, v in old_optimizer.state[param].items()
                }
        if old_weight in old_optimizer.state:
            new_optimizer.state[replacement.weight] = self._expand_adam_state(
                old_weight, replacement.weight, old_capacity
            )
        if old_bias in old_optimizer.state:
            new_optimizer.state[replacement.bias] = self._expand_adam_state(
                old_bias, replacement.bias, old_capacity
            )
        self.optimizer = new_optimizer
        self.max_outcomes = new_capacity
        if count_expansion:
            self.capacity_expansions += 1
            self.capacity_history.append(new_capacity)

    def _ensure_outcome(self, after_state: dict[str, Any]) -> int:
        signature = self._canonical_state(after_state)
        slot = self.outcome_to_slot.get(signature)
        if slot is not None:
            return slot
        if len(self.outcome_to_slot) >= self.max_outcomes:
            if self.max_outcomes >= self.outcome_capacity_limit:
                raise RuntimeError(
                    f"mechanism {self.mechanism_type!r} exceeded outcome_capacity_limit="
                    f"{self.outcome_capacity_limit}"
                )
            target = max(self.max_outcomes + 1, int(math.ceil(self.max_outcomes * self.outcome_growth_factor)))
            self._resize_output_head(min(self.outcome_capacity_limit, target))
        slot = len(self.outcome_to_slot)
        self.outcome_to_slot[signature] = slot
        self.slot_to_outcome[slot] = json.loads(signature)
        self.outcome_support[slot] = 0
        return slot

    def predict(
        self,
        *,
        entity_id: str,
        state: dict[str, Any],
        action: str,
        neighborhood: dict[str, Any] | None = None,
        dt: float = 1.0,
    ) -> TransitionPrediction:
        if not self.outcome_to_slot:
            return TransitionPrediction(
                self.mechanism_type, str(entity_id), None, 0.0, 1.0, None, 0, self.total_observations
            )
        self.net.eval()
        x = self._vectorize(self._features(state, action, neighborhood, dt))
        hidden = self._hidden(entity_id)
        with torch.no_grad():
            logits, _ = self.net(x, hidden)
            active = len(self.outcome_to_slot)
            probs = torch.softmax(logits[0, :active], dim=0)
            slot = int(torch.argmax(probs).item())
            raw_conf = float(probs[slot].item())
        visible_signature = self._input_signature(state, action, neighborhood, dt)
        consolidated_slot, consolidated_conf, _ = self._query_consolidation(visible_signature)
        if consolidated_slot is not None and 0 <= consolidated_slot < len(self.outcome_to_slot):
            # Stable explicit transition memory is allowed to override a drifting
            # neural classifier. It is exact-keyed and disabled for ambiguous
            # recurrent cases, so this is memory retrieval rather than a claim
            # of neural generalization.
            slot = int(consolidated_slot)
            raw_conf = max(raw_conf, float(consolidated_conf))
        else:
            exception = self.abstraction_exceptions.get(visible_signature)
            if exception is not None and 0 <= int(exception.get("slot", -1)) < len(self.outcome_to_slot):
                slot = int(exception["slot"])
                raw_conf = max(raw_conf, min(0.99, 0.90 + 0.01 * min(9, int(exception.get("support", 1)))))
                self.abstraction_exception_hits += 1
            else:
                abstract_slot, abstract_conf, _, _ = self._query_abstraction(state, action, neighborhood, dt)
                if abstract_slot is not None and 0 <= abstract_slot < len(self.outcome_to_slot):
                    slot = int(abstract_slot)
                    raw_conf = max(raw_conf, min(0.98, 0.86 + 0.12 * float(abstract_conf)))
        trace_signature = self._trace_signature(
            str(entity_id), state=state, action=action, neighborhood=neighborhood, dt=dt
        )
        if trace_signature:
            counts = self.trace_outcome_support.get(trace_signature, {})
            trace_support = sum(int(v) for v in counts.values())
            if trace_support >= self.trace_min_support and counts:
                trace_slot, trace_count = max(counts.items(), key=lambda kv: (int(kv[1]), -int(kv[0])))
                trace_precision = int(trace_count) / max(1, trace_support)
                if (
                    int(trace_slot) < active
                    and trace_precision >= 0.80
                    and raw_conf < self.trace_max_neural_confidence
                ):
                    slot = int(trace_slot)
                    raw_conf = max(raw_conf, min(0.95, 0.90 * trace_precision))
                    self.trace_fallback_hits += 1
        support_factor = min(1.0, math.log2(self.total_observations + 1.0) / 5.0)
        calibration = max(0.05, 1.0 - float(self.ema_error))
        recent_surprise = max(0.0, min(1.0, float(self.context_surprise.get(str(entity_id), 0.0))))
        confidence = max(0.0, min(1.0, raw_conf * (0.35 + 0.65 * support_factor) * (0.5 + 0.5 * calibration)))
        confidence *= (1.0 - 0.65 * recent_surprise)
        return TransitionPrediction(
            mechanism_type=self.mechanism_type,
            entity_id=str(entity_id),
            predicted_state=dict(self.slot_to_outcome[slot]),
            confidence=confidence,
            uncertainty=1.0 - confidence,
            outcome_slot=slot,
            known_outcomes=active,
            support=self.total_observations,
        )

    def predict_simulated(
        self,
        *,
        entity_id: str,
        state: dict[str, Any],
        action: str,
        neighborhood: dict[str, Any] | None = None,
        dt: float = 1.0,
        simulation_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Read-only transition prediction with branch-local recurrent context.

        This is the v0.4-alpha.2 planning path. It does not mutate diagnostic
        hit/miss counters, learned weights, replay, stored entity context, or
        observation counts. The returned opaque context can be passed into the
        next simulated branch step.
        """
        if not self.outcome_to_slot:
            result = TransitionPrediction(
                self.mechanism_type, str(entity_id), None, 0.0, 1.0, None, 0, self.total_observations
            ).as_dict()
            result["_simulation_context"] = simulation_context
            result["_simulation_context_key"] = "empty"
            return result

        self.net.eval()
        if simulation_context is None:
            hidden = self._hidden(entity_id)
            trace = list(self.context_trace.get(str(entity_id), []))
            recent_surprise = max(0.0, min(1.0, float(self.context_surprise.get(str(entity_id), 0.0))))
        else:
            raw_hidden = simulation_context.get("hidden")
            hidden = (
                raw_hidden.detach().clone()
                if torch is not None and torch.is_tensor(raw_hidden)
                else self._hidden(entity_id)
            )
            trace = list(simulation_context.get("trace", []))
            recent_surprise = max(0.0, min(1.0, float(simulation_context.get("surprise", 0.0))))

        x = self._vectorize(self._features(state, action, neighborhood, dt))
        with torch.no_grad():
            logits, next_hidden = self.net(x, hidden)
            active = len(self.outcome_to_slot)
            probs = torch.softmax(logits[0, :active], dim=0)
            slot = int(torch.argmax(probs).item())
            raw_conf = float(probs[slot].item())

        visible_signature = self._input_signature(state, action, neighborhood, dt)
        consolidated_slot, consolidated_conf, _ = self._query_consolidation(
            visible_signature, track_stats=False
        )
        if consolidated_slot is not None and 0 <= consolidated_slot < len(self.outcome_to_slot):
            slot = int(consolidated_slot)
            raw_conf = max(raw_conf, float(consolidated_conf))
        else:
            exception = self.abstraction_exceptions.get(visible_signature)
            if exception is not None and 0 <= int(exception.get("slot", -1)) < len(self.outcome_to_slot):
                slot = int(exception["slot"])
                raw_conf = max(raw_conf, min(0.99, 0.90 + 0.01 * min(9, int(exception.get("support", 1)))))
            else:
                abstract_slot, abstract_conf, _, _ = self._query_abstraction(
                    state, action, neighborhood, dt, track_stats=False
                )
                if abstract_slot is not None and 0 <= abstract_slot < len(self.outcome_to_slot):
                    slot = int(abstract_slot)
                    raw_conf = max(raw_conf, min(0.98, 0.86 + 0.12 * float(abstract_conf)))

        trace_signature = self._trace_signature_from_trace(
            trace, state=state, action=action, neighborhood=neighborhood, dt=dt
        )
        if trace_signature:
            counts = self.trace_outcome_support.get(trace_signature, {})
            trace_support = sum(int(v) for v in counts.values())
            if trace_support >= self.trace_min_support and counts:
                trace_slot, trace_count = max(counts.items(), key=lambda kv: (int(kv[1]), -int(kv[0])))
                trace_precision = int(trace_count) / max(1, trace_support)
                if (
                    int(trace_slot) < active
                    and trace_precision >= 0.80
                    and raw_conf < self.trace_max_neural_confidence
                ):
                    slot = int(trace_slot)
                    raw_conf = max(raw_conf, min(0.95, 0.90 * trace_precision))

        support_factor = min(1.0, math.log2(self.total_observations + 1.0) / 5.0)
        calibration = max(0.05, 1.0 - float(self.ema_error))
        confidence = max(0.0, min(1.0, raw_conf * (0.35 + 0.65 * support_factor) * (0.5 + 0.5 * calibration)))
        confidence *= (1.0 - 0.65 * recent_surprise)

        new_trace = trace + [{
            "state": dict(state),
            "action": str(action),
            "neighborhood": dict(neighborhood or {}),
            "dt": float(dt),
        }]
        new_trace = new_trace[-self.context_trace_limit:]
        context_key_material = "||".join(
            self._input_signature(
                item.get("state", {}), item.get("action", ""),
                item.get("neighborhood", {}), float(item.get("dt", 1.0)),
            )
            for item in new_trace
        )
        context_key = hashlib.sha256(context_key_material.encode("utf-8")).hexdigest()[:20]
        result = TransitionPrediction(
            mechanism_type=self.mechanism_type,
            entity_id=str(entity_id),
            predicted_state=dict(self.slot_to_outcome[slot]),
            confidence=confidence,
            uncertainty=1.0 - confidence,
            outcome_slot=slot,
            known_outcomes=active,
            support=self.total_observations,
        ).as_dict()
        result["_simulation_context"] = {
            "hidden": next_hidden.detach().clone(),
            "trace": new_trace,
            "surprise": recent_surprise,
        }
        result["_simulation_context_key"] = context_key
        return result

    def predict_distribution_simulated(
        self,
        *,
        entity_id: str,
        state: dict[str, Any],
        action: str,
        neighborhood: dict[str, Any] | None = None,
        dt: float = 1.0,
        simulation_context: dict[str, Any] | None = None,
        top_k: int = 4,
        empirical_min_support: int | None = None,
    ) -> dict[str, Any]:
        """Read-only bounded distribution over plausible next states.

        Exact observed frequencies are used when enough evidence exists. Neural
        prediction remains a fallback, but is labelled uncalibrated and carries
        explicit residual unknown mass rather than masquerading as a probability
        distribution.
        """
        modal = self.predict_simulated(
            entity_id=entity_id, state=state, action=action,
            neighborhood=neighborhood, dt=dt, simulation_context=simulation_context,
        )
        signature = self._input_signature(state, action, neighborhood, dt)
        empirical, unknown, support = self._conditional_distribution(
            signature, top_k=top_k, min_support=empirical_min_support,
        )
        if empirical:
            outcomes = [
                {
                    "predicted_state": dict(self.slot_to_outcome[slot]),
                    "probability": float(prob),
                    "conditional_probability": float(count / max(1, support)),
                    "support": int(count),
                    "outcome_slot": int(slot),
                }
                for slot, prob, count in empirical
            ]
            source = "empirical_visible"
        elif modal.get("predicted_state") is not None:
            # A neural confidence is not treated as calibrated probability. Cap
            # the committed mass so the planner remains aware that alternatives
            # may exist until repeated empirical outcomes are available.
            modal_mass = min(0.75, max(0.05, float(modal.get("confidence", 0.0))))
            outcomes = [{
                "predicted_state": dict(modal["predicted_state"]),
                "probability": modal_mass,
                "support": 0,
                "outcome_slot": modal.get("outcome_slot"),
            }]
            unknown = 1.0 - modal_mass
            source = "neural_uncalibrated"
        else:
            outcomes = []
            unknown = 1.0
            source = "no_prediction"
        return {
            "mechanism_type": self.mechanism_type,
            "entity_id": str(entity_id),
            "outcomes": outcomes,
            "unknown_probability": float(max(0.0, min(1.0, unknown))),
            "support": int(support),
            "probability_source": source,
            "calibrated": source == "empirical_visible",
            "_simulation_context": modal.get("_simulation_context"),
            "_simulation_context_key": modal.get("_simulation_context_key", ""),
        }

    def observe(
        self,
        *,
        entity_id: str,
        state: dict[str, Any],
        action: str,
        after_state: dict[str, Any],
        neighborhood: dict[str, Any] | None = None,
        dt: float = 1.0,
    ) -> dict[str, Any]:
        before = self.predict(
            entity_id=entity_id, state=state, action=action, neighborhood=neighborhood, dt=dt
        )
        target_slot = self._ensure_outcome(after_state)
        target_signature = self._canonical_state(after_state)
        correct = (
            before.predicted_state is not None
            and self._canonical_state(before.predicted_state) == target_signature
        )
        if correct:
            self.correct_before_learning += 1

        x = self._vectorize(self._features(state, action, neighborhood, dt))
        initial_hidden = self._hidden(entity_id)
        prior_trace = list(self.context_trace.get(str(entity_id), []))
        trace_signature = self._trace_signature_from_trace(
            prior_trace, state=state, action=action, neighborhood=neighborhood, dt=dt
        )
        target = torch.tensor([target_slot], dtype=torch.long)

        # Bounded replay protects previously learned local rules while a new
        # exception is being acquired. Replay examples are trained from a zero
        # recurrent state so the shared mechanism cannot rely on memorized
        # entity contexts for transfer. The current observation also receives a
        # smaller recurrent-context loss, preserving sequence sensitivity.
        replay_item = {
            "state": dict(state),
            "action": str(action),
            "neighborhood": dict(neighborhood or {}),
            "dt": float(dt),
            "slot": int(target_slot),
            "stratum": self._replay_stratum(state, neighborhood),
            "input_signature": self._input_signature(state, action, neighborhood, dt),
        }
        self._record_conditional_outcome(replay_item["input_signature"], target_slot)
        self.replay.append(replay_item)
        self._balanced_replay_trim()
        self._update_retention_anchor(replay_item)
        self._update_consolidation(replay_item)
        self._update_abstractions(
            state=state, action=action, neighborhood=neighborhood, dt=dt, target_slot=target_slot
        )
        batch = self._replay_batch(replay_item)
        current_ambiguous = self._visible_input_is_ambiguous(replay_item["input_signature"])

        self.net.train()
        last_loss = 0.0
        for _ in range(self.train_steps):
            self.optimizer.zero_grad(set_to_none=True)
            losses = []
            zero = torch.zeros((1, self.hidden_dim), dtype=torch.float32)
            for item in batch:
                signature = str(item.get("input_signature") or self._input_signature(
                    item["state"], item["action"], item["neighborhood"], item["dt"]
                ))
                # A visible input that maps to more than one observed outcome is
                # evidence that zero-context prediction is insufficient. Do not
                # force the feed-forward path to average contradictory history-
                # dependent targets; let recurrent context disambiguate them.
                if self._visible_input_is_ambiguous(signature):
                    continue
                bx = self._vectorize(self._features(
                    item["state"], item["action"], item["neighborhood"], item["dt"]
                ))
                logits, _ = self.net(bx, zero)
                bt = torch.tensor([int(item["slot"])], dtype=torch.long)
                losses.append(torch.nn.functional.cross_entropy(logits, bt))
            # Bounded truncated recurrent credit assignment. Reconstruct the
            # recent context inside this graph so a history-dependent error can
            # update how earlier inputs are encoded, instead of treating the
            # previous hidden state as an immutable detached constant.
            trace_hidden = torch.zeros((1, self.hidden_dim), dtype=torch.float32)
            for trace_item in prior_trace[-self.context_trace_limit:]:
                tx = self._vectorize(self._features(
                    trace_item["state"], trace_item["action"],
                    trace_item.get("neighborhood", {}), float(trace_item.get("dt", 1.0))
                ))
                _, trace_hidden = self.net(tx, trace_hidden)
            context_logits, _ = self.net(x, trace_hidden)
            context_weight = 1.0 if current_ambiguous else 0.25
            losses.append(context_weight * torch.nn.functional.cross_entropy(context_logits, target))
            loss = torch.stack(losses).mean()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.net.parameters(), 2.0)
            self.optimizer.step()
            last_loss = float(loss.detach().item())
        with torch.no_grad():
            rebuilt = torch.zeros((1, self.hidden_dim), dtype=torch.float32)
            for trace_item in prior_trace[-self.context_trace_limit:]:
                tx = self._vectorize(self._features(
                    trace_item["state"], trace_item["action"],
                    trace_item.get("neighborhood", {}), float(trace_item.get("dt", 1.0))
                ))
                _, rebuilt = self.net(tx, rebuilt)
            _, context = self.net(x, rebuilt)
        self.context_hidden[str(entity_id)] = context.detach()
        trace_item = {
            "state": dict(state), "action": str(action),
            "neighborhood": dict(neighborhood or {}), "dt": float(dt),
        }
        trace = prior_trace + [trace_item]
        self.context_trace[str(entity_id)] = trace[-self.context_trace_limit:]
        self.total_observations += 1
        self.outcome_support[target_slot] = self.outcome_support.get(target_slot, 0) + 1
        self._record_trace_outcome(trace_signature, target_slot)
        error = 0.0 if correct else 1.0
        self.ema_error = 0.92 * float(self.ema_error) + 0.08 * error
        previous_surprise = float(self.context_surprise.get(str(entity_id), 0.0))
        self.context_surprise[str(entity_id)] = min(1.0, 0.55 * previous_surprise + error)
        after = self.predict(
            entity_id=entity_id, state=state, action=action, neighborhood=neighborhood, dt=dt
        )
        return {
            "mechanism_type": self.mechanism_type,
            "entity_id": str(entity_id),
            "before_prediction": before.as_dict(),
            "after_training_prediction": after.as_dict(),
            "observed_after_state": dict(after_state),
            "target_slot": int(target_slot),
            "correct_before_learning": bool(correct),
            "prediction_error": float(error),
            "loss": float(last_loss),
            "ema_error": float(self.ema_error),
            "recent_surprise": float(self.context_surprise.get(str(entity_id), 0.0)),
            "support": int(self.total_observations),
        }

    def reset_context(self, entity_id: str | None = None) -> None:
        if entity_id is None:
            self.context_hidden.clear()
            self.context_surprise.clear()
            self.context_trace.clear()
        else:
            self.context_hidden.pop(str(entity_id), None)
            self.context_surprise.pop(str(entity_id), None)
            self.context_trace.pop(str(entity_id), None)

    def export_blob(self) -> bytes:
        buffer = io.BytesIO()
        torch.save(
            {
                "state_dict": self.net.state_dict(),
                "optimizer": self.optimizer.state_dict(),
                "outcome_to_slot": self.outcome_to_slot,
                "slot_to_outcome": self.slot_to_outcome,
                "outcome_support": self.outcome_support,
                "context_hidden": {k: v.cpu() for k, v in self.context_hidden.items()},
                "context_surprise": self.context_surprise,
                "context_trace": self.context_trace,
                "context_trace_limit": self.context_trace_limit,
                "trace_outcome_support": self.trace_outcome_support,
                "trace_table_limit": self.trace_table_limit,
                "trace_min_support": self.trace_min_support,
                "trace_max_neural_confidence": self.trace_max_neural_confidence,
                "conditional_outcome_support": self.conditional_outcome_support,
                "conditional_outcome_limit": self.conditional_outcome_limit,
                "conditional_outcome_min_support": self.conditional_outcome_min_support,
                "replay": self.replay,
                "replay_limit": self.replay_limit,
                "replay_batch_limit": self.replay_batch_limit,
                "retention_anchors": self.retention_anchors,
                "retention_ambiguous_signatures": sorted(self.retention_ambiguous_signatures),
                "retention_anchor_limit": self.retention_anchor_limit,
                "retention_anchor_batch_limit": self.retention_anchor_batch_limit,
                "retention_anchor_cursor": self.retention_anchor_cursor,
                "total_observations": self.total_observations,
                "correct_before_learning": self.correct_before_learning,
                "ema_error": self.ema_error,
                "input_dim": self.input_dim,
                "hidden_dim": self.hidden_dim,
                "max_outcomes": self.max_outcomes,
                "outcome_capacity_limit": self.outcome_capacity_limit,
                "outcome_growth_factor": self.outcome_growth_factor,
                "capacity_expansions": self.capacity_expansions,
                "capacity_history": self.capacity_history,
                "consolidation_enabled": self.consolidation_enabled,
                "consolidation_table_size": self.consolidation_table_size,
                "consolidation_hashes": self.consolidation_hashes,
                "consolidation_min_support": self.consolidation_min_support,
                "consolidation_layout_version": self.consolidation_layout_version,
                "consolidation_max_displacements": self.consolidation_max_displacements,
                "consolidation_byte_budget": self.consolidation_byte_budget,
                "consolidation_fingerprints": self.consolidation_fingerprints.tobytes(),
                "consolidation_meta": self.consolidation_meta.tobytes(),
                "consolidation_hits": self.consolidation_hits,
                "consolidation_misses": self.consolidation_misses,
                "consolidation_collisions": self.consolidation_collisions,
                "consolidation_displacements": self.consolidation_displacements,
                "consolidation_placement_failures": self.consolidation_placement_failures,
                "abstraction_enabled": self.abstraction_enabled,
                "abstraction_min_support": self.abstraction_min_support,
                "abstraction_min_precision": self.abstraction_min_precision,
                "abstraction_min_diversity": self.abstraction_min_diversity,
                "abstraction_max_dropped_features": self.abstraction_max_dropped_features,
                "abstraction_sparse_enabled": self.abstraction_sparse_enabled,
                "abstraction_pending_enabled": self.abstraction_pending_enabled,
                "abstraction_sparse_max_retained_features": self.abstraction_sparse_max_retained_features,
                "abstraction_candidates_per_observation": self.abstraction_candidates_per_observation,
                "abstraction_max_candidates": self.abstraction_max_candidates,
                "abstraction_exception_limit": self.abstraction_exception_limit,
                "abstraction_stats": self.abstraction_stats,
                "abstraction_pending_limit": self.abstraction_pending_limit,
                "abstraction_pending_min_support": self.abstraction_pending_min_support,
                "abstraction_pending": self.abstraction_pending,
                "abstraction_pending_promotions": self.abstraction_pending_promotions,
                "abstraction_candidate_evictions": self.abstraction_candidate_evictions,
                "abstraction_exceptions": self.abstraction_exceptions,
                "abstraction_hits": self.abstraction_hits,
                "abstraction_misses": self.abstraction_misses,
                "abstraction_exception_hits": self.abstraction_exception_hits,
                "abstraction_promotions": self.abstraction_promotions,
                "learning_rate": self.learning_rate,
                "train_steps": self.train_steps,
            },
            buffer,
        )
        return buffer.getvalue()

    def import_blob(self, blob: bytes) -> None:
        payload = torch.load(io.BytesIO(blob), map_location="cpu", weights_only=False)
        saved_capacity = int(payload.get("max_outcomes", self.max_outcomes))
        saved_limit = int(payload.get("outcome_capacity_limit", max(saved_capacity, self.outcome_capacity_limit)))
        self.outcome_capacity_limit = max(saved_capacity, saved_limit, self.outcome_capacity_limit)
        self.outcome_growth_factor = max(1.25, float(payload.get("outcome_growth_factor", self.outcome_growth_factor)))
        if saved_capacity > self.max_outcomes:
            self._resize_output_head(saved_capacity, count_expansion=False)
        self.net.load_state_dict(payload["state_dict"])
        try:
            self.optimizer.load_state_dict(payload["optimizer"])
        except Exception:
            pass
        self.capacity_expansions = int(payload.get("capacity_expansions", 0))
        self.capacity_history = [int(x) for x in payload.get("capacity_history", [saved_capacity])]
        if not self.capacity_history:
            self.capacity_history = [saved_capacity]
        self.consolidation_enabled = bool(payload.get("consolidation_enabled", self.consolidation_enabled))
        self.consolidation_table_size = int(payload.get("consolidation_table_size", self.consolidation_table_size))
        self.consolidation_hashes = int(payload.get("consolidation_hashes", self.consolidation_hashes))
        self.consolidation_min_support = int(payload.get("consolidation_min_support", self.consolidation_min_support))
        saved_layout = int(payload.get("consolidation_layout_version", 1))
        self.consolidation_layout_version = 3
        self.consolidation_max_displacements = int(payload.get("consolidation_max_displacements", self.consolidation_max_displacements))
        self.consolidation_slot_bits = 20
        self.consolidation_support_bits = 12
        self.consolidation_slot_mask = (1 << self.consolidation_slot_bits) - 1
        self.consolidation_support_max = (1 << self.consolidation_support_bits) - 1
        self.consolidation_byte_budget = int(payload.get(
            "consolidation_byte_budget",
            self.consolidation_table_size * self.consolidation_hashes * 14 if self.consolidation_enabled else 0,
        ))
        cells = self.consolidation_byte_budget // 12 if self.consolidation_enabled else 0

        def _restore_array(typecode: str, raw: Any, expected: int, default: int):
            arr = array(typecode)
            if isinstance(raw, (bytes, bytearray)):
                arr.frombytes(bytes(raw))
            if len(arr) != expected:
                arr = array(typecode, [default]) * expected
            return arr

        if saved_layout >= 3 and payload.get("consolidation_meta") is not None:
            self.consolidation_fingerprints = _restore_array("Q", payload.get("consolidation_fingerprints"), cells, 0)
            self.consolidation_meta = _restore_array("I", payload.get("consolidation_meta"), cells, 0)
        else:
            # Alpha.8/alpha.9 used 14-byte logical cells with separate int32 slot
            # and uint16 support arrays. Repack every unique live record into the
            # denser alpha.10 layout without increasing the byte budget.
            old_cells = self.consolidation_table_size * self.consolidation_hashes if self.consolidation_enabled else 0
            old_fps = _restore_array("Q", payload.get("consolidation_fingerprints"), old_cells, 0)
            old_slots = _restore_array("i", payload.get("consolidation_slots"), old_cells, -1)
            old_support = _restore_array("H", payload.get("consolidation_support"), old_cells, 0)
            legacy_records: dict[tuple[int, int], int] = {}
            for old_fp, old_slot, old_sup in zip(old_fps, old_slots, old_support):
                fp_i, slot_i, sup_i = int(old_fp), int(old_slot), int(old_sup)
                if fp_i and slot_i >= 0:
                    key = (fp_i, slot_i)
                    legacy_records[key] = max(legacy_records.get(key, 0), sup_i)
            self.consolidation_fingerprints = array("Q", [0]) * cells
            self.consolidation_meta = array("I", [0]) * cells
            for (fp_i, slot_i), sup_i in legacy_records.items():
                self._place_consolidation_record(fp_i, slot_i, max(1, sup_i))
        self.consolidation_hits = int(payload.get("consolidation_hits", 0))
        self.consolidation_misses = int(payload.get("consolidation_misses", 0))
        self.consolidation_collisions = int(payload.get("consolidation_collisions", self.consolidation_collisions))
        self.consolidation_displacements = int(payload.get("consolidation_displacements", self.consolidation_displacements))
        self.consolidation_placement_failures = int(payload.get("consolidation_placement_failures", self.consolidation_placement_failures))
        self.abstraction_enabled = bool(payload.get("abstraction_enabled", self.abstraction_enabled))
        self.abstraction_min_support = int(payload.get("abstraction_min_support", self.abstraction_min_support))
        self.abstraction_min_precision = float(payload.get("abstraction_min_precision", self.abstraction_min_precision))
        self.abstraction_min_diversity = int(payload.get("abstraction_min_diversity", self.abstraction_min_diversity))
        self.abstraction_max_dropped_features = int(payload.get("abstraction_max_dropped_features", self.abstraction_max_dropped_features))
        self.abstraction_sparse_enabled = bool(payload.get("abstraction_sparse_enabled", self.abstraction_sparse_enabled))
        self.abstraction_pending_enabled = bool(payload.get("abstraction_pending_enabled", self.abstraction_pending_enabled))
        self.abstraction_sparse_max_retained_features = int(payload.get("abstraction_sparse_max_retained_features", self.abstraction_sparse_max_retained_features))
        self.abstraction_candidates_per_observation = int(payload.get("abstraction_candidates_per_observation", self.abstraction_candidates_per_observation))
        self.abstraction_max_candidates = int(payload.get("abstraction_max_candidates", self.abstraction_max_candidates))
        self.abstraction_exception_limit = int(payload.get("abstraction_exception_limit", self.abstraction_exception_limit))
        self.abstraction_stats = {}
        for key, raw in dict(payload.get("abstraction_stats", {})).items():
            rec = dict(raw)
            rec["counts"] = {int(k): int(v) for k, v in dict(rec.get("counts", {})).items()}
            rec["signatures"] = {int(x) for x in rec.get("signatures", set())}
            rec["contradictions"] = {int(x) for x in rec.get("contradictions", set())}
            self.abstraction_stats[str(key)] = rec
        self.abstraction_pending_limit = int(payload.get("abstraction_pending_limit", self.abstraction_pending_limit))
        self.abstraction_pending_min_support = int(payload.get("abstraction_pending_min_support", self.abstraction_pending_min_support))
        self.abstraction_pending = {}
        for key, raw in dict(payload.get("abstraction_pending", {})).items():
            rec = dict(raw)
            rec["counts"] = {int(k): int(v) for k, v in dict(rec.get("counts", {})).items()}
            rec["signatures"] = {int(x) for x in rec.get("signatures", set())}
            rec["contradictions"] = {int(x) for x in rec.get("contradictions", set())}
            self.abstraction_pending[str(key)] = rec
        self.abstraction_pending_promotions = int(payload.get("abstraction_pending_promotions", 0))
        self.abstraction_candidate_evictions = int(payload.get("abstraction_candidate_evictions", 0))
        self.abstraction_exceptions = {
            str(k): {"slot": int(v.get("slot", -1)), "support": int(v.get("support", 0))}
            for k, v in dict(payload.get("abstraction_exceptions", {})).items()
        }
        self.abstraction_hits = int(payload.get("abstraction_hits", 0))
        self.abstraction_misses = int(payload.get("abstraction_misses", 0))
        self.abstraction_exception_hits = int(payload.get("abstraction_exception_hits", 0))
        self.abstraction_promotions = int(payload.get("abstraction_promotions", 0))
        self.outcome_to_slot = {str(k): int(v) for k, v in payload.get("outcome_to_slot", {}).items()}
        self.slot_to_outcome = {int(k): dict(v) for k, v in payload.get("slot_to_outcome", {}).items()}
        self.outcome_support = {int(k): int(v) for k, v in payload.get("outcome_support", {}).items()}
        self.context_hidden = {
            str(k): v.detach().cpu() for k, v in payload.get("context_hidden", {}).items()
        }
        self.context_surprise = {str(k): float(v) for k, v in payload.get("context_surprise", {}).items()}
        self.context_trace = {str(k): list(v) for k, v in payload.get("context_trace", {}).items()}
        self.context_trace_limit = int(payload.get("context_trace_limit", 4))
        self.trace_outcome_support = {
            str(k): {int(slot): int(count) for slot, count in dict(v).items()}
            for k, v in payload.get("trace_outcome_support", {}).items()
        }
        self.trace_table_limit = int(payload.get("trace_table_limit", 512))
        self.trace_min_support = int(payload.get("trace_min_support", 3))
        self.trace_max_neural_confidence = float(payload.get("trace_max_neural_confidence", 0.75))
        self.trace_fallback_hits = 0
        self.conditional_outcome_limit = int(payload.get("conditional_outcome_limit", 2048))
        self.conditional_outcome_min_support = int(payload.get("conditional_outcome_min_support", 6))
        self.conditional_outcome_support = {
            str(sig): {int(slot): int(count) for slot, count in dict(counts).items()}
            for sig, counts in dict(payload.get("conditional_outcome_support", {})).items()
        }
        self.replay = list(payload.get("replay", []))
        self.replay_limit = int(payload.get("replay_limit", 256))
        self.replay_batch_limit = int(payload.get("replay_batch_limit", 14))
        self.retention_anchors = {str(k): dict(v) for k, v in payload.get("retention_anchors", {}).items()}
        self.retention_ambiguous_signatures = {str(x) for x in payload.get("retention_ambiguous_signatures", [])}
        self.retention_anchor_limit = int(payload.get("retention_anchor_limit", 96))
        self.retention_anchor_batch_limit = int(payload.get("retention_anchor_batch_limit", 6))
        self.retention_anchor_cursor = int(payload.get("retention_anchor_cursor", 0))
        # Upgrade alpha.2-alpha.5 replay records in memory without changing persisted experience rows.
        for item in self.replay:
            item.setdefault("stratum", self._replay_stratum(item.get("state", {}), item.get("neighborhood", {})))
            item.setdefault("input_signature", self._input_signature(
                item.get("state", {}), item.get("action", ""), item.get("neighborhood", {}), float(item.get("dt", 1.0))
            ))
        if not self.conditional_outcome_support:
            for item in self.replay:
                self._record_conditional_outcome(
                    str(item.get("input_signature", "")), int(item.get("slot", -1))
                )
        self._balanced_replay_trim()
        if not self.retention_anchors:
            for item in self.replay:
                self._update_retention_anchor(item)
        self.total_observations = int(payload.get("total_observations", 0))
        self.correct_before_learning = int(payload.get("correct_before_learning", 0))
        self.ema_error = float(payload.get("ema_error", 1.0))

    def stats(self) -> dict[str, Any]:
        accuracy = self.correct_before_learning / self.total_observations if self.total_observations else 0.0
        params = sum(p.numel() for p in self.net.parameters())
        return {
            "mechanism_type": self.mechanism_type,
            "observations": self.total_observations,
            "known_outcomes": len(self.outcome_to_slot),
            "outcome_capacity": self.max_outcomes,
            "outcome_capacity_limit": self.outcome_capacity_limit,
            "capacity_expansions": self.capacity_expansions,
            "capacity_history": list(self.capacity_history),
            "contexts": len(self.context_hidden),
            "traced_contexts": len(self.context_trace),
            "context_trace_limit": self.context_trace_limit,
            "trace_fallback_entries": len(self.trace_outcome_support),
            "trace_fallback_support": sum(sum(v.values()) for v in self.trace_outcome_support.values()),
            "trace_fallback_hits": self.trace_fallback_hits,
            "conditional_distribution_inputs": len(self.conditional_outcome_support),
            "conditional_distribution_support": sum(sum(v.values()) for v in self.conditional_outcome_support.values()),
            "conditional_distribution_ambiguous": sum(1 for v in self.conditional_outcome_support.values() if len(v) > 1),
            "surprised_contexts": sum(1 for v in self.context_surprise.values() if v > 0.25),
            "replay_size": len(self.replay),
            "retention_anchors": len(self.retention_anchors),
            "retention_anchor_outcomes": len({int(v.get("slot", -1)) for v in self.retention_anchors.values()}),
            "retention_ambiguous_inputs": len(self.retention_ambiguous_signatures),
            "retention_anchor_limit": self.retention_anchor_limit,
            "retention_anchor_batch_limit": self.retention_anchor_batch_limit,
            "consolidation_enabled": self.consolidation_enabled,
            "consolidation_table_size": self.consolidation_table_size,
            "consolidation_hashes": self.consolidation_hashes,
            "consolidation_layout_version": self.consolidation_layout_version,
            "consolidation_max_displacements": self.consolidation_max_displacements,
            "consolidation_cells": len(self.consolidation_fingerprints),
            "consolidation_byte_budget": self.consolidation_byte_budget,
            "consolidation_used_cells": sum(1 for fp in self.consolidation_fingerprints if int(fp) != 0),
            "consolidation_bytes": self._consolidation_bytes(),
            "consolidation_hits": self.consolidation_hits,
            "consolidation_misses": self.consolidation_misses,
            "consolidation_collisions": self.consolidation_collisions,
            "consolidation_displacements": self.consolidation_displacements,
            "consolidation_placement_failures": self.consolidation_placement_failures,
            "consolidation_load_factor": (sum(1 for fp in self.consolidation_fingerprints if int(fp) != 0) / max(1, len(self.consolidation_fingerprints))),
            "abstraction_enabled": self.abstraction_enabled,
            "abstraction_candidates": len(self.abstraction_stats),
            "abstraction_pending_candidates": len(self.abstraction_pending),
            "abstraction_pending_limit": self.abstraction_pending_limit,
            "abstraction_pending_promotions": self.abstraction_pending_promotions,
            "abstraction_candidate_evictions": self.abstraction_candidate_evictions,
            "abstraction_sparse_enabled": self.abstraction_sparse_enabled,
            "abstraction_pending_enabled": self.abstraction_pending_enabled,
            "abstraction_sparse_max_retained_features": self.abstraction_sparse_max_retained_features,
            "abstraction_candidates_per_observation": self.abstraction_candidates_per_observation,
            "abstraction_promoted": sum(1 for r in self.abstraction_stats.values() if self._abstraction_record_qualifies(r)),
            "abstraction_exceptions": len(self.abstraction_exceptions),
            "abstraction_hits": self.abstraction_hits,
            "abstraction_misses": self.abstraction_misses,
            "abstraction_exception_hits": self.abstraction_exception_hits,
            "abstraction_promotions": self.abstraction_promotions,
            "pre_learning_accuracy": accuracy,
            "ema_error": self.ema_error,
            "parameters": params,
        }


class TransitionMechanismBank:
    """Persistent bank of small recurrent local transition mechanisms."""

    def __init__(
        self,
        db_path: str | Path,
        *,
        input_dim: int = 128,
        hidden_dim: int = 64,
        max_outcomes: int = 32,
        learning_rate: float = 0.012,
        train_steps: int = 6,
        seed: int = 17,
        scheduler_max_calls: int = 1,
        scheduler_min_relevance: float = 0.45,
        scheduler_recovery_uncertainty: float = 0.72,
        scheduler_medium_calls: int = 3,
        scheduler_high_confidence: float = 0.74,
        scheduler_low_confidence: float = 0.46,
        scheduler_min_margin: float = 0.08,
        scheduler_calibration_min_support: int = 4,
        recent_route_limit: int = 256,
        retention_anchor_limit: int = 96,
        retention_anchor_batch_limit: int = 6,
        outcome_capacity_limit: int = 4096,
        outcome_growth_factor: float = 2.0,
        consolidation_table_size: int = 1024,
        consolidation_hashes: int = 3,
        consolidation_min_support: int = 4,
        consolidation_max_displacements: int = 24,
        consolidation_enabled: bool = True,
        abstraction_enabled: bool = True,
        abstraction_min_support: int = 8,
        abstraction_min_precision: float = 0.95,
        abstraction_min_diversity: int = 4,
        abstraction_max_dropped_features: int = 2,
        abstraction_sparse_enabled: bool = True,
        abstraction_pending_enabled: bool = True,
        abstraction_sparse_max_retained_features: int = 2,
        abstraction_candidates_per_observation: int = 48,
        abstraction_max_candidates: int = 2048,
        abstraction_exception_limit: int = 512,
    ):
        self.path = str(db_path)
        self.input_dim = int(input_dim)
        self.hidden_dim = int(hidden_dim)
        self.max_outcomes = int(max_outcomes)
        self.learning_rate = float(learning_rate)
        self.train_steps = int(train_steps)
        self.seed = int(seed)
        self.scheduler_max_calls = max(1, int(scheduler_max_calls))
        self.scheduler_min_relevance = float(scheduler_min_relevance)
        self.scheduler_recovery_uncertainty = float(scheduler_recovery_uncertainty)
        self.scheduler_medium_calls = max(2, int(scheduler_medium_calls))
        self.scheduler_high_confidence = float(scheduler_high_confidence)
        self.scheduler_low_confidence = float(scheduler_low_confidence)
        self.scheduler_min_margin = max(0.0, float(scheduler_min_margin))
        self.scheduler_calibration_min_support = max(1, int(scheduler_calibration_min_support))
        self.recent_route_limit = max(16, int(recent_route_limit))
        self.retention_anchor_limit = max(1, int(retention_anchor_limit))
        self.retention_anchor_batch_limit = max(0, int(retention_anchor_batch_limit))
        self.outcome_capacity_limit = max(self.max_outcomes, int(outcome_capacity_limit))
        self.outcome_growth_factor = max(1.25, float(outcome_growth_factor))
        self.consolidation_table_size = max(64, int(consolidation_table_size))
        self.consolidation_hashes = max(1, min(8, int(consolidation_hashes)))
        self.consolidation_min_support = max(1, int(consolidation_min_support))
        self.consolidation_max_displacements = max(1, int(consolidation_max_displacements))
        self.consolidation_enabled = bool(consolidation_enabled)
        self.abstraction_enabled = bool(abstraction_enabled)
        self.abstraction_min_support = max(2, int(abstraction_min_support))
        self.abstraction_min_precision = max(0.5, min(1.0, float(abstraction_min_precision)))
        self.abstraction_min_diversity = max(2, int(abstraction_min_diversity))
        self.abstraction_max_dropped_features = max(1, min(4, int(abstraction_max_dropped_features)))
        self.abstraction_sparse_enabled = bool(abstraction_sparse_enabled)
        self.abstraction_pending_enabled = bool(abstraction_pending_enabled)
        self.abstraction_sparse_max_retained_features = max(1, min(3, int(abstraction_sparse_max_retained_features)))
        self.abstraction_candidates_per_observation = max(16, min(128, int(abstraction_candidates_per_observation)))
        self.abstraction_max_candidates = max(64, int(abstraction_max_candidates))
        self.abstraction_exception_limit = max(16, int(abstraction_exception_limit))
        self.scheduler_calls = 0
        self.scheduler_dense_equivalent_calls = 0
        self.scheduler_fallbacks = 0
        self.scheduler_recoveries = 0
        self.scheduler_high_confidence_routes = 0
        self.scheduler_competitive_routes = 0
        self.scheduler_confidence_fallbacks = 0
        self.scheduler_feedback_updates = 0
        self._recent_routes: dict[str, dict[str, Any]] = {}
        self.available = torch is not None
        self.db = sqlite3.connect(self.path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS world_mechanism_models(
                mechanism_type TEXT PRIMARY KEY,
                model_blob BLOB NOT NULL,
                observations INTEGER NOT NULL,
                updated_ts REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS world_mechanism_experiences(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mechanism_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                before_state TEXT NOT NULL,
                action TEXT NOT NULL,
                neighborhood TEXT NOT NULL,
                dt REAL NOT NULL,
                after_state TEXT NOT NULL,
                predicted_state TEXT,
                correct_before_learning INTEGER NOT NULL,
                prediction_error REAL NOT NULL,
                loss REAL NOT NULL,
                uncertainty_before REAL NOT NULL,
                created_ts REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_world_mech_exp_type
            ON world_mechanism_experiences(mechanism_type, id DESC);
            CREATE TABLE IF NOT EXISTS world_mechanism_applicability(
                mechanism_type TEXT NOT NULL,
                feature TEXT NOT NULL,
                support INTEGER NOT NULL,
                PRIMARY KEY(mechanism_type, feature)
            );
            CREATE INDEX IF NOT EXISTS idx_world_mech_app_feature
            ON world_mechanism_applicability(feature, mechanism_type);
            CREATE TABLE IF NOT EXISTS world_mechanism_routing_evidence(
                mechanism_type TEXT NOT NULL,
                feature TEXT NOT NULL,
                positive INTEGER NOT NULL DEFAULT 0,
                negative INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(mechanism_type, feature)
            );
            CREATE INDEX IF NOT EXISTS idx_world_mech_route_feature
            ON world_mechanism_routing_evidence(feature, mechanism_type);
            CREATE TABLE IF NOT EXISTS world_mechanism_router_calibration(
                bucket INTEGER PRIMARY KEY,
                correct INTEGER NOT NULL DEFAULT 0,
                total INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS world_mechanism_routing_feedback(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                correct_mechanism TEXT NOT NULL,
                top_mechanism TEXT,
                attempted_mechanisms TEXT NOT NULL,
                raw_confidence REAL NOT NULL,
                was_top_correct INTEGER NOT NULL,
                created_ts REAL NOT NULL
            );
            """
        )
        self.db.commit()
        self.mechanisms: dict[str, LocalRecurrentTransitionMechanism] = {}
        self._backfill_applicability_if_needed()
        self._backfill_routing_evidence_if_needed()

    @staticmethod
    def _feature_weight(feature: str) -> float:
        # Alpha.5 gives learned conjunctions enough weight to separate mechanisms
        # that share broad action/kind features without hardcoding any domain.
        if feature.startswith("context:"):
            return 3.0
        if feature.startswith("pair:kind+neighbor:"):
            return 2.75
        if feature.startswith("pair:kind+action:"):
            return 2.5
        if feature.startswith("pair:kind+state:"):
            return 2.2
        if feature.startswith("state:kind="):
            return 3.0
        if feature.startswith("action="):
            return 1.5
        if feature.startswith("neighbor:"):
            return 1.25
        if feature.startswith("state:"):
            return 1.0
        if feature.startswith("dt="):
            return 0.25
        return 0.5

    def _routing_features(
        self, state: dict[str, Any], action: str,
        neighborhood: dict[str, Any] | None, dt: float,
    ) -> list[str]:
        base = LocalRecurrentTransitionMechanism._features(state, action, neighborhood, dt)
        kind = next((f for f in base if f.startswith("state:kind=")), None)
        action_feature = next((f for f in base if f.startswith("action=")), None)
        enriched = list(base)
        if kind and action_feature:
            enriched.append(f"pair:kind+action:{kind}|{action_feature}")
        if kind:
            for feature in base:
                if feature == kind:
                    continue
                if feature.startswith("state:"):
                    enriched.append(f"pair:kind+state:{kind}|{feature}")
                elif feature.startswith("neighbor:"):
                    enriched.append(f"pair:kind+neighbor:{kind}|{feature}")
        # Exact structured context token gives prediction-error feedback somewhere
        # safe to attach without poisoning broad features shared by other contexts.
        context_material = "|".join(sorted(base))
        context_hash = hashlib.sha256(context_material.encode("utf-8")).hexdigest()[:20]
        enriched.append(f"context:{context_hash}")
        return sorted(set(enriched))

    @staticmethod
    def _route_key(
        entity_id: str, state: dict[str, Any], action: str,
        neighborhood: dict[str, Any] | None, dt: float,
    ) -> str:
        payload = {
            "entity_id": str(entity_id),
            "state": state,
            "action": str(action).strip().lower(),
            "neighborhood": neighborhood or {},
            "dt": round(float(dt), 6),
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)

    def _record_applicability(self, mechanism_type: str, features: list[str]) -> None:
        # Legacy positive profile remains for alpha.4 migration/debug visibility.
        for feature in set(features):
            self.db.execute(
                """
                INSERT INTO world_mechanism_applicability(mechanism_type,feature,support)
                VALUES(?,?,1)
                ON CONFLICT(mechanism_type,feature) DO UPDATE SET support=support+1
                """,
                (str(mechanism_type).strip().lower(), feature),
            )

    def _record_routing_evidence(
        self, mechanism_type: str, features: list[str], *, positive: int = 0, negative: int = 0,
    ) -> None:
        if positive <= 0 and negative <= 0:
            return
        key = str(mechanism_type).strip().lower()
        for feature in set(features):
            self.db.execute(
                """
                INSERT INTO world_mechanism_routing_evidence(mechanism_type,feature,positive,negative)
                VALUES(?,?,?,?)
                ON CONFLICT(mechanism_type,feature) DO UPDATE SET
                    positive=positive+excluded.positive,
                    negative=negative+excluded.negative
                """,
                (key, feature, int(positive), int(negative)),
            )

    def _backfill_applicability_if_needed(self) -> None:
        count = int(self.db.execute("SELECT COUNT(*) FROM world_mechanism_applicability").fetchone()[0])
        if count:
            return
        rows = self.db.execute(
            "SELECT mechanism_type,before_state,action,neighborhood,dt FROM world_mechanism_experiences ORDER BY id"
        ).fetchall()
        for mechanism_type, before_state, action, neighborhood, dt in rows:
            try:
                state = json.loads(before_state)
                neighbors = json.loads(neighborhood)
            except Exception:
                continue
            self._record_applicability(
                str(mechanism_type), self._routing_features(state, str(action), neighbors, float(dt))
            )
        if rows:
            self.db.commit()

    def _backfill_routing_evidence_if_needed(self) -> None:
        count = int(self.db.execute("SELECT COUNT(*) FROM world_mechanism_routing_evidence").fetchone()[0])
        if count:
            return
        rows = self.db.execute(
            "SELECT mechanism_type,feature,support FROM world_mechanism_applicability"
        ).fetchall()
        for mechanism_type, feature, support in rows:
            self.db.execute(
                """
                INSERT OR IGNORE INTO world_mechanism_routing_evidence(
                    mechanism_type,feature,positive,negative
                ) VALUES(?,?,?,0)
                """,
                (str(mechanism_type), str(feature), int(support)),
            )
        if rows:
            self.db.commit()

    def _routing_profile(
        self, mechanism_type: str, *, state: dict[str, Any], action: str,
        neighborhood: dict[str, Any] | None = None, dt: float = 1.0,
    ) -> dict[str, Any]:
        features = self._routing_features(state, action, neighborhood, dt)
        rows = self.db.execute(
            "SELECT feature,positive,negative FROM world_mechanism_routing_evidence WHERE mechanism_type=?",
            (str(mechanism_type).strip().lower(),),
        ).fetchall()
        known = {str(feature): (int(pos), int(neg)) for feature, pos, neg in rows}
        denom = sum(self._feature_weight(f) for f in features) or 1.0
        score_num = 0.0
        matched_weight = 0.0
        positive_support = 0
        negative_support = 0
        matched = []
        for feature in features:
            pos, neg = known.get(feature, (0, 0))
            weight = self._feature_weight(feature)
            if pos <= 0:
                if neg > 0:
                    # Negative-only evidence means this visible context was tried
                    # and contradicted for this mechanism. Penalize only while the
                    # same feature/context is present; unrelated contexts survive.
                    penalty = min(1.0, neg / 2.0)
                    score_num -= weight * penalty
                    negative_support += neg
                    matched.append({"feature": feature, "positive": 0, "negative": neg, "precision": 0.0})
                continue
            # Applicability relevance keeps alpha.4 semantics when there is only
            # positive evidence (precision=1). Negative feedback lowers the score
            # proportionally; route confidence separately accounts for support.
            precision = pos / max(1.0, pos + neg)
            score_num += weight * precision
            matched_weight += weight
            positive_support += pos
            negative_support += neg
            matched.append({"feature": feature, "positive": pos, "negative": neg, "precision": precision})
        coverage = matched_weight / denom
        relevance = max(0.0, min(1.0, score_num / denom))
        support_confidence = 1.0 - math.exp(-positive_support / 8.0) if positive_support else 0.0
        return {
            "mechanism_type": str(mechanism_type).strip().lower(),
            "relevance": relevance,
            "coverage": max(0.0, min(1.0, coverage)),
            "positive_support": positive_support,
            "negative_support": negative_support,
            "support_confidence": support_confidence,
            "matched_features": matched,
        }

    def mechanism_relevance(
        self, mechanism_type: str, *, state: dict[str, Any], action: str,
        neighborhood: dict[str, Any] | None = None, dt: float = 1.0,
    ) -> float:
        return float(self._routing_profile(
            mechanism_type, state=state, action=action, neighborhood=neighborhood, dt=dt
        )["relevance"])

    @staticmethod
    def _confidence_bucket(confidence: float) -> int:
        return max(0, min(9, int(float(confidence) * 10.0)))

    def _calibrate_confidence(self, raw_confidence: float) -> tuple[float, str, int]:
        bucket = self._confidence_bucket(raw_confidence)
        row = self.db.execute(
            "SELECT correct,total FROM world_mechanism_router_calibration WHERE bucket=?", (bucket,)
        ).fetchone()
        if row is None or int(row[1]) < self.scheduler_calibration_min_support:
            return float(raw_confidence), "heuristic", 0 if row is None else int(row[1])
        correct, total = int(row[0]), int(row[1])
        posterior = (correct + 1.0) / (total + 2.0)
        # Preserve some structure from the live evidence score while anchoring it
        # to observed top-route correctness for this confidence bucket.
        calibrated = 0.25 * float(raw_confidence) + 0.75 * posterior
        return max(0.0, min(1.0, calibrated)), "empirical", total

    def _record_calibration(self, raw_confidence: float, correct: bool) -> None:
        bucket = self._confidence_bucket(raw_confidence)
        self.db.execute(
            """
            INSERT INTO world_mechanism_router_calibration(bucket,correct,total)
            VALUES(?,?,1)
            ON CONFLICT(bucket) DO UPDATE SET
                correct=correct+excluded.correct,
                total=total+1
            """,
            (bucket, 1 if correct else 0),
        )

    def _remember_route(self, key: str, payload: dict[str, Any]) -> None:
        self._recent_routes[key] = payload
        while len(self._recent_routes) > self.recent_route_limit:
            first = next(iter(self._recent_routes))
            self._recent_routes.pop(first, None)

    def _apply_recent_routing_feedback(
        self, *, correct_mechanism: str, entity_id: str, state: dict[str, Any], action: str,
        neighborhood: dict[str, Any] | None, dt: float,
    ) -> dict[str, Any] | None:
        key = self._route_key(entity_id, state, action, neighborhood, dt)
        previous = self._recent_routes.pop(key, None)
        if not previous:
            return None
        correct = str(correct_mechanism).strip().lower()
        attempted = [str(x).strip().lower() for x in previous.get("attempted", [])]
        top = str(previous.get("top_mechanism") or "").strip().lower() or None
        raw_confidence = float(previous.get("raw_confidence", 0.0))
        top_correct = top == correct
        self._record_calibration(raw_confidence, top_correct)
        features = self._routing_features(state, action, neighborhood, dt)
        # The known correct mechanism receives positive routing evidence. Wrong
        # mechanisms are penalized only if they were actually executed, making
        # the update prediction-error driven rather than blanket anti-learning.
        self._record_routing_evidence(correct, features, positive=1)
        wrong = []
        specific = [
            f for f in features
            if f.startswith("context:") or f.startswith("pair:") or f.startswith("neighbor:") or (
                f.startswith("state:") and not f.startswith("state:kind=")
            )
        ]
        for mechanism in attempted:
            if mechanism == correct:
                continue
            # Penalize only features that were not already positive evidence for
            # the wrong mechanism. If two mechanisms are observationally identical,
            # alpha.5 must widen rather than damaging a valid shared profile.
            known_rows = self.db.execute(
                "SELECT feature,positive FROM world_mechanism_routing_evidence WHERE mechanism_type=?",
                (mechanism,),
            ).fetchall()
            known_positive = {str(f) for f, pos in known_rows if int(pos) > 0}
            targets = [f for f in specific if f not in known_positive]
            if not targets:
                continue
            wrong.append(mechanism)
            self._record_routing_evidence(mechanism, targets, negative=1)
        self.db.execute(
            """
            INSERT INTO world_mechanism_routing_feedback(
                correct_mechanism,top_mechanism,attempted_mechanisms,raw_confidence,
                was_top_correct,created_ts
            ) VALUES(?,?,?,?,?,?)
            """,
            (correct, top, json.dumps(attempted), raw_confidence, 1 if top_correct else 0, time.time()),
        )
        self.scheduler_feedback_updates += 1
        return {"top_correct": top_correct, "wrong_penalized": wrong, "raw_confidence": raw_confidence}

    def route(
        self, *, state: dict[str, Any], action: str, neighborhood: dict[str, Any] | None = None,
        dt: float = 1.0, max_calls: int | None = None, mode: str = "seismic",
    ) -> dict[str, Any]:
        types = [str(r[0]) for r in self.db.execute(
            "SELECT mechanism_type FROM world_mechanism_models ORDER BY mechanism_type"
        ).fetchall()]
        ranked = [
            self._routing_profile(m, state=state, action=action, neighborhood=neighborhood, dt=dt)
            for m in types
        ]
        ranked.sort(key=lambda r: (-float(r["relevance"]), -float(r["support_confidence"]), r["mechanism_type"]))
        best = float(ranked[0]["relevance"]) if ranked else 0.0
        runner = float(ranked[1]["relevance"]) if len(ranked) > 1 else 0.0
        margin = max(0.0, best - runner)
        support_conf = float(ranked[0]["support_confidence"]) if ranked else 0.0
        margin_quality = min(1.0, margin / max(self.scheduler_min_margin * 2.0, 1e-6))
        raw_confidence = max(0.0, min(1.0, 0.62 * best + 0.28 * margin_quality + 0.10 * support_conf))
        decision_confidence, calibration_source, calibration_support = self._calibrate_confidence(raw_confidence)

        if mode == "dense":
            selected = list(ranked)
            fallback = False
            reason = "dense_baseline"
            breadth = len(selected)
        elif not ranked:
            selected = []
            fallback = False
            reason = "no_mechanisms"
            breadth = 0
        elif best < self.scheduler_min_relevance:
            selected = list(ranked)
            fallback = True
            reason = "low_relevance_dense_fallback"
            breadth = len(selected)
            self.scheduler_fallbacks += 1
        elif decision_confidence < self.scheduler_low_confidence:
            selected = list(ranked)
            fallback = True
            reason = "low_confidence_dense_fallback"
            breadth = len(selected)
            self.scheduler_fallbacks += 1
            self.scheduler_confidence_fallbacks += 1
        else:
            explicit_limit = max(1, int(max_calls)) if max_calls is not None else None
            if decision_confidence >= self.scheduler_high_confidence and margin >= self.scheduler_min_margin:
                breadth = explicit_limit or self.scheduler_max_calls
                reason = "seismic_confident_topk"
                self.scheduler_high_confidence_routes += 1
            else:
                breadth = explicit_limit or self.scheduler_medium_calls
                reason = "seismic_competitive_topk"
                self.scheduler_competitive_routes += 1
            selected = ranked[:max(1, min(int(breadth), len(ranked)))]
            fallback = False

        return {
            "mode": mode,
            "reason": reason,
            "fallback": fallback,
            "candidates": ranked,
            "selected": selected,
            "total_mechanisms": len(ranked),
            "top_relevance": best,
            "runner_up_relevance": runner,
            "margin": margin,
            "raw_confidence": raw_confidence,
            "routing_confidence": decision_confidence,
            "calibration_source": calibration_source,
            "calibration_support": calibration_support,
            "breadth": breadth,
        }

    def predict_routed(
        self, *, entity_id: str, state: dict[str, Any], action: str,
        neighborhood: dict[str, Any] | None = None, dt: float = 1.0,
        mode: str = "seismic", max_calls: int | None = None, recover: bool = True,
    ) -> dict[str, Any]:
        routing = self.route(
            state=state, action=action, neighborhood=neighborhood, dt=dt,
            max_calls=max_calls, mode=mode,
        )
        ranked = routing["candidates"]
        selected = list(routing["selected"])
        called: list[dict[str, Any]] = []
        called_types: set[str] = set()

        def call(row: dict[str, Any]) -> None:
            m = row["mechanism_type"]
            if m in called_types:
                return
            pred = self.predict(
                m, entity_id=entity_id, state=state, action=action,
                neighborhood=neighborhood, dt=dt,
            )
            called.append({**row, "prediction": pred})
            called_types.add(m)

        for row in selected:
            call(row)
        if recover and mode != "dense" and not routing["fallback"] and called:
            best_uncertainty = min(float(x["prediction"].get("uncertainty", 1.0)) for x in called)
            if best_uncertainty > self.scheduler_recovery_uncertainty:
                for row in ranked:
                    if row["mechanism_type"] not in called_types:
                        call(row)
                        self.scheduler_recoveries += 1
                        if min(float(x["prediction"].get("uncertainty", 1.0)) for x in called) <= self.scheduler_recovery_uncertainty:
                            break

        def utility(row: dict[str, Any]) -> tuple[float, float, str]:
            pred = row["prediction"]
            confidence = float(pred.get("confidence", 0.0))
            has_value = 1.0 if pred.get("predicted_state") is not None else 0.0
            return (has_value, float(row["relevance"]) * 0.75 + confidence * 0.25, row["mechanism_type"])

        chosen = max(called, key=utility) if called else None
        calls = len(called)
        total = len(ranked)
        self.scheduler_calls += calls
        self.scheduler_dense_equivalent_calls += total
        route_key = self._route_key(entity_id, state, action, neighborhood, dt)
        self._remember_route(route_key, {
            "attempted": list(called_types),
            "top_mechanism": ranked[0]["mechanism_type"] if ranked else None,
            "raw_confidence": routing["raw_confidence"],
            "routing_confidence": routing["routing_confidence"],
            "created_ts": time.time(),
        })
        return {
            **routing,
            "calls": calls,
            "dense_equivalent_calls": total,
            "call_reduction": (1.0 - calls / total) if total else 0.0,
            "predictions": called,
            "chosen": chosen,
        }

    def _new(self, mechanism_type: str) -> LocalRecurrentTransitionMechanism:
        return LocalRecurrentTransitionMechanism(
            mechanism_type,
            input_dim=self.input_dim,
            hidden_dim=self.hidden_dim,
            max_outcomes=self.max_outcomes,
            learning_rate=self.learning_rate,
            train_steps=self.train_steps,
            seed=self.seed,
            retention_anchor_limit=self.retention_anchor_limit,
            retention_anchor_batch_limit=self.retention_anchor_batch_limit,
            outcome_capacity_limit=self.outcome_capacity_limit,
            outcome_growth_factor=self.outcome_growth_factor,
            consolidation_table_size=self.consolidation_table_size,
            consolidation_hashes=self.consolidation_hashes,
            consolidation_min_support=self.consolidation_min_support,
            consolidation_max_displacements=self.consolidation_max_displacements,
            consolidation_enabled=self.consolidation_enabled,
            abstraction_enabled=self.abstraction_enabled,
            abstraction_min_support=self.abstraction_min_support,
            abstraction_min_precision=self.abstraction_min_precision,
            abstraction_min_diversity=self.abstraction_min_diversity,
            abstraction_max_dropped_features=self.abstraction_max_dropped_features,
            abstraction_sparse_enabled=self.abstraction_sparse_enabled,
            abstraction_pending_enabled=self.abstraction_pending_enabled,
            abstraction_sparse_max_retained_features=self.abstraction_sparse_max_retained_features,
            abstraction_candidates_per_observation=self.abstraction_candidates_per_observation,
            abstraction_max_candidates=self.abstraction_max_candidates,
            abstraction_exception_limit=self.abstraction_exception_limit,
        )

    def _get(self, mechanism_type: str, *, create: bool) -> LocalRecurrentTransitionMechanism | None:
        key = str(mechanism_type).strip().lower()
        if not key:
            raise ValueError("mechanism_type must be non-empty")
        found = self.mechanisms.get(key)
        if found is not None:
            return found
        if not self.available:
            return None
        row = self.db.execute(
            "SELECT model_blob FROM world_mechanism_models WHERE mechanism_type=?", (key,)
        ).fetchone()
        mechanism = self._new(key)
        if row is not None:
            mechanism.import_blob(bytes(row[0]))
        elif not create:
            return None
        self.mechanisms[key] = mechanism
        return mechanism

    def _persist(self, mechanism: LocalRecurrentTransitionMechanism) -> None:
        blob = sqlite3.Binary(mechanism.export_blob())
        self.db.execute(
            """
            INSERT INTO world_mechanism_models(mechanism_type,model_blob,observations,updated_ts)
            VALUES(?,?,?,?)
            ON CONFLICT(mechanism_type) DO UPDATE SET
                model_blob=excluded.model_blob,
                observations=excluded.observations,
                updated_ts=excluded.updated_ts
            """,
            (mechanism.mechanism_type, blob, mechanism.total_observations, time.time()),
        )
        self.db.commit()

    def predict(
        self,
        mechanism_type: str,
        *,
        entity_id: str,
        state: dict[str, Any],
        action: str,
        neighborhood: dict[str, Any] | None = None,
        dt: float = 1.0,
    ) -> dict[str, Any]:
        mechanism = self._get(mechanism_type, create=False)
        if mechanism is None:
            return TransitionPrediction(
                str(mechanism_type), str(entity_id), None, 0.0, 1.0, None, 0, 0
            ).as_dict()
        return mechanism.predict(
            entity_id=entity_id,
            state=state,
            action=action,
            neighborhood=neighborhood,
            dt=dt,
        ).as_dict()

    def predict_simulated(
        self,
        mechanism_type: str,
        *,
        entity_id: str,
        state: dict[str, Any],
        action: str,
        neighborhood: dict[str, Any] | None = None,
        dt: float = 1.0,
        simulation_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        mechanism = self._get(mechanism_type, create=False)
        if mechanism is None:
            result = TransitionPrediction(
                str(mechanism_type), str(entity_id), None, 0.0, 1.0, None, 0, 0
            ).as_dict()
            result["_simulation_context"] = simulation_context
            result["_simulation_context_key"] = "missing"
            return result
        return mechanism.predict_simulated(
            entity_id=entity_id,
            state=state,
            action=action,
            neighborhood=neighborhood,
            dt=dt,
            simulation_context=simulation_context,
        )

    def predict_distribution_simulated(
        self,
        mechanism_type: str,
        *,
        entity_id: str,
        state: dict[str, Any],
        action: str,
        neighborhood: dict[str, Any] | None = None,
        dt: float = 1.0,
        simulation_context: dict[str, Any] | None = None,
        top_k: int = 4,
        empirical_min_support: int | None = None,
    ) -> dict[str, Any]:
        mechanism = self._get(mechanism_type, create=False)
        if mechanism is None:
            return {
                "mechanism_type": str(mechanism_type), "entity_id": str(entity_id),
                "outcomes": [], "unknown_probability": 1.0, "support": 0,
                "probability_source": "missing", "calibrated": False,
                "_simulation_context": simulation_context,
                "_simulation_context_key": "missing",
            }
        return mechanism.predict_distribution_simulated(
            entity_id=entity_id, state=state, action=action, neighborhood=neighborhood,
            dt=dt, simulation_context=simulation_context, top_k=top_k,
            empirical_min_support=empirical_min_support,
        )

    def observe(
        self,
        mechanism_type: str,
        *,
        entity_id: str,
        state: dict[str, Any],
        action: str,
        after_state: dict[str, Any],
        neighborhood: dict[str, Any] | None = None,
        dt: float = 1.0,
    ) -> dict[str, Any]:
        if not self.available:
            return {"learned": False, "reason": "torch_unavailable"}
        mechanism = self._get(mechanism_type, create=True)
        assert mechanism is not None
        result = mechanism.observe(
            entity_id=entity_id,
            state=state,
            action=action,
            after_state=after_state,
            neighborhood=neighborhood,
            dt=dt,
        )
        before = result["before_prediction"]
        self.db.execute(
            """
            INSERT INTO world_mechanism_experiences(
                mechanism_type,entity_id,before_state,action,neighborhood,dt,
                after_state,predicted_state,correct_before_learning,prediction_error,
                loss,uncertainty_before,created_ts
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                mechanism.mechanism_type,
                str(entity_id),
                json.dumps(state, sort_keys=True),
                str(action),
                json.dumps(neighborhood or {}, sort_keys=True),
                float(dt),
                json.dumps(after_state, sort_keys=True),
                json.dumps(before.get("predicted_state"), sort_keys=True) if before.get("predicted_state") is not None else None,
                1 if result["correct_before_learning"] else 0,
                float(result["prediction_error"]),
                float(result["loss"]),
                float(before["uncertainty"]),
                time.time(),
            ),
        )
        routing_features = self._routing_features(state, action, neighborhood, dt)
        self._record_applicability(mechanism.mechanism_type, routing_features)
        feedback = self._apply_recent_routing_feedback(
            correct_mechanism=mechanism.mechanism_type, entity_id=str(entity_id),
            state=state, action=action, neighborhood=neighborhood, dt=dt,
        )
        if feedback is None:
            # Ordinary supervised mechanism experience still teaches where the
            # mechanism applies. Negative evidence is reserved for an actually
            # attempted wrong route, so unrelated mechanisms are not punished.
            self._record_routing_evidence(mechanism.mechanism_type, routing_features, positive=1)
        self.db.commit()
        self._persist(mechanism)
        result["routing_feedback"] = feedback
        result["learned"] = True
        return result

    def reset_context(self, mechanism_type: str, entity_id: str | None = None) -> None:
        mechanism = self._get(mechanism_type, create=False)
        if mechanism is None:
            return
        mechanism.reset_context(entity_id)
        self._persist(mechanism)

    def stats(self) -> dict[str, Any]:
        rows = self.db.execute(
            "SELECT mechanism_type,observations FROM world_mechanism_models ORDER BY mechanism_type"
        ).fetchall()
        exp = int(self.db.execute("SELECT COUNT(*) FROM world_mechanism_experiences").fetchone()[0])
        detail = []
        for mechanism_type, observations in rows:
            mechanism = self._get(str(mechanism_type), create=False)
            detail.append(mechanism.stats() if mechanism is not None else {
                "mechanism_type": str(mechanism_type), "observations": int(observations)
            })
        dense = self.scheduler_dense_equivalent_calls
        total_anchors = sum(int(x.get("retention_anchors", 0)) for x in detail)
        anchor_outcomes = sum(int(x.get("retention_anchor_outcomes", 0)) for x in detail)
        consolidation_bytes = sum(int(x.get("consolidation_bytes", 0)) for x in detail)
        consolidation_used = sum(int(x.get("consolidation_used_cells", 0)) for x in detail)
        abstraction_candidates = sum(int(x.get("abstraction_candidates", 0)) for x in detail)
        abstraction_pending = sum(int(x.get("abstraction_pending_candidates", 0)) for x in detail)
        abstraction_promoted = sum(int(x.get("abstraction_promoted", 0)) for x in detail)
        abstraction_exceptions = sum(int(x.get("abstraction_exceptions", 0)) for x in detail)
        return {
            "enabled": bool(self.available),
            "mechanisms": len(rows),
            "experiences": exp,
            "retention": {
                "anchors": total_anchors,
                "covered_outcomes": anchor_outcomes,
                "anchor_limit_per_mechanism": self.retention_anchor_limit,
                "anchor_batch_limit": self.retention_anchor_batch_limit,
            },
            "consolidation": {
                "enabled": self.consolidation_enabled,
                "table_size_per_hash": self.consolidation_table_size,
                "hashes": self.consolidation_hashes,
                "min_support": self.consolidation_min_support,
                "layout_version": 3,
                "max_displacements": self.consolidation_max_displacements,
                "fixed_bytes": consolidation_bytes,
                "used_cells": consolidation_used,
            },
            "abstraction": {
                "enabled": self.abstraction_enabled,
                "min_support": self.abstraction_min_support,
                "min_precision": self.abstraction_min_precision,
                "min_diversity": self.abstraction_min_diversity,
                "max_dropped_features": self.abstraction_max_dropped_features,
                "sparse_enabled": self.abstraction_sparse_enabled,
                "pending_enabled": self.abstraction_pending_enabled,
                "sparse_max_retained_features": self.abstraction_sparse_max_retained_features,
                "candidates_per_observation": self.abstraction_candidates_per_observation,
                "candidate_limit_per_mechanism": self.abstraction_max_candidates,
                "pending_candidates": abstraction_pending,
                "exception_limit_per_mechanism": self.abstraction_exception_limit,
                "candidates": abstraction_candidates,
                "promoted": abstraction_promoted,
                "exceptions": abstraction_exceptions,
            },
            "scheduler": {
                "max_calls": self.scheduler_max_calls,
                "medium_calls": self.scheduler_medium_calls,
                "min_relevance": self.scheduler_min_relevance,
                "high_confidence": self.scheduler_high_confidence,
                "low_confidence": self.scheduler_low_confidence,
                "min_margin": self.scheduler_min_margin,
                "recovery_uncertainty": self.scheduler_recovery_uncertainty,
                "calibration_min_support": self.scheduler_calibration_min_support,
                "calls": self.scheduler_calls,
                "dense_equivalent_calls": dense,
                "observed_call_reduction": (1.0 - self.scheduler_calls / dense) if dense else 0.0,
                "fallbacks": self.scheduler_fallbacks,
                "confidence_fallbacks": self.scheduler_confidence_fallbacks,
                "recoveries": self.scheduler_recoveries,
                "high_confidence_routes": self.scheduler_high_confidence_routes,
                "competitive_routes": self.scheduler_competitive_routes,
                "feedback_updates": self.scheduler_feedback_updates,
                "recent_routes": len(self._recent_routes),
                "applicability_features": int(self.db.execute("SELECT COUNT(*) FROM world_mechanism_applicability").fetchone()[0]),
                "routing_evidence_features": int(self.db.execute("SELECT COUNT(*) FROM world_mechanism_routing_evidence").fetchone()[0]),
                "negative_evidence": int(self.db.execute("SELECT COALESCE(SUM(negative),0) FROM world_mechanism_routing_evidence").fetchone()[0]),
                "calibration_samples": int(self.db.execute("SELECT COALESCE(SUM(total),0) FROM world_mechanism_router_calibration").fetchone()[0]),
            },
            "input_dim": self.input_dim,
            "hidden_dim": self.hidden_dim,
            "max_outcomes": self.max_outcomes,
            "initial_outcome_capacity": self.max_outcomes,
            "outcome_capacity_limit": self.outcome_capacity_limit,
            "outcome_growth_factor": self.outcome_growth_factor,
            "detail": detail,
        }

    def close(self) -> None:
        for mechanism in list(self.mechanisms.values()):
            self._persist(mechanism)
        self.db.close()
