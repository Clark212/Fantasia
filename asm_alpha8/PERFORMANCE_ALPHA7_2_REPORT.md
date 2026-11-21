# Performance Profile — ASM v0.4.0-alpha.7.2

Fresh local profile (`benchmark_v040a72_performance.py`):

| Measurement | Manual | Autonomous | Ratio |
|---|---:|---:|---:|
| initial discovery median, 20 runs | 0.00364163 s | 0.00389487 s | 1.06954x |
| 500 active observations, median | 0.0297468 s | 0.0316951 s | 1.06550x |
| median DB bytes after steady profile | 147456 | 147456 | 1.0x |

The measured autonomous overhead was ~6.95% during initial discovery and ~6.55% in the steady procedure-observation path in this environment. These are environment-specific measurements, not universal performance claims.
