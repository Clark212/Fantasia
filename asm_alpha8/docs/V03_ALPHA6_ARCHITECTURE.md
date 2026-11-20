# ASM v0.3.0-alpha.6 — Continual Retention Stress

## Research question

Can a shared local recurrent mechanism continue learning later outcomes without erasing previously learned outcomes after its bounded recency replay buffer has been flooded?

## Observed predecessor failure

A 32-outcome curriculum was split into an old half and a new half. Under the inherited alpha.5 replay path, the old half reached 15/16, then fell to 3/16 after the new half dominated later training. New outcomes still reached 16/16. This isolated a retention problem rather than a basic inability to learn the later data.

## Alpha.6 mechanism

Each `LocalRecurrentTransitionMechanism` now has two bounded rehearsal timescales:

```text
recent experience
    -> balanced recency replay (max 256)

stable visible mapping
    -> long-horizon retention anchors (max 96)
    -> rotating bounded sample (default 6/update)
```

An anchor is keyed by the visible input signature plus learned outcome slot. It stores a representative structured transition example. It is not a domain rule and does not use entity identity as a predictive feature.

### Activation guard

Long-horizon anchors are not used while `len(replay) < replay_limit`. This keeps early learning equivalent to the inherited mechanism until recency eviction pressure actually exists.

### Ambiguity guard

If one visible input signature has multiple observed outcome slots, that signature is marked ambiguous. Its anchors are removed/not created, and ambiguous current inputs use the inherited recurrent-learning replay path. History-dependent behavior therefore remains the responsibility of recurrent context and the bounded trace fallback rather than a contradictory zero-context rehearsal table.

### Persistence

The following are serialized inside the mechanism blob:

- anchor dictionary
- ambiguous-signature set
- anchor cap
- per-update anchor budget
- rotation cursor

Older alpha.2-alpha.5 model blobs have no anchor fields. On import, alpha.6 can backfill bounded candidate anchors from the existing replay buffer while detecting ambiguous signatures.

## Frozen experiment

Same network/optimizer/seed/curriculum; only anchor rehearsal is disabled in the historical replay ablation.

- protected old retention after late stream: **15/16**
- alpha.5 replay ablation after late stream: **3/16**
- protected new set: **16/16**
- protected serialize/reload old: **15/16**
- protected serialize/reload new: **16/16**
- alpha.6 gates: **11/11**

## What this does not prove

It does not prove general catastrophic-forgetting resistance, unbounded memory, mechanism discovery, causal learning, planning, structural representation editing, or AGI. It establishes a narrower result: a bounded long-horizon rehearsal layer materially improves retention on the specific shared-mechanism sequential stream that broke the predecessor.
