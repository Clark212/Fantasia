# ASM v0.3.0-alpha.5 Architecture — Competitive Seismic Routing

## Research question

Alpha.4 established that a learned scheduler could avoid executing every mechanism on clean inputs. Alpha.5 tests the harder case:

> Can sparse execution remain reliable when several mechanisms overlap, while admitting ambiguity and learning from routing mistakes?

```text
structured local state + action + neighborhood + dt
        ↓
generic routing features + learned conjunctions
        ↓
positive / negative applicability evidence
        ↓
rank competing mechanisms
        ↓
confidence + top-two margin + empirical correction
   ┌──────────────┼─────────────────────┐
 high            medium                 low / OOD
   ↓               ↓                       ↓
 top-1/top-k     competitive top-k      dense fallback
   └──────────────┼─────────────────────┘
                  ↓
        recurrent transition predictions
                  ↓
            outcome observed
                  ↓
        prediction-error route feedback
```

## Routing representation

Routing starts from the same generic structured features used by alpha.4, for example:

```text
action=open
state:kind=valve
state:open=false
neighbor:pressure_safe=false
dt=unit
```

Alpha.5 also learns generic conjunction features, such as kind+action, kind+state and kind+neighbor. A hashed exact structured-context token gives negative feedback a narrow place to attach without hardcoding domain labels.

No code branch says that a door must use a door mechanism, a valve must use a valve mechanism, etc. Mechanism identities are still supplied to the learning API; discovering mechanism decomposition remains future work.

## Competitive routing

Each mechanism receives a relevance score from matching positive and negative routing evidence. The scheduler also measures the margin between the two highest-ranked candidates.

- High confidence and a sufficient margin use sparse top-k execution (top-1 by default).
- Mid-confidence or tied evidence widens to a bounded competitive set.
- Low relevance or low confidence executes all known mechanisms.
- High prediction uncertainty can still widen after the first mechanism calls, preserving alpha.4's recovery path.

Observationally identical mechanisms cannot be reliably separated. In that case alpha.5 is supposed to widen rather than invent confidence.

## Prediction-error routing feedback

`predict_routed(...)` remembers a bounded recent routing trace keyed by the entity and structured transition query. When the real transition is later supplied to `observe(...)`:

1. the correct mechanism gets positive routing evidence;
2. only wrong mechanisms that were actually executed are candidates for negative evidence;
3. negative evidence is attached only to context-specific or previously unseen discriminators;
4. the top-route correctness outcome updates a persisted confidence bucket.

An earlier implementation penalized broad shared features and could damage a previously valid normal-valve route after learning a safety-valve exception. That design was rejected. The release version passes a retention gate after correction.

## Confidence correction

Before enough routed outcomes exist, routing confidence is explicitly marked `heuristic`. Once a confidence bucket reaches the configured support minimum (4 by default), alpha.5 blends the live evidence score with the bucket's observed correctness posterior and marks the source `empirical`.

This is a small online calibration mechanism, not a claim of globally calibrated probability.

## Recurrent-history stabilization

While validating alpha.5, the unchanged alpha.2 recurrence benchmark reproduced a history failure in the current runtime: one of two identical visible `READ` queries lost its prior-prime distinction. The same failure reproduced in the untouched alpha.4 implementation in this environment.

Rather than lowering the inherited gate, alpha.5 adds a bounded shared one-step trace-conditioned empirical fallback inside each recurrent transition mechanism:

- the GRU remains the primary predictor;
- the fallback is only eligible when the neural softmax confidence is below 0.75;
- it requires at least three observations and >=80% trace-conditioned outcome precision;
- keys use structured predecessor/current inputs, never entity IDs;
- the table is capped (512 entries by default) and persisted.

This restores the unchanged alpha.2 history gate to 2/2 in this runtime. Because the fallback can now contribute on uncertain history cases, alpha.5 should **not** claim that its inherited history success is purely evidence for GRU credit assignment.

## Deliberately excluded

- automatic mechanism discovery/splitting
- causal inference
- counterfactual planning
- structural SPLIT/MERGE/FACTOR operations
- neural-to-program compilation
- broad world knowledge
- autonomous tool use
