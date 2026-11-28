# v0.3.0-alpha.8 — Long-Horizon Consolidation

## Problem

Alpha.7 can grow a mechanism's output head, but its alpha.6 long-horizon rehearsal still keeps at most 96 full anchors. The 256-outcome hard feed showed that representational capacity and retention capacity had become mismatched: the head could represent 256 outcomes while the learner retained only 191/256 under a long sequential stream.

## Design

Alpha.8 keeps the existing stack and adds a bounded consolidation layer:

```text
observation
  ↓
local recurrent mechanism
  ├─ recent balanced replay
  ├─ up to 96 full retention anchors
  └─ fixed associative consolidation sketch   ← alpha.8
          ↓
     stable visible mapping retrieval
```

The sketch does not replace recurrence. It activates only after known outcomes exceed the full-anchor limit.

### Cell layout

Default:

```text
3 hash tables × 1024 buckets
cell = uint64 fingerprint + int32 outcome slot + uint16 support
fixed bytes = 3 × 1024 × 14 = 43,008
```

The mapping key is the canonical visible input signature already used by the mechanism layer. A separate 64-bit fingerprint is stored in each candidate bucket. On lookup, a cell is usable only when the fingerprint matches exactly and support clears the minimum threshold.

### Collision handling

Each new observation touches one bucket per hash table. Same-key observations increase support. A colliding key applies a bounded Boyer–Moore-style decrement/replacement rule. There is no dynamically growing dictionary of consolidated mappings.

### Ambiguity safety

If the same visible input is observed with multiple outcomes, that signature is marked ambiguous. Its consolidation entries are cleared and future consolidation is blocked. Such cases remain the responsibility of recurrent context / trace learning.

## What this buys

The frozen 256-outcome case retains all 256 mappings after late pressure and reload while retaining only 96 full examples. A fresh 192-outcome lockbox also retains all mappings. The memory allocation remains 43,008 bytes in both runs.

## What this does not buy

- no unseen-transition generalization from the sketch;
- no proof that the recurrent weights themselves retain all mappings;
- no unbounded capacity;
- no autonomous mechanism discovery;
- no causal learning or planning;
- no broad knowledge acquisition.

At sufficiently high load, fixed-size hash collisions will degrade coverage. That future failure should be measured rather than assumed away.
