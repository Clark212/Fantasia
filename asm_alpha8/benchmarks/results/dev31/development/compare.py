"""Compare the old and new phase-3 outputs input by input (candidates exactly; timings reported)."""
import json, sys
old = {r["id"]: r for r in map(json.loads, open(sys.argv[1]))}
new = {r["id"]: r for r in map(json.loads, open(sys.argv[2]))}
both = [k for k in old if k in new]
diff = [k for k in both if any(old[k][f] != new[k][f] for f in ("knowledge", "shapes", "steps"))]
n = sum(len(old[k][f]) for k in both for f in ("knowledge", "shapes", "steps"))
to, tn = sum(old[k]["seconds"] for k in both), sum(new[k]["seconds"] for k in both)
print(f"compared {len(both)} inputs ({n} candidates): {len(diff)} differ; seconds old {to:.0f}, new {tn:.0f} ({to / max(tn, 1e-9):.1f}x)")
for k in diff[:5]:
    print("DIFFERS:", k, {f: (len(old[k][f]), len(new[k][f]), old[k][f] == new[k][f]) for f in ("knowledge", "shapes", "steps")})
