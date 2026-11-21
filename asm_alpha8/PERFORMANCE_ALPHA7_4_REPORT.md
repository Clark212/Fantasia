# Performance Report — ASM v0.4.0-alpha.7.4

Fresh local microbenchmarks from `ALPHA74_PERFORMANCE.json`:

- XOR synthesis: median **8.9428 ms**, p90 **9.2899 ms**;
- XOR information query: median **5.4515 ms**, p90 **5.5696 ms**;
- tested piecewise conditional synthesis: median **5.9228 ms**, p90 **6.0423 ms**;
- active conditional prediction: ~**80,023 predictions/s**.

Exact alpha.7.3 baseline measured in the same performance profile:

- 2-input affine synthesis: median **0.3849 ms**, p90 **0.4020 ms**;
- 2-input product synthesis: median **1.0751 ms**, p90 **1.1712 ms**;
- active prior procedure prediction: ~**68,781 predictions/s**.

The new conditional/Boolean searches are intentionally more expensive than the older narrow affine/product paths because they maintain competing typed hypotheses and ambiguity checks. Search remains bounded rather than being allowed to grow until a fit is found.

All timings are environment-specific microbenchmarks and can vary with hardware, OS scheduling, database state, and Python runtime.
