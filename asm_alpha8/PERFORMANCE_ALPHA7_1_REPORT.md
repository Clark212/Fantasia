# ASM v0.4.0-alpha.7.1 Performance Profile

Fresh results are stored in `ALPHA71_PERFORMANCE.json`.

- 1 source / 1,000 resolved trials: non-temporal median `0.005243913 s`; temporal median `0.010398490 s`; overhead `1.98296x`.
- 9 sources / 1,000 resolved trials: non-temporal median `0.025839651 s`; temporal median `0.199803791 s`; overhead `7.73245x`.
- 9 sources / 3,000 temporal trials: `0.627442062 s`, or `4,781.32 trials/s`.
- 10,000 recent-dependency queries: O(1) sufficient-statistics path `0.019190528 s` versus reference 192-item rescan `0.277816278 s`; the reference rescan was `14.4767x` slower.

The O(1) result applies to maintaining/querying each rolling dependency view. Training a trial with many sources still constructs bounded cross-source pairs and therefore retains pairwise source-count cost.
