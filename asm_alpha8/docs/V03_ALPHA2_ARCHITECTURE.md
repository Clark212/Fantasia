# ASM v0.3.0-alpha.2 Architecture — Local Recurrent Transition Mechanisms

## Objective

Teach ASM a local action-conditioned transition model before attempting planning or program compilation.

```text
(state_t, action_t, dt, neighborhood_t)
                 ↓
        recurrent mechanism M
                 ↓
          prediction state_t+1
                 ↓
            observed state_t+1
                 ↓
             prediction error
                 ↓
         online parameter update
```

## Mechanism bank

`TransitionMechanismBank` stores one shared `LocalRecurrentTransitionMechanism` per mechanism type. Compatible entity instances use the same neural parameters.

Entity names are never hashed into the input feature vector. They only select recurrent context. This separates:

- **mechanism knowledge**: shared weights;
- **instance history**: recurrent context.

## Input representation

The alpha.2 prototype uses deterministic feature hashing over bounded structured features:

- current local `state` key/value pairs;
- `action`;
- optional neighborhood key/value pairs;
- coarse elapsed-time bucket.

The representation is deliberately simple. Entity discovery and learned continuous state encoders are later research problems.

## Network

Default release configuration:

```text
input dimensions     128
hidden dimensions     64
max known outcomes    32 / mechanism type
optimizer             Adam
online train steps      6 / observation
```

A linear projection feeds a `GRUCell`, then an outcome-classification head. New observed next-state dictionaries are mapped to unused bounded outcome slots.

## Online learning and replay

A first implementation trained mostly through the persistent recurrent context. It learned the training entities but only transferred 3/5 held-out door transitions, and a new jammed-door exception temporarily overwrote the ordinary-door rule.

The shipped version therefore trains two paths:

1. zero recurrent context on a small bounded replay set, forcing shared state/action competence;
2. an auxiliary loss from the entity's current recurrent context, retaining sequence sensitivity.

Replay is capped at 256 experiences per mechanism in alpha.2.

## Recurrent-state necessity test

The benchmark trains identical visible `READ` inputs with history-dependent targets:

```text
prime_left  → READ → bit 0
prime_right → READ → bit 1
```

Fresh entities are primed independently and then receive the exact same visible `READ` input. The trained mechanism predicts the correct different outputs for both. This demonstrates that recurrent context changes behavior.

## Surprise / uncertainty

Prediction confidence combines:

- softmax confidence over known outcomes;
- mechanism support;
- global exponential moving prediction error;
- per-entity recent surprise.

A wrong transition sets recent surprise high. Correct subsequent observations decay it. This is a functional uncertainty signal, not a formal Bayesian posterior.

## Persistence

SQLite tables:

```text
world_mechanism_models
world_mechanism_experiences
```

The model blob contains neural weights, optimizer state, outcome mapping, replay buffer, recurrent contexts, surprise contexts, and counters.

## Safety / epistemic boundary

Alpha.2 learns correlations in supplied state/action transition tuples. It does not claim that a learned transition is a causal law. Alpha.1's `world_transition_evidence.causal` field remains false.

## Not implemented yet

- automatic learned routing from the seismic scheduler;
- action extraction from arbitrary natural language;
- continuous numeric state prediction;
- entity induction from raw perception;
- causal interventions;
- compiled executable programs;
- counterfactual branches;
- planning.
