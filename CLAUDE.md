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
- Latest: **DEV35** (causal repair by intervention, `asm/coding/causal.py`, opt-in; development only, no gate). While
  the bug's tests run, ASM flips conditions, moves constants and swaps locals one site at a time (one pytest process,
  5 s per test), and turns causes into edits. On 229 seen bugs: a cause in 41, 13 plausible edits, 1 equal to the
  developer's fix (mistletoe-2, already repaired by the workflow); every other plausible edit is wrong. Not run fresh.
  **The owner's instruction (2026-11-28): if the DEV route cannot pass M4's real-data gate, focus on the main roadmap.**
  The next step there is the 0.4.9 closure check (`ROADMAP.md`, Stage 4: a pre-registered check that the Stage 4
  components work together).
- **Main route, step 1 done (2026-11-28): the frozen baseline reproduces**
  (`asm_alpha8/benchmarks/results/mainroute/BASELINE_REPRODUCTION.md`).
  - With CPU PyTorch installed (`pip install torch --index-url https://download.pytorch.org/whl/cpu`), the historical
    tests pass exactly as alpha 7.9's release notes say: 470 passed, 1 skipped.
  - Release gate (`run_release_checks.py`, run from a scratch copy, since it writes into `results/`): the frozen archive
    passes 48 of 55 jobs, today's code 41.
    - The 7 jobs failing in both are stale version pins (planning alpha 1-4, abstraction, alpha12), a temp file, and a
      runner bug at the end.
    - The 7 failing only today are the alpha 7.2-7.4 procedure benchmarks. Their cause is DEV3.3's owner-approved
      `extrapolation_guard='abstain'`; they pass with it off (`asm_alpha8/tools/with_cortex_options.py
      extrapolation_guard=off <script>`).
  - No Stage 4 planning capability was lost.
  - The release gate is refreshed (owner-approved 2026-11-28): today's code passes 56 of 56 (`release_checks_refreshed.json`).
- **DEV34** (project adaptation in development; the M4 real-data gate again with the fixed check, on 59 fresh
  real bugs). G34-A **not passed**.
  - **The changes:** DEV33's check fixed. Its suite runs get at most the remaining time, and test ids are compared
    without memory addresses (`faultloc._stable_id`; `tests/test_alpha8_dev34.py`). `dev17_mine_history.examples(repo,
    name, rev=...)` mines a project's fixes reachable from a revision.
  - **Development (191 seen bugs, 149 measurable):** learning a project's own earlier fixes into DEV20's libraries
    reproduced the developer's fix in 2 bugs, the same as without it. With the bug's own fix leaked in and no candidate
    cap, 11 of 16: ASM can represent most fixes once seen, but they rarely recur. Adaptation was not run fresh.
  - **The result** (16 new projects; 103 bugs mined, 59 valid): 0 learned-only correct repairs (2 needed). The one
    accepted patch (pycparser-5, both arms) is wrong. The check held the clock (max 304 s) and rejected no developer
    fix.
  - **The M4 real-data gate has failed five times** (DEV29, DEV31-DEV34: 1, 0, 2 with too many wrong, 1, 0).
  - **Running real-bug shards:** detach them (`setsid`); **keep a background task running the whole time** (an idle
    session's container is reclaimed and the shards die; a background task stops at 2 hours, so start another);
    `evaluate --resume` finishes a stopped run.
- **DEV33** (G33-A passed, G33-B not): `RepairWorkflow(regression_suite=[...])`, opt-in. A patch must also keep passing
  the project's own suite (`benchmarks/dev33_development.py: project_suite`). On 48 fresh bugs it halved learned
  knowledge's wrong patches (4 → 2), kept its correct repairs, and rejected 1 of 48 developer fixes.
- **DEV32** (G32-A and G32-B not passed): `RepairWorkflow(test_copy_guard=True)`, opt-in, drops phase-3 candidates that
  copy a whole failing-test string into the code. On 143 fresh bugs it stopped nothing. Learned knowledge repaired 2
  correctly (astroid-4, sqlglot-14) but added 2 wrong patches; the control's patches were 8 of 10 wrong. The miner
  `asm_alpha8/benchmarks/dev32_mine_bugs.py` builds BugsInPy-format bugs from any project's history.
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
- Reproducing earlier runs: the alpha 7.2-7.4 procedure benchmarks need `extrapolation_guard='off'` (see above); DEV4's published numbers need `cortex_options={'family_sharing': 'listing'}`; DEV21's
  held-out lab records need `family_mapping='exact'` (`asm_alpha8/benchmarks/dev23_lab_check.py exact`); the other
  committed lab runs reproduce as they are (`asm_alpha8/benchmarks/results/dev23/development/default_flip_check.txt`).
  `asm_alpha8/benchmarks/lab_check.py <dir> family_mapping=exact` re-runs all eight DEV21–DEV24 lab runs and compares.
- Records: reports `asm_alpha8/ALPHA8_CODING_DEV*_IMPLEMENTATION.md`; pre-registrations and amendments
  `asm_alpha8/benchmarks/preregistration/`; raw results `asm_alpha8/benchmarks/results/devN/` (hash-chained JSONL; never
  edit); progress page `README.md` from `progress/`.
- Tests: `cd asm_alpha8 && python3 -m pytest -q tests/test_alpha8_*.py` (634 passed, 3 skipped at DEV34). The rest of
  `tests/` needs PyTorch (not installed by default in a fresh container; CPU wheel from download.pytorch.org): with it,
  470 passed, 1 skipped (2026-11-28); without it, 57 fail and three modules cannot import.
- Open work:
  - Owner decisions:
    - make `family_parameters='solve'`, `family_ambiguity='ask'` and `family_memory='index'` the defaults (DEV25–DEV27;
      see DEV30's ablation);
    - whether to use `contradiction_policy='tolerant'` anywhere (DEV28, DEV30);
    - whether DEV29 and DEV30 support any promotion. M4 also needs real data, where DEV29 and DEV31-DEV34 fell short;
    - whether to keep repeating the M4 real-data gate or redesign it (DEV34 report);
    - whether to keep `phase3_seconds`, `test_copy_guard` and `regression_suite` (all opt-in, free when off), and
      whether `regression_suite` should become the default for real-bug repair (DEV33 G33-A);
    - whether G33-A counts as alpha.8.4 evidence on real data (`alpha8_plan.validated` was not changed).
  - Next (owner, 2026-11-28): the main roadmap, starting with the 0.4.9 closure check. The DEV coding track has tried
    learned knowledge (DEV29, DEV31-DEV34) and causal intervention (DEV35) on real bugs without passing M4's gate.
  - Roadmap: the owner's DEV8–DEV40 list is a long-range map in `ROADMAP.md`, merged so the final DEV is DEV36 (DEV33
    and DEV34 spent on the M4 real-data gate, DEV34 also on adaptation; DEV35 causal reasoning with integration; DEV36
    closure). The repository's DEV numbers stay as they are. The owner said "U pick" for DEV33 and "I trust you" for
    DEV34 (2026-11-27).
  - DEV16's study needs generated pairs from the owner's PC (`asm_alpha8/tools/generate_pairs.py`, instructions in
    `asm_alpha8/tools/README_DEV16_DATA.md`).
  - Real-bug environments: `asm_alpha8/benchmarks/dev14_realbugs.py` builds them (Python 3.8:
    `/root/.local/bin/python3.8` via uv; DEV32's with `--python=/usr/bin/python3.11`);
    `asm_alpha8/benchmarks/dev34_realbugs.py` evaluates the checked arms (DEV33's four: `dev33_realbugs.py`).
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
