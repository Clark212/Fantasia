# ASM Alpha 8 — DEV8 combined build (experimental, not promoted)

Built from: DEV8 research loop (`ASM_alpha8_CODING_DEV8`) on the DEV7 Alpha 8 tree. Earlier releases are preserved unchanged.

## What "combined" means here
- DEV8 `CodingResearchLoop`, `FailureLedger`, `Candidate`, `ResearchContext` live in `asm/coding/research.py` and are exported from `asm.coding`.
- New single entry point: `CodingAgent.research(root, task, generator, ...)` ties DEV8 to the Alpha 8 coding agent (shared `TestRunner`, optional ledger and `ProcedureStore` paths). It never modifies the repository and never applies the winning candidate.

## Not done (stated plainly)
- The coding package is **not connected to ASM's cognitive core** (`mind.py`, goals, world model, memory). That integration is roadmap DEV36, not claimed here.
- `main.py` has no coding command; nothing was added there.
- No code-generation model exists; a trusted caller supplies the generator.
- No DEV8-vs-DEV7 benchmark has been run; no improvement is claimed. See the DEV8 promotion gate.
