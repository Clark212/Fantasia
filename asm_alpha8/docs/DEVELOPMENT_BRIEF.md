# ASM Development Brief — v0.3.0-alpha.9

Current release: **Adaptive Multi-Choice Consolidation**.

Alpha.9 keeps the v0.3 stack intact and targets the fixed-sketch collision pressure exposed by the alpha.8 extreme feed. Alpha.8's default 43,008-byte consolidation memory wrote redundant copies across three hash tables; alpha.9 uses the same physical arrays as a one-copy multi-choice placement pool with bounded displacement.

Validated scope:

- exact fixed-memory component stress through 2,560 mappings;
- end-to-end 1,024-outcome recurrent-mechanism learning;
- late sequential pressure and serialization/reload;
- a fresh 768-outcome different-seed lockbox;
- direct legacy alpha.8 layout reproduction and untouched alpha.8 same-curriculum comparison;
- alpha.8 mechanism-blob migration;
- inherited alpha.2–alpha.8 regression/capability gates.

Default consolidation memory remains 43,008 logical bytes per mechanism. Default elastic outcome capacity now grows lazily from 32 up to 1,024 slots when needed.

Do not interpret alpha.9 as pure neural lifelong learning, unseen-transition generalization, automatic structure discovery, planning, causal reasoning, broad world knowledge, AGI, or unlimited memory capacity.
