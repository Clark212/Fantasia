# ASM v0.3.0-alpha.9 — Adaptive Multi-Choice Consolidation

## Trigger

Alpha.8's fixed 43,008-byte consolidation sketch degraded as stable mappings grew: 98.8% exact recall at 256, 79.3% at 1,024, and 54.5% at 2,048 in the extreme-feed diagnostic. Wrong exact-key recalls were not the main failure; mappings were being lost through collision/eviction.

## Design

Alpha.8 effectively spent three cells per stable mapping by writing one copy into each hash table. Alpha.9 instead treats the same total cells as a multi-choice placement pool.

For a stable unambiguous visible mapping:

1. compute its 64-bit exact fingerprint;
2. derive several candidate cells from that fingerprint;
3. update the existing cell if already present;
4. otherwise use an empty candidate;
5. if all candidates are occupied, perform a bounded displacement chain;
6. if the bounded chain cannot find room, one record is dropped and later lookup becomes a miss rather than a false-key hit.

The fingerprint alone determines candidate positions, so displaced entries can be relocated without storing the original text signature.

## Memory

Default arrays remain:

- fingerprint: uint64
- outcome slot: int32
- support: uint16
- 1,024 table-size units × 3 choices = 3,072 physical cells
- logical bytes: **43,008**

Alpha.9 therefore improves utilization without simply making the table larger.

## Safety boundaries

- ambiguous/history-dependent visible signatures are excluded;
- consolidation remains dormant while the 96 full anchors can cover all known outcomes;
- exact fingerprint matching is required before explicit-memory override;
- neural/recurrent learning remains the fallback when no consolidated entry is available.

## Migration

Alpha.9 can import alpha.8 mechanism blobs. Legacy duplicate cells are deduplicated by `(fingerprint, outcome slot)` and reinserted into the new layout. The project trained DB contains zero learned transition mechanisms, so its release migration does not depend on this conversion path, but the path is unit-tested separately.

## Limits

Alpha.9 does not provide unlimited memory. With the default 43,008-byte table, component recall remains 100% through 2,048 mappings in the tested stream, then begins to degrade around high physical load (98.5% at 2,560). This is still a bounded associative memory, not a compressed semantic model or proof of generalization.
