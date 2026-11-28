# Performance Report — ASM v0.4.0-alpha.7.3

Fresh local microbenchmarks from `benchmark_v040a73_performance.py`:

- multi-input affine: median **0.0008588 s**, p90 **0.0010917 s**, median 1 candidate / 4 evaluator calls;
- `x*y`: median **0.0014240 s**, p90 **0.0015656 s**, median 18 candidates / 72 evaluator calls;
- `x²+y`: median **0.0036012 s**, p90 **0.0040206 s**, median 71 candidates / 284 evaluator calls;
- active procedure prediction: **20,000 predictions in 0.14224 s** (~140,605/s).

Exact alpha.7.2 vs alpha.7.3 unary compatibility microbenchmark:

- initial autonomous discovery median: alpha.7.2 `0.0041870 s`; alpha.7.3 `0.0041435 s`;
- steady 500 active observations median: alpha.7.2 `0.0296491 s`; alpha.7.3 `0.0346677 s`;
- steady ratio in that run: **1.1693x**;
- median SQLite DB size: `147456` bytes for both.

Timings are environment-specific and can be noisy. The steady unary slowdown is preserved as an optimization target rather than treated as a universal regression percentage.
