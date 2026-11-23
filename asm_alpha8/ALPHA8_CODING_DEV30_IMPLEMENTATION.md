# ASM Alpha 8 DEV30 — An M4-Candidate Battery of the Whole Transfer Stack (implementation report)

Status: **experimental; NOT promoted; no default changed; no ASM code changed** (pre-registered). **The gate G30-A
passed** on six held-out structures. Alpha 8 (= milestone 0.4.9) plan item: alpha.8.9 (M4 stage-closure candidate), with
alpha.8.5. ASM contains no language model and no transformer.

## Headline (read this first)
- **What DEV30 tests.** DEV21–DEV28 each tested one transfer mechanism in one condition. DEV30 runs every opt-in
  mechanism of DEV25–DEV28 together:
  - solved parameters (`family_parameters='solve'`);
  - a question when fitting candidates disagree (`family_ambiguity='ask'`);
  - the family index (`family_memory='index'`);
  - one tolerated wrong label (`contradiction_policy='tolerant'`).

  This stack runs against today's defaults, under every condition so far, on structures no run had used: three with two
  inputs, three with three.
- **Result: G30-A passed, all five checks.** 5,472 paired attempts:

  | condition (attempts per configuration) | defaults | stack |
  |---|---|---|
  | relevant donors (288) | 1.000 (43 evaluator calls) | 1.000 (48) |
  | constants beyond −8..8 (216) | 0.000 | **1.000** |
  | ambiguous fits, points from {0,1,2}ⁿ (288) | 0.997 | 0.976 (0.05 questions per attempt) |
  | 60 background procedures (288) | 0.000 | **1.000** |
  | the same, after closing and reopening (288) | 0.000 | **1.000** |
  | each label wrong with probability 0.05 (288) | 0.111 | **0.573** |
  | all of these at once (216) | 0.000 | **0.639** |
  | all transfer conditions (1,872) | 0.324 | **0.889** |
  | none / unrelated / shuffled labels | 0 / 0 / 0 | 0 / 0 / 0 |
  | wrong answers (13,626 answers given) | 0 | 0 |

  Paired over all transfer conditions: 1,064 attempts succeed only with the stack and 7 only with the defaults
  (p = 1.3 × 10⁻³⁰⁵).
- **The price.** On ambiguous fits the stack loses 7 attempts that the defaults win. They are all one case. In each, x = 0 at
  four of the five fit points, so only the fifth point tells the hypotheses apart. Tolerance then counted that point as
  the one wrong label: a wrong hypothesis agreeing with the other four was proposed, validation suspended it, and no
  answer was given. With the strict policy, the same stack wins all 7.
- **A correction.** The pre-registration attributed development's one loss to DEV26's known limit, an undetermined
  parameter. Diagnosis shows the same tolerated false fit (below).
- **Under wrong labels, each configuration does exactly what its rule says:**
  - with wrong labels alone (the noisy condition), the defaults succeed exactly when all 45 labels of the target and
    both donors are clean (32 of 32; 0 of 256 others);
  - the stack succeeds exactly when no hypothesis has more than one wrong label: noisy 165 of 165 (0 of 123 others),
    combined 138 of 138 (0 of 78 others).

  At 5% that is 0.95⁴⁵ ≈ 0.10 against (0.95¹⁵ + 15 · 0.05 · 0.95¹⁴)³ ≈ 0.57, as observed.
- **What it means.** In the lab, the four mechanisms work as one system. Every condition passes its bar at once, on
  fresh structures, with no false transfer and no wrong answer. This is the alpha.8.9 candidate evidence from the lab.
  It is not evidence on real data: DEV29 measures that separately.

## What DEV30 ran (no ASM code changes)
| piece | file |
|---|---|
| harness | `benchmarks/dev30_battery.py`: the two configurations paired on every attempt, ten conditions, gate G30-A |
| held-out run | `benchmarks/results/dev30/battery.jsonl` (+ `battery_summary.txt`) |
| development run | `benchmarks/results/dev30/development/battery_dev.jsonl` |
| exploratory ablation (after the held-out test) | `benchmarks/dev30_ablation.py` → `benchmarks/results/dev30/exploratory/ablation.jsonl` |
| exploratory analysis (after the held-out test) | `benchmarks/dev30_analysis.py`: `losses` → `exploratory/losses.jsonl`; `noise` → `exploratory/noise_by_wrong_labels.txt` |
| tests | `tests/test_alpha8_dev30.py` (3) |

ASM's code is the code of DEV28. The held-out manifest's `asm_procedure_cortex_sha256` and `asm_coding_sha256` are
those of DEV28's run, and `git diff 4fae7f6 HEAD -- asm_alpha8/asm` is empty.

The protocol for every target and donor:
- 5 fit labels, 10 validation labels, one `induce` (budget 512);
- the oracle answers at most 2 questions;
- success: 6 queries inside the evidence range, all answered and all correct.

Relevant donors are two donors of the target's structure over (u, v[, w]), in a role order drawn per attempt from all n!
orders.

## Development (development data only)
Development structures: x·(y + c) + y, x·(y + c) + z and x·x·y − z + c. Development used a development unrelated set and
DEV27's development memory (seed 1), seed 30001.
- **Transfer conditions:** 0.308 → 0.889 (545 vs 1 paired), no wrong answer, controls 0. Per condition: see the
  pre-registration.
- **Changes after looking at development results:**
  - B5 (cost) was added.
  - The static checks found that the held-out unrelated sets formed only one family each. The set that had been run
    became the development set, and a new held-out set forming two families per arity was written.

## Pre-registered held-out test — G30-A passed
`benchmarks/results/dev30/battery.jsonl`. The pre-registration was committed as `f3ec692` (SHA-256 `c8525b25…`, recorded
in the manifest) before any held-out attempt. The run: 5,472 attempts in 290 s, no amendment.

| check | rule | observed | |
|---|---|---|---|
| B1 transfer everywhere | stack ≥ 0.90 on relevant, far, ambiguous, memory, restart; ≥ 0.40 on noisy and combined | 1.000, 1.000, 0.976, 1.000, 1.000; 0.573, 0.639 | ✓ |
| B2 gain over the defaults | stack − defaults ≥ 0.30 over all transfer conditions, paired p < 0.01 | 0.889 − 0.324 = 0.565; 1,064 vs 7, p = 1.3 × 10⁻³⁰⁵ | ✓ |
| B3 no false transfer | ≤ 0.05 on none, unrelated, shuffled, both configurations | 0 in all six cells | ✓ |
| B4 safety | wrong per query ≤ 0.02 every cell; stack ≤ defaults + 0.005 every condition | no wrong answer | ✓ |
| B5 cost | relevant evaluator calls, stack / defaults ≤ 1.5 | 48.4 / 43.4 = 1.12 | ✓ |

### Reported, not gated
- **By arity** (all transfer conditions): two inputs 0.324 → 0.887, three inputs 0.325 → 0.891.
- **By structure** (defaults → stack):

  | structure | relevant | far | ambiguous | memory | restart | noisy | combined |
  |---|---|---|---|---|---|---|---|
  | x·y·y − c·x | 1.00 → 1.00 | 0 → 1.00 | 1.00 → 1.00 | 0 → 1.00 | 0 → 1.00 | 0.17 → 0.56 | 0 → 0.44 |
  | (y − c)·x + y | 1.00 → 1.00 | 0 → 1.00 | 1.00 → 1.00 | 0 → 1.00 | 0 → 1.00 | 0.08 → 0.58 | 0 → 0.61 |
  | x·x + y·(x + c) | 1.00 → 1.00 | 0 → 1.00 | 1.00 → 1.00 | 0 → 1.00 | 0 → 1.00 | 0.06 → 0.54 | 0 → 0.75 |
  | x·(y + z + c) | 1.00 → 1.00 | 0 → 1.00 | 1.00 → 0.94 | 0 → 1.00 | 0 → 1.00 | 0.17 → 0.67 | 0 → 0.67 |
  | y·y − x·(z + c) | 1.00 → 1.00 | 0 → 1.00 | 1.00 → 0.92 | 0 → 1.00 | 0 → 1.00 | 0.08 → 0.56 | 0 → 0.75 |
  | (z − c)·(x + 2y) | 1.00 → 1.00 | 0 → 1.00 | 0.98 → 1.00 | 0 → 1.00 | 0 → 1.00 | 0.10 → 0.52 | 0 → 0.61 |

- **Questions** (stack; the defaults never ask):
  - ambiguous: 14 questions in 13 attempts;
  - memory and restart: 27 questions in 26 attempts. Relevant donors alone never led to a question, so the disagreeing
    candidates come with the background memory.
  - combined: 5 questions in 5 attempts.

  Every attempt that asked succeeded. The controls asked in 5 attempts (6 questions), none succeeded.
- **Evaluator calls** (mean per attempt, defaults → stack):

  | condition | defaults | stack |
  |---|---|---|
  | relevant | 43 | 48 |
  | far | 2,287 | 48 |
  | ambiguous | 62 | 62 |
  | memory | 1,534 | 439 |
  | restart | 1,530 | 438 |
  | noisy | 2,068 | 839 |
  | combined | 1,539 | 870 |
  | all transfer | 1,247 | 387 |
  | none | 2,500 | 2,500 |
  | unrelated | 1,998 | 2,214 |
  | shuffled | 2,281 | 2,377 |

  Where the defaults fail, they exhaust the search; the stack finds a candidate early. On controls, the stack's extra
  candidates cost up to 11% more.
- **Under wrong labels** (noisy and combined). `benchmarks/dev30_analysis.py noise` replays the harness's noise
  generator, which draws the same sequence whatever the label values:

  | wrong labels among the 45 (target 15, two donors 15 each) | noisy: defaults | noisy: stack | combined: defaults | combined: stack |
  |---|---|---|---|---|
  | none | 32 of 32 | 32 of 32 | 0 of 20 | 20 of 20 |
  | some, but at most 1 per hypothesis | 0 of 133 | **133 of 133** | 0 of 118 | **118 of 118** |
  | 2 or more in the target | 0 of 50 | 0 of 50 | 0 of 31 | 0 of 31 |
  | 2 or more in a donor (target ≤ 1) | 0 of 73 | 0 of 73 | 0 of 47 | 0 of 47 |

  In combined, the defaults also fail clean attempts, because far constants and the background memory are out of
  their reach. The stack's other attempts under noise were proposed (55) or found nothing (146), and none gave an
  answer, so a wrong hypothesis was never kept.
- **The 7 attempts the stack loses**: all ambiguous. In every one, x = 0 at four of the five sorted fit points, so the
  x-term vanishes there. The four points hold whatever the parameter (x·(y + z + c)) or the mapping of the inputs
  (y·y − x·(z + c)). Only the fifth point carries the information:

  | structure | c (fit seed) | what the stack proposed | outcome |
  |---|---|---|---|
  | x·(y + z + c) | −3 (0), 7 (0), 8 (1) | the right mapping with a wrong constant, enumerated. The voting solver needs two determining examples and had one, so nothing was solved | 4 fit labels agreed, 1 contradicted (tolerated); suspended by the first validation label; no answer |
  | y·y − x·(z + c) | −4 (2), −2 (2), 4 (0), 8 (1) | a wrong mapping, its parameter solved from the uninformative points. The right mapping's parameter has one determining example, so it was not solved, and no question was asked | the same |

  The diagnosis is exploratory and was run after the held-out test (`benchmarks/dev30_analysis.py losses` →
  `benchmarks/results/dev30/exploratory/losses.jsonl`). It re-ran the 7 attempts:
  - the stack: all 7 lost again, each with 4 fit labels matched and 1 contradicted;
  - the stack with `contradiction_policy='strict'`: all 7 succeed with a solved candidate;
  - the stack with `family_parameters='enumerate'`: all 7 still lost.

  The cause is tolerance on degenerate fits. Parameter solving and asking do not cause it.
- **Correction to the pre-registration.** It describes development's one loss (x·(y + c) + z, c = 6) as "DEV26's known
  limit": an undetermined parameter, so no solved candidate, and a wrong one fit. Re-running that attempt shows a
  solved candidate of a wrong mapping that matched 4 fit labels and contradicted 1: the same tolerated false fit, which
  the strict policy avoids. The pre-registration is frozen and stays as committed; this report corrects it.

## Exploratory ablation (not pre-registered; after the held-out test)
`benchmarks/dev30_ablation.py` runs the stack without one mechanism at a time (that option back at its default) on the
same held-out attempts, and compares each attempt with the stack's committed record. It shows what each mechanism
contributes inside the whole; it is not a gate.

**Pending.** It runs once DEV29's real-bug shards no longer share this 4-CPU machine. DEV29's repair workflow runs under
a wall-clock budget, so extra load could change its outcomes. A first start was stopped after 6 minutes for that
reason, and its partial output was deleted without being read.

## Validation
- **`tests/test_alpha8_dev30.py`, 3 tests:**
  - the two configurations set exactly the intended options;
  - donors agree with the structure in every role order, for both arities;
  - queries stay inside the evidence range and away from fit and validation points.
- **Full `test_alpha8_*`:** pending, for the same reason (605 passed and 3 skipped at DEV28, plus DEV29's 2 and these 3).
- **No `lab_check` re-run:** ASM's code is unchanged since DEV28, whose `lab_check` reproduced all 38,224 committed lab
  records on the defaults.

## Limitations
- **A lab.** The structures are integer polynomials of degree ≤ 3 with one constant, under symmetric noise at one rate,
  with a synthetic memory. They are new structures, but of the kind DEV21–DEV28 used. Real data is DEV29's question.
- **One stack.** All four options run together. The ablation shows each one's contribution only on these held-out
  attempts, after the fact.
- **Wrong labels:** one per hypothesis is tolerated, two are not (0 of 201 such attempts). At 5% noise that caps
  success near 0.57.
- **Degenerate fits:** tolerance can discount the only informative point (7 of 288 ambiguous attempts, 2.4%). No wrong
  answer resulted, but the attempt is lost. The defaults lose 1 of those 288: they propose the first fitting mapping,
  a wrong one there, where the stack asked twice and won.
- **Narrow transfer:** donors share the target's arity and structure, two relevant donors at a time; a family across
  arities was not tested.

## What this means, and what is next
DEV30 is the lab half of the M4 question: the transfer mechanisms of alpha 8 work together under every condition
measured so far, with no wrong answer and no false transfer. M4 ("verified cross-task structural transfer") also needs
real data, which DEV29 measures. Nothing is promoted.
- **Owner's decisions:**
  - whether to make `family_parameters='solve'`, `family_ambiguity='ask'` and `family_memory='index'` the defaults (the
    ablation above shows what each adds);
  - whether to use `contradiction_policy='tolerant'` anywhere: it gains under wrong labels and costs 7 of 288 on
    degenerate fits;
  - whether DEV29 and DEV30 together support promoting alpha.8.9 or 0.4.9.
- **Possible next step:** tolerate a contradiction only when the contradicting point is not the only one that separates
  the fitting hypotheses. The point would then be asked about again rather than discounted. It needs its own
  pre-registered test.

Consciousness-related architecture: not touched.
