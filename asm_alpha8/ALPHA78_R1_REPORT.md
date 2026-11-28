# ASM v0.4.0-alpha.7.8 Experimental R1

R1 extends the frozen alpha.7.7 router in two bounded ways while leaving the default router unchanged:

1. **Wide covariance ablation** — the certified fail-closed inverse-covariance solve may operate on connected components up to 64 sources instead of 16. Unsafe negative/amplifying/unstable solutions still fall back.
2. **Latent common-cause ablation** — Procedure Cortex receives read-only raw pair diagnostics and may fit at most two non-negative factors for 8..16 sources. The latent layer is redundancy-only: each final source weight is capped by the wide-covariance baseline, so it cannot add routing confidence.

R1 is experimental and must not replace alpha.7.7 until null false-activation, drift, adversarial, regression, consciousness, and package-recertification gates pass.
