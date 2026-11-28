# ASM Alpha 8 DEV28 — Tolerating One Contradicting Label (implementation report)

Status: **experimental; NOT promoted; no default changed** (pre-registered; testing approved by the owner as an opt-in
experiment). **The gate G28-A passed** on held-out three-input structures. Alpha 8 (= milestone 0.4.9) plan item:
alpha.8.7 (adversarial generalization hardening). ASM contains no language model and no transformer.

## Headline (read this first)
- **What DEV28 tests.** Under the strict policy one wrong label suspends a hypothesis, so DEV24 found that a wrong label
  costs its whole attempt. `contradiction_policy='tolerant'` (opt-in) lets a hypothesis stand with one contradicting
  label in total, counting fit and validation together, beside at least 4 agreeing labels. Its parameter solving votes,
  so one wrong label cannot decide a value. Targets and donors get 5 fit and 10 validation labels.
- **Result: G28-A passed.** On three three-input structures no run had used (216 attempts per arm):

  | arm | strict (the default) | tolerant |
  |---|---|---|
  | each label wrong with probability 0.05 | 0.102 | **0.579** |
  | each label wrong with probability 0.10 | 0.009 | **0.181** |
  | at 0.10, with unrelated donors too | 0.014 | **0.143** |
  | clean relevant and mixed arms (648) | 0.999 (65 evaluator calls) | 0.986 (102) |
  | none / unrelated / shuffled labels | 0 / 0 / 0 | 0 / 0 / 0 |
  | wrong answers (9,048 answers given) | 0 | 0 |

  Paired, noisy arms: 168 attempts succeed only with tolerance, none only without (p = 2.7 × 10⁻⁵¹).
- **The price.** On clean data, 8 of 648 attempts lost: a wrong family or mapping agreed with 4 of the 5 fit labels,
  was proposed, and clean validation suspended it, with no answer. Tolerance also costs 1.6× the evaluator calls on
  clean data.
- **The limit.** Tolerance covers one wrong label per hypothesis. A target with two or more wrong labels never
  succeeded (0 of 146), and a donor with two never becomes active, so at 10% noise most attempts still fail.
- **What it means.** One wrong label no longer costs a transfer, with no wrong answer and no false transfer. That is a
  real but bounded robustness; the default stays strict.

## What DEV28 added
| piece | code |
|---|---|
| policy | `asm/procedure_cortex.py`: `ProcedureCortex(contradiction_policy='strict'|'tolerant')`, default `'strict'` (unchanged). `_tolerates(mismatches, agreeing)`: never with `'strict'`; with `'tolerant'`, one mismatch beside at least `TOLERATED_AGREEMENT` = 4 agreeing labels |
| where it applies | `propose`: its training check, recording the contradiction on the version. `observe`: one contradiction in total is kept, with an audit event `tolerated_contradiction`; a second suspends or makes suspicious, as the first does when strict. Also the 2–4-input family step of `induce` |
| voting solver | `_solve_tolerant`: each example (or pair) votes for the value it determines until one has as many votes as n + 1 consistent examples give it. It must then agree with all examples but one and be identified (no neighbouring value agrees as often) |
| harness | `benchmarks/dev28_transfer.py`: three-input protocol with 5 fit and 10 validation labels, noise arms at 0.05 and 0.10 (paired corruption), gate G28-A |
| tests | `tests/test_alpha8_dev28.py` (6) |

With the default, ASM behaves exactly as before: all eight committed DEV21–DEV24 lab runs reproduce every record
(`benchmarks/results/dev28/development/lab_check_strict.txt`). The other searches of `induce` and the one-input path
stay strict in both modes.

## Development (development structures only)
x·(y + c) + z and x·x·y − z + c (`benchmarks/results/dev28/development/`):
- **Wrong labels:** at 0.05, 0.118 → 0.597; at 0.10, 0.007 → 0.146; mixed at 0.10, 0.000 → 0.090. 102 vs 0 paired.
- **Clean arms:** 0.998 → 0.993; no wrong answer.

The first solver scored a solution from every example on all examples, at 4.3× strict's evaluator calls on clean
arms, which C5 rejected. Voting with early stopping gave the same successes at 1.5×. This change was made before the
pre-registration.

## Pre-registered held-out test — G28-A passed
`benchmarks/results/dev28/transfer.jsonl` (pre-registration `431575f`, before any held-out attempt; 3,888 attempts,
76 s; no amendment).

| check | rule | observed | |
|---|---|---|---|
| C1 noise gain | noisy arms: tolerant − strict ≥ 0.15, paired p < 0.01 | 0.301 − 0.042 = 0.259; 168 vs 0, p = 2.7 × 10⁻⁵¹ | ✓ |
| C2 no clean loss | clean relevant: strict − tolerant ≤ 0.02 | 0.999 − 0.986 = 0.013 | ✓ |
| C3 no false transfer | unrelated ≤ none + 0.05; shuffled ≤ 0.05 | 0 = 0; 0 | ✓ |
| C4 safety | wrong per query ≤ 0.02 every cell; tolerant ≤ strict + 0.005 | no wrong answer | ✓ |
| C5 cost | clean relevant calls, tolerant / strict ≤ 3.0 | 101.5 / 65.1 = 1.56 | ✓ |

- **Per structure** (noisy arms, strict → tolerant): y·(x + c) − z 0.028 → 0.301; z·z + x·(y − c) 0.042 → 0.329;
  (x − y)·(z + c) 0.056 → 0.273.
- **Under noise, by the target's wrong labels** (tolerant):
  - at 0.05: 125 of 168 attempts with at most one wrong target label succeed, and 0 of 48 with two or more;
  - at 0.10: 39 of 118, and 0 of 98.

  The rest of the shortfall is donors with two wrong labels, which never activate.
- **The 8 clean losses** (6 mixed_r0, 2 relevant_r5) were each a wrong family or mapping agreeing with 4 of 5 fit
  labels. It was proposed, clean validation suspended it, and no answer was given.

## Validation
- **`tests/test_alpha8_dev28.py`, 6 tests:**
  - the default and an unknown value;
  - `_tolerates`;
  - `propose` with one wrong fit label (strict rejects, tolerant proposes and records it);
  - validation keeps one contradiction in total and suspends at the second (strict suspends at the first);
  - solving outvotes one wrong label, where strict trusts the first;
  - a noisy transfer that strict loses and tolerance wins without a wrong answer.
- **Full `test_alpha8_*`:** 605 passed, 3 skipped, 0 failed (599 before, plus 6).
- **`benchmarks/lab_check.py <dir> family_mapping=exact`** reproduces all 38,224 committed lab records on the default.

## Limitations
- **A lab with symmetric noise:** independent offsets of ±1..3 at one of two rates. Adversarial or systematic errors
  were not tested.
- **One wrong label per hypothesis.** Two or more are not tolerated, so at 10% noise most attempts still fail. A rule
  with a tolerance proportional to the evidence would need its own pre-registered test.
- **Narrow scope.** Tolerance covers `propose`, `observe`, and the family step and solving of the 2–4-input path. The
  other searches of `induce` and the one-input path stay strict.
- **Tolerated false fits.** With one mismatch allowed, a wrong hypothesis agreeing with 4 of 5 fit labels can be
  proposed first. Validation catches it, but the attempt is lost (8 of 648 clean attempts).

## What this means, and what is next
DEV28 shows that ASM's evidence rules can be made robust to an isolated wrong label without a single wrong answer, in a
lab. The default stays strict.
- **Owner's decision:** whether to use `'tolerant'` anywhere by default. It is a safety-critical policy, and this is
  one experiment.
- **Next, DEV29:** real-bug repair with fault localization on DEV15's BugsInPy bugs, leaving the lab.

Consciousness-related architecture: not touched.
