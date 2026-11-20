from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, List


@dataclass
class Goal:
    text: str
    priority: float = 0.5
    progress: float = 0.0
    active: bool = True


class GoalSystem:
    def __init__(self):
        self.goals: List[Goal] = []

    def add(self, text: str, priority: float = 0.5) -> Goal:
        goal = Goal(text=text.strip(), priority=max(0.0, min(1.0, priority)))
        self.goals.append(goal)
        return goal

    def concepts(self) -> Dict[str, float]:
        result: Dict[str, float] = {}
        for goal in self.goals:
            if not goal.active:
                continue
            for token in goal.text.lower().split():
                token = token.strip(".,!?()[]{}")
                if token:
                    result[f"WORD:{token}"] = max(
                        result.get(f"WORD:{token}", 0.0),
                        goal.priority,
                    )
        return result

    def export_state(self):
        return [asdict(g) for g in self.goals]

    def import_state(self, payload):
        self.goals = [Goal(**item) for item in (payload or [])]
