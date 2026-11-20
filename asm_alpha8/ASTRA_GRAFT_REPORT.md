# ASM v0.4.0-alpha.7.1 — Astra Procedure/Evidence Graft Candidate

## Status

This is an additive research candidate built on the certified ASM v0.4.0-alpha.7.1 branch.
It does **not** replace or weaken alpha.7/alpha.7.1 hidden-dependency learning.
It intentionally keeps the internal release version at `0.4.0-alpha.7.1` until this donor integration is explicitly promoted.

Base artifact SHA-256:
`3dfb15a801a86946a194bec0f6fcaf20406cf778ac795e093ebbf144eae47159`

Astra donor artifact SHA-256:
`ca4a255b88c30d0efdfcf169e0a0dfdf0bda3e5296e5df5a6b9b9cfec2671176`

## Donor mechanisms accepted

1. **Typed bounded procedure language** (`asm/procedure_program.py`)
   - typed `int` / `bool` inputs
   - bounded expression size/depth
   - no Python `eval` / `exec`, imports, loops, files, network, or arbitrary code generation
   - lazy compilation with interpreted/compiled equivalence tests
   - structural anti-unification and bounded disagreement query selection

2. **Audited SQLite Procedure Cortex** (added alongside the existing `ExperimentalProcedureCortex`)
   - independent fit evidence requirement
   - held-out validation before activation
   - evidence-root de-duplication
   - source reliability/regime dependencies
   - automatic abstention when a bound source regime changes
   - retained procedure versions and audit events
   - family proposals / structural transfer
   - contradiction-driven suspicious/suspended states
   - lazy DB opening so unrelated cognition does not pay connection overhead

3. **Versioned structured proposal contract** (`asm/proposal_contract.py`)
   - strict schemas for entities, relations, propositions, observations, requested actions, and candidate procedures
   - validation grants no action authority
   - requested actions remain unexecuted proposals
   - candidate procedures enter the Procedure Cortex validation gate only

4. **Explicit ancestry-aware EvidenceLedger** (additive to the existing lineage graph)
   - independent root events are support units
   - known copies/derivations can be suppressed conservatively
   - bounded snapshot/export/import
   - invalid additions fail before mutation

5. **Semantic exact-cache/index optimizations**
   - Astra pair-cache implementation transplanted with exact-equivalence regression coverage
   - SQLite `semantic_lsh(event_id)` index added
   - no performance speedup is claimed from this recreation because the quick microbenchmark was dominated by the pre-existing higher-level similarity cache.

## Donor mechanisms rejected / not merged

- Astra's `RegimeEvidenceModel` did **not** replace alpha.7.1 adaptive evidence.
- Astra's declared-ancestry-only dependency handling did **not** replace `EvidenceDependencyModel`.
- Astra's engine wholesale was **not** merged.
- Hidden dependency remains learned from externally resolved grouped evidence.
- Time-aware dependency regime learning remains alpha.7.1's implementation.

## Important integration improvement beyond Astra donor

Procedure source dependencies bind to alpha.7.1's **active source reliability regime ID** and use its **effective reliability**. A procedure validated under source regime 1 automatically abstains after alpha.7.1 detects a genuine source reliability change to regime 2, even before the procedure receives a contradictory output label.

## Fresh test results

Completed bounded unit batches after the final lazy-load integration:

- Batch A (review + v0.1/v0.2): **159/159 PASS**
- Batch B (v0.3): **77 executed = 76 PASS + 1 inherited intentional SKIP**
- Batch C (v0.4 + old experimental Procedure Cortex + donor graft): **136/136 PASS**
- Total: **372 executed = 371 PASS + 1 inherited intentional SKIP**

New donor-graft tests alone: **10/10 PASS**.

Critical cognition reruns:

- alpha.7.1 frozen benchmark: **8/8 PASS**
- alpha.7.1 torture: **9/9 PASS**
- alpha.7 frozen benchmark: **7/7 PASS**
- alpha.7 torture: **9/9 PASS**
- smoke test: **PASS**

A combined recertification command timed out and is **not counted**. The three bounded unit batches above were rerun separately and completed.

## Graft-specific verified behaviors

- Typed programs: interpreted and compiled execution agree on generated inputs.
- Unsafe/unsupported operations fail closed.
- Procedure candidate stays abstained until held-out support activates it.
- Procedure state persists in SQLite.
- Contradictory validation can suspend an active version.
- Family transfer produced the same target program with fewer evaluator calls in the controlled donor test.
- Explicit evidence ancestry suppresses repeated copies of one root.
- EvidenceLedger snapshot roundtrip preserves belief exactly.
- Requested-action proposals are returned as `requires_grounding` and `executed=False`.
- Candidate-procedure proposals enter the procedure gate and are not executed.
- Procedure prediction does not mutate/train the hidden dependency model.
- A real alpha.7.1 source-regime change invalidates a stale bound procedure.
- Semantic pair-cache enabled/disabled paths produced identical answers in the generated regression stream.

## Research status

The graft is useful and passes regression, but Procedure Cortex remains **experimental**. It is not being described as a new general-intelligence capability, and the donor integration is not promoted to a new official numbered release in this artifact.
