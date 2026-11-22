# ASM Roadmap

**Current: v0.4.0-alpha.7.9 (promoted). In development: alpha 8 = 0.4.8, not promoted; its DEV steps are experiments
(latest DEV21).**

## How versions are named
- **Version (0.N)**: the roadmap stage being built.
- **Alpha N**: a development series within a stage. The last promoted release is v0.4.0-alpha.7.9; alpha 8 is the
  series for milestone 0.4.8 (project owner).
- **DEV N**: one pre-registered development step inside an alpha: an experiment (a side track), not a milestone.
- **Promotion**: a version counts as reached only when it passes a pre-registered gate on fresh data. Every alpha 8
  step so far (DEV1–DEV21) is experimental and not promoted.

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

Alpha 8 (0.4.8) is not promoted: its target, M4 (verified cross-task structural transfer), is not met (the plan below).
DEV21 passed its first held-out transfer gate: sharing the candidate budget round-robin removes an interference between
learned families (opt-in; making it the default is the owner's decision). The same rule did not significantly change
learned edit steps on fresh fixes. Learned families are consulted only for one-input integer targets.

### Release governance and the alpha 8 plan
- Official frozen baseline: **v0.4.0-alpha.7.9** (`asm.__version__`), milestone **M3 — Adaptive Research AI**.
- In development: **v0.4.0-alpha.8 (milestone 0.4.8) — Structural Transfer & Analogical Procedure Generalization**,
  toward **M4 — Generalizing Research AI** (verified cross-task structural transfer).
- The alpha 8 sequence below lists targets, not completed milestones; none is promoted. The table shows what exists for
  each so far, keeping implemented, demonstrated and validated apart.

| target | closest existing work | evidence so far |
|---|---|---|
| alpha.8.1 Structural Anti-Unification | `asm/coding/induction.py` (DEV17): real fixes generalized into executable procedures | demonstrated: held-out fixes reproduced in 2 other projects; transfer gate G17-1 not passed (0 of 59 real bugs) |
| alpha.8.2 Compositional Procedure Reuse | `asm/coding/steps.py` (DEV20): steps combined at several places and in pairs; round-robin step sharing (DEV21, opt-in) | G20-1 not passed: the compositions cost more than they gained; DEV21 G21-B not passed (2 gained, 0 lost on 197 fresh fixes) |
| alpha.8.3 Uncertain Analogy Mapping | `asm/structural.py` (relation schemas, structural analogies) and `asm/expansion.py`, from earlier releases | no alpha 8 report evaluates it |
| alpha.8.4 Negative Transfer Protection | DEV4 structural-transfer experiment (`asm/learning/structtransfer.py`); procedure retire/supersede (DEV17); `ProcedureCortex(family_sharing='round_robin')` (DEV21, opt-in) | DEV4: unrelated donors added to relevant ones took success from 1.00 to 0.00 (interference). DEV21: round-robin family sharing removes it on three held-out structures, no wrong answer, cost ratio 1.06 (G21-A passed). One mechanism, a noise-free lab, opt-in: the target is not yet validated |
| alpha.8.5 Held-Out Transfer Benchmarking | pre-registered fresh-project harnesses (DEV18–DEV21: 472, 103, 483, 197 unseen fixes); DEV4 Part B and DEV21 Part A (held-out structures, toy) | the benchmarks exist; no M4-level gate has passed |
| alpha.8.6 Persistent Transfer Memory | sealed knowledge, shape and step libraries (DEV17–DEV20) | implemented; not validated as transfer memory |
| alpha.8.7 Adversarial Generalization Hardening | none identified | not started |
| alpha.8.8 Transfer Scaling & Efficiency | DEV19 (12.6× training data); lazy candidate building (DEV20) | more data added no reproduced fix (DEV19) |
| alpha.8.9 M4 Stage-Closure Candidate | — | not started |

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
