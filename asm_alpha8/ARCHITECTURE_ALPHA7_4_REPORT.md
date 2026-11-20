# Architecture Report — ASM v0.4.0-alpha.7.4

## Capability added

Alpha.7.4 adds **Conditional Procedures & Active Information Gathering** to the integrated Procedure Cortex. It extends alpha.7.3; it does not replace ASM's memory, world model, self/agent models, planners, source reliability, lineage, or learned hidden-dependency architecture.

## Authority flow

```text
Externally resolved experience
        |
        v
source reliability + source-regime check
        |
        v
independent evidence-root filter
        |
        v
bounded typed hypothesis synthesis
   +--> Boolean procedures
   +--> integer predicates
   +--> piecewise affine conditionals
   +--> prior integer/compositional procedures
        |
        +--> one simple supported hypothesis
        |        |
        |        v
        |     PROPOSED
        |
        +--> several plausible hypotheses disagree
                 |
                 v
         READ-ONLY INFORMATION QUERY
         "which input separates them?"
                 |
        external world/user resolves it
                 |
                 v
          ordinary evidence path
                 |
                 v
       8 distinct held-out validations
                 |
                 v
              ACTIVE
                 |
      mismatch / stale dependency
                 |
                 v
       ABSTAIN + versioned repair
```

## Boolean synthesis

Boolean search is typed and bounded. Candidate programs are signature-deduplicated over observed evidence, and the DSL evaluator remains bounded. Release stress exercises ordinary Boolean families rather than arbitrary source-code execution.

## Conditional synthesis

The new integer conditional path composes:

- small typed predicates (for example integer comparisons);
- bounded affine branch expressions;
- the existing safe typed DSL `if` expression.

The learner remains conservative: if the evidence cannot uniquely justify a near-simple rule, it can request a discriminating observation instead of activating a guessed rule.

## Ambiguity / information gate

For a given evidence set:

1. synthesize bounded candidate programs that fit the observations;
2. retain a near-simple hypothesis set (small MDL-size window);
3. generate a bounded hypothetical input pool, prioritizing observed neighborhoods and gaps;
4. evaluate **candidate programs only** on those hypothetical inputs;
5. choose an input with high prediction disagreement;
6. return that input as a read-only query.

No predicted output is inserted into evidence. The query mechanism does not mutate fit history, validation support, procedure versions, or the world database.

## Evidence authority

A procedure query or synthesized program has no authority merely because ASM generated it. Activation still depends on externally resolved, source-gated, independent evidence and held-out validation.

Alpha.7.1 remains the authority for hidden statistical evidence dependency and time-varying dependency regimes. Explicit ancestry/lineage remains separately available through the evidence ledger.

## Drift / revalidation compatibility

Alpha.7.4 preserves the procedure version model:

- active mismatch creates an abstention/fresh-evidence boundary;
- a previously validated procedure may be re-proposed only from clean post-boundary evidence;
- reactivation creates a **new auditable version**;
- source-regime invalidation still blocks stale procedures.

The post-boundary revalidation path was explicitly hardened during alpha.7.4 development after a backward-compatibility stress found that an outlier could contaminate the ambiguity window.

## Boundedness

Inherited limits remain in force, including:

- max program inputs: 4;
- max synthesis candidates per attempt: 512;
- max source dependencies per procedure version: 8;
- 8 distinct held-out validation inputs;
- typed program node/depth limits;
- bounded query/hypothesis pools;
- no Python `eval` and no arbitrary code execution.

## Snapshot migration

Alpha.7.4 uses `asm_snapshot_v0_4_0_alpha_7_4` and explicitly recognizes alpha.7.3 snapshots. Procedure tables remain additive SQLite state. Loading an older snapshot does not synthesize conditional/Boolean procedure history.
