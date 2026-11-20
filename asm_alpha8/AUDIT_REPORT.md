# ASM v0.4.0-alpha.5 Audit

## What changed

Alpha.5 adds a new planning layer; it does not replace transition learning, semantic memory, world state, routing, consolidation, or the alpha.1-alpha.4 planners.

## Read-only simulation

Belief updates happen on immutable `DiscreteBeliefState` objects inside simulated branches. The planner does not call transition `observe()` or write simulated states into episodic/world memory.

## Boundedness

Default alpha.5 bounds:

- max horizon: 8
- max expansions: 256
- top-k outcomes: 4
- max hypotheses: 32
- memo entries: 8192
- posterior memo key precision: 12 decimal places

## Evidence semantics

When an outcome supplies `hypothesis_likelihoods`, its branch mass is calculated from the current belief:

`P(observation) = Σ_h P(h) P(observation | h)`

The child branch then receives the normalized posterior. Outcomes without latent likelihoods retain the existing alpha.3/alpha.4 probability path.

## Policy representation

Equivalent `(visible state, belief posterior, simulation-context key, remaining depth)` tuples are memoized. Public alpha.5 policy output uses a node graph with `next_node` references, avoiding recursive duplication of equivalent raw-history branches.

## Migration

Alpha.5 uses `asm_snapshot_v0_4_0_alpha_5` and falls back to alpha.4 and older snapshot keys. A copy of the trained DB round-tripped without changing the measured 897/897/897 memory counts or 24/50 world-state counts.

## Known limitations

- latent hypothesis labels are supplied; automatic latent-state discovery is not implemented
- likelihood quality is only as good as the supplied/learned evidence model
- exact discrete belief tracking can still grow with many hypotheses or complex continuous latent state
- policy-DAG merging uses rounded probability keys; this is a bounded engineering choice, not an exact symbolic theorem prover
- no claim of general causal reasoning, AGI, or RSI
- full inherited alpha.8-alpha.10 mega stress was not rerun after final alpha.5 changes
