# ASM v0.4.0-alpha.6.2 — Evidence Lineage Hardening

Alpha.6.2 is a same-stage hardening release. It does **not** claim automatic correlation discovery and is not alpha.7.

## Added
- `EvidenceLineageGraph` with bounded, fail-closed provenance records.
- Optional `evidence_id`, `parent_evidence_ids`, and `lineage_root_ids` in `ASMEngine.update_belief_from_source(...)`.
- Fractional likelihood weighting when incoming evidence only partly adds independent roots.
- Belief memo keys now distinguish equal posteriors with different lineage histories.
- Snapshot key `asm_snapshot_v0_4_0_alpha_6_2` with alpha.6.1 fallback.
- Bounded graph/item/belief lineage capacities; overflow fails closed rather than silently forgetting ancestry.

## BEFORE vs AFTER
Controlled binary sensor, true reliability 70%, 20,000 trials:

| Case | Before | After |
|---|---:|---:|
| 9 copies of one shared clue: accuracy | 69.895% | 69.895% |
| 9 copies: mean confidence | 99.951% | 70.000% |
| 9 copies: calibration gap | 30.056% | 0.105% |
| 9 independent clues: accuracy | 89.770% | 89.770% |
| 9 independent clues: mean confidence | 90.067% | 90.067% |

Three independent roots, each copied three times: calibration gap improved from 16.894% to 0.136% while accuracy stayed 78.470%.

## Known limits
- Hidden correlation is not inferred. If callers falsely label copies as independent, overconfidence remains possible.
- If callers falsely collapse independent observations onto one root, ASM will conservatively under-count evidence.
- Belief-state planning does not yet carry future evidence lineage through simulated sensing branches.
- Explicit lineage storage is bounded (`65536` evidence nodes by default, `4096` roots per belief); capacity exhaustion raises instead of silently degrading.
- Procedure Cortex remains experimental and unintegrated.
