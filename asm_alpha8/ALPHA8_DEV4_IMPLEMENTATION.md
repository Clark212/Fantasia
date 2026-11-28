# ASM v0.4.0-alpha.8.0-DEV4 — Structural discovery map and structural-transfer measurement

**Status:** experimental development branch, not an official release. **Parent:** `ASM_alpha8_DEV3_3.zip` (sha256 f4be197c51eb3ba1…).
`asm.__version__` unchanged (`0.4.0-alpha.7.9`). **DEV4 changes no ASM core code**: it measures what ASM already does. Not an Alpha 8 pass.

## What was built
| File | Purpose |
|---|---|
| `asm/learning/structlab.py` | Part A: 6 hidden-structure families with declared grids, determined held-out interior queries, grid reference learner, ASM adapter, evaluator. |
| `asm/learning/structtransfer.py` | Part B: structural-transfer experiment on `y = x*x + c` with six donor arms, a derangement-based shuffled control, evaluator. |
| `asm/learning/structlab_prereg.py`, `ALPHA8_DEV4_PREREGISTRATION.md` | Pre-registered criteria (code + prose, test-checked identical), with the pre-registration SHA-256 and a disclosure of the exploratory probe that preceded it. |
| `run_dev4_benchmark.py`, `results/ALPHA8_DEV4_RESULTS.{md,json}` | Official run (about 4 minutes) and results. |
| `tests/test_alpha8_dev4_structdiscovery.py` | 18 tests, mutation-checked. |

## Result: pre-registered verdicts (`DEV4-prereg-1`, seed 20261102)
**Harness (A-H1..H5, B-V1, B-V2): all PASS.** Reference learner never wrong and 100% correct, memorizer canary silent, shuffled references 0%, majority floor beaten, no donor ever contained the target constant, shuffled-label arm never succeeded.

**Part A — ASM default configuration (guard = abstain), 40 tasks per family, correct / wrong rate on held-out determined interior queries:**
| family | k=8 | k=16 | k=24 | note |
|---|---|---|---|---|
| affine `a*x+b` | 0.00 / 0 | 1.00 / 0 | 1.00 / 0 | discovered |
| linear2 `a*x+b*y` | 0.00 / 0 | 1.00 / 0 | 1.00 / 0 | discovered |
| threshold `p if x<c else q` | 0.00 / 0 | 0.17 / 0 | 0.61 / 0 | partial, still rising |
| clamp `min/max(x,c)` | 0.00 / 0 | 0.25 / 0 | 0.55 / 0 | partial, still rising |
| product2 `x*y+c` | 0.00 / 0 | 0.10 / 0 | 0.10 / 0 | barely |
| quad `a*x*x+b`, a in ±2,±3 | 0.00 / 0 | 0.00 / 0 | 0.00 / 0 | not discoverable |
- **A1 never wrong: PASS** (0 wrong answers in every family and budget). **A2 shuffled labels: PASS but not clean**: ASM trained on shuffled labels answered 3 threshold queries and 1 was wrong (0.97%, bar 2%): it can occasionally fit noise.
- **A3 coverage: FAIL.** Only 2 of 6 families reach 0.80 at k=24 (bar: 3).
- ASM abstains at k=8 everywhere (it needs several distinct examples before activating), so its map is about what it finds with enough data, not data-efficiency.

**Part B — structural transfer, target `y = x*x + c` (48 in-range attempts per arm):**
| arm | success | mean evaluator calls | family-origin |
|---|---|---|---|
| none | 0.00 | 304 | 0.00 |
| one relevant donor | 0.00 | 304 | 0.00 |
| **two relevant donors** | **1.00** | **13** | 1.00 |
| unrelated donors (2 affine + 2 max) | 0.00 | 304 | 0.00 |
| **mixed (relevant + unrelated)** | **0.00** | 304 | 0.00 |
| relevant donors, shuffled target labels | 0.00 | 311 | 0.00 |
Out-of-range constants (|c| = 9..12): 0.00 in every arm.
- **T1 capability gain: PASS** (0.00 to 1.00). **T2 one donor not enough: PASS.** **T3 no negative transfer from unrelated donors: PASS** (cost ratio 1.00). **T4 safety: PASS** (0 wrong answers). **T5 parameter range limit: PASS** (predicted).
- **T3b no interference: FAIL, decisively.** Adding unrelated donors to the two relevant ones takes success from 1.00 to 0.00.

## What this means
1. **ASM has a real, previously unmeasured structural-transfer mechanism.** Two validated donors sharing a structure let ASM solve, in about 13 evaluator calls, a task its baseline cannot solve in 300. Controls show it is not memorization (donor constants never equal the target's), not noise (shuffled labels never succeed), and not harmful when donors are unrelated.
2. **It is fragile in a way that matters for any real system.** With unrelated donors also present, transfer disappears completely. Diagnosis from the code and a listing of the cortex's families (not yet confirmed by a fix): `induce` gives all templates one **shared budget of at most 64 candidates** (`min(64, budget-291)`), iterating templates in listing order. In the mixed case the first template is the two-parameter affine one (17x17 = 289 instantiations), which consumes the entire budget, so the relevant `x*x + $0` template is never reached. The same cap means a two-parameter template can only try 64 of its 289 instantiations.
3. **Structural discovery is real but narrow.** ASM reliably discovers linear structure in one or two variables, partially discovers thresholds and clamps, barely discovers `x*y+c`, and cannot discover `a*x*x+b` (and, from DEV3, modular arithmetic) unless transfer supplies the template.
4. **Safety held:** across 120+ honest-data cells ASM never answered wrongly; the only wrong answer came under shuffled labels.

## Process disclosures
- An exploratory probe (documented in the pre-registration) preceded the pre-registration; target structures and arms were chosen with it in mind. Thresholds were fixed before any benchmark run.
- While strengthening a test I found the shuffled-label arm used a plain shuffle, which is the identity permutation 1 time in 6 for 3 labels. I had not read any benchmark result; I replaced it with a derangement (no label stays in place), added tests (including a mutant that reverts it), and restarted the run. The pre-registered V2 criterion is unchanged.
- The runs reported here use the final code. A repeat run reproduced the results (see test report).

## Limits
- Toy, noise-free families; one seed; author-set thresholds; author and runner are the same party.
- Part A coverage is a lower bound: ASM can issue `needs_information` queries (seen in the probe) and this lab never answers them.
- Part B tests one target structure with constants limited to ±8 and donors installed through the public API, not learned autonomously. It shows the mechanism works, not that ASM would build such donors on its own.
- Not evaluated: cross-domain transfer, continual learning/forgetting, causal discovery, real data.

## Suggested next steps (not done)
- **DEV4.1:** fix the budget starvation behind a flag (per-template budget or dropping templates redundant with the built-in affine grid), re-evaluate T3b and T1-T5 under the same pre-registered criteria, and decide the default separately.
- Answer `needs_information` queries in the lab to measure ASM as an active learner.
- Extend the grammar or discovery for the gaps found (`a*x*x+b`, modulus), only with controls like these.
