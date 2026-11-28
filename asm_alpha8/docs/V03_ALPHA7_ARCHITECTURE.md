# ASM v0.3.0-alpha.7 — Elastic Mechanism Capacity

## Problem
Alpha.6 mechanisms had a fixed output head. `max_outcomes=32` meant the 33rd distinct outcome raised a runtime error even if the recurrent mechanism otherwise had enough representational capacity.

## Change
When a genuinely new outcome arrives and the active head is full, alpha.7 grows the output layer up to a configured bound. Old rows are copied exactly. New rows receive deterministic initialization. Adam moments for unchanged layers and prior output rows are preserved. The model blob records current capacity, ceiling, growth factor, expansion count, and capacity history.

Conceptually:

`local state + action + recurrent context -> hidden state -> elastic outcome head -> predicted next state`

The head expands only on observed novelty. It does not create new mechanisms, infer causal structure, or restructure representations.

## Bounds
The default initial capacity is 32 and default configured ceiling is 256. Alpha.7 validates 96 learned outcomes and two expansions (32 -> 64 -> 128). The full 256 ceiling is not claimed as retention-validated. Alpha.6's default retention-anchor set remains 96, so future work must test retention behavior if mechanisms regularly exceed 96 distinct stable outcomes.

## Safety / regression constraints
- expansion may not alter old output rows at the instant of resizing;
- fixed capacity limits still raise rather than silently overwrite outcomes;
- expanded blobs must reload into a fresh initial-32 model;
- alpha.2-alpha.6 gates remain unchanged.
