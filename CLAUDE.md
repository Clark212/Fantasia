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
- Latest: **DEV32** (a guard against test-copied patches, on 143 freshly mined real bugs; alpha.8.4 and alpha.8.1/8.2
  on real data). G32-A and G32-B **not passed**.
  - **The change:** `RepairWorkflow(test_copy_guard=True)`, opt-in, drops phase-3 candidates that write a whole failing-test
    string into the code (`asm.coding.content.copied_test_strings`; name-like strings and error/log messages allowed).
    The miner `asm_alpha8/benchmarks/dev32_mine_bugs.py` builds BugsInPy-format bugs from any project's history
    (Python 3.11 environments).
  - **The result:** 143 valid bugs from 16 projects (sqlglot, astroid, rich, loguru, soupsieve, ...).
    - **Learned knowledge** repaired 2 correctly that the control did not, even at 300 s (astroid-4, identical to the
      developer's fix; sqlglot-14, equivalent). That is the count G31-A needed, a first on fresh bugs.
    - **It also added 2 wrong patches** (autoflake-2, marko-4), one over the limit, so G32-B is not passed.
    - **The guard** stopped DEV31's two test-copied patches on seen bugs. On the fresh bugs no accepted patch copied a
      test string, so it stopped nothing (G32-A not passed). It flags 1 of 143 developer fixes.
    - **The control's own patches** are 8 of 10 wrong: the bugs' tests are weak acceptance checks.
  - **Running real-bug shards:**
    - They must be detached (`setsid`).
    - **Keep a background task running the whole time:** with none, the idle session's container is reclaimed and the
      shards die (three restarts in DEV32).
    - `evaluate --resume` finishes a stopped run.
- **DEV31** (G31-A not passed): `RepairWorkflow(phase3_seconds=150)`, opt-in, gives learned knowledge 150 s of its own;
  exact speedups build learned candidates up to 160x faster. On 75 fresh BugsInPy bugs it repaired none the control
  does not (Phase 3 tested a median of 89 candidates in 44 bugs). black: the tracer times out on 14 of its 19 bugs.
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
- Tests: `cd asm_alpha8 && python3 -m pytest -q tests/test_alpha8_*.py` (627 passed, 3 skipped at DEV32). The whole
  `tests/` directory has 57 more failures in v0.2–v0.4 modules that need PyTorch, which is not installed (checked at
  DEV23: the same 57 test IDs as on the DEV22 commit), and `test_v030a7.py`, `test_v030a9.py`, `test_v030a10.py` cannot import.
- Open work:
  - Owner decisions:
    - make `family_parameters='solve'`, `family_ambiguity='ask'` and `family_memory='index'` the defaults (DEV25–DEV27;
      see DEV30's ablation);
    - whether to use `contradiction_policy='tolerant'` anywhere (DEV28, DEV30);
    - whether DEV29 and DEV30 support any promotion. M4 also needs real data, where DEV29, DEV31 and DEV32 fell short;
    - whether to keep `phase3_seconds` and `test_copy_guard` (both opt-in, free when off);
    - whether DEV32's 2 learned-only correct repairs change the M4 picture (its gate failed on safety).
  - Recommended next DEVs (DEV32 report): a stronger acceptance check for every arm (more of the project's own tests than
    the bug's, probes for value changes); localization that scales to large test suites (18 fresh bugs and black time
    out); learned knowledge from the fresh projects' own histories.
  - Roadmap: the owner's DEV8–DEV40 list is a long-range map in `ROADMAP.md`, merged so the final DEV is DEV36 (DEV33
    experimental design and causal reasoning; DEV34 meta-learning; DEV35 integration; DEV36 closure). The repository's
    DEV numbers stay as they are.
  - DEV16's study needs generated pairs from the owner's PC (`asm_alpha8/tools/generate_pairs.py`, instructions in
    `asm_alpha8/tools/README_DEV16_DATA.md`).
  - Real-bug environments: `asm_alpha8/benchmarks/dev14_realbugs.py` builds them (Python 3.8:
    `/root/.local/bin/python3.8` via uv; DEV32's with `--python=/usr/bin/python3.11`);
    `asm_alpha8/benchmarks/dev32_realbugs.py` evaluates the arms.
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
