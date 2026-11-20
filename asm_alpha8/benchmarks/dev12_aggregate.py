import json, sys, glob, collections, statistics
recs = [json.loads(l) for f in sorted(glob.glob(sys.argv[1])) for l in open(f)]
n = len(recs)
print(f"{n} detected faults (fresh seed); by subject:", dict(collections.Counter(r['subject'] for r in recs)))
print("workflow status:", dict(collections.Counter(r['status'] for r in recs)))
res = [r for r in recs if r['status'] == 'resolved']
print(f"\n== REPAIR OUTCOME vs the differential oracle (resolved = {len(res)}/{n})")
oc = collections.Counter(r['oracle'] for r in res)
print("oracle classes:", dict(oc))
print(f"  correct (restored or equivalent on all compared inputs): {oc['restored'] + oc['equivalent']}/{len(res)}")
print(f"  confirmed WRONG (differs from the original program on a real input): {oc['wrong']}/{len(res)}")
print(f"  unknown (differential execution unavailable): {oc['unknown']}/{len(res)}")
print(f"  held-out tests passed by those confirmed wrong: {sum(1 for r in res if r['oracle']=='wrong' and r['held_out_passed'])}/{oc['wrong']}")
print("\n== CONFIDENCE LABELS vs the oracle")
print(f"{'label':8} {'n':>3} {'restored':>9} {'equiv':>6} {'WRONG':>6} {'unknown':>8}")
for lab in ('high', 'medium', 'low'):
    rs = [r for r in res if r.get('confidence') == lab]
    c = collections.Counter(r['oracle'] for r in rs)
    print(f"{lab:8} {len(rs):>3} {c['restored']:>9} {c['equivalent']:>6} {c['wrong']:>6} {c['unknown']:>8}")
flagged = [r for r in res if r.get('flags')]
print(f"\nflags present on {len(flagged)}/{len(res)} resolved repairs; of confirmed-wrong repairs flagged: "
      f"{sum(1 for r in res if r['oracle']=='wrong' and r.get('flags'))}/{oc['wrong']}; "
      f"of correct repairs flagged (false alarms): {sum(1 for r in res if r['oracle'] in ('restored','equivalent') and r.get('flags'))}/{oc['restored']+oc['equivalent']}")
print("flag counts:", dict(collections.Counter(f for r in res for f in r.get('flags', []))))
print("\n== COUNTEREXAMPLE SEARCH coverage")
print(f"  available on {sum(1 for r in res if r.get('cx_available'))}/{len(res)} accepted patches;"
      f" faults with >=1 other passing candidate: {sum(1 for r in res if r.get('n_alternatives'))}")
amb = [r for r in res if r.get('n_alternatives')]
for r in amb:
    print("   ", r['truth'].split('.')[-1], '| alternatives', r['n_alternatives'], '| cx_available', r.get('cx_available'), '| agree', r.get('cx_agree'), '| oracle', r['oracle'], '| conf', r.get('confidence'))
print("\n== SELECTION POLICY (faults where several candidates passed)")
pol = [r for r in res if r.get('candidates')]
def correct(c): return c['class'] in ('restored', 'equivalent')
for r in pol:
    cands = r['candidates']
    fps = [c['footprint'] for c in cands if c['footprint'] is not None]
    order = cands[0]; minfp = min(cands, key=lambda c: (c['footprint'] if c['footprint'] is not None else 9, cands.index(c)))
    print("   ", r['truth'].split('.')[-1], [(c['class'], c['footprint']) for c in cands], '| order picks', order['class'], '| min-footprint picks', minfp['class'])
if pol:
    print(f"  evidence-order picks a correct candidate in {sum(correct(r['candidates'][0]) for r in pol)}/{len(pol)}; "
          f"min-footprint in {sum(correct(min(r['candidates'], key=lambda c: (c['footprint'] if c['footprint'] is not None else 9))) for r in pol)}/{len(pol)}; "
          f"at least one correct candidate exists in {sum(any(correct(c) for c in r['candidates']) for r in pol)}/{len(pol)}")
print("\n== DEV10 evidence in localization (tie-break mode)")
w = [r['rank_with_dev10'] for r in recs]; wo = [r['rank_without_dev10'] for r in recs]
same = sum(1 for a, b in zip(w, wo) if a == b)
print(f"  rank identical with and without DEV10 evidence: {same}/{n}; faults where DEV10 evidence was non-zero for any suspect: {sum(1 for r in recs if r['dev10_nonzero_suspects'])}/{n}")
def top(rs, k): return sum(1 for x in rs if x and x[1] <= k)
print(f"  top-1 (pessimistic) with DEV10: {top(w,1)}/{n}, without: {top(wo,1)}/{n};  top-3: {top(w,3)}/{n} vs {top(wo,3)}/{n}")
print("\n== NOT RESOLVED:")
for r in recs:
    if r['status'] != 'resolved':
        print("  ", r['subject'], r['truth'].split('.')[-1], r['kind'], r['status'], f"{r['repair_seconds']}s")
print(f"\nrepair seconds: median {statistics.median(r['repair_seconds'] for r in recs):.1f}, max {max(r['repair_seconds'] for r in recs):.1f}")
