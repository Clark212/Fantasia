"""Small, dependency-free simulation protocol and episode runner."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol
from .experience import Experience


class Environment(Protocol):
    def reset(self, seed: int | None = None) -> Mapping[str, Any]: ...
    def step(self, action: Mapping[str, Any]) -> tuple[Mapping[str, Any], bool, Mapping[str, Any]]: ...


@dataclass(slots=True)
class EpisodeResult:
    experiences: list[Experience]
    steps: int
    terminated: bool


class ExperienceRunner:
    def __init__(self, *, domain: str, max_steps: int = 100) -> None:
        if not domain.strip() or max_steps < 1:
            raise ValueError("domain must be non-empty and max_steps positive")
        self.domain, self.max_steps = domain, max_steps

    def run(self, environment: Environment, policy: Any, *, episode_id: str,
            seed: int | None = None) -> EpisodeResult:
        if not episode_id.strip():
            raise ValueError("episode_id must be non-empty")
        observation = environment.reset(seed=seed)
        experiences: list[Experience] = []
        terminated = False
        for step in range(self.max_steps):
            # Policy sees observations only; no simulator internals are exposed.
            action = policy(observation)
            if not isinstance(action, Mapping):
                raise TypeError("policy must return an action mapping")
            prediction = None
            if hasattr(policy, "predict"):
                prediction = policy.predict(observation, action)
            next_observation, terminated, info = environment.step(action)
            if not isinstance(next_observation, Mapping) or not isinstance(info, Mapping):
                raise TypeError("environment step must return mapping observation and info")
            experiences.append(Experience(
                experience_id=f"{episode_id}:{step}", source="simulation", domain=self.domain,
                task_id=episode_id, observation={"state": dict(observation), "action": dict(action)},
                prediction=dict(prediction) if isinstance(prediction, Mapping) else None,
                outcome={"next_state": dict(next_observation), "info": dict(info)},
                evidence_status="observed", timestamp=float(step),
                metadata={"episode_id": episode_id, "step": step, "seed": seed},
            ))
            observation = next_observation
            if terminated:
                break
        return EpisodeResult(experiences, len(experiences), terminated)
