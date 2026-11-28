# ASM v0.4.0-alpha.5 Benchmark Report

## Alpha.5 acceptance benchmark

`benchmark_v040a5.py`: **13/13 PASS**

- 1 clue: 70.000%
- 3 clues: 78.400%
- 5 clues: 83.692%
- 7 clues: 87.3964%
- contradictory A→B posterior: 50/50
- 7-clue search: 108 expansions
- belief memo hits: 140
- policy graph nodes: 77
- outcome-specific context probe: 100% goal probability with correct branch-specific actions

## Alpha.5 randomized hard feed

`benchmark_v040a5_stress.py`: **6/6 PASS**

- 80 randomized binary sensor tasks
- maximum closed-form error: `3.33e-16`
- all within 256 expansions
- all 80 exercised belief merging
- 200/200 randomized posterior sequences matched direct Bayes
- 3-hypothesis exact-enumeration control: expected `0.8155`, alpha.5 `0.8154999999999998`
- ternary absolute error: `1.11e-16`

## Inherited planning preservation

- alpha.1: PASS
- alpha.2: PASS
- alpha.3: PASS
- alpha.4: PASS
- alpha.4 stress: 300/300 useful contingent cases and 200/200 useless-sensing controls PASS

## Unit compatibility

282/282 executed tests passed in split runs; one inherited test was intentionally skipped.

## Other validation

- smoke: PASS
- world model: 19/19 PASS
- world scaling: 10,000 updates; 200/200 filtered queries correct
- trained DB round-trip: 897 episodic / 897 semantic vectors / 897 typed events preserved

## Not freshly certified here

The alpha.8-alpha.10 full long-stream suites are extremely slow and were not rerun to completion after the final alpha.5 patch. Their historical results are not relabeled as current alpha.5 results.
