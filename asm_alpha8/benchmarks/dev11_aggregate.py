import json, sys, glob, statistics, collections
recs = [json.loads(l) for f in sorted(glob.glob(sys.argv[1])) for l in open(f)]
print(f"{len(recs)} detected faults; by subject:", dict(collections.Counter(r['subject'] for r in recs)),
      "| by kind:", dict(collections.Counter(r['kind'] for r in recs)))
def summarize(rs, label):
    print(f"\n== {label} (n={len(rs)})   [pessimistic rank: every tied function counted ahead of the truth]")
    print(f"{'source':10} {'top1':>6} {'top3':>6} {'top5':>6} {'top10':>6} {'unlocalised':>12} {'mean avg-rank':>14}")
    for src in ("combined", "spectrum", "traceback", "semantic"):
        ranks = [r['rank'][src] for r in rs]
        found = [x for x in ranks if x]
        pess = lambda k: sum(1 for x in found if x[1] <= k)
        avg = statistics.mean(x[2] for x in found) if found else float('nan')
        print(f"{src:10} {pess(1):>3}/{len(rs):<2} {pess(3):>3}/{len(rs):<2} {pess(5):>3}/{len(rs):<2} {pess(10):>3}/{len(rs):<2} {len(rs)-len(found):>12} {avg:>14.2f}")
summarize(recs, "all subjects")
for s in sorted({r['subject'] for r in recs}): summarize([r for r in recs if r['subject']==s], s)
print("\nfaults with ANY traceback evidence (i.e. raised an exception inside repository code):",
      sum(r['has_traceback_evidence'] for r in recs), "of", len(recs))
print("median number of suspects with non-zero score:", statistics.median(r['n_suspects_scored'] for r in recs))
print("localization time (s): median %.1f, max %.1f" % (statistics.median(r['loc_seconds'] for r in recs), max(r['loc_seconds'] for r in recs)))
print("\nper-fault combined rank (opt, pess, avg) for the misses (pessimistic rank > 3):")
for r in recs:
    c = r['rank']['combined']
    if not c or c[1] > 3: print("  ", r['truth'], r['kind'], repr(r['original']), '->', repr(r['option']), 'failing', len(r['failing']), 'rank', c, 'spectrum', r['rank']['spectrum'])
print("\nby fault kind (combined, pessimistic top-3):")
for k in sorted({r['kind'] for r in recs}):
    rs=[r for r in recs if r['kind']==k]; print(f"  {k:8} {sum(1 for r in rs if r['rank']['combined'] and r['rank']['combined'][1]<=3)}/{len(rs)}")
