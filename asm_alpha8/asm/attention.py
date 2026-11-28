from __future__ import annotations

from typing import Dict, Iterable, List, Tuple

from .config import ASMConfig


class AttentionSystem:
    """
    Persistent attention derived from the active seismic workspace.

    Attention is not a Transformer attention matrix. It is a small persistent
    state describing which currently active concepts are receiving the highest
    processing priority.
    """

    def __init__(self, config: ASMConfig):
        self.cfg = config
        self.targets: Dict[str, float] = {}
        self.epicenter: str | None = None
        self.history: List[dict] = []

    def update(
        self,
        workspace: Iterable[Tuple[str, float]],
        *,
        surprise: float,
        magnitude: float,
        event_id: int,
    ) -> dict:
        previous_epicenter = self.epicenter

        # Inertia retains some context across events.
        retained = {
            concept: score * self.cfg.attention_inertia
            for concept, score in self.targets.items()
            if score * self.cfg.attention_inertia > 0.02
            and not str(concept).startswith("ATTEND:")
        }

        # Attention metadata is not itself eligible to become a new target.
        # This prevents ATTEND:ATTEND:* recursive graph pollution.
        incoming = [
            (concept, activation)
            for concept, activation in workspace
            if not str(concept).startswith("ATTEND:")
        ]
        max_activation = max(
            [abs(v) for _, v in incoming] or [1.0]
        )
        novelty_pressure = max(0.0, min(1.0, float(surprise)))
        magnitude = max(0.0, min(1.0, float(magnitude)))

        for rank, (concept, activation) in enumerate(incoming):
            normalized = abs(float(activation)) / max_activation
            rank_discount = 1.0 / (1.0 + 0.08 * rank)
            score = normalized * rank_discount

            # Strong/surprising events pull attention toward their workspace.
            score *= (
                1.0
                + self.cfg.attention_surprise_gain
                * novelty_pressure
                * magnitude
            )
            retained[concept] = max(retained.get(concept, 0.0), score)

        ranked = sorted(
            retained.items(),
            key=lambda kv: kv[1],
            reverse=True,
        )[: self.cfg.attention_max_targets]

        # Normalize top target to 1.
        top = ranked[0][1] if ranked else 1.0
        self.targets = {
            concept: (score / top if top > 0 else 0.0)
            for concept, score in ranked
        }
        self.epicenter = ranked[0][0] if ranked else None

        shifted = (
            previous_epicenter is not None
            and self.epicenter is not None
            and self.epicenter != previous_epicenter
        )

        state = {
            "event_id": int(event_id),
            "epicenter": self.epicenter,
            "previous_epicenter": previous_epicenter,
            "shifted": shifted,
            "targets": [
                {"concept": c, "score": s}
                for c, s in self.targets.items()
            ],
        }
        self.history.append(state)
        if len(self.history) > 256:
            self.history = self.history[-256:]
        return state

    def concepts(self) -> Dict[str, float]:
        return {
            f"ATTEND:{concept}": 0.55 * score
            for concept, score in self.targets.items()
            if score >= 0.12 and not str(concept).startswith("ATTEND:")
        }

    def state(self) -> dict:
        return {
            "epicenter": self.epicenter,
            "targets": [
                {"concept": c, "score": s}
                for c, s in self.targets.items()
            ],
            "history_length": len(self.history),
        }

    def export_state(self) -> dict:
        return {
            "targets": self.targets,
            "epicenter": self.epicenter,
            "history": self.history,
        }

    def import_state(self, payload: dict) -> None:
        self.targets = {
            str(k): float(v)
            for k, v in payload.get("targets", {}).items()
            if not str(k).startswith("ATTEND:")
        }
        epicenter = payload.get("epicenter")
        self.epicenter = (
            epicenter
            if epicenter is None or not str(epicenter).startswith("ATTEND:")
            else None
        )
        self.history = [dict(x) for x in payload.get("history", [])][-256:]
