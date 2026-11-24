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
- Latest: **DEV31** (phase 3 on its own clock, on fresh real bugs; alpha.8.8 and alpha.8.1/8.2 on real data). G31-A
  **not passed**.
  - **The change:** `RepairWorkflow(phase3_seconds=150)`, opt-in, gives learned knowledge 150 s of its own after phases
    1-2. Exact speedups build learned candidates up to 160x faster with identical candidates (55 real functions, 4,400
    candidates).
  - **The result:** on 75 fresh BugsInPy bugs (scrapy 33, black 19, fastapi 15, tornado 6, sanic 2; luigi and ansible
    gave none), learned knowledge repaired 0 bugs the workflow without it does not; 2 were needed. Phase 3 tested a
    median of 89 candidates in each of 44 bugs and accepted nothing. Time was not the limit.
  - **Development** (DEV15's bugs): learned shapes wrote a failing test's expected value into the code (2 wrong
    patches); there is no guard yet.
  - **black:** DEV15's tracer times out on its test suite, so 14 of its 19 bugs have no spectrum.
  - **Running real-bug shards:** they must be detached (`setsid`); a launcher stopped at its time limit takes its
    children with it (`evaluate --resume` finishes a stopped run).
- The owner-approved plan of 2026-11-23 (DEV25–DEV30) is done; nothing is promoted.
  - **DEV30** (an M4-candidate battery of the whole transfer stack; alpha.8.9 candidate, lab only): G30-A **passed**.
    The four opt-in mechanisms together (`family_parameters='solve'`, `family_ambiguity='ask'`, `family_memory='index'`,
    `contradiction_policy='tolerant'`) against today's defaults, under every lab condition at once, on six held-out
    structures: 0.324 → 0.889 over all transfer conditions, no false transfer, no wrong answer. Tolerance loses 7 of 288
    degenerate fits. In the exploratory ablation, solve + ask + index with the strict policy reach 1.000 on every clean
    condition.
  - **DEV29** (DEV20's learned libraries in the repair workflow's phase 3, on DEV15's 83 real bugs): G29-A **not
    passed**. 1 bug was repaired correctly only with learned knowledge (thefuck-19, identical to the developer's fix);
    2 were needed. There was no loss and no extra wrong patch. Phase 3 is reached in 37 bugs and runs out of time in
    30. On youtube-dl, building learned candidates outlasts the budget, which is checked only between candidates.
  - **The DEV29 bug.** The first run crashed on an ASM bug (`FailureAnalyzer` and output that begins with an exception
    name without a message). It was fixed under rule R3, and the run is kept unused in
    `asm_alpha8/benchmarks/results/dev29/discarded_run1/`. Workflow runs have a wall-clock budget: run nothing else on
    the machine while real-bug shards run.
  - DEV25–DEV28, each opt-in and each gate passed: `family_parameters='solve'`, `family_ambiguity='ask'`,
    `family_memory='index'`, `contradiction_policy='tolerant'` (approved for testing only).
- The cortex defaults, all by the owner's approval: `family_sharing='round_robin'` (DEV21), `family_scope='any_int'`
  (DEV22) and `family_mapping='rename'` (DEV23; the last two since 2026-11-23).
- Reproducing earlier runs: DEV4's published numbers need `cortex_options={'family_sharing': 'listing'}`; DEV21's
  held-out lab records need `family_mapping='exact'` (`asm_alpha8/benchmarks/dev23_lab_check.py exact`); the other
  committed lab runs reproduce as they are (`asm_alpha8/benchmarks/results/dev23/development/default_flip_check.txt`).
  `asm_alpha8/benchmarks/lab_check.py <dir> family_mapping=exact` re-runs all eight DEV21–DEV24 lab runs and compares.
- Records: reports `asm_alpha8/ALPHA8_CODING_DEV*_IMPLEMENTATION.md`; pre-registrations and amendments
  `asm_alpha8/benchmarks/preregistration/`; raw results `asm_alpha8/benchmarks/results/devN/` (hash-chained JSONL; never
  edit); progress page `README.md` from `progress/`.
- Tests: `cd asm_alpha8 && python3 -m pytest -q tests/test_alpha8_*.py` (617 passed, 3 skipped at DEV31). The whole
  `tests/` directory has 57 more failures in v0.2–v0.4 modules that need PyTorch, which is not installed (checked at
  DEV23: the same 57 test IDs as on the DEV22 commit), and `test_v030a7.py`, `test_v030a9.py`, `test_v030a10.py` cannot import.
- Open work:
  - Owner decisions:
    - make `family_parameters='solve'`, `family_ambiguity='ask'` and `family_memory='index'` the defaults (DEV25–DEV27;
      see DEV30's ablation);
    - whether to use `contradiction_policy='tolerant'` anywhere (DEV28, DEV30);
    - whether DEV29 and DEV30 support any promotion. M4 also needs real data, where DEV29 fell short.
  - Recommended next DEVs (DEV31 report): a guard against copying a failing test's expected value into the code; learned
    knowledge from the fresh projects' own histories; localization that scales to large test suites (black).
  - Owner decision: whether to keep `phase3_seconds` (opt-in) at all; the speedups are exact and free when it is off.
  - DEV16's study needs generated pairs from the owner's PC (`asm_alpha8/tools/generate_pairs.py`, instructions in
    `asm_alpha8/tools/README_DEV16_DATA.md`).
  - Real-bug environments: `asm_alpha8/benchmarks/dev14_realbugs.py` builds them (Python 3.8:
    `/root/.local/bin/python3.8` via uv); `asm_alpha8/benchmarks/dev29_realbugs.py` evaluates both arms.
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
