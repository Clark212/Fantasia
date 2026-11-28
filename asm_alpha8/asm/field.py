from __future__ import annotations

from dataclasses import dataclass
from math import copysign, log1p, tanh
from typing import Dict, List, Tuple

from .config import ASMConfig


@dataclass(slots=True)
class NodeState:
    activation: float = 0.0
    usage: int = 0
    last_event: int = 0


class SeismicField:
    """
    Sparse dynamic graph with competition and homeostasis.

    v0.1.1 changes:
      - inactive nodes no longer re-enter from stale activation values
      - lateral inhibition reduces runaway co-activation
      - high-usage nodes receive a small homeostatic penalty
      - field activity is peak-normalized before top-K selection
    """

    def __init__(self, config: ASMConfig):
        self.cfg = config
        self.nodes: Dict[str, NodeState] = {}
        self.edges: Dict[str, Dict[str, float]] = {}
        self.active: Dict[str, float] = {}

    def _touch(self, name: str, event_id: int = 0) -> NodeState:
        node = self.nodes.get(name)
        if node is None:
            node = self.nodes[name] = NodeState()
        node.usage += 1
        node.last_event = event_id
        return node

    def begin_event(self) -> None:
        # Carry a decayed working state, not the full stale node activation map.
        self.active = {
            k: v * self.cfg.activation_decay
            for k, v in self.active.items()
            if abs(v * self.cfg.activation_decay) >= self.cfg.activation_floor
        }

    def inject(
        self,
        concepts: Dict[str, float],
        gain: float = 1.0,
        event_id: int = 0,
        *,
        persistent: bool = True,
    ) -> None:
        for name, amount in concepts.items():
            node = self._touch(name, event_id) if persistent else self.nodes.get(name)
            value = self.active.get(name, 0.0)
            value = tanh(value + amount * gain)
            if node is not None and persistent:
                node.activation = value
            if abs(value) >= self.cfg.activation_floor:
                self.active[name] = value
        self.active = self._competitive_normalize(self.active)
        self._cap_active()

    def propagate(self, event_id: int = 0, *, persistent: bool = True) -> None:
        for _ in range(self.cfg.propagation_steps):
            if not self.active:
                return

            incoming: Dict[str, float] = {}
            for src, src_act in list(self.active.items()):
                out = self.edges.get(src)
                if not out:
                    continue
                strongest = sorted(
                    out.items(),
                    key=lambda kv: abs(kv[1]),
                    reverse=True,
                )[: self.cfg.max_fanout]
                for dst, weight in strongest:
                    incoming[dst] = (
                        incoming.get(dst, 0.0)
                        + src_act * weight * self.cfg.propagation_gain
                    )

            raw: Dict[str, float] = {}
            keys = set(self.active) | set(incoming)
            for name in keys:
                old = self.active.get(name, 0.0) * self.cfg.activation_decay
                inc = incoming.get(name, 0.0)
                value = tanh(old + inc)

                node = self._touch(name, event_id) if persistent else self.nodes.get(name)
                # Homeostasis: common nodes need slightly more support.
                usage = node.usage if node is not None else 0
                penalty = 1.0 + self.cfg.homeostasis_strength * log1p(usage)
                value /= penalty
                if node is not None and persistent:
                    node.activation = value

                if abs(value) >= self.cfg.activation_floor:
                    raw[name] = value

            self.active = self._competitive_normalize(raw)
            self._cap_active()

    def _competitive_normalize(self, values: Dict[str, float]) -> Dict[str, float]:
        if not values:
            return {}

        mean_abs = sum(abs(v) for v in values.values()) / len(values)
        threshold = self.cfg.inhibition_strength * mean_abs

        competed: Dict[str, float] = {}
        for name, value in values.items():
            mag = max(0.0, abs(value) - threshold)
            if mag >= self.cfg.activation_floor:
                competed[name] = copysign(mag, value)

        if not competed:
            # Keep the strongest node so the field does not collapse completely.
            name, value = max(values.items(), key=lambda kv: abs(kv[1]))
            competed[name] = value

        peak = max(abs(v) for v in competed.values()) or 1.0
        if peak > 1.0:
            competed = {k: v / peak for k, v in competed.items()}

        return competed

    def workspace(self) -> List[Tuple[str, float]]:
        return sorted(
            self.active.items(),
            key=lambda kv: abs(kv[1]),
            reverse=True,
        )[: self.cfg.workspace_size]

    def learn_coactivation(self, workspace: List[Tuple[str, float]]) -> None:
        top = workspace[: min(12, len(workspace))]
        for i, (a, aa) in enumerate(top):
            for b, bb in top[i + 1 :]:
                delta = self.cfg.association_lr * aa * bb
                self._adjust_edge(a, b, delta)
                self._adjust_edge(b, a, delta)

    def learn_temporal(
        self,
        previous: List[Tuple[str, float]],
        current: List[Tuple[str, float]],
    ) -> None:
        for a, aa in previous[:10]:
            for b, bb in current[:10]:
                if a == b:
                    continue
                self._adjust_edge(a, b, self.cfg.temporal_lr * aa * bb)

    def _adjust_edge(self, src: str, dst: str, delta: float) -> None:
        if src == dst:
            return
        out = self.edges.setdefault(src, {})
        old = out.get(dst, 0.0)
        proposed = old + delta * (
            1.0 - min(abs(old) / self.cfg.max_edge_weight, 0.95)
        )
        out[dst] = max(
            -self.cfg.max_edge_weight,
            min(self.cfg.max_edge_weight, proposed),
        )

        # v0.1.1.1: bound graph degree. A very common concept must not collect
        # thousands of weak outgoing edges and make propagation progressively
        # slower forever.
        if len(out) > self.cfg.max_association_fanout:
            strongest = sorted(
                out.items(),
                key=lambda kv: abs(kv[1]),
                reverse=True,
            )[: self.cfg.max_association_fanout]
            self.edges[src] = dict(strongest)

    def prune(self) -> int:
        removed = 0
        threshold = self.cfg.edge_prune_threshold
        for src in list(self.edges):
            out = self.edges[src]
            for dst in list(out):
                if abs(out[dst]) < threshold:
                    del out[dst]
                    removed += 1
            if not out:
                del self.edges[src]
        return removed

    def _cap_active(self) -> None:
        if len(self.active) <= self.cfg.max_active_nodes:
            return
        keep = sorted(
            self.active.items(),
            key=lambda kv: abs(kv[1]),
            reverse=True,
        )[: self.cfg.max_active_nodes]
        self.active = dict(keep)

    def export_state(self) -> dict:
        return {
            "nodes": {
                name: {
                    "activation": state.activation,
                    "usage": state.usage,
                    "last_event": state.last_event,
                }
                for name, state in self.nodes.items()
            },
            "edges": self.edges,
            "active": self.active,
        }

    def import_state(self, payload: dict) -> None:
        self.nodes.clear()
        for name, state in payload.get("nodes", {}).items():
            self.nodes[name] = NodeState(
                activation=float(state.get("activation", 0.0)),
                usage=int(state.get("usage", 0)),
                last_event=int(state.get("last_event", 0)),
            )
        self.edges = {
            src: {dst: float(w) for dst, w in out.items()}
            for src, out in payload.get("edges", {}).items()
        }
        self.active = {
            k: float(v)
            for k, v in payload.get("active", {}).items()
        }
        self._cap_active()
