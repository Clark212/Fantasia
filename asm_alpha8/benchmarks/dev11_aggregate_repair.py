import json, sys, glob, statistics, collections
recs = [json.loads(l) for f in sorted(glob.glob(sys.argv[1])) for l in open(f)]
n = len(recs)
print(f"{n} detected faults repaired-or-attempted; by subject:", dict(collections.Counter(r['subject'] for r in recs)))
st = collections.Counter(r['repair_status'] for r in recs)
print("workflow status:", dict(st))
res = [r for r in recs if r['repair_status'] == 'resolved']
print(f"\nPLAUSIBLE (passes the tests it was given): {len(res)}/{n}")
print(f"  EXACT RESTORATION of the original program (AST-equal): {sum(r['restored'] for r in res)}/{len(res)}")
print(f"  patched the truly faulty function: {sum(r['truth_function_patched'] for r in res)}/{len(res)}")
print(f"  CORRECT by held-out tests the repair never saw: {sum(bool(r['held_out_passed']) for r in res)}/{len(res)}  "
      f"(held-out set sizes: {sorted({r['held_out_n'] for r in res})})")
print(f"  also passes the FULL original suite: {sum(r['full_suite_passed'] for r in res)}/{len(res)}")
print(f"  flagged with a behavioural caveat (DEV10 still_deviant): {sum(r['caveats'] > 0 for r in res)}/{len(res)}")
nr = [r for r in recs if r['repair_status'] != 'resolved']
print(f"\nNOT resolved: {len(nr)}/{n}")
for r in nr:
    print("  ", r['subject'], r['truth'].split('.')[-1], r['kind'], repr(r['original']), '->', repr(r['option']), '|', r['repair_status'],
          '| failing', len(r['failing']), '| rank', r['rank']['combined'], '| rejected', r['rejected'], f"{r['repair_seconds']}s")
print("\nrepair seconds: median %.1f, max %.1f" % (statistics.median(r['repair_seconds'] for r in recs), max(r['repair_seconds'] for r in recs)))
print("\nresolved by fault kind:")
for k in sorted({r['kind'] for r in recs}):
    rs = [r for r in recs if r['kind'] == k]; print(f"  {k:8} {sum(r['repair_status']=='resolved' for r in rs)}/{len(rs)}")
print("\ncontract rejections observed across all runs:", sum(r['rejected'].get('rejected_semantic_contract', 0) for r in recs))
print("localization of these 17 (combined, pessimistic top-3):", sum(1 for r in recs if r['rank']['combined'] and r['rank']['combined'][1] <= 3), "/", n)
