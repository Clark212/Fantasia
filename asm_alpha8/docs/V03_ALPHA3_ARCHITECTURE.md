# ASM v0.3.0-alpha.3 Architecture — Multi-Domain Mechanism Learning

## Scope

Alpha.3 does not add planning. It hardens the alpha.2 local recurrent transition learner so the same generic mechanism can survive sequential experience from several structured domains and learn a short history-dependent transition.

## Balanced structural replay

Alpha.2 retained the newest 256 replay records. A sufficiently long run in one domain could therefore displace all old-domain evidence.

Alpha.3 assigns each replay item a structural stratum derived from visible state and neighborhood keys. When the buffer exceeds its cap, eviction comes from the most overrepresented stratum. Training batches first sample across strata, then fill remaining capacity with bounded strided history.

No task-specific domain rule is encoded by this policy.

## Ambiguous visible inputs

For an input signature `x = (state, action, neighborhood, dt)`, alpha.3 tracks whether replay contains more than one observed outcome.

If only one outcome is observed, zero-context shared training remains the main transfer path.

If multiple outcomes occur for the same visible input, alpha.3 does not force the zero-context path to average contradictory targets. The recurrent-context loss receives higher weight instead.

## Bounded truncated recurrent credit

Each entity stores at most four recent input records:

```text
[(state, action, neighborhood, dt), ...]
```

During recurrent-context training, alpha.3 reconstructs hidden state from that bounded trace inside the current computation graph, then applies the current input and outcome loss.

This allows a later `READ` error to update how an earlier `prime_left` or `prime_right` input is encoded.

The trace is persisted with mechanism state and cleared by `reset_context()`.

## What this does not solve

- object/entity discovery from raw perception;
- automatic mechanism-type discovery;
- long-horizon credit assignment;
- optimal replay allocation;
- cross-domain abstraction;
- causal inference;
- planning;
- program induction.

The trace limit of 4 is an experimental bound, not a cognitive claim.
