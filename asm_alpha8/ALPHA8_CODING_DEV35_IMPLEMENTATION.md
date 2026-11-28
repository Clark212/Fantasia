# ASM Alpha 8 DEV35 — Causal Repair by Intervention (development only; implementation report)

Status: **experimental; NOT promoted; no default changed; no fresh run.** Design chosen by the assistant (the project
owner: "do it, I trust you; if we can't, focus on the main roadmap"). In development on 229 seen real bugs, causal repair
by intervention produced **no correct repair beyond what the workflow already makes**. It was therefore not
pre-registered and not run on fresh data, and the work turns to the main roadmap. ASM contains no language model and no
transformer.

## What DEV35 built (`asm/coding/causal.py`, opt-in; nothing calls it by default)
- **Experiments on the buggy program.** While the bug's tests run, the suspect function is instrumented in a throwaway
  copy, and one site at a time is intervened on: each condition is flipped (always, or only while a failing test runs),
  each integer constant is moved by one, each local-variable load is replaced by another local of the same type.
- **One process.** A pytest plugin re-runs the test items in one process (`runtestprotocol`), with a 5 s alarm per
  test so a flipped loop condition cannot hang the run. Tests run through `SafeTestRunner`.
- **Causes become edits.** A cause is an intervention under which the failing tests pass and the passing ones still
  pass. It becomes an edit:
  - a flipped condition: its negation or the complementary comparison;
  - a condition that must differ between failing and passing runs: a guard (`c and not p` / `c or p`) with an atom over
    the recorded locals;
  - a moved constant or a swapped variable.
- On a toy bug it finds both real fixes, a synthesised guard (`n > 3 or n == 3`) and the moved constant (`3 → 2`).

## Development (`benchmarks/dev35_development.py`; `results/dev35/development/causal_on_seen_bugs_*of3.jsonl`)
- **What was run:** DEV32–DEV34's 250 valid bugs. For each, DEV15's localization's top 3 suspects and the functions the
  developer changed were investigated. Each edit was checked as the workflow would: the bug's tests, then the
  project's own suite (DEV33's check).

  | | bugs |
  |---|---|
  | investigated (spectrum available) | 229 |
  | an intervention found a cause | 41 |
  | an edit passes the bug's tests and the project's suite (plausible) | 13 |
  | the edit equals the developer's fix | 1 (mistletoe-2, already repaired by the checked workflow) |

- **Every other plausible edit is wrong**, read against the developer's diff:
  - **one case of two:** bitstring-9, where the developer changed both branches;
  - **the wrong site or element:** parsel-4 uses the last selector instead of all, num2words-2 and pygments-7;
  - **a condition made always true or false:** mdit-py-plugins-1 ignores a custom renderer, w3lib-9, soupsieve-8;
  - **guards keyed to the tests' own data:** inflect-7 (`word == 'pair of scissors'`), jsonpickle-1 (a test class's
    name), pyupgrade-2 (`part == '\N{SNOWMAN}'`), soupsieve-14 (`len(el) == 0`);
  - **pycparser-5:** `1 → 0` in the same assertion as DEV34's wrong patch.
- **The suite check passed 57 of the 170 edits that pass the bug's tests.** Interventions find many edits that the
  project's tests do not cover.
- **Time:** median 16 s per bug. 46 of 821 investigated functions could not be studied, because a failing test passed
  once instrumented (timing- or frame-sensitive tests).

## Why it fails, briefly
The single-site interventions find *a* cause of the test outcome, almost never *the* developer's change. Real fixes in
these bugs are mostly new conditions or code (a new branch, a loop over all elements, a deduplication), which no
single-value intervention expresses. The guard synthesis then fits the tests' data. This matches DEV34's finding: the
fixes ASM cannot make are not near the code it can perturb.

## Validation
- `tests/test_alpha8_*.py` unchanged in behaviour: causal.py is opt-in and not called by the workflow.
- The toy bug (`/scratchpad`, recorded in the commit message) finds both fixes.
- The development records are as described.

## Decision (owner's instruction)
Not run on fresh data; no gate. The project turns to the main roadmap. `ROADMAP.md`: the open item before 0.4.9 can be
promoted is a pre-registered check that the Stage 4 components work together.
