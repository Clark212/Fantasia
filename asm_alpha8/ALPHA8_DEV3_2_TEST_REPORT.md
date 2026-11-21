# Alpha 8 DEV3.2 Test Report

**Artifact:** `ASM_alpha8_DEV3_2.zip` (parent: `ASM_alpha8_DEV3_1.zip`, sha256 f970373f8038a642f1285167879730c7eaf5356c94a93a785b38f3ae79861d51).
Development prototype; not an official release; no Alpha 8 capability claim. **This revision modifies ASM core files** (`procedure_cortex.py`, `config.py`, `engine.py`), all behind an opt-in flag.

## Verified
- Guard tests: **19 passed**, stable over repeated runs. They cover: default equals `off`, adds no key and still answers far outside the range; config/engine default off; abstain leaves inside-range
  answers (including both boundaries and interior gaps) unchanged and refuses outside with a reason; multi-variable (either variable triggers); bool-only procedures unguarded; unknown support;
  dependency-source filter (white-box); discount caps without ever raising confidence and never alters values; invalid settings rejected; engine passes config through; and the DEV3.1 U1-U3 criteria
  re-evaluated for off / abstain / discount caps.
- **Default behaviour unchanged:** both official benchmarks (DEV3 and DEV3.1) re-run with the modified code under the default config give results identical to the shipped ones (excluding runtime;
  DEV3 suite log byte-identical).
- Non-torch regression subset: **508 passed, 57 failed, 1 skipped, 1 xfailed** (508 = 489 + 19). The 57 failures match the 7.9 baseline run without PyTorch in this sandbox.
- Mutation checks on the guard (abstain never triggers; boundaries treated as outside; discount raises instead of caps; bool-only procedures guarded; unknown support treated as inside; off-mode key leak;
  engine ignores config; mode not validated; only first variable checked; evidence from any source): all caught. The last initially survived because untrusted evidence suspends a procedure through the
  public API, so a white-box test was added.
- Guard comparison (`results/ALPHA8_DEV3_2_GUARD_COMPARISON.*`) re-run in a fresh process for determinism (see below).
- A fixture bug (7 distinct training inputs never activate a procedure) was found by the tests' own sanity assertion, investigated, and turned into a documented finding.

## Not verified
- The 3 torch-dependent test files and the 57 torch-related failures were not run with PyTorch here.
- One toy population, one seed; no evaluation inside the full ASM engine with real data; no evaluation of `predict_routed` beyond inheriting `predict`.
- Performance cost of the guard was not benchmarked at scale (it reads that mechanism's evidence rows per guarded prediction).
- Cross-task transfer, continual learning, causal discovery and cognitive-core integration remain unevaluated; DEV2 limits still apply.
