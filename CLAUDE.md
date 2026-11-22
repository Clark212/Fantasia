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
- Latest: **DEV22** (learned families for two-input targets; alpha.8.2/8.5). G22-A **passed** on held-out two-input
  structures: `ProcedureCortex(family_scope='any_int')` (opt-in; making it the default is the owner's decision) lets
  families propose for integer targets with 2–4 inputs, before the affine solve. DEV21 before it: round-robin family
  sharing (`family_sharing='round_robin'`, the default since the owner approved it) removed DEV4's interference.
- Records: reports `asm_alpha8/ALPHA8_CODING_DEV*_IMPLEMENTATION.md`; pre-registrations and amendments
  `asm_alpha8/benchmarks/preregistration/`; raw results `asm_alpha8/benchmarks/results/devN/` (hash-chained JSONL; never
  edit); progress page `README.md` from `progress/`.
- Tests: `cd asm_alpha8 && python3 -m pytest -q tests/test_alpha8_*.py` (567 passed, 3 skipped at DEV22). The whole
  `tests/` directory has 57 more failures in v0.2–v0.4 modules that need PyTorch, which is not installed (checked at
  DEV21: identical without DEV21's changes), and `test_v030a7.py`, `test_v030a9.py`, `test_v030a10.py` cannot import.
- Open work:
  - Owner decision: make `family_scope='any_int'` the default (DEV22 report).
  - Recommended next (DEV22 report): DEV23, alpha.8.3: let a family learned over one set of input names apply to a
    target over another (families need identical input names today; the composer already remaps whole donors).
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
