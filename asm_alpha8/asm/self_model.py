from __future__ import annotations

from collections import deque
from math import sqrt
from typing import Dict, Iterable, List, Optional

from .config import ASMConfig
from .mind import canonical_proposition
from .mental_language import MentalLanguagePerception


class SelfModel:
    """
    Persistent ASM self-model.

    This is not a claim of consciousness. It is an explicit computational model
    of ASM's own beliefs, capability estimates, strategy outcomes, and
    internally useful appraisal signals.

    Internal state currently tracks:
      - curiosity: uncertainty/novelty-driven exploration pressure
      - frustration_like: repeated failure / goal blockage signal
      - confidence: recent success/predictability signal
      - urgency: externally supplied priority pressure
    """

    def __init__(self, config: ASMConfig):
        self.cfg = config
        self.beliefs: Dict[str, dict] = {}
        self.capabilities: Dict[str, dict] = {}
        self.strategies: Dict[str, Dict[str, dict]] = {}
        self.recent_outcomes: deque[dict] = deque(
            maxlen=max(4, self.cfg.frustration_failure_window)
        )
        self.internal = {
            "curiosity": 0.0,
            "frustration_like": 0.0,
            "confidence": 0.5,
            "urgency": 0.0,
        }
        self.history: List[dict] = []

    def _belief_slot(self, proposition: str) -> dict:
        return self.beliefs.setdefault(
            proposition,
            {
                "true_evidence": 0.0,
                "false_evidence": 0.0,
                "observations": 0,
                "last_event": 0,
                "sources": [],
            },
        )

    def believe(
        self,
        proposition: str,
        truth: bool,
        confidence: float,
        event_id: int,
        source: str = "self_observation",
    ) -> dict:
        base, requested_truth = canonical_proposition(proposition)
        # If proposition itself was negative, combine that with caller truth.
        actual_truth = requested_truth if truth else not requested_truth

        slot = self._belief_slot(base)
        t = float(slot.get("true_evidence", 0.0)) * self.cfg.self_belief_decay
        f = float(slot.get("false_evidence", 0.0)) * self.cfg.self_belief_decay

        gain = max(0.0, min(1.0, float(confidence)))
        if actual_truth:
            t += gain
        else:
            f += gain

        sources = list(slot.get("sources", []))
        sources.append({
            "event_id": int(event_id),
            "source": source,
            "truth": bool(actual_truth),
            "confidence": gain,
        })
        sources = sources[-12:]

        slot.update(
            true_evidence=t,
            false_evidence=f,
            observations=int(slot.get("observations", 0)) + 1,
            last_event=int(event_id),
            sources=sources,
        )
        return self.query(base)

    def query(self, proposition: str) -> dict:
        base, _ = canonical_proposition(proposition)
        slot = self.beliefs.get(base)
        if not slot:
            return {
                "proposition": base,
                "status": "unknown",
                "truth": None,
                "confidence": 0.0,
                "observations": 0,
            }

        t = float(slot.get("true_evidence", 0.0))
        f = float(slot.get("false_evidence", 0.0))
        total = t + f
        if total <= 0:
            truth = None
            confidence = 0.0
            status = "unknown"
        else:
            p = t / total
            margin = abs(p - 0.5)
            if margin < self.cfg.belief_confidence_margin:
                truth = None
                confidence = 2.0 * margin
                status = "uncertain"
            elif p > 0.5:
                truth = True
                confidence = p
                status = "believed_true"
            else:
                truth = False
                confidence = 1.0 - p
                status = "believed_false"

        return {
            "proposition": base,
            "status": status,
            "truth": truth,
            "confidence": confidence,
            "true_evidence": t,
            "false_evidence": f,
            "observations": int(slot.get("observations", 0)),
            "last_event": int(slot.get("last_event", 0)),
            "sources": list(slot.get("sources", [])),
        }

    @staticmethod
    def _capability_record() -> dict:
        return {
            "successes": 0.0,
            "failures": 0.0,
            "attempts": 0,
            "last_event": 0,
        }

    @staticmethod
    def _strategy_record() -> dict:
        return {
            "successes": 0.0,
            "failures": 0.0,
            "attempts": 0,
            "last_event": 0,
        }

    @staticmethod
    def _success_estimate(record: dict) -> float:
        # Beta(1,1) prior prevents unjustified certainty from one attempt.
        s = float(record.get("successes", 0.0))
        f = float(record.get("failures", 0.0))
        return (s + 1.0) / (s + f + 2.0)

    def record_strategy_outcome(
        self,
        task_family: str,
        strategy: str,
        success: bool,
        event_id: int,
        score: float = 1.0,
    ) -> dict:
        task = str(task_family).strip().lower() or "unknown"
        strategy = str(strategy).strip().lower() or "unknown"
        weight = max(0.0, min(1.0, float(score)))

        cap = self.capabilities.setdefault(task, self._capability_record())
        strat = self.strategies.setdefault(task, {}).setdefault(
            strategy,
            self._strategy_record(),
        )

        for rec in (cap, strat):
            rec["attempts"] = int(rec.get("attempts", 0)) + 1
            rec["last_event"] = int(event_id)

        if success:
            gain = self.cfg.self_success_gain * weight
            cap["successes"] = float(cap.get("successes", 0.0)) + gain
            strat["successes"] = float(strat.get("successes", 0.0)) + gain
        else:
            gain = self.cfg.self_failure_gain * weight
            cap["failures"] = float(cap.get("failures", 0.0)) + gain
            strat["failures"] = float(strat.get("failures", 0.0)) + gain

        estimate = self._success_estimate(cap)
        self.believe(
            f"capable at {task}",
            truth=estimate >= 0.5,
            confidence=abs(estimate - 0.5) * 2.0,
            event_id=event_id,
            source="strategy_outcomes",
        )

        outcome = {
            "task_family": task,
            "strategy": strategy,
            "success": bool(success),
            "score": weight,
            "event_id": int(event_id),
        }
        self.recent_outcomes.append(outcome)

        # Internal states respond immediately.
        self._decay_internal()
        if success:
            self.internal["confidence"] = min(
                1.0,
                self.internal["confidence"] + self.cfg.confidence_success_gain * weight,
            )
            self.internal["frustration_like"] *= 0.70
        else:
            failure_count = sum(
                1 for x in self.recent_outcomes if not x["success"]
            )
            pressure = min(
                1.0,
                failure_count * self.cfg.frustration_failure_gain,
            )
            self.internal["frustration_like"] = max(
                self.internal["frustration_like"],
                pressure,
            )
            self.internal["confidence"] = max(
                0.0,
                self.internal["confidence"] - 0.12 * weight,
            )
            self.internal["curiosity"] = min(
                1.0,
                self.internal["curiosity"] + 0.08 * weight,
            )

        self._log_state(event_id, reason="strategy_outcome")
        return {
            "outcome": outcome,
            "capability": self.capability(task),
            "strategy_state": self.strategy_state(task, strategy),
            "internal_state": self.internal_state(),
        }

    def observe_language_outcome(self, text: str, event_id: int) -> dict | None:
        """Convert a self-referential natural-language result into metacognitive evidence."""
        parsed = MentalLanguagePerception.parse_self_outcome(text)
        if not parsed:
            return None
        result = self.record_strategy_outcome(
            parsed["task_family"],
            parsed["strategy"],
            bool(parsed["success"]),
            event_id,
            score=float(parsed.get("confidence", 0.8)),
        )
        result["source"] = parsed.get("source", "mental_language")
        result["language_text"] = text
        return result

    def capability(self, task_family: str) -> dict:
        task = str(task_family).strip().lower() or "unknown"
        rec = self.capabilities.get(task, self._capability_record())
        estimate = self._success_estimate(rec)
        attempts = int(rec.get("attempts", 0))
        return {
            "task_family": task,
            "success_probability": estimate,
            "confidence": min(
                1.0,
                attempts / 6.0,
            ),
            "attempts": attempts,
            "successes": float(rec.get("successes", 0.0)),
            "failures": float(rec.get("failures", 0.0)),
            "last_event": int(rec.get("last_event", 0)),
        }

    def strategy_state(self, task_family: str, strategy: str) -> dict:
        task = str(task_family).strip().lower() or "unknown"
        strategy = str(strategy).strip().lower() or "unknown"
        rec = self.strategies.get(task, {}).get(
            strategy,
            self._strategy_record(),
        )
        return {
            "task_family": task,
            "strategy": strategy,
            "success_probability": self._success_estimate(rec),
            "attempts": int(rec.get("attempts", 0)),
            "successes": float(rec.get("successes", 0.0)),
            "failures": float(rec.get("failures", 0.0)),
            "last_event": int(rec.get("last_event", 0)),
        }

    def choose_strategy(
        self,
        task_family: str,
        candidates: Iterable[str],
    ) -> List[dict]:
        task = str(task_family).strip().lower() or "unknown"
        rows = []
        total_attempts = sum(
            int(rec.get("attempts", 0))
            for rec in self.strategies.get(task, {}).values()
        )

        for raw in candidates:
            strategy = str(raw).strip().lower()
            rec = self.strategies.get(task, {}).get(
                strategy,
                self._strategy_record(),
            )
            estimate = self._success_estimate(rec)
            attempts = int(rec.get("attempts", 0))

            # Simple UCB-like exploration bonus: untried alternatives remain
            # available after a once-good strategy starts failing.
            exploration = self.cfg.strategy_exploration_bonus * sqrt(
                max(0.0, (total_attempts + 1.0) / (attempts + 1.0))
            )
            failure_rate = (
                float(rec.get("failures", 0.0))
                / max(1.0, float(rec.get("successes", 0.0)) + float(rec.get("failures", 0.0)))
            )
            score = estimate + exploration - self.cfg.strategy_failure_penalty * failure_rate
            rows.append({
                "strategy": strategy,
                "score": score,
                "success_probability": estimate,
                "attempts": attempts,
            })

        rows.sort(key=lambda x: (-x["score"], x["strategy"]))
        return rows

    def observe_prediction_state(
        self,
        surprise: float,
        predictive_error: float,
        novelty: float,
        event_id: int,
    ) -> dict:
        self._decay_internal()

        uncertainty = max(
            0.0,
            min(1.0, 0.55 * float(surprise) + 0.45 * float(predictive_error)),
        )
        novelty = max(0.0, min(1.0, float(novelty)))

        curiosity_target = min(
            1.0,
            self.cfg.curiosity_uncertainty_gain * uncertainty
            + self.cfg.curiosity_novelty_gain * novelty,
        )
        self.internal["curiosity"] = max(
            self.internal["curiosity"],
            curiosity_target,
        )

        predictability = 1.0 - uncertainty
        self.internal["confidence"] = max(
            0.0,
            min(
                1.0,
                0.78 * self.internal["confidence"] + 0.22 * predictability,
            ),
        )

        self._log_state(event_id, reason="prediction_update")
        return self.internal_state()

    def set_urgency(self, value: float, event_id: int) -> None:
        self.internal["urgency"] = max(0.0, min(1.0, float(value)))
        self._log_state(event_id, reason="urgency")

    def _decay_internal(self) -> None:
        decay = self.cfg.internal_state_decay
        self.internal["curiosity"] *= decay
        self.internal["frustration_like"] *= decay
        self.internal["urgency"] *= decay
        # Confidence decays gently toward neutral 0.5 instead of zero.
        self.internal["confidence"] = (
            0.5 + (self.internal["confidence"] - 0.5) * decay
        )

    def _log_state(self, event_id: int, reason: str) -> None:
        self.history.append({
            "event_id": int(event_id),
            "reason": reason,
            "state": dict(self.internal),
        })
        if len(self.history) > 256:
            self.history = self.history[-256:]

    def internal_state(self) -> dict:
        return dict(self.internal)

    def concepts(self) -> Dict[str, float]:
        out = {}
        for name, value in self.internal.items():
            if value >= 0.08:
                out[f"SELFSTATE:{name.upper()}"] = float(value)

        # Only expose capability beliefs once they have evidence.
        for task, rec in self.capabilities.items():
            if int(rec.get("attempts", 0)) <= 0:
                continue
            p = self._success_estimate(rec)
            out[f"SELF:CAPABILITY:{task}:{'HIGH' if p >= 0.5 else 'LOW'}"] = abs(p - 0.5) * 2.0
        return out

    def export_state(self) -> dict:
        return {
            "beliefs": self.beliefs,
            "capabilities": self.capabilities,
            "strategies": self.strategies,
            "recent_outcomes": list(self.recent_outcomes),
            "internal": self.internal,
            "history": self.history,
        }

    def import_state(self, payload: dict) -> None:
        self.beliefs = {
            str(k): dict(v)
            for k, v in payload.get("beliefs", {}).items()
        }
        self.capabilities = {
            str(k): dict(v)
            for k, v in payload.get("capabilities", {}).items()
        }
        self.strategies = {
            str(task): {
                str(strategy): dict(rec)
                for strategy, rec in rows.items()
            }
            for task, rows in payload.get("strategies", {}).items()
        }
        self.recent_outcomes = deque(
            [dict(x) for x in payload.get("recent_outcomes", [])],
            maxlen=max(4, self.cfg.frustration_failure_window),
        )
        base = {
            "curiosity": 0.0,
            "frustration_like": 0.0,
            "confidence": 0.5,
            "urgency": 0.0,
        }
        base.update({
            str(k): float(v)
            for k, v in payload.get("internal", {}).items()
            if k in base
        })
        self.internal = base
        self.history = [dict(x) for x in payload.get("history", [])][-256:]
