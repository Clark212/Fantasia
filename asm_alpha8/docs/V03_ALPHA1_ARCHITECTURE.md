# ASM v0.3.0-alpha.1 Architecture

## Purpose

Alpha.1 creates an explicit world-state boundary between semantic understanding and future predictive mechanisms.

```text
language / observation
        ↓
Semantic Event Cortex
        ↓
PersistentWorldModel
        ├─ current state
        ├─ state history
        ├─ graph topology
        ├─ transition evidence
        └─ dependency scheduler
        ↓
future v0.3 local mechanisms
```

## State identity

A state slot is keyed by:

```text
(event_type, holder/perspective, canonical_proposition)
```

Truth and epistemic state are mutable values inside that slot.

This means a changed truth value revises a state instead of creating an unrelated proposition, while different holders and epistemic scopes remain isolated.

## Nested mental state

`Alice thinks Bob believes P` is represented as a scoped perspective path:

```text
nested_belief|alice>bob|P
```

The graph also contains:

```text
agent:alice --models_mind--> agent:bob
agent:bob --scoped_by_path--> mindpath:alice>bob
mindpath:alice>bob --holds_nested_state--> state:P
```

The architecture therefore does not infer that Alice independently believes P or that Bob's belief is reality.

## World graph

Alpha.1 uses four persistent table families:

1. `world_current_state` — latest explicit state per slot.
2. `world_state_history` — immutable event-scoped observations of each slot.
3. `world_nodes` / `world_edges` — graph topology for holder, state, and proposition-term anchors.
4. `world_transition_evidence` / `world_dependencies` — revision evidence and local scheduling dependencies.

Proposition terms are **anchors**, not claims of solved entity induction. Physical entity discovery remains a later problem.

## Transition semantics

Transitions are classified as:

- `new_state`
- `reaffirm`
- `truth_revision`
- `epistemic_shift`

`causal` is always false in alpha.1.

A future causal mechanism must require action-conditioned/interventional evidence or another declared causal test. Sequential observations alone are insufficient.

## Scheduler

A persistent state update creates bounded `MechanismCandidate` records in memory for that processing result. Priorities currently use deterministic dependencies:

```text
changed exact state     1.00
holder/perspective      0.72
event type              0.62
proposition term        0.40
```

These constants are engineering defaults, not learned optimal values. Alpha.2 should test whether recurrent transition mechanisms can actually use the selected neighborhoods.

## Research invariant

Do not call a future module a mechanism merely because it has a name or receives a scheduled event. It must improve held-out prediction or adaptation, and deleting it must measurably change behavior.
