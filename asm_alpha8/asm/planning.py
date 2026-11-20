from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import math
from typing import Any, Callable, Iterable


@dataclass(slots=True)
class StateGoal:
    """Explicit state-space goal used by the ASM planner.

    v0.4 still deliberately refuses to pretend free-form language is grounded
    into mechanism state. Callers provide target fields explicitly. Alpha.2
    adds a generic distance/proximity signal for search; exact satisfaction is
    unchanged and remains the only definition of success.
    """

    target: dict[str, Any]
    avoid: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.target = dict(self.target or {})
        self.avoid = dict(self.avoid or {})
        if not self.target:
            raise ValueError("StateGoal.target must contain at least one field")

    @staticmethod
    def _matches(state: dict[str, Any], pattern: dict[str, Any]) -> bool:
        return bool(pattern) and all(state.get(k) == v for k, v in pattern.items())

    def violates(self, state: dict[str, Any]) -> bool:
        return self._matches(state, self.avoid)

    def score(self, state: dict[str, Any]) -> float:
        """Fraction of target fields exactly satisfied."""
        if self.violates(state):
            return -1.0
        hits = sum(1 for k, v in self.target.items() if state.get(k) == v)
        return hits / max(1, len(self.target))

    @staticmethod
    def _field_distance(actual: Any, target: Any) -> float:
        if actual == target:
            return 0.0
        # bool is an int subclass but treating True/False as geometry is not useful.
        if (
            isinstance(actual, (int, float)) and not isinstance(actual, bool)
            and isinstance(target, (int, float)) and not isinstance(target, bool)
            and math.isfinite(float(actual)) and math.isfinite(float(target))
        ):
            return abs(float(actual) - float(target))
        return 1.0

    def distance(self, state: dict[str, Any]) -> float:
        """Generic target distance used only as a search heuristic.

        Numeric target fields use absolute distance; categorical mismatches cost
        one. This never changes the exact goal predicate and therefore cannot turn
        a merely-near state into a successful plan.
        """
        if self.violates(state):
            return math.inf
        return sum(self._field_distance(state.get(k), v) for k, v in self.target.items())

    def proximity(self, state: dict[str, Any]) -> float:
        distance = self.distance(state)
        if not math.isfinite(distance):
            return 0.0
        return 1.0 / (1.0 + max(0.0, distance))

    def satisfied(self, state: dict[str, Any]) -> bool:
        return not self.violates(state) and all(state.get(k) == v for k, v in self.target.items())


@dataclass(slots=True)
class SimulationStep:
    depth: int
    action: str
    before_state: dict[str, Any]
    predicted_state: dict[str, Any]
    confidence: float
    uncertainty: float
    mechanism_type: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PlanCandidate:
    actions: tuple[str, ...]
    predicted_state: dict[str, Any]
    goal_score: float
    goal_proximity: float
    path_confidence: float
    uncertainty: float
    utility: float
    trace: tuple[SimulationStep, ...]
    goal_reached: bool
    # Opaque branch-local mechanism state. Never serialized into the public plan.
    simulation_context: Any = field(default=None, repr=False)
    simulation_context_key: str = field(default="", repr=False)

    def as_dict(self) -> dict[str, Any]:
        return {
            "actions": list(self.actions),
            "predicted_state": dict(self.predicted_state),
            "goal_score": float(self.goal_score),
            "goal_proximity": float(self.goal_proximity),
            "path_confidence": float(self.path_confidence),
            "uncertainty": float(self.uncertainty),
            "utility": float(self.utility),
            "trace": [step.as_dict() for step in self.trace],
            "goal_reached": bool(self.goal_reached),
            "source": "simulated",
        }


class BoundedInternalPlanner:
    """Bounded rollout planner over learned local mechanisms.

    Alpha.2 strengthens alpha.1 in four places:
      * branch-local opaque simulation context can advance independently;
      * generic goal proximity gives search a gradient without relaxing success;
      * loop/dominance suppression stops cyclic states wasting the beam;
      * bounded adaptive widening is triggered only by search stalls/uncertainty.

    The planner never calls observe()/learn methods and simulated states are never
    written to ASM's observed world state.
    """

    def __init__(
        self,
        predictor: Callable[..., dict[str, Any]],
        *,
        max_horizon: int = 5,
        beam_width: int = 8,
        max_expansions: int = 64,
        uncertainty_penalty: float = 0.35,
        step_penalty: float = 0.01,
        min_step_confidence: float = 0.0,
        adaptive_beam_max: int | None = None,
        stall_patience: int = 1,
        uncertainty_widen_threshold: float = 0.55,
        proximity_weight: float = 0.20,
    ) -> None:
        self.predictor = predictor
        self.max_horizon = max(1, int(max_horizon))
        self.beam_width = max(1, int(beam_width))
        default_max = max(self.beam_width, self.beam_width * 2)
        self.adaptive_beam_max = max(self.beam_width, int(adaptive_beam_max or default_max))
        self.max_expansions = max(1, int(max_expansions))
        self.uncertainty_penalty = max(0.0, float(uncertainty_penalty))
        self.step_penalty = max(0.0, float(step_penalty))
        self.min_step_confidence = max(0.0, min(1.0, float(min_step_confidence)))
        self.stall_patience = max(1, int(stall_patience))
        self.uncertainty_widen_threshold = max(0.0, min(1.0, float(uncertainty_widen_threshold)))
        self.proximity_weight = max(0.0, float(proximity_weight))

    @staticmethod
    def _state_key(state: dict[str, Any]) -> str:
        return json.dumps(state, sort_keys=True, separators=(",", ":"), default=str)

    def _candidate_key(self, candidate: PlanCandidate) -> str:
        return f"{self._state_key(candidate.predicted_state)}|ctx={candidate.simulation_context_key}"

    def _utility(
        self,
        goal_score: float,
        goal_proximity: float,
        path_confidence: float,
        steps: int,
    ) -> float:
        uncertainty = 1.0 - max(0.0, min(1.0, path_confidence))
        return (
            float(goal_score)
            + self.proximity_weight * float(goal_proximity)
            - self.uncertainty_penalty * uncertainty
            - self.step_penalty * steps
        )

    @staticmethod
    def _rank(candidate: PlanCandidate) -> tuple[float, ...]:
        return (
            1.0 if candidate.goal_reached else 0.0,
            candidate.utility,
            candidate.goal_score,
            candidate.goal_proximity,
            candidate.path_confidence,
            -float(len(candidate.actions)),
        )

    @staticmethod
    def _state_diversity(a: dict[str, Any], b: dict[str, Any]) -> float:
        """Domain-generic distance used only to keep search branches diverse.

        Numeric fields contribute bounded absolute distance and categorical fields
        contribute one when different. Missing fields also count as different.
        """
        total = 0.0
        for key in set(a) | set(b):
            av, bv = a.get(key), b.get(key)
            if av == bv:
                continue
            if (
                isinstance(av, (int, float)) and not isinstance(av, bool)
                and isinstance(bv, (int, float)) and not isinstance(bv, bool)
            ):
                try:
                    total += min(4.0, abs(float(av) - float(bv)))
                    continue
                except (TypeError, ValueError):
                    pass
            total += 1.0
        return total

    def plan(
        self,
        mechanism_type: str,
        *,
        entity_id: str,
        initial_state: dict[str, Any],
        actions: Iterable[str],
        goal: StateGoal | dict[str, Any],
        neighborhood: dict[str, Any] | None = None,
        dt: float = 1.0,
        horizon: int | None = None,
    ) -> dict[str, Any]:
        action_space = tuple(dict.fromkeys(str(a) for a in actions if str(a)))
        if not action_space:
            raise ValueError("actions must contain at least one non-empty action")
        if not isinstance(goal, StateGoal):
            goal = StateGoal(target=dict(goal))

        actual_horizon = min(self.max_horizon, max(1, int(horizon or self.max_horizon)))
        root_state = dict(initial_state)
        root_score = goal.score(root_state)
        root_proximity = goal.proximity(root_state)
        root = PlanCandidate(
            actions=(), predicted_state=root_state, goal_score=root_score,
            goal_proximity=root_proximity,
            path_confidence=1.0, uncertainty=0.0,
            utility=self._utility(root_score, root_proximity, 1.0, 0), trace=(),
            goal_reached=goal.satisfied(root_state),
        )
        if root.goal_reached:
            return {
                "status": "goal_already_satisfied",
                "reason": "initial_state_satisfies_goal",
                "goal": asdict(goal),
                "best": root.as_dict(),
                "alternatives": [],
                "expansions": 0,
                "horizon": actual_horizon,
                "beam_width": self.beam_width,
                "effective_beam_width_peak": self.beam_width,
                "adaptive_widenings": 0,
                "rescue_used": False,
                "rescue_expansions": 0,
                "deferred_candidates": 0,
                "dominated_pruned": 0,
                "unsafe_pruned": 0,
                "simulated_only": True,
            }

        beam = [root]
        completed: list[PlanCandidate] = []
        all_candidates: list[PlanCandidate] = []
        expansions = 0
        dominated_pruned = 0
        unsafe_pruned = 0
        prediction_failures = 0
        adaptive_widenings = 0
        deferred: dict[str, PlanCandidate] = {}
        expanded_keys: set[str] = set()
        rescue_used = False
        rescue_expansions = 0
        current_beam_width = self.beam_width
        effective_beam_width_peak = current_beam_width
        best_proximity = root_proximity
        stalled_depths = 0

        # Dominance map across depths. A repeated state+branch-context is useful
        # only if reached with better confidence or fewer actions.
        visited: dict[str, tuple[float, int]] = {self._candidate_key(root): (1.0, 0)}

        for depth in range(1, actual_horizon + 1):
            next_nodes: list[PlanCandidate] = []
            depth_best_proximity = best_proximity
            depth_uncertainties: list[float] = []

            for node in beam:
                expanded_keys.add(self._candidate_key(node))
                if node.goal_reached:
                    completed.append(node)
                    continue
                for action in action_space:
                    if expansions >= self.max_expansions:
                        break
                    pred = self.predictor(
                        mechanism_type,
                        entity_id=str(entity_id),
                        state=dict(node.predicted_state),
                        action=action,
                        neighborhood=dict(neighborhood or {}),
                        dt=float(dt),
                        simulation_context=node.simulation_context,
                    )
                    expansions += 1
                    predicted = pred.get("predicted_state")
                    if predicted is None:
                        prediction_failures += 1
                        continue
                    confidence = max(0.0, min(1.0, float(pred.get("confidence", 0.0))))
                    if confidence < self.min_step_confidence:
                        prediction_failures += 1
                        continue
                    state = dict(predicted)
                    path_conf = max(0.0, min(1.0, node.path_confidence * confidence))
                    uncertainty = 1.0 - path_conf
                    goal_score = goal.score(state)
                    goal_proximity = goal.proximity(state)
                    sim_context = pred.get("_simulation_context")
                    sim_context_key = str(pred.get("_simulation_context_key", ""))
                    trace = node.trace + (SimulationStep(
                        depth=depth,
                        action=action,
                        before_state=dict(node.predicted_state),
                        predicted_state=state,
                        confidence=confidence,
                        uncertainty=float(pred.get("uncertainty", 1.0 - confidence)),
                        mechanism_type=str(pred.get("mechanism_type", mechanism_type)),
                    ),)
                    candidate = PlanCandidate(
                        actions=node.actions + (action,),
                        predicted_state=state,
                        goal_score=goal_score,
                        goal_proximity=goal_proximity,
                        path_confidence=path_conf,
                        uncertainty=uncertainty,
                        utility=self._utility(goal_score, goal_proximity, path_conf, depth),
                        trace=trace,
                        goal_reached=goal.satisfied(state),
                        simulation_context=sim_context,
                        simulation_context_key=sim_context_key,
                    )
                    all_candidates.append(candidate)
                    depth_uncertainties.append(uncertainty)

                    if goal.violates(state):
                        unsafe_pruned += 1
                        continue

                    key = self._candidate_key(candidate)
                    previous = visited.get(key)
                    if previous is not None:
                        prev_conf, prev_depth = previous
                        # Strictly dominated repeated states are loops/dead work.
                        if prev_depth <= depth and prev_conf >= path_conf - 1e-12:
                            dominated_pruned += 1
                            if candidate.goal_reached:
                                completed.append(candidate)
                            continue
                    visited[key] = (path_conf, depth)
                    next_nodes.append(candidate)
                    depth_best_proximity = max(depth_best_proximity, goal_proximity)
                    if candidate.goal_reached:
                        completed.append(candidate)
                if expansions >= self.max_expansions:
                    break

            if completed:
                # Continue only while budget remains: a later route can be more
                # reliable, but completed candidates are never thrown away.
                pass
            if not next_nodes:
                break

            improved = depth_best_proximity > best_proximity + 1e-12
            if improved:
                best_proximity = depth_best_proximity
                stalled_depths = 0
                # Recover toward the configured base width after progress.
                current_beam_width = max(self.beam_width, current_beam_width // 2)
            else:
                stalled_depths += 1

            mean_uncertainty = (
                sum(depth_uncertainties) / len(depth_uncertainties)
                if depth_uncertainties else 0.0
            )
            should_widen = (
                stalled_depths >= self.stall_patience
                or mean_uncertainty >= self.uncertainty_widen_threshold
            )
            if should_widen and current_beam_width < self.adaptive_beam_max:
                new_width = min(self.adaptive_beam_max, max(current_beam_width + 1, current_beam_width * 2))
                if new_width > current_beam_width:
                    current_beam_width = new_width
                    adaptive_widenings += 1
                    effective_beam_width_peak = max(effective_beam_width_peak, current_beam_width)
                stalled_depths = 0

            # Depth-local dedup happens after global dominance so branch-local
            # contexts that happen to share visible state remain independent.
            dedup: dict[str, PlanCandidate] = {}
            for candidate in next_nodes:
                key = self._candidate_key(candidate)
                old = dedup.get(key)
                if old is None or self._rank(candidate) > self._rank(old):
                    dedup[key] = candidate

            ranked = sorted(dedup.values(), key=self._rank, reverse=True)
            if len(ranked) <= current_beam_width:
                beam = ranked
            else:
                # Diversity reserve: most slots follow utility, while a bounded
                # minority preserves high-confidence distinct states even when a
                # heuristic temporarily says they moved away from the goal.
                reserve = max(1, current_beam_width // 2)
                main_count = max(1, current_beam_width - reserve)
                selected = ranked[:main_count]
                selected_keys = {self._candidate_key(c) for c in selected}
                remaining = [c for c in ranked[main_count:] if self._candidate_key(c) not in selected_keys]
                exploratory: list[PlanCandidate] = []
                # Greedily preserve branches whose predicted states are far from
                # the already-kept states. This prevents a narrow beam from
                # collapsing into one corridor merely because all steps have
                # similar confidence.
                while remaining and len(exploratory) < reserve:
                    anchors = selected + exploratory
                    pick = max(
                        remaining,
                        key=lambda c: (
                            min(
                                (self._state_diversity(c.predicted_state, a.predicted_state) for a in anchors),
                                default=0.0,
                            ),
                            c.path_confidence,
                            c.goal_proximity,
                            -len(c.actions),
                        ),
                    )
                    exploratory.append(pick)
                    remaining.remove(pick)
                beam = selected + exploratory
                kept_keys = {self._candidate_key(c) for c in beam}
                for candidate in ranked:
                    key = self._candidate_key(candidate)
                    if key not in kept_keys and key not in expanded_keys:
                        old = deferred.get(key)
                        if old is None or self._rank(candidate) > self._rank(old):
                            deferred[key] = candidate

            if expansions >= self.max_expansions:
                break

        # If the fast depth-beam path misses the goal, alpha.2 can spend only the
        # *remaining* expansion budget on candidates it deliberately deferred.
        # This is a bounded best-first rescue, not a second unbounded search. It
        # preserves temporarily-unpromising corridors without widening every depth.
        if not completed and deferred and expansions < self.max_expansions:
            rescue_used = True
            frontier = [c for k, c in deferred.items() if k not in expanded_keys]
            frontier_keys = {self._candidate_key(c) for c in frontier}
            while frontier and expansions < self.max_expansions and not completed:
                frontier.sort(
                    key=lambda c: (
                        len(c.actions) + goal.distance(c.predicted_state),
                        c.uncertainty,
                        -c.utility,
                        -c.goal_proximity,
                    )
                )
                node = frontier.pop(0)
                node_key = self._candidate_key(node)
                frontier_keys.discard(node_key)
                if node_key in expanded_keys or len(node.actions) >= actual_horizon:
                    continue
                expanded_keys.add(node_key)
                for action in action_space:
                    if expansions >= self.max_expansions:
                        break
                    pred = self.predictor(
                        mechanism_type, entity_id=str(entity_id),
                        state=dict(node.predicted_state), action=action,
                        neighborhood=dict(neighborhood or {}), dt=float(dt),
                        simulation_context=node.simulation_context,
                    )
                    expansions += 1
                    rescue_expansions += 1
                    predicted = pred.get("predicted_state")
                    if predicted is None:
                        prediction_failures += 1
                        continue
                    confidence = max(0.0, min(1.0, float(pred.get("confidence", 0.0))))
                    if confidence < self.min_step_confidence:
                        prediction_failures += 1
                        continue
                    state = dict(predicted)
                    path_conf = max(0.0, min(1.0, node.path_confidence * confidence))
                    uncertainty = 1.0 - path_conf
                    score = goal.score(state)
                    proximity = goal.proximity(state)
                    step_depth = len(node.actions) + 1
                    sim_context = pred.get("_simulation_context")
                    sim_context_key = str(pred.get("_simulation_context_key", ""))
                    trace = node.trace + (SimulationStep(
                        depth=step_depth, action=action,
                        before_state=dict(node.predicted_state), predicted_state=state,
                        confidence=confidence,
                        uncertainty=float(pred.get("uncertainty", 1.0-confidence)),
                        mechanism_type=str(pred.get("mechanism_type", mechanism_type)),
                    ),)
                    candidate = PlanCandidate(
                        actions=node.actions + (action,), predicted_state=state,
                        goal_score=score, goal_proximity=proximity,
                        path_confidence=path_conf, uncertainty=uncertainty,
                        utility=self._utility(score, proximity, path_conf, step_depth),
                        trace=trace, goal_reached=goal.satisfied(state),
                        simulation_context=sim_context,
                        simulation_context_key=sim_context_key,
                    )
                    all_candidates.append(candidate)
                    if goal.violates(state):
                        unsafe_pruned += 1
                        continue
                    key = self._candidate_key(candidate)
                    previous = visited.get(key)
                    if previous is not None:
                        prev_conf, prev_depth = previous
                        if prev_depth <= step_depth and prev_conf >= path_conf - 1e-12:
                            dominated_pruned += 1
                            if candidate.goal_reached:
                                completed.append(candidate)
                            continue
                    visited[key] = (path_conf, step_depth)
                    if candidate.goal_reached:
                        completed.append(candidate)
                        break
                    if step_depth < actual_horizon and key not in expanded_keys and key not in frontier_keys:
                        frontier.append(candidate)
                        frontier_keys.add(key)

        pool = completed or all_candidates or [root]
        best = max(pool, key=self._rank)
        alternatives = sorted(
            [c for c in pool if c is not best],
            key=self._rank,
            reverse=True,
        )[: max(0, self.beam_width - 1)]

        if best.goal_reached:
            status = "goal_reached"
            reason = "bounded_rollout_found_goal"
        elif expansions >= self.max_expansions:
            status = "budget_exhausted"
            reason = "expansion_budget_reached_before_goal"
        elif unsafe_pruned > 0 and not any(not goal.violates(c.predicted_state) for c in all_candidates):
            status = "no_safe_plan"
            reason = "all_predicted_branches_violated_avoid_constraint"
        elif all_candidates:
            status = "horizon_exhausted"
            reason = "goal_not_reached_within_horizon"
        else:
            status = "no_prediction"
            reason = "transition_model_returned_no_usable_predictions"

        return {
            "status": status,
            "reason": reason,
            "goal": asdict(goal),
            "best": best.as_dict(),
            "alternatives": [c.as_dict() for c in alternatives],
            "expansions": expansions,
            "prediction_failures": prediction_failures,
            "horizon": actual_horizon,
            "beam_width": self.beam_width,
            "effective_beam_width_peak": effective_beam_width_peak,
            "adaptive_widenings": adaptive_widenings,
            "rescue_used": rescue_used,
            "rescue_expansions": rescue_expansions,
            "deferred_candidates": len(deferred),
            "dominated_pruned": dominated_pruned,
            "unsafe_pruned": unsafe_pruned,
            "simulated_only": True,
        }


@dataclass(slots=True)
class StochasticScenario:
    state: dict[str, Any]
    probability: float
    simulation_context: Any = field(default=None, repr=False)
    simulation_context_key: str = field(default="", repr=False)


@dataclass(slots=True)
class StochasticPlanCandidate:
    actions: tuple[str, ...]
    scenarios: tuple[StochasticScenario, ...]
    goal_probability: float
    hazard_probability: float
    unknown_probability: float
    expected_proximity: float
    expected_cost: float
    risk: float
    utility: float
    trace: tuple[dict[str, Any], ...]

    def representative_state(self) -> dict[str, Any]:
        if not self.scenarios:
            return {}
        return dict(max(self.scenarios, key=lambda s: s.probability).state)

    def as_dict(self) -> dict[str, Any]:
        return {
            "actions": list(self.actions),
            "representative_state": self.representative_state(),
            "goal_probability": float(self.goal_probability),
            "hazard_probability": float(self.hazard_probability),
            "unknown_probability": float(self.unknown_probability),
            "known_probability": float(max(0.0, 1.0 - self.unknown_probability)),
            "expected_proximity": float(self.expected_proximity),
            "expected_cost": float(self.expected_cost),
            "risk": float(self.risk),
            "utility": float(self.utility),
            "trace": list(self.trace),
            "source": "stochastic_simulation",
        }


class ProbabilisticInternalPlanner:
    """Bounded open-loop planner over explicit outcome distributions.

    v0.4-alpha.3 does not pretend a modal neural confidence is a calibrated
    outcome probability. The distribution predictor must expose bounded outcome
    mass plus residual unknown probability. Plans are scored over all retained
    outcome branches, with explicit hazard/unknown risk and action costs.

    This alpha intentionally plans an open-loop action sequence. Adaptive policy
    trees (choosing different later actions after observing different outcomes)
    are a later planning capability rather than being implied here.
    """

    def __init__(
        self,
        distribution_predictor: Callable[..., dict[str, Any]],
        *,
        max_horizon: int = 5,
        beam_width: int = 8,
        max_expansions: int = 128,
        max_scenarios: int = 24,
        top_k_outcomes: int = 4,
        risk_aversion: float = 2.0,
        unknown_risk_weight: float = 0.65,
        cost_weight: float = 0.02,
        proximity_weight: float = 0.20,
        step_penalty: float = 0.005,
        min_goal_probability: float = 0.70,
        max_hazard_probability: float = 0.10,
        max_unknown_probability: float = 0.25,
    ) -> None:
        self.distribution_predictor = distribution_predictor
        self.max_horizon = max(1, int(max_horizon))
        self.beam_width = max(1, int(beam_width))
        self.max_expansions = max(1, int(max_expansions))
        self.max_scenarios = max(2, int(max_scenarios))
        self.top_k_outcomes = max(1, int(top_k_outcomes))
        self.risk_aversion = max(0.0, float(risk_aversion))
        self.unknown_risk_weight = max(0.0, min(1.0, float(unknown_risk_weight)))
        self.cost_weight = max(0.0, float(cost_weight))
        self.proximity_weight = max(0.0, float(proximity_weight))
        self.step_penalty = max(0.0, float(step_penalty))
        self.min_goal_probability = max(0.0, min(1.0, float(min_goal_probability)))
        self.max_hazard_probability = max(0.0, min(1.0, float(max_hazard_probability)))
        self.max_unknown_probability = max(0.0, min(1.0, float(max_unknown_probability)))

    @staticmethod
    def _scenario_key(scenario: StochasticScenario) -> str:
        state = json.dumps(scenario.state, sort_keys=True, separators=(",", ":"), default=str)
        return f"{state}|ctx={scenario.simulation_context_key}"

    def _merge_and_bound(
        self, scenarios: list[StochasticScenario], unknown_probability: float,
    ) -> tuple[tuple[StochasticScenario, ...], float]:
        merged: dict[str, StochasticScenario] = {}
        for scenario in scenarios:
            if scenario.probability <= 0.0:
                continue
            key = self._scenario_key(scenario)
            old = merged.get(key)
            if old is None:
                merged[key] = StochasticScenario(
                    state=dict(scenario.state), probability=float(scenario.probability),
                    simulation_context=scenario.simulation_context,
                    simulation_context_key=scenario.simulation_context_key,
                )
            else:
                old.probability += float(scenario.probability)
        ranked = sorted(merged.values(), key=lambda s: s.probability, reverse=True)
        if len(ranked) > self.max_scenarios:
            unknown_probability += sum(s.probability for s in ranked[self.max_scenarios:])
            ranked = ranked[:self.max_scenarios]
        return tuple(ranked), min(1.0, max(0.0, unknown_probability))

    def _metrics(
        self,
        scenarios: tuple[StochasticScenario, ...],
        *,
        goal: StateGoal,
        unknown_probability: float,
        hazard_probability: float,
        expected_cost: float,
        depth: int,
    ) -> tuple[float, float, float, float]:
        goal_p = sum(s.probability for s in scenarios if goal.satisfied(s.state))
        expected_proximity = sum(s.probability * goal.proximity(s.state) for s in scenarios)
        risk = min(1.0, max(0.0, hazard_probability + self.unknown_risk_weight * unknown_probability))
        utility = (
            goal_p + self.proximity_weight * expected_proximity
            - self.risk_aversion * risk
            - self.cost_weight * expected_cost
            - self.step_penalty * depth
        )
        return goal_p, expected_proximity, risk, utility

    @staticmethod
    def _rank(candidate: StochasticPlanCandidate) -> tuple[float, ...]:
        return (
            candidate.utility,
            candidate.goal_probability,
            -candidate.risk,
            -candidate.hazard_probability,
            -candidate.unknown_probability,
            -candidate.expected_cost,
            -float(len(candidate.actions)),
        )

    def _acceptable(self, candidate: StochasticPlanCandidate) -> bool:
        return (
            candidate.goal_probability >= self.min_goal_probability
            and candidate.hazard_probability <= self.max_hazard_probability
            and candidate.unknown_probability <= self.max_unknown_probability
        )

    def plan(
        self,
        mechanism_type: str,
        *,
        entity_id: str,
        initial_state: dict[str, Any],
        actions: Iterable[str],
        goal: StateGoal | dict[str, Any],
        action_costs: dict[str, float] | None = None,
        neighborhood: dict[str, Any] | None = None,
        dt: float = 1.0,
        horizon: int | None = None,
    ) -> dict[str, Any]:
        action_space = tuple(dict.fromkeys(str(a) for a in actions if str(a)))
        if not action_space:
            raise ValueError("actions must contain at least one non-empty action")
        if not isinstance(goal, StateGoal):
            goal = StateGoal(target=dict(goal))
        costs = {str(k): max(0.0, float(v)) for k, v in dict(action_costs or {}).items()}
        actual_horizon = min(self.max_horizon, max(1, int(horizon or self.max_horizon)))

        root_scenario = StochasticScenario(dict(initial_state), 1.0)
        root_goal = 1.0 if goal.satisfied(initial_state) else 0.0
        root_hazard = 1.0 if goal.violates(initial_state) else 0.0
        root_prox = goal.proximity(initial_state)
        root_risk = root_hazard
        root = StochasticPlanCandidate(
            actions=(), scenarios=(root_scenario,), goal_probability=root_goal,
            hazard_probability=root_hazard, unknown_probability=0.0,
            expected_proximity=root_prox, expected_cost=0.0, risk=root_risk,
            utility=root_goal + self.proximity_weight * root_prox - self.risk_aversion * root_risk,
            trace=(),
        )
        if root_goal >= self.min_goal_probability and root_hazard <= self.max_hazard_probability:
            return {
                "status": "goal_already_satisfied", "reason": "initial_state_satisfies_goal",
                "goal": asdict(goal), "best": root.as_dict(), "alternatives": [],
                "expansions": 0, "horizon": actual_horizon, "beam_width": self.beam_width,
                "simulated_only": True, "probabilistic": True,
            }

        beam = [root]
        all_candidates: list[StochasticPlanCandidate] = []
        acceptable: list[StochasticPlanCandidate] = []
        expansions = 0
        prediction_failures = 0
        calibrated_calls = 0
        uncalibrated_calls = 0

        for depth in range(1, actual_horizon + 1):
            next_nodes: list[StochasticPlanCandidate] = []
            for node in beam:
                for action in action_space:
                    scenarios: list[StochasticScenario] = []
                    unknown = float(node.unknown_probability)
                    hazard = float(node.hazard_probability)
                    step_sources: dict[str, int] = {}
                    step_known_mass = 0.0
                    budget_hit = False
                    for scenario in node.scenarios:
                        p_parent = float(scenario.probability)
                        if p_parent <= 0.0:
                            continue
                        if goal.satisfied(scenario.state):
                            scenarios.append(scenario)
                            step_known_mass += p_parent
                            continue
                        if goal.violates(scenario.state):
                            hazard += p_parent
                            continue
                        if expansions >= self.max_expansions:
                            unknown += p_parent
                            budget_hit = True
                            continue
                        pred = self.distribution_predictor(
                            mechanism_type, entity_id=str(entity_id), state=dict(scenario.state),
                            action=action, neighborhood=dict(neighborhood or {}), dt=float(dt),
                            simulation_context=scenario.simulation_context, top_k=self.top_k_outcomes,
                        )
                        expansions += 1
                        source = str(pred.get("probability_source", "unknown"))
                        step_sources[source] = step_sources.get(source, 0) + 1
                        if bool(pred.get("calibrated", False)):
                            calibrated_calls += 1
                        else:
                            uncalibrated_calls += 1
                        outcomes = list(pred.get("outcomes") or [])
                        residual = max(0.0, min(1.0, float(pred.get("unknown_probability", 1.0))))
                        if not outcomes:
                            prediction_failures += 1
                            unknown += p_parent
                            continue
                        out_mass = 0.0
                        next_context = pred.get("_simulation_context")
                        next_context_key = str(pred.get("_simulation_context_key", ""))
                        for outcome in outcomes:
                            prob = max(0.0, min(1.0, float(outcome.get("probability", 0.0))))
                            state = outcome.get("predicted_state")
                            if state is None or prob <= 0.0:
                                continue
                            out_mass += prob
                            branch_p = p_parent * prob
                            branch_state = dict(state)
                            if goal.violates(branch_state):
                                hazard += branch_p
                            else:
                                scenarios.append(StochasticScenario(
                                    branch_state, branch_p, next_context, next_context_key
                                ))
                            step_known_mass += branch_p
                        # Any probability not explicitly accounted for is unknown.
                        residual = max(residual, 1.0 - min(1.0, out_mass))
                        unknown += p_parent * residual
                    scenarios_t, unknown = self._merge_and_bound(scenarios, unknown)
                    total = sum(s.probability for s in scenarios_t) + hazard + unknown
                    if total > 1.0 + 1e-9:
                        scale = 1.0 / total
                        scenarios_t = tuple(StochasticScenario(
                            s.state, s.probability * scale, s.simulation_context, s.simulation_context_key
                        ) for s in scenarios_t)
                        hazard *= scale
                        unknown *= scale
                    cost = node.expected_cost + costs.get(action, 0.0)
                    goal_p, prox, risk, utility = self._metrics(
                        scenarios_t, goal=goal, unknown_probability=unknown,
                        hazard_probability=hazard, expected_cost=cost, depth=depth,
                    )
                    trace_entry = {
                        "depth": depth, "action": action,
                        "goal_probability": goal_p, "hazard_probability": hazard,
                        "unknown_probability": unknown, "risk": risk,
                        "expected_cost": cost, "probability_sources": step_sources,
                        "budget_hit": budget_hit,
                    }
                    candidate = StochasticPlanCandidate(
                        actions=node.actions + (action,), scenarios=scenarios_t,
                        goal_probability=goal_p, hazard_probability=hazard,
                        unknown_probability=unknown, expected_proximity=prox,
                        expected_cost=cost, risk=risk, utility=utility,
                        trace=node.trace + (trace_entry,),
                    )
                    all_candidates.append(candidate)
                    next_nodes.append(candidate)
                    if self._acceptable(candidate):
                        acceptable.append(candidate)
                if expansions >= self.max_expansions and not next_nodes:
                    break
            if not next_nodes:
                break
            next_nodes.sort(key=self._rank, reverse=True)
            beam = next_nodes[: self.beam_width]
            if expansions >= self.max_expansions:
                break

        pool = acceptable or all_candidates or [root]
        best = max(pool, key=self._rank)
        alternatives = sorted([c for c in pool if c is not best], key=self._rank, reverse=True)[:max(0, self.beam_width - 1)]
        if self._acceptable(best):
            status = "risk_aware_plan_found"
            reason = "goal_probability_and_risk_thresholds_satisfied"
        elif expansions >= self.max_expansions:
            status = "budget_exhausted"
            reason = "expansion_budget_reached_before_acceptable_plan"
        elif all_candidates:
            status = "risk_threshold_not_met"
            reason = "no_plan_satisfied_goal_risk_and_unknown_thresholds"
        else:
            status = "no_prediction"
            reason = "transition_model_returned_no_usable_distributions"
        return {
            "status": status, "reason": reason, "goal": asdict(goal),
            "best": best.as_dict(), "alternatives": [c.as_dict() for c in alternatives],
            "expansions": expansions, "prediction_failures": prediction_failures,
            "calibrated_calls": calibrated_calls, "uncalibrated_calls": uncalibrated_calls,
            "horizon": actual_horizon, "beam_width": self.beam_width,
            "max_scenarios": self.max_scenarios, "top_k_outcomes": self.top_k_outcomes,
            "risk_aversion": self.risk_aversion, "unknown_risk_weight": self.unknown_risk_weight,
            "min_goal_probability": self.min_goal_probability,
            "max_hazard_probability": self.max_hazard_probability,
            "max_unknown_probability": self.max_unknown_probability,
            "simulated_only": True, "probabilistic": True,
        }

@dataclass(slots=True)
class ContingentPolicyEvaluation:
    """Evaluation of one observation-conditioned policy subtree."""

    action: str | None
    state: dict[str, Any]
    goal_probability: float
    hazard_probability: float
    unknown_probability: float
    expected_proximity: float
    expected_cost: float
    risk: float
    utility: float
    branches: tuple[dict[str, Any], ...] = ()
    terminal_reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "action": self.action,
            "state": dict(self.state),
            "goal_probability": float(self.goal_probability),
            "hazard_probability": float(self.hazard_probability),
            "unknown_probability": float(self.unknown_probability),
            "known_probability": float(max(0.0, 1.0 - self.unknown_probability)),
            "expected_proximity": float(self.expected_proximity),
            "expected_cost": float(self.expected_cost),
            "risk": float(self.risk),
            "utility": float(self.utility),
            "branches": [dict(branch) for branch in self.branches],
            "source": "contingent_stochastic_simulation",
        }
        if self.terminal_reason is not None:
            payload["terminal_reason"] = self.terminal_reason
        return payload


class ContingentInternalPlanner:
    """Bounded AND/OR planner that can condition future actions on observations.

    v0.4-alpha.4 adds the missing representation from alpha.3: an action may
    produce several observable future states and each observed branch may select
    a different continuation. This makes information useful only when it changes
    downstream decisions; no action is hard-coded as a special "sense" action.

    The search remains bounded, uses the alpha.3 probability/unknown interface,
    and never learns from simulated branches.
    """

    def __init__(
        self,
        distribution_predictor: Callable[..., dict[str, Any]],
        *,
        max_horizon: int = 5,
        max_expansions: int = 192,
        top_k_outcomes: int = 4,
        risk_aversion: float = 2.0,
        unknown_risk_weight: float = 0.65,
        cost_weight: float = 0.02,
        proximity_weight: float = 0.20,
        step_penalty: float = 0.005,
        min_goal_probability: float = 0.70,
        max_hazard_probability: float = 0.10,
        max_unknown_probability: float = 0.25,
        memo_limit: int = 4096,
        compute_open_loop_reference: bool = True,
    ) -> None:
        self.distribution_predictor = distribution_predictor
        self.max_horizon = max(1, int(max_horizon))
        self.max_expansions = max(1, int(max_expansions))
        self.top_k_outcomes = max(1, int(top_k_outcomes))
        self.risk_aversion = max(0.0, float(risk_aversion))
        self.unknown_risk_weight = max(0.0, min(1.0, float(unknown_risk_weight)))
        self.cost_weight = max(0.0, float(cost_weight))
        self.proximity_weight = max(0.0, float(proximity_weight))
        self.step_penalty = max(0.0, float(step_penalty))
        self.min_goal_probability = max(0.0, min(1.0, float(min_goal_probability)))
        self.max_hazard_probability = max(0.0, min(1.0, float(max_hazard_probability)))
        self.max_unknown_probability = max(0.0, min(1.0, float(max_unknown_probability)))
        self.memo_limit = max(0, int(memo_limit))
        self.compute_open_loop_reference = bool(compute_open_loop_reference)

    @staticmethod
    def _state_key(state: dict[str, Any]) -> str:
        return json.dumps(state, sort_keys=True, separators=(",", ":"), default=str)

    def _risk(self, hazard: float, unknown: float) -> float:
        return min(1.0, max(0.0, hazard + self.unknown_risk_weight * unknown))

    def _utility(
        self, goal_p: float, hazard_p: float, unknown_p: float,
        expected_proximity: float, expected_cost: float, depth_used: int,
    ) -> float:
        return (
            goal_p
            + self.proximity_weight * expected_proximity
            - self.risk_aversion * self._risk(hazard_p, unknown_p)
            - self.cost_weight * expected_cost
            - self.step_penalty * depth_used
        )

    def _acceptable(self, result: ContingentPolicyEvaluation) -> bool:
        return (
            result.goal_probability >= self.min_goal_probability
            and result.hazard_probability <= self.max_hazard_probability
            and result.unknown_probability <= self.max_unknown_probability
        )

    @staticmethod
    def _rank(result: ContingentPolicyEvaluation) -> tuple[float, ...]:
        return (
            1.0 if (
                result.goal_probability > 0.0
                and result.hazard_probability <= 1.0
            ) else 0.0,
            result.utility,
            result.goal_probability,
            -result.risk,
            -result.hazard_probability,
            -result.unknown_probability,
            -result.expected_cost,
        )

    def plan(
        self,
        mechanism_type: str,
        *,
        entity_id: str,
        initial_state: dict[str, Any],
        actions: Iterable[str],
        goal: StateGoal | dict[str, Any],
        action_costs: dict[str, float] | None = None,
        neighborhood: dict[str, Any] | None = None,
        dt: float = 1.0,
        horizon: int | None = None,
    ) -> dict[str, Any]:
        action_space = tuple(dict.fromkeys(str(a) for a in actions if str(a)))
        if not action_space:
            raise ValueError("actions must contain at least one non-empty action")
        if not isinstance(goal, StateGoal):
            goal = StateGoal(target=dict(goal))
        costs = {str(k): max(0.0, float(v)) for k, v in dict(action_costs or {}).items()}
        actual_horizon = min(self.max_horizon, max(1, int(horizon or self.max_horizon)))
        expansions = 0
        prediction_failures = 0
        calibrated_calls = 0
        uncalibrated_calls = 0
        memo: dict[tuple[str, str, int], ContingentPolicyEvaluation] = {}

        def terminal(state: dict[str, Any], reason: str) -> ContingentPolicyEvaluation:
            gp = 1.0 if goal.satisfied(state) else 0.0
            hp = 1.0 if goal.violates(state) else 0.0
            prox = goal.proximity(state)
            risk = self._risk(hp, 0.0)
            return ContingentPolicyEvaluation(
                action=None, state=dict(state), goal_probability=gp,
                hazard_probability=hp, unknown_probability=0.0,
                expected_proximity=prox, expected_cost=0.0, risk=risk,
                utility=self._utility(gp, hp, 0.0, prox, 0.0, 0),
                branches=(), terminal_reason=reason,
            )

        def solve(
            state: dict[str, Any], simulation_context: Any,
            simulation_context_key: str, depth_left: int,
        ) -> ContingentPolicyEvaluation:
            nonlocal expansions, prediction_failures, calibrated_calls, uncalibrated_calls
            if goal.satisfied(state):
                return terminal(state, "goal")
            if goal.violates(state):
                return terminal(state, "hazard")
            if depth_left <= 0:
                return terminal(state, "horizon")

            key = (self._state_key(state), str(simulation_context_key or ""), int(depth_left))
            if key in memo:
                return memo[key]

            options: list[ContingentPolicyEvaluation] = []
            depth_used = actual_horizon - depth_left + 1
            for action in action_space:
                if expansions >= self.max_expansions:
                    break
                pred = self.distribution_predictor(
                    mechanism_type, entity_id=str(entity_id), state=dict(state),
                    action=action, neighborhood=dict(neighborhood or {}), dt=float(dt),
                    simulation_context=simulation_context, top_k=self.top_k_outcomes,
                )
                expansions += 1
                if bool(pred.get("calibrated", False)):
                    calibrated_calls += 1
                else:
                    uncalibrated_calls += 1
                outcomes = list(pred.get("outcomes") or [])
                residual = max(0.0, min(1.0, float(pred.get("unknown_probability", 1.0))))
                if not outcomes:
                    prediction_failures += 1
                    continue

                out_mass = 0.0
                goal_p = 0.0
                hazard_p = 0.0
                unknown_p = residual
                prox = 0.0
                future_cost = 0.0
                branches: list[dict[str, Any]] = []
                next_context = pred.get("_simulation_context")
                next_context_key = str(pred.get("_simulation_context_key", ""))

                for outcome in outcomes:
                    p = max(0.0, min(1.0, float(outcome.get("probability", 0.0))))
                    predicted_state = outcome.get("predicted_state")
                    if p <= 0.0 or predicted_state is None:
                        continue
                    out_mass += p
                    child_state = dict(predicted_state)
                    child = solve(child_state, next_context, next_context_key, depth_left - 1)
                    goal_p += p * child.goal_probability
                    hazard_p += p * child.hazard_probability
                    unknown_p += p * child.unknown_probability
                    prox += p * child.expected_proximity
                    future_cost += p * child.expected_cost
                    branches.append({
                        "probability": p,
                        "observation": child_state,
                        "policy": child.as_dict(),
                    })

                # Probability omitted by bounded top-k is explicitly unknown.
                residual = max(residual, 1.0 - min(1.0, out_mass))
                unknown_p = max(unknown_p, residual)
                total = goal_p + hazard_p + unknown_p
                if total > 1.0 + 1e-9:
                    scale = 1.0 / total
                    goal_p *= scale
                    hazard_p *= scale
                    unknown_p *= scale
                    prox *= scale
                    future_cost *= scale

                expected_cost = costs.get(action, 0.0) + future_cost
                risk = self._risk(hazard_p, unknown_p)
                utility = self._utility(
                    goal_p, hazard_p, unknown_p, prox, expected_cost, depth_used,
                )
                options.append(ContingentPolicyEvaluation(
                    action=action, state=dict(state), goal_probability=goal_p,
                    hazard_probability=hazard_p, unknown_probability=unknown_p,
                    expected_proximity=prox, expected_cost=expected_cost,
                    risk=risk, utility=utility, branches=tuple(branches),
                ))

            if not options:
                # Budget exhaustion is uncertainty, not evidence that the state is safe.
                result = ContingentPolicyEvaluation(
                    action=None, state=dict(state), goal_probability=0.0,
                    hazard_probability=0.0, unknown_probability=1.0,
                    expected_proximity=goal.proximity(state), expected_cost=0.0,
                    risk=self._risk(0.0, 1.0),
                    utility=self._utility(0.0, 0.0, 1.0, goal.proximity(state), 0.0, depth_used),
                    branches=(), terminal_reason=(
                        "budget" if expansions >= self.max_expansions else "no_prediction"
                    ),
                )
            else:
                acceptable_options = [o for o in options if self._acceptable(o)]
                result = max(acceptable_options or options, key=self._rank)

            if self.memo_limit and len(memo) < self.memo_limit:
                memo[key] = result
            return result

        best = solve(dict(initial_state), None, "", actual_horizon)
        def policy_branch_stats(policy: dict[str, Any]) -> tuple[bool, int, int]:
            branches = list(policy.get("branches") or [])
            actions_here = {
                b.get("policy", {}).get("action") for b in branches
                if float(b.get("probability", 0.0)) > 0.0
                and b.get("policy", {}).get("action") is not None
            }
            contingent_here = len(actions_here) > 1
            max_diversity = len(actions_here)
            nodes = 1
            for branch in branches:
                child = branch.get("policy") or {}
                child_contingent, child_diversity, child_nodes = policy_branch_stats(child)
                contingent_here = contingent_here or child_contingent
                max_diversity = max(max_diversity, child_diversity)
                nodes += child_nodes
            return contingent_here, max_diversity, nodes

        contingent, max_branch_diversity, policy_nodes = policy_branch_stats(best.as_dict())
        if goal.satisfied(initial_state):
            status = "goal_already_satisfied"
            reason = "initial_state_satisfies_goal"
        elif self._acceptable(best):
            status = "contingent_plan_found"
            reason = "goal_probability_and_risk_thresholds_satisfied"
        elif expansions >= self.max_expansions:
            status = "budget_exhausted"
            reason = "expansion_budget_reached_before_acceptable_policy"
        elif best.action is None:
            status = "no_prediction"
            reason = "transition_model_returned_no_usable_distributions"
        else:
            status = "risk_threshold_not_met"
            reason = "no_policy_satisfied_goal_risk_and_unknown_thresholds"

        open_loop_reference = None
        contingency_gain = None
        if self.compute_open_loop_reference:
            reference = ProbabilisticInternalPlanner(
                self.distribution_predictor,
                max_horizon=actual_horizon, beam_width=min(8, max(2, len(action_space) * 2)),
                max_expansions=self.max_expansions, max_scenarios=24,
                top_k_outcomes=self.top_k_outcomes, risk_aversion=self.risk_aversion,
                unknown_risk_weight=self.unknown_risk_weight, cost_weight=self.cost_weight,
                proximity_weight=self.proximity_weight, step_penalty=self.step_penalty,
                min_goal_probability=self.min_goal_probability,
                max_hazard_probability=self.max_hazard_probability,
                max_unknown_probability=self.max_unknown_probability,
            ).plan(
                mechanism_type, entity_id=entity_id, initial_state=dict(initial_state),
                actions=action_space, goal=goal, action_costs=costs,
                neighborhood=neighborhood, dt=dt, horizon=actual_horizon,
            )
            ref_best = reference.get("best") or {}
            ref_utility = float(ref_best.get("utility", -math.inf))
            contingency_gain = float(best.utility - ref_utility) if math.isfinite(ref_utility) else None
            open_loop_reference = {
                "status": reference.get("status"),
                "actions": list(ref_best.get("actions") or []),
                "goal_probability": float(ref_best.get("goal_probability", 0.0)),
                "hazard_probability": float(ref_best.get("hazard_probability", 0.0)),
                "unknown_probability": float(ref_best.get("unknown_probability", 0.0)),
                "utility": ref_utility if math.isfinite(ref_utility) else None,
                "expansions": int(reference.get("expansions", 0)),
            }

        return {
            "status": status,
            "reason": reason,
            "goal": asdict(goal),
            "best": best.as_dict(),
            "open_loop_reference": open_loop_reference,
            "contingency_gain": contingency_gain,
            "expansions": expansions,
            "prediction_failures": prediction_failures,
            "calibrated_calls": calibrated_calls,
            "uncalibrated_calls": uncalibrated_calls,
            "horizon": actual_horizon,
            "top_k_outcomes": self.top_k_outcomes,
            "risk_aversion": self.risk_aversion,
            "unknown_risk_weight": self.unknown_risk_weight,
            "min_goal_probability": self.min_goal_probability,
            "max_hazard_probability": self.max_hazard_probability,
            "max_unknown_probability": self.max_unknown_probability,
            "observation_conditioned": True,
            "contingent_branching_used": contingent,
            "branch_action_diversity": max_branch_diversity,
            "policy_nodes": policy_nodes,
            "simulated_only": True,
            "probabilistic": True,
        }

@dataclass(frozen=True, slots=True)
class DiscreteBeliefState:
    """Compact bounded latent belief with log-space numerical hardening.

    Alpha.5.1 keeps a normalized log posterior internally so extremely unlikely
    hypotheses are not deleted merely because ordinary floating-point
    probabilities underflow to zero. Public ``weights`` remain probabilities for
    compatibility, while Bayesian updates and memo keys retain recoverable log
    odds. Exact zero likelihood still eliminates a hypothesis by design.
    """

    weights: tuple[tuple[str, float], ...]
    evidence_count: int = 0
    _log_weights: tuple[tuple[str, float], ...] | None = field(default=None, repr=False, compare=False)
    _structural_zeros: tuple[str, ...] = field(default=(), repr=False, compare=False)
    # alpha.6.2: independent upstream evidence roots already incorporated into
    # this posterior. Empty means no explicit lineage bookkeeping is in use.
    _evidence_roots: tuple[str, ...] = field(default=(), repr=False, compare=False)

    @staticmethod
    def _logsumexp(values: Iterable[float]) -> float:
        vals = [float(v) for v in values if math.isfinite(float(v))]
        if not vals:
            return float('-inf')
        m = max(vals)
        return m + math.log(sum(math.exp(v - m) for v in vals))

    def __post_init__(self) -> None:
        evidence_count = max(0, int(self.evidence_count))
        object.__setattr__(self, 'evidence_count', evidence_count)
        lineage_roots = tuple(sorted({str(root).strip() for root in self._evidence_roots if str(root).strip()}))
        object.__setattr__(self, '_evidence_roots', lineage_roots)

        zero_names = {str(k) for k in self._structural_zeros}
        if self._log_weights is not None:
            merged_logs: dict[str, float] = {}
            for name, value in self._log_weights:
                key = str(name)
                lv = float(value)
                if not math.isfinite(lv):
                    zero_names.add(key)
                    continue
                if key in merged_logs:
                    merged_logs[key] = self._logsumexp((merged_logs[key], lv))
                else:
                    merged_logs[key] = lv
            zero_names.difference_update(merged_logs)
            if not merged_logs:
                raise ValueError('belief state must contain positive probability mass')
            z = self._logsumexp(merged_logs.values())
            norm_logs = tuple(sorted((k, v-z) for k,v in merged_logs.items()))
            probs = tuple((k, math.exp(lp) if lp > -745.0 else 0.0) for k,lp in norm_logs)
            ptotal = sum(v for _,v in probs)
            if ptotal > 0.0:
                probs = tuple((k, v/ptotal) for k,v in probs)
            object.__setattr__(self, 'weights', probs)
            object.__setattr__(self, '_log_weights', norm_logs)
            object.__setattr__(self, '_structural_zeros', tuple(sorted(zero_names)))
            return

        merged: dict[str, float] = {}
        for name, value in self.weights:
            key = str(name)
            raw = float(value)
            if not math.isfinite(raw):
                continue
            prob = max(0.0, raw)
            if prob > 0.0:
                merged[key] = merged.get(key, 0.0) + prob
                zero_names.discard(key)
            else:
                zero_names.add(key)
        total = sum(merged.values())
        if total <= 0.0:
            raise ValueError('belief state must contain positive probability mass')
        probs = tuple(sorted((k, v/total) for k,v in merged.items()))
        logs = tuple((k, math.log(v)) for k,v in probs)
        object.__setattr__(self, 'weights', probs)
        object.__setattr__(self, '_log_weights', logs)
        object.__setattr__(self, '_structural_zeros', tuple(sorted(zero_names - set(merged))))

    @classmethod
    def from_mapping(cls, probabilities: dict[str, float], *, evidence_count: int = 0) -> 'DiscreteBeliefState':
        return cls(tuple((str(k), float(v)) for k,v in dict(probabilities).items()), evidence_count)

    def as_dict(self) -> dict[str, float]:
        return {k: float(v) for k,v in self.weights}

    def as_log_dict(self) -> dict[str, float]:
        return {k: float(v) for k,v in (self._log_weights or ())}

    def hypothesis_names(self) -> tuple[str, ...]:
        return tuple(sorted({k for k,_ in (self._log_weights or ())} | set(self._structural_zeros)))

    def structural_zero_hypotheses(self) -> tuple[str, ...]:
        return tuple(self._structural_zeros)

    def evidence_roots(self) -> tuple[str, ...]:
        """Independent upstream evidence units already fused into this belief."""
        return tuple(self._evidence_roots)

    def _validated_likelihoods(self, likelihoods: dict[str, float]) -> dict[str, float]:
        if not isinstance(likelihoods, dict) or not likelihoods:
            raise ValueError('likelihoods must be a non-empty mapping of hypothesis probabilities')
        likes: dict[str, float] = {}
        for raw_key, raw_value in likelihoods.items():
            key = str(raw_key)
            try:
                value = float(raw_value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f'likelihood for {key!r} is not numeric') from exc
            if not math.isfinite(value):
                raise ValueError(f'likelihood for {key!r} must be finite')
            if value < 0.0 or value > 1.0:
                raise ValueError(f'likelihood for {key!r} must be within [0, 1]')
            if key in likes:
                raise ValueError(f'duplicate hypothesis likelihood key: {key!r}')
            likes[key] = value
        expected = set(self.hypothesis_names())
        got = set(likes)
        if got != expected:
            missing = sorted(expected - got)
            extra = sorted(got - expected)
            raise ValueError(f'likelihood hypothesis keys mismatch; missing={missing}, extra={extra}')
        if not any(v > 0.0 for v in likes.values()):
            raise ValueError('evidence likelihood is zero under every hypothesis')
        return likes

    def key(self, precision: int = 12) -> str:
        precision = max(3, int(precision))
        # Keep alpha.5's compact quantized memo behavior, but include the exact
        # posterior ordering so near-tie states on opposite decision sides never
        # collapse to the same memo key merely because rounding erased the sign.
        rank = ','.join(k for k,_ in sorted((self._log_weights or ()), key=lambda item:(-item[1], item[0])))
        zero_suffix = '' if not self._structural_zeros else ';zero=' + ','.join(self._structural_zeros)
        lineage_suffix = ''
        if self._evidence_roots:
            digest = hashlib.blake2b('\x1f'.join(self._evidence_roots).encode('utf-8'), digest_size=16).hexdigest()
            lineage_suffix = ';lineage=' + digest
        if self.weights and all(v > 0.0 for _,v in self.weights):
            base='|'.join(f'{k}:{round(v, precision):.{precision}f}' for k,v in self.weights)
        else:
            base='log|' + '|'.join(f'{k}:{round(v, precision):.{precision}f}' for k,v in (self._log_weights or ()))
        return base + ';rank=' + rank + zero_suffix + lineage_suffix

    def evidence_log_probability(self, likelihoods: dict[str, float]) -> float:
        likes = self._validated_likelihoods(likelihoods)
        terms=[]
        for h,lp in self._log_weights or ():
            like=likes[h]
            if like > 0.0:
                terms.append(lp + math.log(like))
        return self._logsumexp(terms)

    def evidence_probability(self, likelihoods: dict[str, float]) -> float:
        lp = self.evidence_log_probability(likelihoods)
        if not math.isfinite(lp) or lp < -745.0:
            return 0.0
        return float(math.exp(lp))

    def update_weighted(
        self, likelihoods: dict[str, float], *, evidence_weight: float = 1.0,
        evidence_roots: Iterable[str] = (),
    ) -> 'DiscreteBeliefState':
        """Bayesian update with bounded effective evidence weight.

        ``evidence_weight`` is normally 1.0. Alpha.6.2 uses values in [0,1]
        when explicit provenance reveals partial or complete overlap with evidence
        already fused into this belief. Weight 0 records the lineage but leaves
        the posterior unchanged; this prevents exact copies from multiplying
        confidence. This is *not* automatic hidden-correlation learning.
        """
        likes = self._validated_likelihoods(likelihoods)
        try:
            weight = float(evidence_weight)
        except (TypeError, ValueError) as exc:
            raise ValueError('evidence_weight must be numeric') from exc
        if not math.isfinite(weight) or weight < 0.0 or weight > 1.0:
            raise ValueError('evidence_weight must be finite and within [0, 1]')
        roots = tuple(sorted({str(root).strip() for root in evidence_roots if str(root).strip()}))
        combined_roots = tuple(sorted(set(self._evidence_roots) | set(roots)))
        if weight == 0.0:
            return DiscreteBeliefState(
                self.weights, self.evidence_count + 1, self._log_weights,
                self._structural_zeros, combined_roots,
            )

        logs=[]
        structural_zeros=set(self._structural_zeros)
        for h,lp in self._log_weights or ():
            like=likes[h]
            if like > 0.0:
                logs.append((h, lp + weight * math.log(like)))
            else:
                structural_zeros.add(h)
        if not logs:
            raise ValueError('evidence has zero probability under the current belief')
        z=self._logsumexp(v for _,v in logs)
        norm_logs=tuple((h,v-z) for h,v in logs)
        probs=tuple((h, math.exp(v) if v > -745.0 else 0.0) for h,v in norm_logs)
        return DiscreteBeliefState(
            probs, self.evidence_count+1, norm_logs, tuple(sorted(structural_zeros)),
            combined_roots,
        )

    def update(self, likelihoods: dict[str, float]) -> 'DiscreteBeliefState':
        return self.update_weighted(likelihoods, evidence_weight=1.0)

    def entropy_bits(self) -> float:
        # Underflowed tails make a negligible entropy contribution; computing
        # directly from log weights avoids deleting them from future updates.
        total=0.0
        for _,lp in self._log_weights or ():
            if lp > -745.0:
                p=math.exp(lp)
                if p>0.0: total -= p*(lp/math.log(2.0))
        return float(total)

    def most_likely(self) -> tuple[str, float]:
        h,lp=max(self._log_weights or (), key=lambda item:(item[1],item[0]))
        return h, (math.exp(lp) if lp > -745.0 else 0.0)


@dataclass(slots=True)
class BeliefPolicyEvaluation:
    node_id: str
    action: str | None
    state: dict[str, Any]
    belief: DiscreteBeliefState
    goal_probability: float
    hazard_probability: float
    unknown_probability: float
    expected_proximity: float
    expected_cost: float
    risk: float
    utility: float
    branches: tuple[dict[str, Any], ...] = ()
    terminal_reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "node_id": self.node_id,
            "action": self.action,
            "state": dict(self.state),
            "belief": self.belief.as_dict(),
            "belief_entropy_bits": self.belief.entropy_bits(),
            "evidence_count": int(self.belief.evidence_count),
            "goal_probability": float(self.goal_probability),
            "hazard_probability": float(self.hazard_probability),
            "unknown_probability": float(self.unknown_probability),
            "known_probability": float(max(0.0, 1.0 - self.unknown_probability)),
            "expected_proximity": float(self.expected_proximity),
            "expected_cost": float(self.expected_cost),
            "risk": float(self.risk),
            "utility": float(self.utility),
            "branches": [dict(branch) for branch in self.branches],
            "source": "belief_state_contingent_simulation",
        }
        if self.terminal_reason is not None:
            payload["terminal_reason"] = self.terminal_reason
        return payload


class BeliefStateInternalPlanner:
    """Bounded contingent planner with a compact latent belief state.

    Outcomes may optionally carry ``hypothesis_likelihoods`` containing
    P(observation | hidden hypothesis).  When present, alpha.5 computes the
    branch probability from the current belief, performs a Bayesian update, and
    carries the posterior into that branch.  Equivalent (world, posterior,
    recurrent-context, depth) tuples share one memoized policy node, yielding a
    compact policy DAG instead of a raw-history tree.

    The normal transition model remains read-only.  A caller may supply a
    likelihood_provider when its predictor cannot annotate outcomes directly.
    """

    def __init__(
        self,
        distribution_predictor: Callable[..., dict[str, Any]],
        *,
        max_horizon: int = 8,
        max_expansions: int = 256,
        top_k_outcomes: int = 4,
        risk_aversion: float = 2.0,
        unknown_risk_weight: float = 0.65,
        cost_weight: float = 0.02,
        proximity_weight: float = 0.20,
        step_penalty: float = 0.005,
        min_goal_probability: float = 0.70,
        max_hazard_probability: float = 0.10,
        max_unknown_probability: float = 0.25,
        memo_limit: int = 8192,
        max_hypotheses: int = 32,
        belief_key_precision: int = 12,
    ) -> None:
        self.distribution_predictor = distribution_predictor
        self.max_horizon = max(1, int(max_horizon))
        self.max_expansions = max(1, int(max_expansions))
        self.top_k_outcomes = max(1, int(top_k_outcomes))
        self.risk_aversion = max(0.0, float(risk_aversion))
        self.unknown_risk_weight = max(0.0, min(1.0, float(unknown_risk_weight)))
        self.cost_weight = max(0.0, float(cost_weight))
        self.proximity_weight = max(0.0, float(proximity_weight))
        self.step_penalty = max(0.0, float(step_penalty))
        self.min_goal_probability = max(0.0, min(1.0, float(min_goal_probability)))
        self.max_hazard_probability = max(0.0, min(1.0, float(max_hazard_probability)))
        self.max_unknown_probability = max(0.0, min(1.0, float(max_unknown_probability)))
        self.memo_limit = max(0, int(memo_limit))
        self.max_hypotheses = max(1, int(max_hypotheses))
        self.belief_key_precision = max(3, int(belief_key_precision))

    @staticmethod
    def _state_key(state: dict[str, Any]) -> str:
        return json.dumps(state, sort_keys=True, separators=(",", ":"), default=str)

    def _risk(self, hazard: float, unknown: float) -> float:
        return min(1.0, max(0.0, hazard + self.unknown_risk_weight * unknown))

    def _utility(self, goal_p: float, hazard_p: float, unknown_p: float,
                 expected_proximity: float, expected_cost: float, depth_used: int) -> float:
        return (
            goal_p + self.proximity_weight * expected_proximity
            - self.risk_aversion * self._risk(hazard_p, unknown_p)
            - self.cost_weight * expected_cost - self.step_penalty * depth_used
        )

    def _acceptable(self, result: BeliefPolicyEvaluation) -> bool:
        return (
            result.goal_probability >= self.min_goal_probability
            and result.hazard_probability <= self.max_hazard_probability
            and result.unknown_probability <= self.max_unknown_probability
        )

    @staticmethod
    def _rank(result: BeliefPolicyEvaluation) -> tuple[float, ...]:
        return (
            1.0 if result.goal_probability > 0.0 else 0.0,
            result.utility, result.goal_probability, -result.risk,
            -result.hazard_probability, -result.unknown_probability,
            -result.expected_cost,
        )

    def plan(
        self,
        mechanism_type: str,
        *,
        entity_id: str,
        initial_state: dict[str, Any],
        actions: Iterable[str],
        goal: StateGoal | dict[str, Any],
        initial_belief: DiscreteBeliefState | dict[str, float],
        likelihood_provider: Callable[[DiscreteBeliefState, dict[str, Any], str, Any, dict[str, Any]], dict[str, float] | None] | None = None,
        likelihood_provider_overrides: bool = False,
        action_costs: dict[str, float] | None = None,
        neighborhood: dict[str, Any] | None = None,
        dt: float = 1.0,
        horizon: int | None = None,
    ) -> dict[str, Any]:
        action_space = tuple(dict.fromkeys(str(a) for a in actions if str(a)))
        if not action_space:
            raise ValueError("actions must contain at least one non-empty action")
        if not isinstance(goal, StateGoal):
            goal = StateGoal(target=dict(goal))
        belief = initial_belief if isinstance(initial_belief, DiscreteBeliefState) else DiscreteBeliefState.from_mapping(initial_belief)
        if len(belief.hypothesis_names()) > self.max_hypotheses:
            raise ValueError(f"belief has {len(belief.hypothesis_names())} hypotheses; max_hypotheses={self.max_hypotheses}")
        costs = {str(k): max(0.0, float(v)) for k, v in dict(action_costs or {}).items()}
        actual_horizon = min(self.max_horizon, max(1, int(horizon or self.max_horizon)))

        expansions = 0
        prediction_failures = 0
        invalid_likelihood_models = 0
        budget_exhausted_during_search = False
        probability_mass_truncated = False
        calibrated_calls = 0
        uncalibrated_calls = 0
        memo_hits = 0
        evidence_updates = 0
        max_evidence_count = belief.evidence_count
        unique_beliefs: set[str] = {belief.key(self.belief_key_precision)}
        memo: dict[tuple[str, str, str, int], BeliefPolicyEvaluation] = {}
        graph: dict[str, dict[str, Any]] = {}
        node_counter = 0

        def new_node_id() -> str:
            nonlocal node_counter
            node_counter += 1
            return f"b{node_counter}"

        def store(result: BeliefPolicyEvaluation) -> BeliefPolicyEvaluation:
            graph[result.node_id] = result.as_dict()
            return result

        def terminal(state: dict[str, Any], b: DiscreteBeliefState, reason: str, depth_used: int) -> BeliefPolicyEvaluation:
            gp = 1.0 if goal.satisfied(state) else 0.0
            hp = 1.0 if goal.violates(state) else 0.0
            prox = goal.proximity(state)
            risk = self._risk(hp, 0.0)
            return store(BeliefPolicyEvaluation(
                node_id=new_node_id(), action=None, state=dict(state), belief=b,
                goal_probability=gp, hazard_probability=hp, unknown_probability=0.0,
                expected_proximity=prox, expected_cost=0.0, risk=risk,
                utility=self._utility(gp, hp, 0.0, prox, 0.0, depth_used),
                branches=(), terminal_reason=reason,
            ))

        def solve(state: dict[str, Any], b: DiscreteBeliefState, simulation_context: Any,
                  simulation_context_key: str, depth_left: int) -> BeliefPolicyEvaluation:
            nonlocal expansions, prediction_failures, invalid_likelihood_models, budget_exhausted_during_search, probability_mass_truncated, calibrated_calls, uncalibrated_calls
            nonlocal memo_hits, evidence_updates, max_evidence_count
            bkey = b.key(self.belief_key_precision)
            unique_beliefs.add(bkey)
            key = (self._state_key(state), bkey, str(simulation_context_key or ""), int(depth_left))
            if key in memo:
                memo_hits += 1
                return memo[key]

            depth_used = actual_horizon - depth_left
            if goal.satisfied(state):
                result = terminal(state, b, "goal", depth_used)
                if self.memo_limit and len(memo) < self.memo_limit: memo[key] = result
                return result
            if goal.violates(state):
                result = terminal(state, b, "hazard", depth_used)
                if self.memo_limit and len(memo) < self.memo_limit: memo[key] = result
                return result
            if depth_left <= 0:
                result = terminal(state, b, "horizon", depth_used)
                if self.memo_limit and len(memo) < self.memo_limit: memo[key] = result
                return result

            options: list[BeliefPolicyEvaluation] = []
            for action in action_space:
                if expansions >= self.max_expansions:
                    budget_exhausted_during_search = True
                    break
                pred = self.distribution_predictor(
                    mechanism_type, entity_id=str(entity_id), state=dict(state), action=action,
                    neighborhood=dict(neighborhood or {}), dt=float(dt),
                    simulation_context=simulation_context, top_k=self.top_k_outcomes,
                )
                expansions += 1
                if bool(pred.get("calibrated", False)): calibrated_calls += 1
                else: uncalibrated_calls += 1
                outcomes = list(pred.get("outcomes") or [])
                residual = max(0.0, min(1.0, float(pred.get("unknown_probability", 1.0))))
                if not outcomes:
                    prediction_failures += 1
                    continue

                # Alpha.5.1 likelihood contract hardening. These are
                # probabilities P(observation | hypothesis), not arbitrary weights.
                supplied_rows = [o.get("hypothesis_likelihoods") for o in outcomes]
                has_likelihood_model = any(row is not None for row in supplied_rows)
                invalid_matrix = False
                if has_likelihood_model:
                    if any(row is None for row in supplied_rows):
                        invalid_matrix = True
                    expected_hypotheses = set(b.hypothesis_names())
                    likelihood_sums = {h: 0.0 for h in expected_hypotheses}
                    observation_keys: set[str] = set()
                    for _outcome, _likes in zip(outcomes, supplied_rows):
                        if invalid_matrix:
                            break
                        if not isinstance(_likes, dict) or not _likes:
                            invalid_matrix = True
                            break
                        parsed: dict[str, float] = {}
                        for _h, _v in _likes.items():
                            _key = str(_h)
                            try:
                                _fv = float(_v)
                            except (TypeError, ValueError):
                                invalid_matrix = True
                                break
                            if _key in parsed or not math.isfinite(_fv) or _fv < 0.0 or _fv > 1.0:
                                invalid_matrix = True
                                break
                            parsed[_key] = _fv
                        if invalid_matrix or set(parsed) != expected_hypotheses or not any(v > 0.0 for v in parsed.values()):
                            invalid_matrix = True
                            break
                        obs_identity = _outcome.get("observation", _outcome.get("predicted_state"))
                        try:
                            obs_key = json.dumps(obs_identity, sort_keys=True, separators=(",", ":"), allow_nan=False)
                        except (TypeError, ValueError):
                            invalid_matrix = True
                            break
                        if obs_key in observation_keys:
                            invalid_matrix = True
                            break
                        observation_keys.add(obs_key)
                        for _h, _fv in parsed.items():
                            likelihood_sums[_h] += _fv
                    if not invalid_matrix:
                        invalid_matrix = any(abs(total - 1.0) > 1e-9 for total in likelihood_sums.values())
                if invalid_matrix:
                    invalid_likelihood_models += 1
                    prediction_failures += 1
                    continue

                out_mass = goal_p = hazard_p = prox = future_cost = 0.0
                unknown_p = residual
                branches: list[dict[str, Any]] = []
                shared_context = pred.get("_simulation_context")
                shared_context_key = str(pred.get("_simulation_context_key", ""))

                for outcome in outcomes:
                    predicted_state = outcome.get("predicted_state")
                    if predicted_state is None:
                        continue
                    child_state = dict(predicted_state)
                    observation = outcome.get("observation", dict(child_state))
                    likelihoods = outcome.get("hypothesis_likelihoods")
                    if likelihood_provider is not None and (likelihood_provider_overrides or likelihoods is None):
                        provided = likelihood_provider(b, dict(state), action, observation, child_state)
                        if provided is not None:
                            likelihoods = provided

                    child_belief = b
                    if likelihoods is not None:
                        try:
                            p = b.evidence_probability(dict(likelihoods))
                            if p <= 1e-15:
                                continue
                            child_belief = b.update(dict(likelihoods))
                        except (TypeError, ValueError, OverflowError):
                            invalid_likelihood_models += 1
                            prediction_failures += 1
                            continue
                        evidence_updates += 1
                        max_evidence_count = max(max_evidence_count, child_belief.evidence_count)
                    else:
                        p = max(0.0, min(1.0, float(outcome.get("probability", 0.0))))
                    if p <= 0.0:
                        continue

                    out_mass += p
                    branch_context = outcome.get("_simulation_context", shared_context)
                    branch_context_key = str(outcome.get("_simulation_context_key", shared_context_key))
                    child = solve(child_state, child_belief, branch_context, branch_context_key, depth_left - 1)
                    goal_p += p * child.goal_probability
                    hazard_p += p * child.hazard_probability
                    unknown_p += p * child.unknown_probability
                    prox += p * child.expected_proximity
                    future_cost += p * child.expected_cost
                    branches.append({
                        "probability": float(p),
                        "observation": observation,
                        "belief_after": child_belief.as_dict(),
                        "belief_entropy_bits": child_belief.entropy_bits(),
                        "next_node": child.node_id,
                    })

                residual = max(residual, 1.0 - min(1.0, out_mass))
                if residual > 1e-12:
                    probability_mass_truncated = True
                unknown_p = max(unknown_p, residual)
                total = goal_p + hazard_p + unknown_p
                if total > 1.0 + 1e-9:
                    scale = 1.0 / total
                    goal_p *= scale; hazard_p *= scale; unknown_p *= scale
                    prox *= scale; future_cost *= scale

                expected_cost = costs.get(action, 0.0) + future_cost
                risk = self._risk(hazard_p, unknown_p)
                options.append(BeliefPolicyEvaluation(
                    node_id="", action=action, state=dict(state), belief=b,
                    goal_probability=goal_p, hazard_probability=hazard_p,
                    unknown_probability=unknown_p, expected_proximity=prox,
                    expected_cost=expected_cost, risk=risk,
                    utility=self._utility(goal_p, hazard_p, unknown_p, prox, expected_cost, depth_used + 1),
                    branches=tuple(branches),
                ))

            if not options:
                result = BeliefPolicyEvaluation(
                    node_id=new_node_id(), action=None, state=dict(state), belief=b,
                    goal_probability=0.0, hazard_probability=0.0, unknown_probability=1.0,
                    expected_proximity=goal.proximity(state), expected_cost=0.0,
                    risk=self._risk(0.0, 1.0),
                    utility=self._utility(0.0, 0.0, 1.0, goal.proximity(state), 0.0, depth_used),
                    branches=(), terminal_reason=("budget" if expansions >= self.max_expansions else "no_prediction"),
                )
            else:
                acceptable = [o for o in options if self._acceptable(o)]
                chosen = max(acceptable or options, key=self._rank)
                chosen.node_id = new_node_id()
                result = chosen
            store(result)
            if self.memo_limit and len(memo) < self.memo_limit:
                memo[key] = result
            return result

        best = solve(dict(initial_state), belief, None, "", actual_horizon)

        # Graph statistics traverse references, not duplicated child trees.
        visited: set[str] = set()
        contingent = False
        max_diversity = 0
        stack = [best.node_id]
        while stack:
            nid = stack.pop()
            if nid in visited or nid not in graph: continue
            visited.add(nid)
            node = graph[nid]
            child_actions: set[str] = set()
            for branch in node.get("branches") or []:
                nxt = str(branch.get("next_node", ""))
                if nxt and nxt in graph:
                    act = graph[nxt].get("action")
                    if act is not None: child_actions.add(str(act))
                    stack.append(nxt)
            contingent = contingent or len(child_actions) > 1
            max_diversity = max(max_diversity, len(child_actions))

        if goal.satisfied(initial_state):
            status, reason = "goal_already_satisfied", "initial_state_satisfies_goal"
        elif budget_exhausted_during_search:
            status, reason = "budget_exhausted_partial_policy", "expansion_budget_reached_before_search_completed"
        elif self._acceptable(best):
            status, reason = "belief_contingent_plan_found", "goal_probability_and_risk_thresholds_satisfied"
        elif expansions >= self.max_expansions:
            status, reason = "budget_exhausted", "expansion_budget_reached_before_acceptable_policy"
        elif best.action is None:
            status, reason = "no_prediction", "transition_model_returned_no_usable_distributions"
        else:
            status, reason = "risk_threshold_not_met", "no_policy_satisfied_goal_risk_and_unknown_thresholds"

        return {
            "status": status, "reason": reason, "goal": asdict(goal),
            "initial_belief": belief.as_dict(), "best": best.as_dict(),
            "root_node": best.node_id, "policy_graph": graph,
            "expansions": expansions, "prediction_failures": prediction_failures,
            "invalid_likelihood_models": invalid_likelihood_models,
            "search_complete": not budget_exhausted_during_search,
            "search_budget_exhausted": budget_exhausted_during_search,
            "hypothesis_cap_reached": len(belief.hypothesis_names()) >= self.max_hypotheses,
            "probability_mass_truncated": probability_mass_truncated,
            "calibrated_calls": calibrated_calls, "uncalibrated_calls": uncalibrated_calls,
            "belief_updates": evidence_updates, "belief_merge_hits": memo_hits,
            "unique_belief_states": len(unique_beliefs), "policy_nodes": len(graph),
            "max_evidence_count": max_evidence_count, "horizon": actual_horizon,
            "top_k_outcomes": self.top_k_outcomes, "risk_aversion": self.risk_aversion,
            "unknown_risk_weight": self.unknown_risk_weight,
            "min_goal_probability": self.min_goal_probability,
            "max_hazard_probability": self.max_hazard_probability,
            "max_unknown_probability": self.max_unknown_probability,
            "observation_conditioned": True, "belief_state_planning": True,
            "contingent_branching_used": contingent,
            "branch_action_diversity": max_diversity,
            "simulated_only": True, "probabilistic": True,
        }

