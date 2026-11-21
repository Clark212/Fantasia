"""Aggregate dev13_calibration.py output: flag/label calibration against the differential oracle, per suite strength."""
import collections
import glob
import json
import math
import sys


from dev13_stats import pct  # noqa: E402


recs = [json.loads(l) for f in sorted(glob.glob(sys.argv[1])) for l in open(f)]
print(f"{len(recs)} detected faults; by subject: {dict(collections.Counter(r['subject'] for r in recs))}")
CORRECT = {"restored", "equivalent"}
for strength in ("half", "weak"):
    runs = [dict(r[strength], subject=r["subject"], truth=r["truth"]) for r in recs if strength in r]
    ok = [x for x in runs if "skipped" not in x]
    print(f"\n{'=' * 100}\nSUITE STRENGTH: {strength}  ({len(ok)} faults analysed, {len(runs) - len(ok)} skipped: "
          f"{dict(collections.Counter(x.get('skipped') for x in runs if 'skipped' in x))})")
    pats = [dict(p, subject=x["subject"]) for x in ok for p in x["patches"]]
    cls = collections.Counter(p["class"] for p in pats)
    wrong = [p for p in pats if p["class"] == "wrong"]
    corr = [p for p in pats if p["class"] in CORRECT]
    print(f"\nA. PLAUSIBLE PATCHES: {len(pats)}; oracle classes {dict(cls)}; faults containing >=1 wrong plausible patch: "
          f"{sum(1 for x in ok if any(p['class'] == 'wrong' for p in x['patches']))}/{len(ok)}; verification available on "
          f"{sum(p['verified'] for p in pats)}/{len(pats)}")
    print(f"   by subject: " + "; ".join(f"{s}: {dict(collections.Counter(p['class'] for p in pats if p['subject'] == s))}"
                                       for s in sorted({p['subject'] for p in pats})))
    print(f"\n   {'flag':40} {'fires on WRONG':>24} {'fires on CORRECT (false alarm)':>32}")
    for fl in sorted({f for p in pats for f in p["flags"]}):
        print(f"   {fl:40} {sum(fl in p['flags'] for p in wrong):>10}/{len(wrong):<13} {sum(fl in p['flags'] for p in corr):>14}/{len(corr):<17}")
    print(f"\n   {'label':7} {'n':>4} {'restored':>9} {'equiv':>6} {'WRONG':>6} {'unknown':>8}   P(wrong | label), known only")
    for lab in ("high", "medium", "low"):
        ps = [p for p in pats if p["label"] == lab]
        c = collections.Counter(p["class"] for p in ps)
        known = c["restored"] + c["equivalent"] + c["wrong"]
        print(f"   {lab:7} {len(ps):>4} {c['restored']:>9} {c['equivalent']:>6} {c['wrong']:>6} {c['unknown']:>8}   {pct(c['wrong'], known)}")
    print(f"\n   detection of wrong patches:  any flag {pct(sum(bool(p['flags']) for p in wrong), len(wrong))};"
          f"  label low {pct(sum(p['label'] == 'low' for p in wrong), len(wrong))}")
    print(f"   false alarms on correct:     any flag {pct(sum(bool(p['flags']) for p in corr), len(corr))};"
          f"  label low {pct(sum(p['label'] == 'low' for p in corr), len(corr))}")
    wfs = [dict(x["workflow"], subject=x["subject"], truth=x["truth"]) for x in ok if "workflow" in x]
    st = collections.Counter(w["status"] for w in wfs)
    res = [w for w in wfs if w["status"] == "resolved"]
    wc = collections.Counter(w.get("class") for w in res)
    print(f"\nB. REAL WORKFLOW: {len(wfs)} runs, status {dict(st)}; chosen-patch oracle classes {dict(wc)}")
    print(f"   accepted & correct {pct(wc['restored'] + wc['equivalent'], len(res))};  accepted & WRONG {pct(wc['wrong'], len(res))};"
          f"  unknown {wc['unknown']}")
    for lab in ("high", "medium", "low"):
        ws = [w for w in res if w.get("label") == lab]
        c = collections.Counter(w.get("class") for w in ws)
        print(f"   label {lab:7} n={len(ws):<3} correct {c['restored'] + c['equivalent']}, WRONG {c['wrong']}, unknown {c['unknown']}")
    for w in res:
        if w.get("class") == "wrong":
            print(f"   WRONG accepted: {w['subject']} truth={w['truth'].split('.')[-1]} patched={w['suspect'].split('.')[-1]} "
                  f"{w['desc'][:45]} | label {w['label']} {w['flags']}")
    print(f"   localization top-1 (pessimistic): {sum(1 for x in ok if x['rank'] and x['rank'][1] <= 1)}/{len(ok)}, "
          f"top-3: {sum(1 for x in ok if x['rank'] and x['rank'][1] <= 3)}/{len(ok)}")
