from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import math
from typing import Any, Iterable, Mapping


@dataclass(slots=True)
class _RunningCorrelation:
    """Online Pearson sufficient statistics."""

    n: int = 0
    sum_x: float = 0.0
    sum_y: float = 0.0
    sum_x2: float = 0.0
    sum_y2: float = 0.0
    sum_xy: float = 0.0

    def add(self, x: float, y: float) -> None:
        x = float(x); y = float(y)
        if not (math.isfinite(x) and math.isfinite(y)):
            raise ValueError("dependency observations must be finite")
        self.n += 1
        self.sum_x += x; self.sum_y += y
        self.sum_x2 += x * x; self.sum_y2 += y * y
        self.sum_xy += x * y

    def add_stats(self, other: "_RunningCorrelation") -> None:
        self.n += int(other.n)
        self.sum_x += float(other.sum_x); self.sum_y += float(other.sum_y)
        self.sum_x2 += float(other.sum_x2); self.sum_y2 += float(other.sum_y2)
        self.sum_xy += float(other.sum_xy)

    def subtract_stats(self, other: "_RunningCorrelation") -> None:
        self.n -= int(other.n)
        self.sum_x -= float(other.sum_x); self.sum_y -= float(other.sum_y)
        self.sum_x2 -= float(other.sum_x2); self.sum_y2 -= float(other.sum_y2)
        self.sum_xy -= float(other.sum_xy)
        if self.n < 0:
            raise RuntimeError("rolling dependency statistics underflow")
        if self.n == 0:
            self.sum_x = self.sum_y = self.sum_x2 = self.sum_y2 = self.sum_xy = 0.0

    def copy(self) -> "_RunningCorrelation":
        return _RunningCorrelation(
            self.n, self.sum_x, self.sum_y, self.sum_x2, self.sum_y2, self.sum_xy
        )

    def correlation(self) -> float:
        if self.n < 2:
            return 0.0
        n = float(self.n)
        vx = self.sum_x2 - (self.sum_x * self.sum_x) / n
        vy = self.sum_y2 - (self.sum_y * self.sum_y) / n
        if vx <= 1e-15 or vy <= 1e-15:
            return 0.0
        cov = self.sum_xy - (self.sum_x * self.sum_y) / n
        return max(-1.0, min(1.0, cov / math.sqrt(vx * vy)))

    def as_dict(self) -> dict[str, Any]:
        return {
            "n": int(self.n), "sum_x": float(self.sum_x), "sum_y": float(self.sum_y),
            "sum_x2": float(self.sum_x2), "sum_y2": float(self.sum_y2),
            "sum_xy": float(self.sum_xy), "correlation": float(self.correlation()),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "_RunningCorrelation":
        row = cls(
            n=int(payload.get("n", 0)),
            sum_x=float(payload.get("sum_x", 0.0)), sum_y=float(payload.get("sum_y", 0.0)),
            sum_x2=float(payload.get("sum_x2", 0.0)), sum_y2=float(payload.get("sum_y2", 0.0)),
            sum_xy=float(payload.get("sum_xy", 0.0)),
        )
        if row.n < 0 or not all(math.isfinite(v) for v in (
            row.sum_x, row.sum_y, row.sum_x2, row.sum_y2, row.sum_xy
        )):
            raise ValueError("malformed dependency correlation state")
        return row


@dataclass(slots=True)
class _SelfDependency:
    pairs: _RunningCorrelation = field(default_factory=_RunningCorrelation)
    trials: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {"trials": int(self.trials), "pairs": self.pairs.as_dict()}


@dataclass(slots=True)
class _RollingContribution:
    stats: _RunningCorrelation
    trial_units: int
    temporal_index: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "stats": self.stats.as_dict(),
            "trial_units": int(self.trial_units),
            "temporal_index": float(self.temporal_index),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "_RollingContribution":
        stats_payload = payload.get("stats", {})
        if not isinstance(stats_payload, Mapping):
            raise ValueError("invalid temporal dependency stats")
        units = int(payload.get("trial_units", 0))
        idx = float(payload.get("temporal_index"))
        if units < 0 or not math.isfinite(idx):
            raise ValueError("invalid temporal dependency contribution")
        return cls(_RunningCorrelation.from_dict(stats_payload), units, idx)


class _RollingWindow:
    """O(1) bounded sufficient statistics with exact removal."""

    __slots__ = ("max_items", "items", "stats", "trial_units")

    def __init__(self, max_items: int) -> None:
        self.max_items = int(max_items)
        if self.max_items < 8:
            raise ValueError("dependency rolling windows must be >= 8")
        self.items: deque[_RollingContribution] = deque()
        self.stats = _RunningCorrelation()
        self.trial_units = 0

    def add(self, contribution: _RollingContribution) -> None:
        self.items.append(contribution)
        self.stats.add_stats(contribution.stats)
        self.trial_units += int(contribution.trial_units)
        while len(self.items) > self.max_items:
            old = self.items.popleft()
            self.stats.subtract_stats(old.stats)
            self.trial_units -= int(old.trial_units)
        if self.trial_units < 0:
            raise RuntimeError("rolling dependency trial count underflow")

    def as_dict(self) -> dict[str, Any]:
        return {
            "max_items": int(self.max_items),
            "items": [x.as_dict() for x in self.items],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any], expected_max_items: int) -> "_RollingWindow":
        row = cls(expected_max_items)
        items = payload.get("items", [])
        if not isinstance(items, list) or len(items) > expected_max_items:
            raise ValueError("invalid temporal dependency rolling window")
        last = None
        for item in items:
            if not isinstance(item, Mapping):
                raise ValueError("invalid temporal dependency rolling item")
            c = _RollingContribution.from_dict(item)
            if last is not None and c.temporal_index <= last:
                raise ValueError("temporal dependency history must be strictly increasing")
            row.add(c)
            last = c.temporal_index
        return row


@dataclass(slots=True)
class _DependencyRegime:
    version: int
    start_index: float
    detected_index: float
    end_index: float | None
    raw_correlation: float
    active_correlation: float
    label: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": int(self.version),
            "start_index": float(self.start_index),
            "detected_index": float(self.detected_index),
            "end_index": None if self.end_index is None else float(self.end_index),
            "raw_correlation": float(self.raw_correlation),
            "active_correlation": float(self.active_correlation),
            "label": str(self.label),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "_DependencyRegime":
        end = payload.get("end_index")
        row = cls(
            version=int(payload.get("version", 0)),
            start_index=float(payload.get("start_index")),
            detected_index=float(payload.get("detected_index")),
            end_index=None if end is None else float(end),
            raw_correlation=float(payload.get("raw_correlation", 0.0)),
            active_correlation=float(payload.get("active_correlation", 0.0)),
            label=str(payload.get("label", "unknown")),
        )
        if row.version < 1 or not all(math.isfinite(v) for v in (
            row.start_index, row.detected_index, row.raw_correlation, row.active_correlation
        )):
            raise ValueError("invalid dependency regime")
        if row.end_index is not None and not math.isfinite(row.end_index):
            raise ValueError("invalid dependency regime end")
        return row


class _TemporalDependency:
    __slots__ = (
        "recent", "change", "regime_stats", "regime_trial_units", "regime_start_index",
        "regimes", "pending_direction", "pending_count",
    )

    def __init__(self, recent_window: int, change_window: int) -> None:
        self.recent = _RollingWindow(recent_window)
        self.change = _RollingWindow(change_window)
        self.regime_stats = _RunningCorrelation()
        self.regime_trial_units = 0
        self.regime_start_index: float | None = None
        self.regimes: list[_DependencyRegime] = []
        self.pending_direction: int = 0
        self.pending_count: int = 0

    def add(self, contribution: _RollingContribution) -> None:
        self.recent.add(contribution)
        self.change.add(contribution)
        if self.regime_start_index is None:
            self.regime_start_index = contribution.temporal_index
        self.regime_stats.add_stats(contribution.stats)
        self.regime_trial_units += contribution.trial_units

    def reset_regime_to_change_window(self, detected_index: float) -> None:
        self.regime_stats = self.change.stats.copy()
        self.regime_trial_units = int(self.change.trial_units)
        if self.change.items:
            self.regime_start_index = self.change.items[0].temporal_index
        else:
            self.regime_start_index = detected_index
        self.pending_direction = 0
        self.pending_count = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "recent": self.recent.as_dict(),
            "change": self.change.as_dict(),
            "regime_stats": self.regime_stats.as_dict(),
            "regime_trial_units": int(self.regime_trial_units),
            "regime_start_index": self.regime_start_index,
            "regimes": [r.as_dict() for r in self.regimes],
            "pending_direction": int(self.pending_direction),
            "pending_count": int(self.pending_count),
        }

    @classmethod
    def from_dict(
        cls, payload: Mapping[str, Any], recent_window: int, change_window: int
    ) -> "_TemporalDependency":
        row = cls(recent_window, change_window)
        recent = payload.get("recent", {})
        change = payload.get("change", {})
        if not isinstance(recent, Mapping) or not isinstance(change, Mapping):
            raise ValueError("invalid temporal dependency state")
        row.recent = _RollingWindow.from_dict(recent, recent_window)
        row.change = _RollingWindow.from_dict(change, change_window)
        rs = payload.get("regime_stats", {})
        if not isinstance(rs, Mapping):
            raise ValueError("invalid temporal dependency regime stats")
        row.regime_stats = _RunningCorrelation.from_dict(rs)
        row.regime_trial_units = int(payload.get("regime_trial_units", 0))
        if row.regime_trial_units < 0:
            raise ValueError("invalid temporal dependency regime trial count")
        start = payload.get("regime_start_index")
        row.regime_start_index = None if start is None else float(start)
        if row.regime_start_index is not None and not math.isfinite(row.regime_start_index):
            raise ValueError("invalid temporal dependency regime start")
        regimes = payload.get("regimes", [])
        if not isinstance(regimes, list):
            raise ValueError("invalid dependency regimes")
        row.regimes = [_DependencyRegime.from_dict(x) for x in regimes if isinstance(x, Mapping)]
        if len(row.regimes) != len(regimes):
            raise ValueError("invalid dependency regime entry")
        row.pending_direction = int(payload.get("pending_direction", 0))
        row.pending_count = int(payload.get("pending_count", 0))
        if row.pending_direction not in (-1, 0, 1) or row.pending_count < 0:
            raise ValueError("invalid dependency change detector state")
        return row


class EvidenceDependencyModel:
    """Learn hidden evidence redundancy from externally resolved grouped trials.

    Alpha.7.1 preserves alpha.7 cumulative statistics exactly and adds an
    opt-in temporal path. Temporal adaptation occurs only when callers provide a
    strictly increasing ``temporal_index``. A bounded O(1) recent view drives
    current inference, while discrete regimes preserve durable change points.
    """

    def __init__(
        self, *, min_trials: int = 64, min_abs_correlation: float = 0.25,
        min_fisher_z: float = 4.0, max_sources: int = 256, max_pairs: int = 32768,
        max_trials: int = 131072, max_readings_per_source_trial: int = 4096,
        recent_window: int = 192, self_change_window: int = 64,
        pair_change_window: int = 96, self_change_delta: float = 0.35,
        pair_change_delta: float = 0.45, self_change_z: float = 4.5,
        pair_change_z: float = 6.0, self_change_persistence: int = 3,
        pair_change_persistence: int = 5,
    ) -> None:
        self.min_trials = int(min_trials)
        self.min_abs_correlation = float(min_abs_correlation)
        self.min_fisher_z = float(min_fisher_z)
        self.max_sources = int(max_sources)
        self.max_pairs = int(max_pairs)
        self.max_trials = int(max_trials)
        self.max_readings_per_source_trial = int(max_readings_per_source_trial)
        self.recent_window = int(recent_window)
        self.self_change_window = int(self_change_window)
        self.pair_change_window = int(pair_change_window)
        self.self_change_delta = float(self_change_delta)
        self.pair_change_delta = float(pair_change_delta)
        self.self_change_z = float(self_change_z)
        self.pair_change_z = float(pair_change_z)
        self.self_change_persistence = int(self_change_persistence)
        self.pair_change_persistence = int(pair_change_persistence)

        if self.min_trials < 8: raise ValueError("min_trials must be >= 8")
        if not (0.0 <= self.min_abs_correlation < 1.0): raise ValueError("min_abs_correlation must be within [0,1)")
        if not math.isfinite(self.min_fisher_z) or self.min_fisher_z <= 0.0: raise ValueError("min_fisher_z must be finite and > 0")
        if self.max_sources < 1 or self.max_pairs < 1 or self.max_trials < 1 or self.max_readings_per_source_trial < 2:
            raise ValueError("dependency capacities must be >= 1 and max_readings_per_source_trial >= 2")
        if self.recent_window < self.min_trials:
            raise ValueError("recent_window must be >= min_trials")
        if not (8 <= self.self_change_window <= self.recent_window and 8 <= self.pair_change_window <= self.recent_window):
            raise ValueError("dependency change windows must be within [8,recent_window]")
        for name, value in (("self_change_delta", self.self_change_delta), ("pair_change_delta", self.pair_change_delta)):
            if not math.isfinite(value) or not (0.0 < value < 1.0): raise ValueError(f"{name} must be within (0,1)")
        for name, value in (("self_change_z", self.self_change_z), ("pair_change_z", self.pair_change_z)):
            if not math.isfinite(value) or value <= 0.0: raise ValueError(f"{name} must be finite and > 0")
        if self.self_change_persistence < 1 or self.pair_change_persistence < 1:
            raise ValueError("dependency change persistence must be >= 1")

        self._self: dict[str, _SelfDependency] = {}
        self._pairs: dict[tuple[str, str], _RunningCorrelation] = {}
        self._seen_trials: set[str] = set()
        self._version: int = 0
        self._last_temporal_index: float | None = None
        self._temporal_self: dict[str, _TemporalDependency] = {}
        self._temporal_pairs: dict[tuple[str, str], _TemporalDependency] = {}

    @property
    def version(self) -> int:
        return int(self._version)

    @staticmethod
    def _key(value: Any, name: str) -> str:
        key = str(value).strip()
        if not key: raise ValueError(f"{name} must be non-empty")
        return key

    @staticmethod
    def _pair(a: str, b: str) -> tuple[str, str]:
        return (a, b) if a < b else (b, a)

    @staticmethod
    def _correctness(observation: Any, truth: str) -> float:
        return 1.0 if str(observation) == truth else 0.0

    @staticmethod
    def _temporal_value(value: Any) -> float:
        if isinstance(value, bool):
            raise ValueError("temporal_index must be a finite increasing number")
        try:
            out = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("temporal_index must be a finite increasing number") from exc
        if not math.isfinite(out):
            raise ValueError("temporal_index must be a finite increasing number")
        return out

    @staticmethod
    def _self_contribution(vals: list[float], temporal_index: float) -> _RollingContribution | None:
        m = len(vals)
        if m < 2:
            return None
        k = float(sum(vals))
        pair_n = m * (m - 1)
        sx = k * float(m - 1)
        sxy = k * (k - 1.0)
        stats = _RunningCorrelation(
            n=int(pair_n), sum_x=sx, sum_y=sx,
            sum_x2=sx, sum_y2=sx, sum_xy=sxy,
        )
        return _RollingContribution(stats=stats, trial_units=1, temporal_index=temporal_index)

    @staticmethod
    def _pair_contribution(x: float, y: float, temporal_index: float) -> _RollingContribution:
        stats = _RunningCorrelation()
        stats.add(x, y)
        return _RollingContribution(stats=stats, trial_units=1, temporal_index=temporal_index)

    def _activate(self, raw_r: float, trials: int) -> float:
        if trials < self.min_trials or raw_r <= 0.0: return 0.0
        r = min(0.999999999999, max(-0.999999999999, float(raw_r)))
        if trials <= 3: return 0.0
        z = abs(math.atanh(r)) * math.sqrt(max(1.0, float(trials - 3)))
        if r < self.min_abs_correlation or z < self.min_fisher_z: return 0.0
        return float(r)

    @staticmethod
    def _change_z(a_r: float, a_n: int, b_r: float, b_n: int) -> float:
        if a_n <= 3 or b_n <= 3:
            return 0.0
        a = min(0.999999, max(-0.999999, float(a_r)))
        b = min(0.999999, max(-0.999999, float(b_r)))
        denom = math.sqrt((1.0 / float(a_n - 3)) + (1.0 / float(b_n - 3)))
        if denom <= 0.0:
            return 0.0
        return abs(math.atanh(a) - math.atanh(b)) / denom

    def _label(self, raw_r: float, trials: int) -> tuple[str, float]:
        active = self._activate(raw_r, trials)
        return ("dependent" if active > 0.0 else "independent_or_unproven", active)

    def _maybe_regime_change(self, state: _TemporalDependency, *, kind: str, temporal_index: float) -> None:
        if kind == "self":
            min_candidate = max(24, min(self.self_change_window, self.min_trials // 2))
            delta_gate = self.self_change_delta
            z_gate = self.self_change_z
            persistence = self.self_change_persistence
        else:
            min_candidate = max(48, min(self.pair_change_window, self.min_trials))
            delta_gate = self.pair_change_delta
            z_gate = self.pair_change_z
            persistence = self.pair_change_persistence

        if state.change.trial_units < min_candidate:
            return

        candidate_raw = state.change.stats.correlation()
        candidate_n = int(state.change.trial_units)

        if not state.regimes and state.change.trial_units < self.min_trials:
            return

        if not state.regimes:
            # The first regime is a descriptive baseline, not a detected split.
            label, active = self._label(candidate_raw, candidate_n)
            state.regimes.append(_DependencyRegime(
                version=1,
                start_index=float(state.regime_start_index if state.regime_start_index is not None else temporal_index),
                detected_index=float(temporal_index), end_index=None,
                raw_correlation=float(candidate_raw), active_correlation=float(active), label=label,
            ))
            # Anchor the first regime in the bounded change window rather than a
            # noisy handful of startup samples.
            state.reset_regime_to_change_window(temporal_index)
            return

        anchor_raw = state.regime_stats.correlation()
        anchor_n = int(state.regime_trial_units)
        # Dependency strength is one-sided: negative correlation remains visible
        # diagnostically but is not exploited as evidence redundancy.
        anchor_dep = max(0.0, anchor_raw)
        candidate_dep = max(0.0, candidate_raw)
        delta = candidate_dep - anchor_dep
        direction = 1 if delta > 0 else (-1 if delta < 0 else 0)
        material = abs(delta) >= delta_gate
        z = self._change_z(anchor_raw, max(anchor_n, 4), candidate_raw, max(candidate_n, 4))

        # Entering dependency is deliberately more conservative than leaving it:
        # this prevents noisy independent sources from fabricating a new regime.
        if direction > 0:
            enter_floor = 0.75 if kind == "self" else 0.65
            material = material and candidate_dep >= max(self.min_abs_correlation + 0.10, enter_floor)
        elif direction < 0:
            material = material and anchor_dep >= max(self.min_abs_correlation, 0.30)

        if not material or z < z_gate:
            state.pending_direction = 0
            state.pending_count = 0
            current_raw = state.regime_stats.correlation()
            current_label, current_active = self._label(current_raw, state.regime_trial_units)
            current = state.regimes[-1]
            current.raw_correlation = float(current_raw)
            current.active_correlation = float(current_active)
            current.label = current_label
            return

        if state.pending_direction == direction:
            state.pending_count += 1
        else:
            state.pending_direction = direction
            state.pending_count = 1
        if state.pending_count < persistence:
            current_raw = state.regime_stats.correlation()
            current_label, current_active = self._label(current_raw, state.regime_trial_units)
            current = state.regimes[-1]
            current.raw_correlation = float(current_raw)
            current.active_correlation = float(current_active)
            current.label = current_label
            return

        # Close the previous regime and start a new one from the actual bounded
        # candidate window. Historical sufficient statistics remain untouched.
        previous = state.regimes[-1]
        previous.raw_correlation = float(anchor_raw)
        previous_active = self._activate(anchor_raw, anchor_n)
        previous.active_correlation = float(previous_active)
        previous.label = "dependent" if previous_active > 0.0 else "independent_or_unproven"
        previous.end_index = float(temporal_index)
        label, active = self._label(candidate_raw, candidate_n)
        start_index = state.change.items[0].temporal_index if state.change.items else temporal_index
        state.regimes.append(_DependencyRegime(
            version=previous.version + 1,
            start_index=float(start_index), detected_index=float(temporal_index), end_index=None,
            raw_correlation=float(candidate_raw), active_correlation=float(active), label=label,
        ))
        state.reset_regime_to_change_window(temporal_index)

    def observe_trial(
        self, trial_id: str, *, resolved_hypothesis: str,
        observations: Mapping[str, Iterable[str]], temporal_index: int | float | None = None,
    ) -> dict[str, Any]:
        tid = self._key(trial_id, "trial_id")
        truth = self._key(resolved_hypothesis, "resolved_hypothesis")
        if tid in self._seen_trials: raise ValueError("dependency trial_id already observed")
        if len(self._seen_trials) >= self.max_trials: raise RuntimeError("evidence dependency trial capacity reached")
        if not isinstance(observations, Mapping) or not observations: raise ValueError("observations must be a non-empty source mapping")

        temporal = None if temporal_index is None else self._temporal_value(temporal_index)
        if temporal is not None and self._last_temporal_index is not None and temporal <= self._last_temporal_index:
            raise ValueError("temporal_index must be strictly increasing")

        per_source: dict[str, list[float]] = {}
        for raw_source, raw_obs in observations.items():
            source = self._key(raw_source, "source_id")
            if isinstance(raw_obs, (str, bytes)):
                raise ValueError("dependency observations for a source must be a sequence, not a string")
            vals = list(raw_obs)
            if not vals: raise ValueError("each dependency source must provide at least one observation")
            if len(vals) > self.max_readings_per_source_trial:
                raise RuntimeError("evidence dependency readings-per-source capacity reached")
            per_source[source] = [self._correctness(obs, truth) for obs in vals]

        # Preflight every cumulative capacity before any mutation. Temporal state
        # uses only sources/pairs already admitted by these same capacities.
        new_sources = [s for s in per_source if s not in self._self]
        if len(self._self) + len(new_sources) > self.max_sources:
            raise RuntimeError("evidence dependency source capacity reached")
        names_pre = sorted(per_source)
        new_pairs = 0
        for i, a in enumerate(names_pre):
            for b in names_pre[i + 1:]:
                if self._pair(a, b) not in self._pairs:
                    new_pairs += 1
        if len(self._pairs) + new_pairs > self.max_pairs:
            raise RuntimeError("evidence dependency pair capacity reached")

        # Build all temporal contributions before mutation, so malformed numeric
        # state cannot leave a half-applied trial.
        temporal_self: dict[str, _RollingContribution] = {}
        temporal_pairs: dict[tuple[str, str], _RollingContribution] = {}
        means = {s: sum(v) / float(len(v)) for s, v in per_source.items()}
        if temporal is not None:
            for source, vals in per_source.items():
                c = self._self_contribution(vals, temporal)
                if c is not None:
                    temporal_self[source] = c
            sources = sorted(means)
            for i, a in enumerate(sources):
                for b in sources[i + 1:]:
                    temporal_pairs[self._pair(a, b)] = self._pair_contribution(means[a], means[b], temporal)

        # Commit cumulative alpha.7 statistics.
        for source in per_source:
            if source not in self._self:
                self._self[source] = _SelfDependency()
        for source, vals in per_source.items():
            c = self._self_contribution(vals, temporal if temporal is not None else 0.0)
            if c is not None:
                row = self._self[source]
                row.trials += 1
                row.pairs.add_stats(c.stats)

        sources = sorted(means)
        for i, a in enumerate(sources):
            for b in sources[i + 1:]:
                key = self._pair(a, b)
                row = self._pairs.get(key)
                if row is None:
                    row = _RunningCorrelation(); self._pairs[key] = row
                row.add(means[a], means[b])

        # Commit explicit-time views only after the cumulative trial succeeded.
        if temporal is not None:
            for source, c in temporal_self.items():
                state = self._temporal_self.get(source)
                if state is None:
                    state = _TemporalDependency(self.recent_window, self.self_change_window)
                    self._temporal_self[source] = state
                state.add(c)
                self._maybe_regime_change(state, kind="self", temporal_index=temporal)
            for key, c in temporal_pairs.items():
                state = self._temporal_pairs.get(key)
                if state is None:
                    state = _TemporalDependency(self.recent_window, self.pair_change_window)
                    self._temporal_pairs[key] = state
                state.add(c)
                self._maybe_regime_change(state, kind="pair", temporal_index=temporal)
            self._last_temporal_index = temporal

        self._seen_trials.add(tid)
        self._version += 1
        return {
            "trial_id": tid, "sources": len(per_source), "observations": sum(len(v) for v in per_source.values()),
            "version": self.version, "temporal_index": temporal,
            "temporal_learning": temporal is not None,
        }

    def _self_views(self, source: str) -> tuple[_SelfDependency | None, _TemporalDependency | None]:
        return self._self.get(source), self._temporal_self.get(source)

    def self_dependency(self, source_id: str) -> dict[str, Any]:
        source = self._key(source_id, "source_id")
        row, temporal = self._self_views(source)
        if row is None:
            return {"source_id": source, "trials": 0, "raw_correlation": 0.0, "active_correlation": 0.0, "status": "insufficient_data"}
        cumulative_raw = row.pairs.correlation()
        cumulative_active = self._activate(cumulative_raw, row.trials)
        raw = cumulative_raw; active = cumulative_active; view = "cumulative"
        recent_trials = 0
        if temporal is not None:
            recent_trials = int(temporal.recent.trial_units)
            if recent_trials >= self.min_trials:
                raw = temporal.recent.stats.correlation()
                active = self._activate(raw, recent_trials)
                view = "recent"
        return {
            "source_id": source, "trials": int(row.trials), "pair_samples": int(row.pairs.n),
            "raw_correlation": float(raw), "active_correlation": float(active),
            "redundancy_strength": float(active * active),
            "status": "dependent" if active > 0.0 else "independent_or_unproven",
            "view": view, "recent_trials": recent_trials,
            "cumulative_raw_correlation": float(cumulative_raw),
            "cumulative_active_correlation": float(cumulative_active),
            "regime_count": 0 if temporal is None else len(temporal.regimes),
            "current_regime_version": 0 if temporal is None or not temporal.regimes else temporal.regimes[-1].version,
        }

    def pair_dependency(self, source_a: str, source_b: str) -> dict[str, Any]:
        a = self._key(source_a, "source_id"); b = self._key(source_b, "source_id")
        if a == b: return self.self_dependency(a)
        key = self._pair(a, b)
        row = self._pairs.get(key)
        if row is None:
            return {"source_a": a, "source_b": b, "trials": 0, "raw_correlation": 0.0, "active_correlation": 0.0, "status": "insufficient_data"}
        cumulative_raw = row.correlation(); cumulative_active = self._activate(cumulative_raw, row.n)
        raw = cumulative_raw; active = cumulative_active; view = "cumulative"
        temporal = self._temporal_pairs.get(key); recent_trials = 0
        if temporal is not None:
            recent_trials = int(temporal.recent.trial_units)
            if recent_trials >= self.min_trials:
                raw = temporal.recent.stats.correlation()
                active = self._activate(raw, recent_trials)
                view = "recent"
        return {
            "source_a": a, "source_b": b, "trials": int(row.n), "raw_correlation": float(raw),
            "active_correlation": float(active), "status": "dependent" if active > 0.0 else "independent_or_unproven",
            "view": view, "recent_trials": recent_trials,
            "cumulative_raw_correlation": float(cumulative_raw),
            "cumulative_active_correlation": float(cumulative_active),
            "regime_count": 0 if temporal is None else len(temporal.regimes),
            "current_regime_version": 0 if temporal is None or not temporal.regimes else temporal.regimes[-1].version,
        }

    def dependency_regimes(self, source_a: str, source_b: str | None = None) -> list[dict[str, Any]]:
        a = self._key(source_a, "source_id")
        if source_b is None or a == str(source_b).strip():
            state = self._temporal_self.get(a)
        else:
            b = self._key(source_b, "source_id")
            state = self._temporal_pairs.get(self._pair(a, b))
        return [] if state is None else [r.as_dict() for r in state.regimes]

    def correlation(self, source_a: str, source_b: str) -> float:
        if str(source_a).strip() == str(source_b).strip():
            return float(self.self_dependency(source_a)["active_correlation"])
        return float(self.pair_dependency(source_a, source_b)["active_correlation"])

    def source_has_active_dependency(self, source_id: str) -> bool:
        source = self._key(source_id, "source_id")
        if self.correlation(source, source) > 0.0:
            return True
        for a, b in self._pairs:
            if (a == source or b == source) and self.correlation(a, b) > 0.0:
                return True
        return False

    def effective_batch(self, source_ids: Iterable[str]) -> dict[str, float]:
        counts: dict[str, int] = {}
        for raw in source_ids:
            source = self._key(raw, "source_id")
            counts[source] = counts.get(source, 0) + 1
        n = sum(counts.values())
        if n < 1:
            raise ValueError("dependency batch requires at least one source")
        denom = float(n)
        names = sorted(counts)
        for source in names:
            c = counts[source]
            if c > 1:
                rho = self.correlation(source, source)
                denom += float(c * (c - 1)) * (rho * rho)
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                rho = self.correlation(a, b)
                denom += 2.0 * float(counts[a] * counts[b]) * (rho * rho)
        effective = (float(n) * float(n)) / max(float(n), denom)
        scale = max(0.0, min(1.0, effective / float(n)))
        return {
            "raw_count": float(n), "effective_count": float(effective),
            "scale": float(scale), "correlation_denominator": float(denom),
        }

    def stats(self) -> dict[str, Any]:
        active_self = sum(1 for s in self._self if self.correlation(s, s) > 0.0)
        active_pairs = sum(1 for a, b in self._pairs if self.correlation(a, b) > 0.0)
        return {
            "sources": len(self._self), "pairs": len(self._pairs), "trials": len(self._seen_trials),
            "active_self_dependencies": active_self, "active_cross_dependencies": active_pairs,
            "temporal_self_views": len(self._temporal_self), "temporal_pair_views": len(self._temporal_pairs),
            "dependency_regimes": sum(len(s.regimes) for s in self._temporal_self.values()) + sum(len(s.regimes) for s in self._temporal_pairs.values()),
            "last_temporal_index": self._last_temporal_index,
            "version": self.version,
        }

    def export_state(self) -> dict[str, Any]:
        return {
            "schema": 2, "min_trials": self.min_trials, "min_abs_correlation": self.min_abs_correlation,
            "min_fisher_z": self.min_fisher_z, "version": self.version,
            "seen_trials": sorted(self._seen_trials),
            "self": {s: row.as_dict() for s, row in sorted(self._self.items())},
            "pairs": {f"{a}\t{b}": row.as_dict() for (a, b), row in sorted(self._pairs.items())},
            "temporal": {
                "last_temporal_index": self._last_temporal_index,
                "self": {s: row.as_dict() for s, row in sorted(self._temporal_self.items())},
                "pairs": {f"{a}\t{b}": row.as_dict() for (a, b), row in sorted(self._temporal_pairs.items())},
            },
        }

    def import_state(self, payload: Mapping[str, Any] | None) -> None:
        if not payload: return
        schema = int(payload.get("schema", 1))
        if schema not in (1, 2): raise ValueError("unsupported evidence dependency snapshot schema")
        seen = payload.get("seen_trials", [])
        if not isinstance(seen, list) or len(seen) > self.max_trials: raise ValueError("invalid dependency trial snapshot")
        seen_set = {self._key(x, "trial_id") for x in seen}
        raw_self = payload.get("self", {}); raw_pairs = payload.get("pairs", {})
        if not isinstance(raw_self, Mapping) or len(raw_self) > self.max_sources: raise ValueError("invalid dependency source snapshot")
        if not isinstance(raw_pairs, Mapping) or len(raw_pairs) > self.max_pairs: raise ValueError("invalid dependency pair snapshot")
        restored_self: dict[str, _SelfDependency] = {}
        for source, item in raw_self.items():
            key = self._key(source, "source_id")
            if not isinstance(item, Mapping): raise ValueError("invalid dependency self state")
            trials = int(item.get("trials", 0))
            if trials < 0: raise ValueError("invalid dependency trial count")
            pairs = item.get("pairs", {})
            if not isinstance(pairs, Mapping): raise ValueError("invalid dependency pair state")
            restored_self[key] = _SelfDependency(pairs=_RunningCorrelation.from_dict(pairs), trials=trials)
        restored_pairs: dict[tuple[str, str], _RunningCorrelation] = {}
        for encoded, item in raw_pairs.items():
            parts = str(encoded).split("\t")
            if len(parts) != 2 or not parts[0] or not parts[1] or parts[0] >= parts[1]: raise ValueError("invalid dependency pair key")
            if not isinstance(item, Mapping): raise ValueError("invalid dependency pair state")
            restored_pairs[(parts[0], parts[1])] = _RunningCorrelation.from_dict(item)

        restored_temporal_self: dict[str, _TemporalDependency] = {}
        restored_temporal_pairs: dict[tuple[str, str], _TemporalDependency] = {}
        restored_last_index: float | None = None
        if schema == 2:
            temporal = payload.get("temporal", {})
            if not isinstance(temporal, Mapping): raise ValueError("invalid temporal dependency snapshot")
            last_idx = temporal.get("last_temporal_index")
            if last_idx is not None:
                restored_last_index = self._temporal_value(last_idx)
            raw_tself = temporal.get("self", {}); raw_tpairs = temporal.get("pairs", {})
            if not isinstance(raw_tself, Mapping) or not isinstance(raw_tpairs, Mapping):
                raise ValueError("invalid temporal dependency snapshot")
            if len(raw_tself) > self.max_sources or len(raw_tpairs) > self.max_pairs:
                raise ValueError("temporal dependency snapshot exceeds capacity")
            for source, item in raw_tself.items():
                key = self._key(source, "source_id")
                if key not in restored_self or not isinstance(item, Mapping):
                    raise ValueError("invalid temporal dependency source state")
                restored_temporal_self[key] = _TemporalDependency.from_dict(
                    item, self.recent_window, self.self_change_window
                )
            for encoded, item in raw_tpairs.items():
                parts = str(encoded).split("\t")
                if len(parts) != 2 or parts[0] >= parts[1] or not isinstance(item, Mapping):
                    raise ValueError("invalid temporal dependency pair state")
                key = (parts[0], parts[1])
                if key not in restored_pairs:
                    raise ValueError("temporal dependency pair missing cumulative state")
                restored_temporal_pairs[key] = _TemporalDependency.from_dict(
                    item, self.recent_window, self.pair_change_window
                )

        # Commit only after the entire snapshot validates. Schema-1 migration
        # intentionally creates no temporal history/regimes.
        self._seen_trials = seen_set; self._self = restored_self; self._pairs = restored_pairs
        self._temporal_self = restored_temporal_self; self._temporal_pairs = restored_temporal_pairs
        self._last_temporal_index = restored_last_index
        self._version = int(payload.get("version", len(seen_set)))
        if self._version < 0: raise ValueError("invalid dependency version")
