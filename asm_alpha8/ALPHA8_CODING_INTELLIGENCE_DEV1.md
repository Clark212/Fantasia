# ASM Alpha 8 Coding Intelligence — DEV1

**Parent:** uploaded `ASM_alpha8_DEV4.zip` (experimental branch). **Scope:** first non-executing coding-intelligence layer. This is a development fork, not a release and not a claim of parity with an LLM coding assistant.

## Added
- `asm/coding/analyzer.py`: bounded Python source scanner, AST symbol index, import/call extraction, local dependency edges, syntax diagnostics, stable content fingerprint. It never imports or executes scanned project code.
- `asm/coding/planner.py`: transparent heuristic task classification and evidence-backed plan skeletons for debugging, features, refactors, tests, explanations, and investigation. It does not edit files or run commands.
- `tests/test_alpha8_coding_intelligence.py`: deterministic unit tests for indexing, syntax diagnostics, bounds/exclusions, planning, and non-mutation.

## Design decisions
1. Keep ASM's cognitive authority: the analyzer emits evidence, not beliefs or actions.
2. No arbitrary code execution in this first increment. Runtime execution will require a separately designed isolated runner with explicit resource and filesystem boundaries.
3. Python-only first, with scan limits and symlink avoidance. Multi-language support is deferred until the Python workflow is validated.
4. File ranking is heuristic and clearly labeled; it is not a semantic understanding claim.

## Known limitations
- No code generation, patch application, test execution, type checking, or runtime debugging yet.
- Relative-import resolution is intentionally conservative and may miss namespace-package edge cases.
- The planner uses token overlap, not learned semantic retrieval.
- No full ASM historical regression suite was run as part of this increment.
