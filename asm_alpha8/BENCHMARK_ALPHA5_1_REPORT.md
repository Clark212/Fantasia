# ASM v0.4.0-alpha.5.1 — Benchmark Report

## Core alpha.5 benchmark

`python benchmark_v040a5.py`

**13/13 PASS**

Controlled 70%-reliable hidden-state task remains:

| Clues | Goal / decision accuracy |
|---:|---:|
| 1 | 70.000% |
| 3 | 78.400% |
| 5 | 83.692% |
| 7 | 87.3964% |

Seven-clue alpha.5.1 planning remained at:

- 108 expansions
- 140 memo hits
- 77 policy nodes
- 19 unique belief states

This preserves the prior alpha.5 controlled result and remains below the recorded alpha.4 external full-history control of 765 expansions / 431 nodes for the same 87.3964% target.

## Original alpha.5 hard feed

`python benchmark_v040a5_stress.py`

**6/6 PASS**

- 80 randomized binary sensor worlds matched closed-form Bayes.
- 200/200 random posterior sequences matched direct Bayes.
- 3-hypothesis exact-enumeration case remained correct at 81.55%.

## v0.4 unit surface rerun

Executed:

```text
python -m unittest \
  tests.test_v040a1 tests.test_v040a2 tests.test_v040a3 \
  tests.test_v040a4 tests.test_v040a5 tests.test_v040a51 \
  tests.test_v040a51_contract
```

Result: **59/59 PASS**.

This is a v0.4 planning/unit recertification only. It is not a claim that every historical long-stream suite in the repository was freshly rerun.

## Hidden-space scale

Additional alpha.5.1 torture feed used exact small-horizon oracles:

| Hypotheses | Clues | Error vs oracle | Expansions | Nodes |
|---:|---:|---:|---:|---:|
| 2 | 5 | 2.22e-16 | 66 | 53 |
| 3 | 4 | 5.55e-16 | 184 | 170 |
| 4 | 4 | 1.22e-15 | 595 | 580 |
| 8 | 3 | 5.11e-15 | 1485 | 1931 |
| 16 | 2 | 2.66e-15 | 2601 | 3465 |
| 32 | 1 | 0 | 1089 | 2177 |

The 32-hypothesis case explicitly reported the architectural cap as reached. The cap was not increased.

## Search-budget pressure

For the 8-hypothesis / 3-clue case, budgets 16 through 1024 reported:

- `status = budget_exhausted_partial_policy`
- `search_complete = false`

At budget 2048, search completed at 1485 expansions and matched the oracle within 5.11e-15.

This confirms the reporting hardening: a budget-exhausted partial policy no longer presents itself as fully evaluated.
