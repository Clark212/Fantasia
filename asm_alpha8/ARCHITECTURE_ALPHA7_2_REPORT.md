# Architecture Report — ASM v0.4.0-alpha.7.2

## Capability added

Alpha.7.2 adds **Autonomous Procedure Induction** as a bounded procedural layer above the existing alpha.7.1 evidence system. It does not replace transition mechanisms, world modeling, planning, memory, or evidence calibration.

## Authority flow

```text
Externally resolved experience
        |
        v
Source reliability + regime check (alpha.6/6.1)
        |
        v
Independent evidence-root filter
        |
        v
Autonomous induction trigger (>=3 trusted roots)
        |
        +--> old-version revalidation candidate
        |        OR
        +--> bounded grammar/family search
        v
PROPOSED procedure version
        |
        v
8 independent held-out validations
        |
        v
ACTIVE procedure
        |
        +--> prediction only while dependencies remain valid
        |
        +--> first mismatch => abstain + fresh regime window
                           |
                           v
                   new/revalidated version
```

## Core invariants

- ASM's own prediction is never used as the truth label for procedure induction.
- Autonomous induction consumes only externally resolved observations already admitted by the procedure evidence API.
- At least three independent roots are required before proposing a procedure.
- Current source reliability must meet the trust floor (`0.8`) and the recorded source-regime version must still match.
- A proposal is not active until held-out evidence validates it.
- Existing versions are never overwritten; revisions and reversals create new versions.
- Prediction cannot train alpha.7 dependency state.
- A failed capacity check never deletes historical versions.
- Explicit manual procedure APIs remain available and unchanged by default.

## Drift handling

A mismatch by an active procedure creates `active_prediction_mismatch` and starts the newest procedure-regime window. Later mismatches from an already-suspicious version do not advance that boundary. This prevents the change point from chasing the newest failure and gives fresh evidence room to accumulate.

A failed proposed hypothesis creates `proposal_prediction_mismatch`, allowing a new candidate window without treating the failed proposal as trusted history.

## Reversal handling

Before spending grammar search, alpha.7.2 checks retired/suspended/suspicious old programs against the fresh trusted fit set. A match creates a **new proposed version** with provenance `asm_auto_revalidation:versionN`. The old version itself is never reactivated in place.

## Persistence

`procedure_auto_state` stores the last fit signature, attempt sequence, result status, and bounded attempt count per `(mechanism, context)`. Restarting during validation therefore does not cause a duplicate induction attempt on identical evidence.

The procedure tables remain additive SQLite state. Alpha.7.2 cognitive snapshots use `asm_snapshot_v0_4_0_alpha_7_2` and fall back to the alpha.7.1 snapshot key during migration.

## Boundedness

- max mechanisms: 128
- max versions per mechanism/context: 64
- fit roots per autonomous attempt: 3..16 (default 3)
- induction candidate budget: <=512
- source dependencies per version: <=8
- built-in autonomous grammar: unary integer identity, square, bounded affine rules, plus bounded family proposals
- typed executable DSL remains total-budgeted and does not use Python `eval`/`exec`

## Relationship to alpha.7.1 evidence dependency

Alpha.7.1 still owns statistical hidden-dependency calibration and temporal dependency regimes for evidence fusion. Procedure induction currently uses explicit evidence roots plus adaptive source reliability/regime binding. This is intentionally conservative: alpha.7.2 does not yet claim that all procedure evidence is fully corrected by the learned cross-source dependency model.
