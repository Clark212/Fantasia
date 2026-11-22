# DEV22 amendments (after the pre-registration `10afa3f`, recorded before re-running)

## A1 — the held-out harness could not draw queries for a fit near the grid's top corner (harness bug; R3)
- **Found by:** the first pre-registered held-out run, which stopped with `ValueError: Sample larger than population`
  while choosing an attempt's 6 query pairs.
- **Cause:** queries were drawn from the pairs between the fit's lowest coordinates and 9, minus the fit pairs. When the
  three fit points lie near the grid's top corner, that region holds fewer than 6 pairs. No development attempt met
  this case.
- **Fix:** `dev22_transfer.queries_for` draws exactly as before whenever the region holds 6 pairs; otherwise it extends
  the region to 17, the validation pairs' range (still inside the evidence range, so the queries stay answerable),
  minus the validation pairs. Regression test: `FamilyScopeTests.test_queries_for_a_fit_near_the_top_corner` (a typical
  fit draws exactly as before; a corner fit gets 6 queries inside the evidence range).
- **Effect on the pre-registration:** none on any threshold, arm, structure, constant or seed. Only attempts whose fit
  leaves fewer than 6 query pairs are affected; the re-run reports how many. The development run reproduces every
  attempt record with the fixed harness.
- **The first run** is kept, unread, in `benchmarks/results/dev22/discarded_run1/` (no outcome in it was looked at),
  and the held-out test is re-run in full.
