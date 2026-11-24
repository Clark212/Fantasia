# ASM Roadmap

**Current: v0.4.0-alpha.7.9 (promoted). In development: alpha 8 = 0.4.9, not promoted; its DEV steps are experiments
(latest DEV28).**

## How versions are named
- **Version (0.N)**: the roadmap stage being built.
- **Alpha N**: a development series within a stage. The last promoted release is v0.4.0-alpha.7.9; alpha 8 is the
  series for milestone 0.4.9, the Stage 4 closure; alpha 7.8 delivered 0.4.7 and 0.4.8 (project owner).
- **DEV N**: one pre-registered development step inside an alpha: an experiment (a side track), not a milestone.
- **Promotion**: a version counts as reached only when it passes a pre-registered gate on fresh data. Every alpha 8
  step so far (DEV1–DEV28) is experimental and not promoted.

## Foundation era — 0.0.x
Establish the foundation of ASM.
0.0.1 Initial Seismic Engine · 0.0.2 Event and Impulse Processing · 0.0.3 Basic Memory System · 0.0.4 Signal
Propagation · 0.0.5 Initial Learning Mechanism · 0.0.6 Associative Connections · 0.0.7 Basic Prediction · 0.0.8 Internal
State Management · 0.0.9 Foundation Integration and Stability

## Stage 1 — Seismic core — 0.1.x
Build the foundational cognitive engine.
0.1.0 Seismic Core Architecture · 0.1.1 Stabilized Seismic Core · 0.1.2 Adaptive Signal Processing · 0.1.3 Dynamic Memory
Connections · 0.1.4 Associative Learning · 0.1.5 Reliability and Evidence Tracking · 0.1.6 Persistent Memory · 0.1.7
Online Learning · 0.1.8 Cognitive State Coordination · 0.1.9 Core Stage Closure

## Stage 2 — Predictive intelligence — 0.2.x
Make ASM learn from consequences and prediction errors.
0.2.0 Predictive Core · 0.2.1 Prediction Error Learning · 0.2.2 Temporal Prediction · 0.2.3 Adaptive Prediction · 0.2.4
Uncertainty Estimation · 0.2.5 Prediction Calibration · 0.2.6 Long-Term Prediction · 0.2.7 Predictive Generalization ·
0.2.8 Multi-Context Prediction · 0.2.9 Predictive Stage Closure

## Stage 3 — Self-forming concepts — 0.3.x
Develop abstractions instead of relying entirely on predefined representations.
0.3.0 Concept Formation · 0.3.1 Pattern Discovery · 0.3.2 Hierarchical Abstraction · 0.3.3 Concept Relationships · 0.3.4
Dynamic Concept Formation · 0.3.5 Generalization · 0.3.6 Concept Revision · 0.3.7 Cross-Domain Abstraction · 0.3.8
Self-Organizing Knowledge · 0.3.9 Abstraction Stage Closure

## Stage 4 — Dynamic cognitive architecture — 0.4.x (current)
Give ASM the ability to internally simulate situations and plan actions.
0.4.0 Dynamic Neural Tissue and Cognitive Coordination · 0.4.1 Internal Simulation · 0.4.2 Branching Simulation · 0.4.3
Probabilistic Futures · 0.4.4 Active Information Gathering · 0.4.5 Belief-State Planning · 0.4.6 Evidence Reliability ·
0.4.7 Latent Dependency Structure · 0.4.8 Higher-Order Epistemic Routing · 0.4.9 Planning and Simulation Stage Closure

This incorporates the planning and simulation work from the existing alpha development rather than throwing it away.

**Open before 0.4.9 can be promoted:** a pre-registered check that the Stage 4 components work together. Related, from
Stage 3: generalization to unseen data (0.3.5) is not yet shown. The alpha 8 coding track (DEV15–DEV20) is the current
measurement. Learned fix patterns reproduce 2 of 472 fresh real fixes that nothing else in ASM reproduces (DEV18; its
gate needed 10). With 12.6× the training fixes, that number is 0 of 103 (DEV19). More data alone does not close the gap.
Smaller learned edit steps that combine give 1 of 483 (DEV20). Steps recur more often than whole-fix shapes, but they
are generic: without knowing where the bug is, the right place competes with every other place in the function. Most
fixes still need a step or a value ASM has not learned.

Alpha 8 (0.4.9) is not promoted: its target, M4 (verified cross-task structural transfer), is not met (the plan below).
DEV21 passed its first held-out transfer gate: sharing the candidate budget round-robin removes an interference between
learned families (now the default, by the owner's decision). The same rule did not significantly change
learned edit steps on fresh fixes. DEV22 extends learned families from one-input integer targets to targets with 2–4
integer inputs (held-out gate passed). DEV23 lets a family apply across input names, trying every mapping of its
inputs onto the target's (held-out gate passed in both role orders); equal names are still taken to mean equal roles,
and when the evidence fits several mappings the first is proposed. Both are now the default, by the owner's decision.
DEV24 extends the transfer to three-input targets (six mappings per family; held-out gate passed in all six role
orders) and measures wrong labels: each costs exactly its own attempt, with no wrong answer. When 18 sources share the
family budget, 3 of 16 constants are out of reach. DEV25 solves a family's parameters from the fit examples instead of
enumerating −8..8 (opt-in; held-out gate passed): constants beyond the grid and beyond the budget's reach transfer, at
half the evaluator calls. DEV26 asks for one more example when fitting candidates disagree instead of proposing the
first (opt-in; held-out gate passed): ambiguous fits 0.817 → 0.991, and the order in which mappings are tried no longer
matters. DEV27 keeps an index of families in the database instead of reading the first 32 procedures (opt-in;
held-out gate passed): transfer works with 48 and 120 background procedures and after a restart. DEV28 lets a hypothesis
survive one contradicting label (opt-in; held-out gate passed): with labels wrong at 5%, transfer rises from 0.10 to
0.58, with no wrong answer. DEV29 puts learned repair knowledge where fault localization points, on DEV15's 83 real bugs
(pre-registered gate not passed): it repairs one bug nothing else in ASM repairs, identical to the developer's fix, where the
gate needed two, and the time left for phase 3 decides most outcomes. DEV30 runs the four opt-in mechanisms of
DEV25–DEV28 together against today's defaults, under every condition so far at once, on six fresh structures
(held-out gate passed): 0.32 → 0.89 over all transfer conditions, with no false transfer and no wrong answer.
Tolerance loses 7 of 288 degenerate fits. DEV31 gives phase 3 its own time and builds learned candidates fast enough to
test them (exactly the same candidates, 33× faster), then tests on 75 fresh real bugs (pre-registered gate not passed):
learned knowledge repairs none that the workflow without it does not, though it tested a median of 89 candidates in
each of 44 bugs. Time was not the limit; the knowledge is.

### Release governance and the alpha 8 plan
- Official frozen baseline: **v0.4.0-alpha.7.9** (`asm.__version__`), milestone **M3 — Adaptive Research AI**.
- In development: **v0.4.0-alpha.8 (milestone 0.4.9) — Structural Transfer & Analogical Procedure Generalization**,
  toward **M4 — Generalizing Research AI** (verified cross-task structural transfer).
- The alpha 8 sequence below lists targets, not completed milestones; none is promoted. The table shows what exists for
  each so far, keeping implemented, demonstrated and validated apart.

| target | closest existing work | evidence so far |
|---|---|---|
| alpha.8.1 Structural Anti-Unification | `asm/coding/induction.py` (DEV17): real fixes generalized into executable procedures | demonstrated: held-out fixes reproduced in 2 other projects; transfer gate G17-1 not passed (0 of 59 real bugs). DEV29, inside fault-localized suspects (repair workflow phase 3) on DEV15's 83 real bugs: 1 bug repaired correctly only with learned knowledge (thefuck-19, a learned shape, identical to the developer's fix); G29-A not passed (needed 2), no loss, no extra wrong patch. DEV31, phase 3 with 150 s of its own and fast exact candidate building, on 75 fresh real bugs from 5 projects: 0 repaired only with learned knowledge (G31-A not passed); in development, learned shapes wrote a failing test's expected value into the code (2 wrong patches) |
| alpha.8.2 Compositional Procedure Reuse | `asm/coding/steps.py` (DEV20): steps combined at several places and in pairs; round-robin step sharing (DEV21, opt-in) | G20-1 not passed: the compositions cost more than they gained; DEV21 G21-B not passed (2 gained, 0 lost on 197 fresh fixes); DEV29: learned steps repaired no real bug in phase 3; DEV31: none of 75 fresh bugs either |
| alpha.8.3 Uncertain Analogy Mapping | `ProcedureCortex(family_mapping='rename')` (DEV23; the default since the owner's approval): a learned family tried under every type-preserving mapping of its inputs onto the target's, the evidence deciding; `asm/structural.py` (relation schemas, structural analogies) and `asm/expansion.py`, from earlier releases | DEV23 G23-A passed: donors over other input names 0.021 → 0.990 on three held-out two-input structures, in both role orders, no wrong answer. One mechanism in a noise-free lab; when the fit points cannot tell mappings apart, the first is proposed (all 7 failures); same arity only. DEV24 G24-A passed: three inputs, six role orders, 0.000 → 0.979, no wrong answer. DEV26 G26-A passed: asking for the input that separates fitting candidates (opt-in) takes ambiguous fits from 0.817 to 0.991 with role order irrelevant; it does not see candidates whose parameter is undetermined |
| alpha.8.4 Negative Transfer Protection | DEV4 structural-transfer experiment (`asm/learning/structtransfer.py`); procedure retire/supersede (DEV17); `ProcedureCortex(family_sharing='round_robin')` (DEV21; the default since the owner's approval) | DEV4: unrelated donors added to relevant ones took success from 1.00 to 0.00 (interference). DEV21: round-robin family sharing removes it on three held-out structures, no wrong answer, cost ratio 1.06 (G21-A passed). One mechanism in a noise-free lab: the target is not yet validated |
| alpha.8.5 Held-Out Transfer Benchmarking | pre-registered fresh-project harnesses (DEV18–DEV21: 472, 103, 483, 197 unseen fixes); held-out structure labs: DEV4 Part B, DEV21 Part A, DEV22 (two-input), DEV23 (other input names, two role orders), DEV24 (three inputs, wrong labels), DEV25 (constants beyond the grid), DEV26 (ambiguous fits, with questions), DEV27 (a large memory, restarts), DEV28 (wrong labels, tolerated), DEV30 (all mechanisms together, every condition); real bugs: DEV29 (DEV15's 83 BugsInPy bugs, learned knowledge in the workflow's phase 3) | DEV21–DEV28 lab gates passed (toy tasks; DEV24 also with wrong labels), and DEV30's with every mechanism together; no M4-level gate on real data has passed (DEV29: 1 of the 2 real bugs needed; DEV31: 0 of 2 on 75 fresh bugs) |
| alpha.8.6 Persistent Transfer Memory | sealed knowledge, shape and step libraries (DEV17–DEV20); `ProcedureCortex(family_memory='index')` (DEV27, opt-in): a family index kept in the database, no window of 32 versions or cap of 16 families | DEV27 G27-A passed: with 48 and 120 background procedures, relevant donors 0.000 → 1.000, unchanged after reopening, no false transfer (lab). Cost grows with the families that apply (2–28% of the search it replaces); capacity is 128 mechanisms |
| alpha.8.7 Adversarial Generalization Hardening | DEV24 Part B: target and donor labels wrong at rate 0.10 (measured); `ProcedureCortex(contradiction_policy='tolerant')` (DEV28, opt-in, approved by the owner for testing): one contradicting label tolerated beside 4 agreeing ones, voting parameter solver | G24-B passed (strict: each wrong label costs its attempt, no wrong answer). DEV28 G28-A passed: at 5% wrong labels 0.102 → 0.579, at 10% 0.009 → 0.181, no wrong answer, clean 0.999 → 0.986. One wrong label per hypothesis only; symmetric noise in a lab |
| alpha.8.8 Transfer Scaling & Efficiency | DEV19 (12.6× training data); lazy candidate building (DEV20); the per-source family budget (DEV23, measured at scale in DEV24); family parameters solved from the fit examples (DEV25, opt-in); phase 3 on its own clock with exact faster candidate building (DEV31: one parse per module, chunk-level checks; identical candidates, 33× faster on 55 real functions) | more data added no reproduced fix (DEV19); DEV24: 18 sources over 256 proposals reach 14 of 17 parameter values, losing 3 of 16 constants in mixed arms (fewer with four inputs). DEV25 G25-A passed: solving reaches them (0 → 1.000) and constants beyond −8..8 (0 → 0.982) at half the evaluator calls. DEV31: learned candidate building for one youtube-dl suspect 623 s → 3.8 s, the same candidates; phase 3 tested candidates in every fresh bug it ran on, and no learned run passed 300 s (DEV29: up to 809 s) |
| alpha.8.9 M4 Stage-Closure Candidate | `benchmarks/dev30_battery.py` (DEV30): the four opt-in mechanisms of DEV25–DEV28 together, against today's defaults, under every lab condition at once | DEV30 G30-A passed (lab, six held-out structures): all transfer conditions 0.324 → 0.889, every condition at its bar, no false transfer, no wrong answer; tolerance loses 7 of 288 degenerate fits. The real-data half is DEV29. Not promoted: that is the owner's decision |

### The DEV8–DEV40 capability map (project owner, 2026-11-24)
The owner gave a list of 33 development steps in six phases, ending at **DEV40 — full architecture evaluation and stage
closure**. Its numbering differs from what the repository did from DEV16 on, and DEV numbers name reports,
pre-registrations and hash-chained results, so **the repository's DEV numbers stay as they are**. The list is the
long-range map:
- **DEV8–DEV31** are done, with the topics the reports record (DEV15 multi-file bug repair; DEV16–DEV24 learning and
  transfer; DEV25–DEV31 transfer mechanisms and real-bug tests).
- **DEV32** (test-copy guard on fresh real bugs) is the first step toward the owner's Phase 5.
- **DEV33–DEV40** take the list's topics in order, each as a pre-registered experiment: experimental design, causal
  reasoning and discovery, meta-learning, cognitive-architecture integration, unified memory and knowledge, integrated
  planning and reasoning, generalized engineering intelligence, and DEV40's full evaluation.
- **M4 first:** the real-data gate (learned knowledge repairing real bugs the workflow without it does not) is still open
  and comes before closure. A DEV that fails its gate is repeated or redesigned, so DEV40 is a target, not a date.
- **Versions:** v0.4.x to v1.0.0 follow the stages below; a version is promoted only when its gates pass.

## Stage 5 — Causal intelligence — 0.5.x
Move beyond recognizing correlations. Learn cause and effect.
0.5.0 Causal Reasoning Foundation · 0.5.1 Causal Relationship Discovery · 0.5.2 Counterfactual Reasoning · 0.5.3
Controlled Experimentation · 0.5.4 Intervention Learning · 0.5.5 Causal World Models · 0.5.6 Causal Generalization ·
0.5.7 Causal Planning · 0.5.8 Causal Knowledge Revision · 0.5.9 Causal Stage Closure

## Stage 6 — Meta-learning — 0.6.x
Learn how to learn more effectively.
0.6.0 Meta-Learning Foundation · 0.6.1 Learning Strategy Selection · 0.6.2 Adaptive Learning Rates and Priorities ·
0.6.3 Learning From Few Examples · 0.6.4 Transfer Learning · 0.6.5 Skill Acquisition · 0.6.6 Knowledge Consolidation ·
0.6.7 Learning Efficiency Optimization · 0.6.8 Adaptive Cognitive Strategies · 0.6.9 Meta-Learning Stage Closure

## Stage 7 — Self-model and bounded self-improvement — 0.7.x
ASM develops an explicit model of its own capabilities and limitations.
0.7.0 Self-Model Foundation · 0.7.1 Capability Awareness · 0.7.2 Limitation Detection · 0.7.3 Internal Performance
Diagnosis · 0.7.4 Improvement Hypothesis Generation · 0.7.5 Bounded Self-Modification · 0.7.6 Autonomous Experimentation
· 0.7.7 Self-Improvement Validation · 0.7.8 Safe Version Evolution · 0.7.9 Self-Improvement Stage Closure

Self-modification must use isolated experiments, independent validation, rollback, and immutable release checkpoints.
ASM must not be allowed to silently rewrite its own evaluation standards.

## Stage 8 — Native communication — 0.8.x
Give ASM its own flexible communication and language capabilities.
0.8.0 Native Language Interface · 0.8.1 Language Understanding · 0.8.2 Semantic Representation · 0.8.3 Language
Generation · 0.8.4 Contextual Communication · 0.8.5 Internal Knowledge-to-Language Translation · 0.8.6 Multilingual
Capabilities · 0.8.7 Language-Grounded Reasoning · 0.8.8 Language Independence Testing · 0.8.9 Communication Stage Closure

Language remains an interface, not the cognitive authority. ASM must still think and reason without depending on an LLM.

## Stage 9 — Multimodal intelligence — 0.9.x
Expand ASM's ability to perceive and understand different forms of information.
0.9.0 Multimodal Architecture · 0.9.1 Visual Perception · 0.9.2 Spatial Understanding · 0.9.3 Audio Perception · 0.9.4
Temporal Event Understanding · 0.9.5 Cross-Modal Associations · 0.9.6 Multimodal Memory · 0.9.7 Multimodal Prediction ·
0.9.8 Integrated Perception and Reasoning · 0.9.9 Multimodal Stage Closure

## Stage 10 — Complete architecture — 1.0.0
**v1.0.0 — Artificial Seismic Machine**: the first complete, validated ASM architecture.
- Integrate all validated cognitive systems.
- Unified memory and knowledge management.
- Continual learning and adaptation.
- Internal world modeling.
- Causal reasoning and experimentation.
- Autonomous goal management.
- Multi-step planning.
- Meta-learning.
- Bounded self-improvement.
- Native language and multimodal interfaces.
- Reliable long-term operation.
- Comprehensive safety and integrity controls.
- Independent capability evaluation.

v1.0.0 is a long-term direction, not a scheduled date: several of its stages (causal world models, native language,
perception) are open research problems.
