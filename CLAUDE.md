# Working on ASM (Fantasia)

Follow the project owner's master development directive (initialization protocol, source-of-truth hierarchy,
benchmark integrity, release governance, final reporting format): @MASTER_DEVELOPMENT_DIRECTIVE.md

## Current state (for a fresh session; update at the end of every DEV)
- Code: `asm_alpha8/` (Python package `asm`). `asm.__version__` is `0.4.0-alpha.7.9`, the official frozen baseline
  (its archive: `asm_alpha8/baseline/ASM_v0.4.0-alpha.7.9.zip`); milestone **M3 — Adaptive Research AI**.
- Versioning (project owner): the last promoted release is **v0.4.0-alpha.7.9**; **alpha 8 = roadmap milestone 0.4.9**,
  not promoted (Structural Transfer & Analogical Procedure Generalization, toward M4); alpha 7.8 delivered 0.4.7 and
  0.4.8 ("Latent Dependency Structure & Higher-Order Epistemic Routing"). DEV steps are experiments inside
  alpha 8 (side tracks), not milestones; none is promoted. The alpha.8.1–8.9 plan and its evidence: `ROADMAP.md`, Stage 4.
- Latest: **DEV24** (three-input transfer across input names, and wrong labels; alpha.8.7/8.4 with 8.3/8.8). G24-A and
  G24-B **passed** on held-out three-input structures; no ASM code changed. Families transfer in all six role orders
  (0.000 → 0.979); a wrong label costs exactly its own attempt, with no wrong answer. Two measured limits: 18 sources
  sharing the 256-proposal family budget reach parameter values −8..5 only; and when several (family, mapping, value)
  candidates fit the three fit points, the first is proposed (18 of 864 failures). The search without families
  solves no three-input target from three fit points.
- The cortex defaults, all by the owner's approval: `family_sharing='round_robin'` (DEV21), `family_scope='any_int'`
  (DEV22) and `family_mapping='rename'` (DEV23; the last two since 2026-11-23).
- Reproducing earlier runs: DEV4's published numbers need `cortex_options={'family_sharing': 'listing'}`; DEV21's
  held-out lab records need `family_mapping='exact'` (`asm_alpha8/benchmarks/dev23_lab_check.py exact`); the other
  committed lab runs reproduce as they are (`asm_alpha8/benchmarks/results/dev23/development/default_flip_check.txt`).
- Records: reports `asm_alpha8/ALPHA8_CODING_DEV*_IMPLEMENTATION.md`; pre-registrations and amendments
  `asm_alpha8/benchmarks/preregistration/`; raw results `asm_alpha8/benchmarks/results/devN/` (hash-chained JSONL; never
  edit); progress page `README.md` from `progress/`.
- Tests: `cd asm_alpha8 && python3 -m pytest -q tests/test_alpha8_*.py` (582 passed, 3 skipped at DEV24). The whole
  `tests/` directory has 57 more failures in v0.2–v0.4 modules that need PyTorch, which is not installed (checked at
  DEV23: the same 57 test IDs as on the DEV22 commit), and `test_v030a7.py`, `test_v030a9.py`, `test_v030a10.py` cannot import.
- Open work:
  - Recommended next (DEV24 report): DEV25, alpha.8.8: screen each family source's parameter range on the first fit
    example before full checks, so budget reach keeps up as sources grow (opt-in, pre-registered). Follow-up
    (alpha.8.3): ask for a disambiguating example when fitting candidates disagree (DEV23's 7 and DEV24's 18 failures).
    Owner's decision: whether to test a noise-tolerant contradiction policy (alpha.8.7).
  - Recommended for the owner's ultra-code session (2026-11-23): the real-bug repair DEV below.
  - DEV16's study needs generated pairs from the owner's PC (`asm_alpha8/tools/generate_pairs.py`, instructions in
    `asm_alpha8/tools/README_DEV16_DATA.md`).
  - The repair workflow on real bugs with fault localization (DEV20 report) on DEV15's 83 BugsInPy bugs
    (`asm_alpha8/benchmarks/dev14_realbugs.py` builds their environments; Python 3.8 is needed).
- Untrusted code and data: clone downloaded repositories into their own new directory, run Python with `-I` when it
  reads them, and run their tests only through ASM's sandboxed `SafeTestRunner`.

## After every DEV step: update the progress to v1.0.0
The repo front page (README.md) shows a progress bar to v1.0.0 and a chart of every DEV's pre-registered gate. Keep it
current at the end of every DEV, in the same commit as the DEV's report:

1. Add the DEV to `progress/progress.json` → `devs`: `dev`, `date`, `title`, `gate` (one short line), `kind`, `promoted`,
   `report` (path to the DEV's report), and the result:
   - `kind: "at_least"` (a gate that needs a count): `needed`, `value_reached`, `of` (the number of problems);
   - `kind: "passed"` or `kind: "not_run"`: a one-line `result`.
2. If the DEV promoted a roadmap milestone, update `roadmap` (`reached_through`, `promoted_in_progress`, `open`,
   `next`, `current`). Nothing counts as reached unless a pre-registered gate on fresh data passed. If it changed the
   evidence for an alpha 8 plan item, update `alpha8_plan` too.
3. Run `python3 progress/make_progress.py`, then `python3 progress/make_progress.py --check` (exit 0 = up to date).
4. Update "Current state" above.
5. Commit `progress/progress.json`, `progress/*.svg`, `README.md` and `CLAUDE.md`.

## Ground rules from the project owner
- Before each task, list your assumptions; if something is unclear, stop and ask.
- Keep code short and clear: if 200 lines could be 50, rewrite them. This applies to new code and to code a task
  touches, with behaviour kept identical and verified; it is not a rewrite pass over existing code.
- ASM itself is not a language model and uses no transformers. Open-source LLMs may only be a source of data fed to ASM.
- Each DEV is pre-registered before its fresh data exists; results are reported in full, including unfavourable ones.
