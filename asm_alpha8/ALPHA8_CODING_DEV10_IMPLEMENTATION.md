# ASM Alpha 8 Coding DEV10 — Semantic Code Intelligence (implementation report)

Status: **experimental; NOT promoted**. Built on `asm_alpha8_dev8_1` (DEV8.1 + DEV9 carried along). All earlier releases preserved.
New: `asm/coding/semantics.py`. Additive: `run_python_worker` in `sandbox.py`; `CodingAgent.semantics()`.

## What it does
Contrasts what code is *called* with what it *does*, from three evidence sources:
1. **Static semantics** (per function): effects (I/O, network, process, randomness, time, env, console/logging, global writes/mutation, self mutation, dynamic exec), parameter mutation with alias tracking, parameter roles/kinds, return behaviour (bool-ness, falls off end, constants), raises/asserts; **propagated through the DEV9 call graph** (transitive effects, "unknown" purity).
2. **Dynamic probing** in the DEV8.1 sandbox (disposable copy, rlimits, scrubbed env, network namespace where available, process-group kill): fixed input batteries, per-call timeouts, observed outputs/exceptions, determinism (second call on fresh copies), argument mutation, printing, files created, module-state changes.
3. **Behavioural fingerprinting** against 121 reference behaviours (add, max, sorted, is_prime, gcd, upper, sort-in-place, ...): "agrees with the reference on every probe input" — identification independent of the name.

Findings: `name_behavior_mismatch`, `likely_bug` (near-miss of the named behaviour, with deviating inputs), `name_implies_pure_but_has_effects`, `predicate_not_boolean`, `name_implies_effect_but_pure` (mutator-named function that neither mutates nor returns), `validator_cannot_fail`, `static_dynamic_disagreement` (static analysis blind spots), and opt-in `name_claim_unverified`.

## Validation actually run
- **Tests:** 45 new; `test_alpha8_*`: **294 passed**, 8 subtests; historical groups identical to the baseline recorded earlier (v01 72 passed; v02 13 failed; v03 3 errors; v04 6 failed; PyTorch absent here).
- **Lying-repo answer key** (my own construction, so circular by itself): 12 expected findings matched as an *exact set* (no extras, none missing), 18 identifications correct (8 with names giving no hint), ~20 negative controls silent, transitive effects through the call graph, un-probed effectful functions never executed.
- **Independent ground truth — Python's stdlib** (functions whose behaviour is known regardless of my code): **44/44** reference-family functions identified; **0 of 47** exact matches outside the acceptable set; **0 of 25** spurious matches on functions with no reference; a control (`list.index`, raises when absent) correctly did not match. Caveat: I chose which families to test, so this is the favourable population.
- **Mutation check:** 21 deliberate defects across the new logic; the first pass caught 18; the survivors exposed 2 weak tests (a secrets test that only checked an output type; no test for minimum evidence size), both fixed and re-verified; a 21st mutant (stub rule) added and caught. **All 21 now caught.**
- **Real code (ASM itself, 2,700 functions, ~130 s, 173 of 241 candidates probed):** static vs runtime cross-check: all 54 statically-pure probed functions behaved purely; the few runtime effects (1 print, 1 global change, 1 nondeterministic function) were all predicted statically. Weak evidence: few effectful functions are probed by design.

## Honest precision on real code (read this)
- First version on ASM: 5 fingerprint identifications (4 correct and meaningful: `_fib`, `_isprime`, and two genuine identity-on-valid-input helpers; **1 accidental**: `outcome_name` matched `first_char` only because the probe fed it strings instead of its real input) and **6 findings, all false positives** (two test-harness `check()` recorders, a functional `update_oracle`, and words like "mod"/"square"/"flip" misread as claims).
- I then fixed rules for principled reasons (side-effecting functions are not no-op validators; the mutator bug is "neither mutates nor returns"; name-claim rule made opt-in; plain `import subprocess` is not import-time risk; stubs/interface methods are not judged by name). A second sweep produced 2 more false positives (interface-stub `reset` methods) → stub rule. **Final ASM sweep: 0 findings.**
- **Consequence:** across all versions the heuristic finding classes produced **0 true positives out of 8 findings on real code**, and no real name/behaviour lie was found in ASM (there may be none). Because rules were adjusted after seeing this sample, ASM is *not* an unbiased evaluation of the final rules, and recall on real-world lying names is **unmeasured**.

## Bugs found by my own tests during this work (all fixed, all covered)
Probe worker called an undefined variable (nothing was probed); `add_numbers` flagged as a "mutator that does nothing" (ambiguous verbs `add/set/update` now need a container-like first parameter); `list[int]` annotation classified as int; import-time risk gate was too coarse; probe results collided when two specs shared a function name; `float(x)` matched `identity` (identity is now type-strict); determinism test wrongly included genuinely random functions.

## Limits — read before relying on this
- **Finite evidence.** A fingerprint match means "equal on every probe input", not equivalence. The reference library (121 behaviours) only identifies what it covers; unlisted behaviour is simply unidentified.
- **Probe typing is heuristic.** Wrong input types give accidental matches or none (`outcome_name`). Dict-typed parameters and arity > 2 are not probed.
- **Not probed:** methods, async functions, generators, decorated functions, `*args/**kwargs` signatures, and (by default) functions with statically detected I/O-write/network/process/dynamic-exec effects, so those are judged statically only.
- **Probing executes repository code** (module import runs top-level code). Mitigations: disposable copy, rlimits, scrubbed env, throwaway cwd, network namespace when available, kill-on-timeout, skip of modules that *call* risky APIs at import time. This is **not an OS security boundary**; use a container/VM for untrusted code.
- **Name rules are English-verb heuristics** and noisy (see above). Static analysis is intraprocedural for mutation: mutation of a caller's argument by a callee is not tracked.
- **Cost:** ~130 s for 241 probe candidates on a 2,700-function repo (import-heavy); a budget leaves some functions `probe_incomplete`.
- No benchmark of downstream usefulness; no claim of "understanding" beyond effect analysis plus behavioural fingerprinting; no consciousness-related claim — everything is deterministic parsing, sandboxed execution and table lookup.

## Promotion gate for DEV10
(1) At least 3 foreign repositories with hand-labelled precision (>=50 findings per class); (2) **recall by injection**: plant known name/behaviour lies (operator swaps, off-by-one, hidden mutation) into foreign functions and measure detection, with separate numbers for in-library and out-of-library behaviours; (3) library-coverage measurement on foreign code (what fraction of pure small functions is identifiable at all); (4) timing and memory on a 10x larger repo; (5) demonstrated downstream value (e.g. DEV13 using `likely_bug` deviations to localise a seeded fault); (6) human review of the sandbox in a real container.
