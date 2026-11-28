# ASM v0.4.0-alpha.7.6 research notes

Experimental branch only. Not a release.

Hypothesis: learned hidden evidence dependence can improve contextual routing of persistent executable procedures by preventing correlated applicability evidence from satisfying independent-support gates.

Initial controlled ablation: four independent sources retain effective support 4.0 and route in all modes. When two of four sources are trained as strongly hidden-correlated, the existing EvidenceDependencyModel computes effective support ~2.6667. Frequency/reliability-only modes route from four raw rows; dependency/full modes abstain below min_support=4.

This is one positive controlled result. It is not evidence that the mechanism is novel, generally superior, conscious, or AGI-like. Required next falsification tests include partial dependence, false-positive dependency, dependency drift, wrong-source reliability, calibration/error rates over many randomized tasks, and query-efficiency ablations.

## Experimental R4

R4 adds routing-only multiple-comparison control (Benjamini-Hochberg q=0.01) and replaces the R3 rho-squared local redundancy mapping with covariance-linear positive-correlation weighting. The phase specifically measures wrong-dependency costs and temporal recovery. See `ALPHA76_R4_REPORT.md` and `ALPHA76_R4_BENCHMARK.json`.
