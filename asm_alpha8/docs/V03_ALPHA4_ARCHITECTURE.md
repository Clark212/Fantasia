# ASM v0.3.0-alpha.4 Architecture — Selective Seismic Scheduling

## Scope

Alpha.4 asks one question: **can ASM avoid executing irrelevant learned mechanisms while preserving the predictions produced by the same mechanism bank?**

```text
structured local state + action
        ↓
learned applicability profiles
        ↓
rank mechanism types
        ↓
seismic top-k execution
        ↓
uncertainty check
   ↙ sufficient   ↘ uncertain/OOD
 answer             widen / dense fallback
```

### Applicability profile

Each observed mechanism transition contributes generic features such as:

```text
action=open
state:kind=door
state:mode=closed
dt=unit
```

The scheduler stores support for these features per mechanism type. Routing is generic; there are no `if door -> door mechanism` branches. `state:kind` and action features receive more routing weight than the coarse time bucket.

### Safety against starvation

If the highest relevance is below the configured minimum, seismic mode executes all known mechanisms. If the selected mechanism is too uncertain, it can widen through lower-ranked candidates. These paths cost more compute by design: uncertainty is not treated as proof that sparse execution is safe.

### What is deliberately not here

- automatic discovery/splitting of mechanism types
- causal claims
- counterfactual simulation
- planning
- neural-to-program compilation
- broad world knowledge

Mechanism identities in the alpha.4 benchmark are supplied so scheduling can be isolated from the later representation-discovery problem.
