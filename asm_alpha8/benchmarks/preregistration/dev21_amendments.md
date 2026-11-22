# DEV21 amendments (after the pre-registration `37d6d7f`, recorded before re-running)

## A1 — the Part A harness could not shuffle repeated labels (harness bug; R3)
- **Found by:** the first pre-registered Part A run, which stopped after 1,876 of 3,888 attempts with
  `RuntimeError: could not derange` in the relevant_shuffled arm of the shift structure.
- **Cause:** the arm deranges the target's labels with DEV4's `structtransfer.derange` (no position keeps its value).
  For shift, y = (x + c)·x, two of the three fit labels can be equal (x = 0 and x = −c both give 0, and x, −c − x give
  the same value), and when one value fills more than half the positions no derangement exists. DEV4's structure
  (x·x + c on distinct x) never repeats a label, so DEV4 never met this.
- **Fix:** `dev21_transfer.shuffled` uses DEV4's derangement whenever one exists (identical result, same random
  stream); otherwise a permutation that changes as many positions as possible (with two equal labels of three: two of
  the three positions change, so the label vector still differs from the truth). DEV4's code is unchanged. Regression
  test: `GateLogicTests.test_shuffled_labels_with_a_repeated_value` (DEV4's `derange` raises on `[0, 0, 5]`).
- **Effect on the pre-registration:** none on any threshold, arm, structure, constant or seed. Only shuffled-arm
  attempts whose fit labels repeat are affected; the re-run reports how many.
- **The first run** is kept, unread, in `benchmarks/results/dev21/discarded_part_a_run1/` (no outcome in it was looked
  at before this fix), and Part A is re-run in full.
