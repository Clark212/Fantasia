from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Iterable


@dataclass(slots=True)
class EvidenceRegime:
    """One temporally coherent reliability regime for an evidence source.

    Regimes preserve older source behaviour instead of averaging incompatible
    periods into one Beta posterior.  They are only created from externally
    resolved, explicitly time-ordered observations.
    """

    regime_id: int
    alpha: float
    beta: float
    start_observation: float
    resolved_observations: float = 0.0
    start_temporal_index: float | None = None
    end_temporal_index: float | None = None
    trigger: str = "initial"

    @property
    def reliability(self) -> float:
        total = self.alpha + self.beta
        return self.alpha / total if total > 0.0 else 0.5

    @property
    def variance(self) -> float:
        total = self.alpha + self.beta
        if total <= 0.0:
            return 0.25
        return (self.alpha * self.beta) / (total * total * (total + 1.0))

    @property
    def stddev(self) -> float:
        return math.sqrt(max(0.0, self.variance))

    def as_dict(self) -> dict[str, Any]:
        return {
            "regime_id": int(self.regime_id),
            "alpha": float(self.alpha),
            "beta": float(self.beta),
            "reliability": float(self.reliability),
            "uncertainty_stddev": float(self.stddev),
            "start_observation": float(self.start_observation),
            "resolved_observations": float(self.resolved_observations),
            "start_temporal_index": self.start_temporal_index,
            "end_temporal_index": self.end_temporal_index,
            "trigger": str(self.trigger),
        }


@dataclass(slots=True)
class EvidenceSourceReliability:
    """Persistent source calibration with optional time-aware regimes.

    ``alpha``/``beta`` retain the full-history Beta posterior from alpha.6.
    ``regimes`` add a second view: when explicitly time-ordered resolved
    observations show a statistically large change, a new active regime is
    created while the old one remains available for provenance/history.

    Inference never self-labels the source from ASM's own posterior.
    """

    source_id: str
    alpha: float
    beta: float
    prior_reliability: float
    prior_strength: float
    resolved_observations: float = 0.0
    regimes: list[EvidenceRegime] = field(default_factory=list)
    temporal_outcomes: list[float] = field(default_factory=list)
    last_temporal_index: float | None = None
    drift_score: float = 0.0
    drift_zscore: float = 0.0
    drift_log_bayes_factor: float = 0.0
    last_change_temporal_index: float | None = None

    @property
    def reliability(self) -> float:
        """Full-history alpha.6-compatible reliability."""
        total = self.alpha + self.beta
        return self.alpha / total if total > 0.0 else 0.5

    @property
    def active_regime(self) -> EvidenceRegime | None:
        return self.regimes[-1] if self.regimes else None

    @property
    def effective_reliability(self) -> float:
        # Once explicit temporal evidence exists, inference uses a bounded recent
        # Beta estimate instead of letting ancient history dominate forever.
        # The cumulative and versioned-regime posteriors are still preserved.
        if self.last_temporal_index is not None and self.temporal_outcomes:
            recent = self.temporal_outcomes
            a0 = max(1e-6, self.prior_reliability * min(self.prior_strength, 4.0))
            b0 = max(1e-6, (1.0 - self.prior_reliability) * min(self.prior_strength, 4.0))
            a = a0 + sum(recent)
            b = b0 + float(len(recent)) - sum(recent)
            return float(a / (a + b))
        regime = self.active_regime
        if regime is None:
            return self.reliability
        return float(regime.reliability)

    @property
    def variance(self) -> float:
        total = self.alpha + self.beta
        if total <= 0.0:
            return 0.25
        return (self.alpha * self.beta) / (total * total * (total + 1.0))

    @property
    def stddev(self) -> float:
        return math.sqrt(max(0.0, self.variance))

    @property
    def effective_variance(self) -> float:
        if self.last_temporal_index is not None and self.temporal_outcomes:
            total_success = sum(self.temporal_outcomes)
            a = max(1e-6, self.prior_reliability * min(self.prior_strength, 4.0)) + total_success
            b = max(1e-6, (1.0 - self.prior_reliability) * min(self.prior_strength, 4.0)) + float(len(self.temporal_outcomes)) - total_success
            total = a + b
            return (a * b) / (total * total * (total + 1.0))
        regime = self.active_regime
        return regime.variance if regime is not None else self.variance

    @property
    def effective_stddev(self) -> float:
        return math.sqrt(max(0.0, self.effective_variance))

    def as_dict(self, *, supplied_reliability: float | None = None) -> dict[str, Any]:
        learned = float(self.reliability)
        effective = float(self.effective_reliability)
        supplied = self.prior_reliability if supplied_reliability is None else float(supplied_reliability)
        regime = self.active_regime
        return {
            "source_id": self.source_id,
            # Preserve alpha.6 meaning for compatibility/research comparison.
            "reliability": learned,
            "effective_reliability": effective,
            "uncertainty_stddev": float(self.stddev),
            "effective_uncertainty_stddev": float(self.effective_stddev),
            "alpha": float(self.alpha),
            "beta": float(self.beta),
            "resolved_observations": float(self.resolved_observations),
            "prior_reliability": float(self.prior_reliability),
            "prior_strength": float(self.prior_strength),
            "supplied_reliability": float(supplied),
            "model_mismatch_abs": abs(learned - float(supplied)),
            "effective_model_mismatch_abs": abs(effective - float(supplied)),
            "calibrated": self.resolved_observations > 0.0,
            "regime_count": len(self.regimes),
            "active_regime_id": int(regime.regime_id) if regime else None,
            "active_regime_observations": float(regime.resolved_observations) if regime else 0.0,
            "drift_score": float(self.drift_score),
            "drift_zscore": float(self.drift_zscore),
            "drift_log_bayes_factor": float(self.drift_log_bayes_factor),
            "last_temporal_index": self.last_temporal_index,
            "last_change_temporal_index": self.last_change_temporal_index,
            "regimes": [r.as_dict() for r in self.regimes],
        }


class AdaptiveEvidenceModel:
    """Learn evidence-source reliability from externally resolved truth.

    Alpha.6.1 adds *bounded temporal regime detection* while retaining the
    alpha.6 cumulative Beta posterior.  Drift detection is activated only when
    the caller supplies a monotonically increasing ``temporal_index``.  This is
    deliberate: without time metadata, calibration examples are exchangeable
    and there is no principled way to distinguish a shuffled stationary sample
    from a genuine temporal change.

    This stage still does NOT learn source correlations, latent causes, or an
    arbitrary confusion matrix.  Those limitations remain visible.
    """

    def __init__(
        self,
        *,
        prior_strength: float = 4.0,
        min_shape: float = 1e-6,
        max_sources: int = 1024,
        drift_detection_enabled: bool = True,
        drift_window: int = 32,
        drift_min_abs_change: float = 0.25,
        drift_min_zscore: float = 3.0,
        drift_min_log_bayes_factor: float = 10.0,
        max_regimes_per_source: int = 16,
    ):
        self.prior_strength = self._finite_positive(prior_strength, "prior_strength")
        self.min_shape = self._finite_positive(min_shape, "min_shape")
        self.max_sources = int(max_sources)
        if self.max_sources < 1:
            raise ValueError("max_sources must be >= 1")
        self.drift_detection_enabled = bool(drift_detection_enabled)
        self.drift_window = int(drift_window)
        if self.drift_window < 4:
            raise ValueError("drift_window must be >= 4")
        self.drift_min_abs_change = self._finite_nonnegative(drift_min_abs_change, "drift_min_abs_change")
        if self.drift_min_abs_change > 1.0:
            raise ValueError("drift_min_abs_change must be <= 1")
        self.drift_min_zscore = self._finite_positive(drift_min_zscore, "drift_min_zscore")
        self.drift_min_log_bayes_factor = self._finite_nonnegative(drift_min_log_bayes_factor, "drift_min_log_bayes_factor")
        self.max_regimes_per_source = int(max_regimes_per_source)
        if self.max_regimes_per_source < 1:
            raise ValueError("max_regimes_per_source must be >= 1")
        self._sources: dict[str, EvidenceSourceReliability] = {}

    @staticmethod
    def _finite_positive(value: float, name: str) -> float:
        try:
            x = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} must be numeric") from exc
        if not math.isfinite(x) or x <= 0.0:
            raise ValueError(f"{name} must be finite and > 0")
        return x

    @staticmethod
    def _finite_nonnegative(value: float, name: str) -> float:
        try:
            x = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} must be numeric") from exc
        if not math.isfinite(x) or x < 0.0:
            raise ValueError(f"{name} must be finite and >= 0")
        return x

    @staticmethod
    def _validate_reliability(value: float | None, *, default: float = 0.5) -> float:
        if value is None:
            return float(default)
        try:
            r = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("reliability must be numeric") from exc
        if not math.isfinite(r) or r < 0.0 or r > 1.0:
            raise ValueError("reliability must be finite and within [0, 1]")
        return r

    @staticmethod
    def _source_key(source_id: str) -> str:
        key = str(source_id).strip()
        if not key:
            raise ValueError("source_id must be non-empty")
        return key

    @staticmethod
    def _validate_temporal_index(value: float | int | None) -> float | None:
        if value is None:
            return None
        try:
            x = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("temporal_index must be numeric") from exc
        if not math.isfinite(x):
            raise ValueError("temporal_index must be finite")
        return x

    def _initial_regime(self, *, alpha: float, beta: float) -> EvidenceRegime:
        return EvidenceRegime(
            regime_id=1,
            alpha=float(alpha),
            beta=float(beta),
            start_observation=0.0,
            resolved_observations=0.0,
            trigger="initial",
        )

    def register_source(self, source_id: str, *, supplied_reliability: float | None = None) -> EvidenceSourceReliability:
        key = self._source_key(source_id)
        existing = self._sources.get(key)
        if existing is not None:
            if supplied_reliability is not None:
                self._validate_reliability(supplied_reliability)
            return existing
        if len(self._sources) >= self.max_sources:
            raise RuntimeError("adaptive evidence source capacity reached")
        r = self._validate_reliability(supplied_reliability)
        strength = self.prior_strength
        # Tiny positive shapes preserve the ability to learn away from exact 0/1.
        alpha = max(self.min_shape, r * strength)
        beta = max(self.min_shape, (1.0 - r) * strength)
        state = EvidenceSourceReliability(
            source_id=key,
            alpha=alpha,
            beta=beta,
            prior_reliability=r,
            prior_strength=strength,
            regimes=[self._initial_regime(alpha=alpha, beta=beta)],
        )
        self._sources[key] = state
        return state

    def get(self, source_id: str) -> EvidenceSourceReliability | None:
        return self._sources.get(self._source_key(source_id))

    def reliability(self, source_id: str, *, supplied_reliability: float | None = None) -> float:
        """Return current effective reliability used by inference."""
        state = self.register_source(source_id, supplied_reliability=supplied_reliability)
        return float(state.effective_reliability)

    def cumulative_reliability(self, source_id: str, *, supplied_reliability: float | None = None) -> float:
        state = self.register_source(source_id, supplied_reliability=supplied_reliability)
        return float(state.reliability)

    @staticmethod
    def _beta_log_marginal(successes: float, failures: float, *, alpha: float = 1.0, beta: float = 1.0) -> float:
        return (math.lgamma(alpha + successes) + math.lgamma(beta + failures)
                - math.lgamma(alpha + beta + successes + failures)
                - (math.lgamma(alpha) + math.lgamma(beta) - math.lgamma(alpha + beta)))

    def _update_temporal_detector(
        self,
        state: EvidenceSourceReliability,
        *,
        correct: float,
        temporal_index: float,
    ) -> bool:
        if state.last_temporal_index is not None and temporal_index <= state.last_temporal_index:
            raise ValueError("temporal_index must increase strictly for each source")
        state.last_temporal_index = float(temporal_index)
        if not self.drift_detection_enabled:
            return False

        # Keep at most two windows.  Bounded memory makes the detector O(window).
        limit = 2 * self.drift_window
        state.temporal_outcomes.append(float(correct))
        if len(state.temporal_outcomes) > limit:
            del state.temporal_outcomes[: len(state.temporal_outcomes) - limit]
        if len(state.temporal_outcomes) < limit:
            state.drift_score = 0.0
            state.drift_zscore = 0.0
            state.drift_log_bayes_factor = 0.0
            return False

        older = state.temporal_outcomes[: self.drift_window]
        recent = state.temporal_outcomes[self.drift_window :]
        p_old = sum(older) / float(self.drift_window)
        p_new = sum(recent) / float(self.drift_window)
        diff = abs(p_new - p_old)
        # Two-proportion normal approximation, used only as a bounded trigger.
        pooled = (sum(older) + sum(recent)) / float(2 * self.drift_window)
        se = math.sqrt(max(1e-12, pooled * (1.0 - pooled) * (2.0 / float(self.drift_window))))
        z = diff / se
        old_s = float(sum(older)); old_f = float(self.drift_window) - old_s
        new_s = float(sum(recent)); new_f = float(self.drift_window) - new_s
        log_bf = (self._beta_log_marginal(old_s, old_f)
                  + self._beta_log_marginal(new_s, new_f)
                  - self._beta_log_marginal(old_s + new_s, old_f + new_f))
        state.drift_score = float(diff)
        state.drift_zscore = float(z)
        state.drift_log_bayes_factor = float(log_bf)

        active = state.active_regime
        if active is None:
            return False
        if active.resolved_observations < float(2 * self.drift_window):
            return False
        if (diff < self.drift_min_abs_change or z < self.drift_min_zscore
                or log_bf < self.drift_min_log_bayes_factor):
            return False
        if len(state.regimes) >= self.max_regimes_per_source:
            return False

        # Preserve the previous regime; seed the new regime from the recent
        # window plus a weak neutral prior.  The recent evidence has already
        # contributed to full-history alpha/beta, but it is intentionally reused
        # to estimate the new temporal regime rather than forgotten.
        active.end_temporal_index = float(temporal_index)
        weak = min(2.0, state.prior_strength)
        recent_success = float(sum(recent))
        recent_fail = float(self.drift_window) - recent_success
        new_regime = EvidenceRegime(
            regime_id=active.regime_id + 1,
            alpha=max(self.min_shape, 0.5 * weak + recent_success),
            beta=max(self.min_shape, 0.5 * weak + recent_fail),
            start_observation=max(0.0, state.resolved_observations - float(self.drift_window)),
            resolved_observations=float(self.drift_window),
            start_temporal_index=float(temporal_index),
            trigger="two_window_change_point",
        )
        state.regimes.append(new_regime)
        state.last_change_temporal_index = float(temporal_index)
        # Retain the recent half so another change needs a genuinely new window.
        state.temporal_outcomes = list(recent)
        return True

    def observe_resolved(
        self,
        source_id: str,
        *,
        observation: str,
        resolved_hypothesis: str,
        supplied_reliability: float | None = None,
        weight: float = 1.0,
        temporal_index: float | int | None = None,
    ) -> dict[str, Any]:
        state = self.register_source(source_id, supplied_reliability=supplied_reliability)
        obs = str(observation)
        truth = str(resolved_hypothesis)
        if not obs or not truth:
            raise ValueError("observation and resolved_hypothesis must be non-empty")
        w = self._finite_positive(weight, "weight")
        t = self._validate_temporal_index(temporal_index)
        correct = 1.0 if obs == truth else 0.0

        # Full-history alpha.6 posterior is never discarded.
        if correct:
            state.alpha += w
        else:
            state.beta += w
        state.resolved_observations += w

        active = state.active_regime
        if active is None:
            active = self._initial_regime(alpha=max(self.min_shape, 0.5 * state.prior_strength), beta=max(self.min_shape, 0.5 * state.prior_strength))
            state.regimes.append(active)
        if correct:
            active.alpha += w
        else:
            active.beta += w
        active.resolved_observations += w

        changed = False
        if t is not None:
            if abs(w - 1.0) > 1e-12:
                raise ValueError("temporal drift detection currently requires unit-weight observations")
            changed = self._update_temporal_detector(state, correct=correct, temporal_index=t)
        result = state.as_dict(supplied_reliability=supplied_reliability)
        result["regime_changed"] = bool(changed)
        return result

    def likelihoods(
        self,
        source_id: str,
        *,
        observation: str,
        hypotheses: Iterable[str],
        supplied_reliability: float | None = None,
    ) -> dict[str, float]:
        names = tuple(dict.fromkeys(str(h) for h in hypotheses))
        if len(names) < 2:
            raise ValueError("adaptive evidence requires at least two distinct hypotheses")
        obs = str(observation)
        if obs not in names:
            raise ValueError("alpha.6 symmetric reliability model requires observation to name one hypothesis")
        r = self.reliability(source_id, supplied_reliability=supplied_reliability)
        spill = (1.0 - r) / float(len(names) - 1)
        return {h: (r if h == obs else spill) for h in names}

    def status(self, source_id: str, *, supplied_reliability: float | None = None) -> dict[str, Any]:
        state = self.register_source(source_id, supplied_reliability=supplied_reliability)
        return state.as_dict(supplied_reliability=supplied_reliability)

    def export_state(self) -> dict[str, Any]:
        return {
            "schema": 2,
            "prior_strength": self.prior_strength,
            "min_shape": self.min_shape,
            "max_sources": self.max_sources,
            "drift_detection_enabled": self.drift_detection_enabled,
            "drift_window": self.drift_window,
            "drift_min_abs_change": self.drift_min_abs_change,
            "drift_min_zscore": self.drift_min_zscore,
            "drift_min_log_bayes_factor": self.drift_min_log_bayes_factor,
            "max_regimes_per_source": self.max_regimes_per_source,
            "sources": {
                key: {
                    "alpha": state.alpha,
                    "beta": state.beta,
                    "prior_reliability": state.prior_reliability,
                    "prior_strength": state.prior_strength,
                    "resolved_observations": state.resolved_observations,
                    "temporal_outcomes": list(state.temporal_outcomes),
                    "last_temporal_index": state.last_temporal_index,
                    "drift_score": state.drift_score,
                    "drift_zscore": state.drift_zscore,
                    "drift_log_bayes_factor": state.drift_log_bayes_factor,
                    "last_change_temporal_index": state.last_change_temporal_index,
                    "regimes": [r.as_dict() for r in state.regimes],
                }
                for key, state in sorted(self._sources.items())
            },
        }

    def import_state(self, payload: dict[str, Any] | None) -> None:
        if not payload:
            return
        schema = int(payload.get("schema", 1))
        if schema not in (1, 2):
            raise ValueError("unsupported adaptive evidence snapshot schema")
        raw_sources = payload.get("sources", {})
        if not isinstance(raw_sources, dict):
            raise ValueError("adaptive evidence snapshot sources must be a mapping")
        if len(raw_sources) > self.max_sources:
            raise ValueError("adaptive evidence snapshot exceeds source capacity")
        restored: dict[str, EvidenceSourceReliability] = {}
        for raw_key, raw in raw_sources.items():
            if not isinstance(raw, dict):
                raise ValueError("adaptive evidence source snapshot must be a mapping")
            key = self._source_key(raw_key)
            alpha = self._finite_positive(raw.get("alpha"), "alpha")
            beta = self._finite_positive(raw.get("beta"), "beta")
            prior_r = self._validate_reliability(raw.get("prior_reliability"))
            prior_strength = self._finite_positive(raw.get("prior_strength", self.prior_strength), "prior_strength")
            resolved = float(raw.get("resolved_observations", 0.0))
            if not math.isfinite(resolved) or resolved < 0.0:
                raise ValueError("resolved_observations must be finite and >= 0")

            regimes: list[EvidenceRegime] = []
            temporal_outcomes: list[float] = []
            last_temporal_index = None
            drift_score = 0.0
            drift_zscore = 0.0
            drift_log_bayes_factor = 0.0
            last_change = None
            if schema == 2:
                raw_regimes = raw.get("regimes", [])
                if not isinstance(raw_regimes, list) or len(raw_regimes) > self.max_regimes_per_source:
                    raise ValueError("adaptive evidence regimes must be a bounded list")
                for index, item in enumerate(raw_regimes, start=1):
                    if not isinstance(item, dict):
                        raise ValueError("adaptive evidence regime snapshot must be a mapping")
                    rid = int(item.get("regime_id", index))
                    ra = self._finite_positive(item.get("alpha"), "regime alpha")
                    rb = self._finite_positive(item.get("beta"), "regime beta")
                    ro = float(item.get("resolved_observations", 0.0))
                    if not math.isfinite(ro) or ro < 0.0:
                        raise ValueError("regime resolved_observations must be finite and >= 0")
                    start_obs = float(item.get("start_observation", 0.0))
                    if not math.isfinite(start_obs) or start_obs < 0.0:
                        raise ValueError("regime start_observation must be finite and >= 0")
                    st = item.get("start_temporal_index")
                    et = item.get("end_temporal_index")
                    st = self._validate_temporal_index(st)
                    et = self._validate_temporal_index(et)
                    regimes.append(EvidenceRegime(
                        regime_id=rid,
                        alpha=ra,
                        beta=rb,
                        start_observation=start_obs,
                        resolved_observations=ro,
                        start_temporal_index=st,
                        end_temporal_index=et,
                        trigger=str(item.get("trigger", "restored")),
                    ))
                temporal = raw.get("temporal_outcomes", [])
                if not isinstance(temporal, list) or len(temporal) > 2 * self.drift_window:
                    raise ValueError("temporal_outcomes must be a bounded list")
                for value in temporal:
                    x = float(value)
                    if x not in (0.0, 1.0):
                        raise ValueError("temporal_outcomes must contain only 0/1")
                    temporal_outcomes.append(x)
                last_temporal_index = self._validate_temporal_index(raw.get("last_temporal_index"))
                drift_score = self._finite_nonnegative(raw.get("drift_score", 0.0), "drift_score")
                drift_zscore = self._finite_nonnegative(raw.get("drift_zscore", 0.0), "drift_zscore")
                drift_log_bayes_factor = float(raw.get("drift_log_bayes_factor", 0.0))
                if not math.isfinite(drift_log_bayes_factor):
                    raise ValueError("drift_log_bayes_factor must be finite")
                last_change = self._validate_temporal_index(raw.get("last_change_temporal_index"))
            if not regimes:
                # Alpha.6 schema migration: one active regime exactly mirrors the
                # cumulative posterior, so migration changes no inference result.
                regimes = [EvidenceRegime(
                    regime_id=1,
                    alpha=alpha,
                    beta=beta,
                    start_observation=0.0,
                    resolved_observations=resolved,
                    trigger="alpha6_migration" if schema == 1 else "restored",
                )]
            restored[key] = EvidenceSourceReliability(
                source_id=key,
                alpha=alpha,
                beta=beta,
                prior_reliability=prior_r,
                prior_strength=prior_strength,
                resolved_observations=resolved,
                regimes=regimes,
                temporal_outcomes=temporal_outcomes,
                last_temporal_index=last_temporal_index,
                drift_score=drift_score,
                drift_zscore=drift_zscore,
                drift_log_bayes_factor=drift_log_bayes_factor,
                last_change_temporal_index=last_change,
            )
        self._sources = restored
