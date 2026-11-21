# Architecture Report — ASM v0.4.0-alpha.7.3

## Capability added

Alpha.7.3 adds **Multi-Input Compositional Procedure Induction** to the experimental-but-integrated Procedure Cortex. It does not replace ASM's memory, evidence calibration, hidden-dependency learning, world model, transition mechanisms, planners, or self/agent models.

## Authority flow

```text
Externally resolved experience
        |
        v
alpha.6/6.1 source reliability + regime check
        |
        v
independent evidence-root filter
        |
        v
arity-aware proposal gate
  unary=3 / 2in=4 / 3in=5 / 4in=6
        |
        v
bounded synthesizer
  +--> exact full-rank affine solve
  +--> trusted active structure donors
  +--> square/nonlinear seeds
  +--> shallow signature-dedup composition
        |
        v
PROPOSED version (never immediately trusted)
        |
        v
8 DISTINCT held-out validation inputs
        |
        v
ACTIVE version
        |
        +--> dependency invalidation => abstain
        +--> prediction mismatch => abstain + new regime window
                                  |
                                  v
                         new/revalidated version
```

## Multi-input affine solver

The affine path solves exactly over rational arithmetic. A solution is accepted only when the observation matrix has full parameter rank and every coefficient/bias is an integer within the configured bound. This prevents alpha.7.3 from inventing an arbitrary member of an underdetermined affine family.

## Compositional synthesis

When affine fitting does not explain the evidence, alpha.7.3 searches a deliberately small expression space.

Base structures include:

- current input variables;
- trusted active donor expressions remapped onto compatible inputs;
- per-input squares;
- constants `-3..3`.

Binary operators:

- `add`
- `sub`
- `mul`
- `min`
- `max`

Search is at most two shallow composition layers. Observationally equivalent candidates are signature-deduplicated and the second-layer frontier is capped. Total candidate count cannot exceed **512**.

## Donor trust rule

A donor can contribute expression structure only if it is currently `active` and every recorded source dependency still has the expected source-regime version with reliability >= `0.8`.

Even then, only **structure** is reused. A new composed procedure:

- receives a new version history under its own mechanism/context;
- is fitted against its own independent roots;
- stores its own evidence-source dependencies;
- requires its own 8 distinct held-out validation inputs.

No procedure inherits another procedure's confidence or activation status.

## Drift and reversal

Alpha.7.2's procedure-regime logic is unchanged. First active/proposed mismatch establishes the fresh evidence boundary. New evidence can induce a new multi-input version. If a historical expression fits the new regime, ASM creates a new revalidation version rather than reactivating stale trust in place.

## Relationship to alpha.7.1

Alpha.7.1 remains the authority for hidden statistical evidence dependency and temporal dependency regimes. Procedure Cortex uses independent explicit roots plus adaptive source trust/regime binding; explicit ancestry remains available through `EvidenceLedger`.

## Boundedness

- max mechanism/context scopes: 128
- max versions per scope: 64
- max program inputs: 4
- max candidate programs per synthesis attempt: 512
- max source dependencies per procedure version: 8
- held-out validation: 8 distinct inputs
- unary fit roots: 3
- 2/3/4-input fit roots: 4/5/6
- typed DSL expression node/depth limits remain enforced
- no Python `eval` or arbitrary code execution

## Snapshot migration

Alpha.7.3 uses `asm_snapshot_v0_4_0_alpha_7_3` and explicitly falls back to `asm_snapshot_v0_4_0_alpha_7_2`. Procedure tables remain additive SQLite state, so migration does not synthesize new versions.
