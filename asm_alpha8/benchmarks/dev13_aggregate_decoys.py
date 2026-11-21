"""Aggregate dev13_decoys.py: can the flags and labels tell DELIBERATELY INCORRECT (but test-passing) repairs from correct ones?"""
import collections
import glob
import json
import sys

from dev13_stats import pct

recs = [json.loads(l) for f in sorted(glob.glob(sys.argv[1])) for l in open(f)]
print(f"{len(recs)} faults; by subject: {dict(collections.Counter(r['subject'] for r in recs))}")
CORRECT = {"restored", "equivalent"}
for strength in ("half", "weak"):
    rows = [dict(row, subject=r["subject"]) for r in recs if strength in r and "rows" in r[strength] for row in r[strength]["rows"]]
    skipped = sum(1 for r in recs if strength in r and "skipped" in r[strength])
    print(f"\n{'=' * 100}\nSUITE STRENGTH: {strength}  ({skipped} faults skipped)")
    for kind in ("true_fix", "single", "decoy"):
        ks = [x for x in rows if x["kind"] == kind]
        print(f"   {kind:9} n={len(ks):<4} oracle {dict(collections.Counter(x['class'] for x in ks))}")
    decoys = [x for x in rows if x["kind"] == "decoy"]
    tried = sum(r[strength].get("tried_decoys", 0) for r in recs if strength in r and "rows" in r[strength])
    print(f"   decoys constructed {tried}; passed the repair suite (kept) {len(decoys)}")
    wrong = [x for x in decoys if x["class"] == "wrong"]
    benign = [x for x in decoys if x["class"] in CORRECT]
    correct = [x for x in rows if x["kind"] in ("true_fix", "single") and x["class"] in CORRECT]
    print(f"\n   WRONG decoys (test-passing, behaviour confirmed different from the correct program): {len(wrong)}"
          f";  benign decoys (extra edit had no observable effect): {len(benign)};  correct controls: {len(correct)}")
    print(f"\n   {'flag':40} {'on WRONG decoys':>26} {'on CORRECT controls':>26}")
    for fl in sorted({f for x in wrong + correct for f in x["flags"]}):
        print(f"   {fl:40} {sum(fl in x['flags'] for x in wrong):>12}/{len(wrong):<13} {sum(fl in x['flags'] for x in correct):>12}/{len(correct):<13}")
    print(f"\n   detection (WRONG flagged):      any flag {pct(sum(bool(x['flags']) for x in wrong), len(wrong))}")
    print(f"                                   label low {pct(sum(x['label'] == 'low' for x in wrong), len(wrong))}")
    print(f"   false alarms (CORRECT flagged): any flag {pct(sum(bool(x['flags']) for x in correct), len(correct))}")
    print(f"                                   label low {pct(sum(x['label'] == 'low' for x in correct), len(correct))}")
    print(f"\n   {'label':7} {'WRONG':>6} {'correct':>8}   P(wrong | label) among wrong decoys + correct controls")
    for lab in ("high", "medium", "low"):
        w = sum(x["label"] == lab for x in wrong)
        c = sum(x["label"] == lab for x in correct)
        print(f"   {lab:7} {w:>6} {c:>8}   {pct(w, w + c)}")
    print("\n   by subject (wrong decoys flagged / wrong decoys):",
          "; ".join(f"{s}: {sum(bool(x['flags']) for x in wrong if x['subject'] == s)}/{sum(x['subject'] == s for x in wrong)}"
                    for s in sorted({x['subject'] for x in decoys})))
    unflagged = [x for x in wrong if not x["flags"]]
    if unflagged:
        print(f"   examples of WRONG decoys that got NO flag ({len(unflagged)}):")
        for x in unflagged[:5]:
            print(f"      {x['subject']}: {x['desc'][:70]} (verified={x['verified']})")
