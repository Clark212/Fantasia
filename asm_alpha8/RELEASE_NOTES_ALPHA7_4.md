# ASM v0.4.0-alpha.7.4 — Conditional Procedures & Active Information Gathering

## Status

Alpha.7.4 extends the certified alpha.7.3 Procedure Cortex with **typed Boolean/conditional procedure induction** and **read-only disagreement-driven information gathering**. The alpha.7.1 evidence/dependency system remains the authority for hidden dependency and temporal dependency regimes.

This is a same-stage capability extension. It does **not** claim AGI, RSI, arbitrary program synthesis, autonomous world experimentation, or broad causal discovery.

## What changed

### Boolean procedure induction

The bounded synthesizer can now propose typed Boolean procedures from externally resolved evidence, including families exercised in release stress: AND, OR, XOR, NAND, NOR, XNOR, implication, majority-of-three, and simple integer predicates.

A Boolean hypothesis is not trusted merely because it fits the current examples. It must still pass the Procedure Cortex evidence gates and **8 distinct held-out validation inputs** before activation.

### Conditional integer procedures

Alpha.7.4 can synthesize conservative piecewise integer procedures such as:

```text
if x < threshold:
    affine branch A
else:
    affine branch B
```

The conditional search remains bounded and typed. It does not execute arbitrary Python or generated source code.

### Active information gathering

When several near-simple hypotheses fit the same evidence but disagree on an unobserved input, ASM can return a **read-only information query** identifying an input that best separates those hypotheses.

Important authority boundary:

- ASM may suggest the input to observe.
- ASM does **not** fabricate the answer.
- A simulated/hypothetical answer does **not** train the procedure learner.
- Only externally resolved experience can become fit/validation evidence.
- Calling the information-query API is read-only and does not mutate the database.

The ambiguity gate uses a small MDL-style preference window so wildly more complex exception rules do not force endless querying when a much simpler supported rule already explains the data.

### Drift and reversal

Conditional procedures retain the existing versioned Procedure Cortex behavior:

- mismatch -> abstain / fresh boundary;
- collect trusted independent evidence;
- induce or revalidate a new version;
- require held-out validation;
- old trust is never silently resurrected.

A backward-compatibility stress run exposed a regression in alpha.7.2 single-outlier recovery while alpha.7.4 was being developed. The new ambiguity window initially kept the outlier inside the new fit set. The architecture was fixed by attempting a clean **post-boundary revalidation pass** for previously validated procedures before inducing replacements. Alpha.7.2 torture then returned to 8/8 PASS.

## BEFORE vs AFTER — exact alpha.7.3 artifact

The BEFORE baseline is the exact packaged `ASM_v0.4.0-alpha.7.3.zip` with SHA-256:

`421527405b0e9f9d7eb87a291e76f988e81fd4c35d01be4107cc1a9ac2b033f9`

Fresh baseline probes showed:

- XOR: `unsupported`, 0 procedure versions;
- mixed Boolean/integer selector: `unsupported`, 0 versions;
- piecewise conditional: `unresolved`, 0 versions;
- no `procedure_information_query` API.

Alpha.7.4 BEFORE/AFTER benchmark: **11/11 PASS**.

Key AFTER results:

- XOR learned and validated after the ambiguity query supplied the missing discriminating case;
- with three XOR observations, ASM suggested `{a: true, b: true}` rather than guessing;
- information-query selection was verified read-only;
- integer predicate learning passed;
- a mixed Boolean/integer selector generalized;
- a piecewise-affine rule generalized on **61/61** benchmark inputs;
- conditional drift induced a new validated version;
- full reversal created a new auditable revalidation version;
- information suggestions had no direct belief/action authority.

Raw evidence: `BASELINE_ALPHA73_CONDITIONAL.json` and `ALPHA74_BEFORE_AFTER.json`.

## Torture

`benchmark_v040a74_torture.py`: **8/8 PASS**.

- Boolean family: **8/8** (AND, OR, XOR, NAND, NOR, XNOR, implication, majority3).
- Random integer thresholds: **32/32**.
- Random piecewise-affine conditionals: **32/32**.
- Conditional drift + reversal: **20/20**.
- Repeated information-query stability: **100/100**.
- Repeated information-query DB mutation: **0 mutations across 100 calls**.
- Duplicate-root query guard: PASS.
- Random Boolean noise: **0 final active procedures / 40 runs**.

An earlier stress run found that sparse threshold evidence could support several rules while the query pool looked near arbitrary small constants rather than the observed data frontier. That run was not counted. The query pool was changed to prioritize observed neighborhoods/gaps, and the same strengthened stress suite was rerun to 8/8.

Raw evidence: `ALPHA74_TORTURE.json`.

## Migration

A real alpha.7.3 SQLite database was created with the exact alpha.7.3 code and then reopened under alpha.7.4.

`MIGRATION_ALPHA74.json`: **9/9 PASS**.

Preserved exactly:

- active multi-input procedure and prediction (`35` for the recorded probe);
- procedure version history/support;
- source calibration;
- evidence dependency state/regimes;
- evidence lineage;
- alpha.7.3 snapshot compatibility.

Alpha.7.4 fabricated **0** new procedure versions/history during migration, and wrote its new snapshot key only when explicitly saved.

## Performance

Fresh environment-specific medians from `ALPHA74_PERFORMANCE.json`:

| operation | median | detail |
|---|---:|---|
| XOR synthesis | **8.943 ms** | 357 candidates in recorded final proposal |
| XOR information query | **5.452 ms** | read-only hypothesis separation |
| piecewise conditional synthesis | **5.923 ms** | 292 candidates in recorded final proposal |
| active conditional prediction | — | ~**80,023 predictions/s** microbenchmark |

Fresh exact-alpha.7.3 comparison in the same profile:

- 2-input affine synthesis median: **0.385 ms**;
- 2-input product synthesis median: **1.075 ms**;
- active old procedure prediction: ~**68,781/s**.

These are local microbenchmarks and are not universal hardware claims.

## Regression recertification

Final working-tree unit batches after the architecture fixes:

- v0.1: **72/72 PASS**
- v0.2: **84/84 PASS**
- v0.3: **77 executed = 76 PASS + 1 inherited intentional SKIP**
- v0.4 including alpha.7.4: **150/150 PASS**
- review / Procedure Cortex / Astra-graft tests: **21/21 PASS**

Total: **404 executed = 403 PASS + 1 inherited intentional SKIP**.

Fresh behavior gates:

- alpha.5 frozen benchmark: **13/13 PASS** after updating only its current-release string assertion;
- alpha.5 hard feed: **6/6 PASS**;
- alpha.5.1 torture: **10/10 PASS**;
- alpha.5.1 extreme torture: **9/9 PASS**;
- alpha.6 torture: **12/12 PASS**;
- alpha.6.1 abrupt drift: **30/30 recovered**;
- alpha.6.1 stationary: **0 false splits** across its stationary runs;
- alpha.6.2 lineage torture: **10/10 PASS**;
- alpha.7 benchmark/torture: **7/7 + 9/9 PASS**;
- alpha.7.1 benchmark/torture: **8/8 + 9/9 PASS**;
- alpha.7.2 benchmark/torture: **8/8 + 8/8 PASS**;
- alpha.7.3 benchmark/torture: **10/10 + 7/7 PASS**;
- alpha.7.4 benchmark/torture: **11/11 + 8/8 PASS**.

One combined legacy-gate command timed out and **none of its partial output was counted**. The affected version gates were rerun separately to completion.

### Preserved inherited failure

`benchmark_v040a5_mega_stress.py` remains **13/14**, failing only:

`topk_truncation_keeps_unknown_mass`

This is the same inherited alpha.5 planning limitation preserved by alpha.7.3; alpha.7.4 did not redefine the check or hide the failure.

### Inherited runtime warnings

The v0.4 unit surface still emits inherited unclosed-SQLite `ResourceWarning`s while passing. These warnings were already present in the prior release line and remain an open cleanup item; this release does not claim warning-free resource handling.

## Packaged-artifact recertification

A fresh extraction of the packaged alpha.7.4 archive was tested directly. Before the final documentation-only stamp, its manifest verified **312/312** payload hashes; smoke, alpha.7.4 unit tests (**12/12**), BEFORE/AFTER (**11/11**), and torture (**8/8**) passed. The full extracted unit suite reproduced **404 executed = 403 PASS + 1 inherited intentional SKIP**. The exact final archive is rebuilt after adding this recertification record and rechecked for manifest integrity plus critical gates.

See `PACKAGE_RECERTIFICATION_ALPHA74.log`.

## Current limitations / next bottleneck

Alpha.7.4 is still a **small bounded procedure learner**. It does not autonomously synthesize arbitrary code, carry out world experiments, or solve general symbolic reasoning tasks.

Important next bottlenecks:

1. contextual procedure routing when several validated rules apply;
2. deeper hierarchical/compositional procedures without search explosion;
3. persistent information-gathering policies across multiple observations rather than single-query selection;
4. tighter procedural use of alpha.7/7.1 learned cross-source dependency;
5. clean up inherited SQLite lifetime warnings;
6. inherited alpha.5 top-k unknown-mass failure remains open.
