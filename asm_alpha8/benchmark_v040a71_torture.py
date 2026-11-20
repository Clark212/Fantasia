from __future__ import annotations

import copy
import json
import math
import random
import statistics
import tempfile
from pathlib import Path

from asm import ASMConfig, ASMEngine
from asm.evidence_dependency import EvidenceDependencyModel
from asm.planning import DiscreteBeliefState

SEED = 47171


def flip(x): return "B" if x == "A" else "A"
def sense(r, truth, p=.7): return truth if r.random() < p else flip(truth)

def self_seq(r, truth, q, n=9):
    if r.random() < q:
        x = sense(r, truth); return [x] * n
    return [sense(r, truth) for _ in range(n)]

def cross_rows(r, truth, q, names):
    if r.random() < q:
        x = sense(r, truth); return {s: [x] for s in names}
    return {s: [sense(r, truth)] for s in names}

def train_self_regimes(qs, seed, phase_trials=500):
    r=random.Random(seed); m=EvidenceDependencyModel(); idx=0
    for phase,q in enumerate(qs):
        for t in range(phase_trials):
            truth="A" if r.random()<.5 else "B"; idx+=1
            m.observe_trial(f"{phase}-{t}",resolved_hypothesis=truth,
                            observations={"s":self_seq(r,truth,q)},temporal_index=idx)
    return m

def train_cross_regimes(qs, seed, n=4, phase_trials=700):
    r=random.Random(seed); m=EvidenceDependencyModel(); idx=0; names=[f"s{i}" for i in range(n)]
    for phase,q in enumerate(qs):
        for t in range(phase_trials):
            truth="A" if r.random()<.5 else "B"; idx+=1
            m.observe_trial(f"{phase}-{t}",resolved_hypothesis=truth,
                            observations=cross_rows(r,truth,q,names),temporal_index=idx)
    return m,names

rows={}

# 1) Material partial-dependency shifts in both directions.
partial_self=[]
for qs in ((.25,.75),(.75,.25)):
    m=train_self_regimes(qs,SEED+int(qs[0]*100)+int(qs[1]*100))
    partial_self.append({"shift":qs,"regimes":m.dependency_regimes("s"),"status":m.self_dependency("s")})
rows["partial_self_shifts"]=partial_self

partial_cross=[]
for qs in ((.25,.75),(.75,.25)):
    m,names=train_cross_regimes(qs,SEED+1000+int(qs[0]*100)+int(qs[1]*100))
    partial_cross.append({"shift":qs,"regimes":m.dependency_regimes(names[0],names[1]),"status":m.pair_dependency(names[0],names[1])})
rows["partial_cross_shifts"]=partial_cross

# Explicit 25 -> 50 -> 75 and 75 -> 50 -> 25 tracking. Moderate
# changes may update the recent view without forcing a discrete regime split.
def track_self_levels(levels, seed, phase_trials=700):
    r=random.Random(seed); m=EvidenceDependencyModel(); idx=0; snapshots=[]
    for phase,q in enumerate(levels):
        for t in range(phase_trials):
            truth="A" if r.random()<.5 else "B"; idx+=1
            m.observe_trial(f"levels-self-{phase}-{t}",resolved_hypothesis=truth,
                            observations={"s":self_seq(r,truth,q)},temporal_index=idx)
        st=m.self_dependency("s")
        snapshots.append({"shared_fraction":q,"raw_correlation":st["raw_correlation"],
                          "active_correlation":st["active_correlation"],"regime_count":st["regime_count"]})
    return snapshots

def track_cross_levels(levels, seed, phase_trials=900):
    r=random.Random(seed); m=EvidenceDependencyModel(); idx=0; names=[f"s{i}" for i in range(4)]; snapshots=[]
    for phase,q in enumerate(levels):
        for t in range(phase_trials):
            truth="A" if r.random()<.5 else "B"; idx+=1
            m.observe_trial(f"levels-cross-{phase}-{t}",resolved_hypothesis=truth,
                            observations=cross_rows(r,truth,q,names),temporal_index=idx)
        st=m.pair_dependency(names[0],names[1])
        snapshots.append({"shared_fraction":q,"raw_correlation":st["raw_correlation"],
                          "active_correlation":st["active_correlation"],"regime_count":st["regime_count"]})
    return snapshots

rows["partial_three_level_tracking"]={
    "self_up":track_self_levels((.25,.5,.75),SEED+1100),
    "self_down":track_self_levels((.75,.5,.25),SEED+1101),
    "cross_up":track_cross_levels((.25,.5,.75),SEED+1102),
    "cross_down":track_cross_levels((.75,.5,.25),SEED+1103),
}
def monotone_tracking(rows_, increasing):
    vals=[float(x["raw_correlation"]) for x in rows_]
    return (vals[0] < vals[1] < vals[2]) if increasing else (vals[0] > vals[1] > vals[2])
partial_levels_ok=(
    monotone_tracking(rows["partial_three_level_tracking"]["self_up"],True) and
    monotone_tracking(rows["partial_three_level_tracking"]["self_down"],False) and
    monotone_tracking(rows["partial_three_level_tracking"]["cross_up"],True) and
    monotone_tracking(rows["partial_three_level_tracking"]["cross_down"],False)
)

# 2) Stationary self-dependency torture: 0/25/50/75/100% dependence, 100 runs.
qs=(0,.25,.5,.75,1.0); false_self=0
for run in range(100):
    q=qs[run%len(qs)]; r=random.Random(SEED+2000+run); m=EvidenceDependencyModel()
    for t in range(700):
        truth="A" if r.random()<.5 else "B"
        m.observe_trial(f"{run}-{t}",resolved_hypothesis=truth,
                        observations={"s":self_seq(r,truth,q)},temporal_index=t+1)
    false_self += max(0,len(m.dependency_regimes("s"))-1)
rows["stationary_self"]={"runs":100,"false_splits":false_self}

# 3) Stationary cross-source torture with stricter pair gate, 24 runs.
false_cross=0
for run in range(24):
    q=qs[run%len(qs)]; r=random.Random(SEED+3000+run); m=EvidenceDependencyModel(); names=[f"s{i}" for i in range(4)]
    for t in range(700):
        truth="A" if r.random()<.5 else "B"
        m.observe_trial(f"{run}-{t}",resolved_hypothesis=truth,
                        observations=cross_rows(r,truth,q,names),temporal_index=t+1)
    for i,a in enumerate(names):
        for b in names[i+1:]:
            false_cross += max(0,len(m.dependency_regimes(a,b))-1)
rows["stationary_cross"]={"runs":24,"false_splits":false_cross}

# 4) Source-count extremes: 2,3,4,8,16,32, common vs independent.
source_extremes=[]
finite=True
for n in (2,3,4,8,16,32):
    for q,label in ((1.0,"common"),(0.0,"independent")):
        r=random.Random(SEED+4000+n+(100 if q else 0)); m=EvidenceDependencyModel(); names=[f"s{i}" for i in range(n)]
        for t in range(260):
            truth="A" if r.random()<.5 else "B"
            m.observe_trial(f"{n}-{label}-{t}",resolved_hypothesis=truth,
                            observations=cross_rows(r,truth,q,names),temporal_index=t+1)
        eff=m.effective_batch(names)
        finite = finite and all(math.isfinite(float(v)) for v in eff.values())
        source_extremes.append({"n":n,"kind":label,"effective":eff["effective_count"]})
rows["source_extremes"]=source_extremes

# 5) Unordered/non-temporal trials retain alpha.7 cumulative semantics and are order-invariant.
def build_unordered(order):
    base=[]; r=random.Random(SEED+5000)
    for t in range(500):
        truth="A" if r.random()<.5 else "B"; vals=self_seq(r,truth,.5)
        base.append((t,truth,vals))
    m=EvidenceDependencyModel()
    for i in order:
        t,truth,vals=base[i]
        m.observe_trial(str(t),resolved_hypothesis=truth,observations={"s":vals})
    return m
m1=build_unordered(list(range(500)))
perm=list(range(500)); random.Random(SEED+5001).shuffle(perm)
m2=build_unordered(perm)
rows["non_temporal_order"]={
    "r1":m1.self_dependency("s")["raw_correlation"],
    "r2":m2.self_dependency("s")["raw_correlation"],
    "regimes1":len(m1.dependency_regimes("s")),"regimes2":len(m2.dependency_regimes("s")),
}

# 6) Fail-closed malformed/decreasing indices and capacity rejection are atomic.
fail_closed=[]
m=EvidenceDependencyModel(max_sources=1)
m.observe_trial("ok",resolved_hypothesis="A",observations={"a":["A","A"]},temporal_index=5)
for name,call in (
    ("decreasing",lambda: m.observe_trial("d",resolved_hypothesis="A",observations={"a":["A"]},temporal_index=4)),
    ("nan",lambda: m.observe_trial("n",resolved_hypothesis="A",observations={"a":["A"]},temporal_index=float("nan"))),
    ("bool",lambda: m.observe_trial("bool",resolved_hypothesis="A",observations={"a":["A"]},temporal_index=True)),
    ("string",lambda: m.observe_trial("str",resolved_hypothesis="A",observations={"a":["A"]},temporal_index="not-a-time")),
    ("source_capacity",lambda: m.observe_trial("c",resolved_hypothesis="A",observations={"a":["A"],"b":["A"]},temporal_index=6)),
):
    before=copy.deepcopy(m.export_state())
    try: call()
    except (ValueError,RuntimeError):
        if before==m.export_state(): fail_closed.append(name)

# Pair-capacity failure is tested separately so the source cap does not mask it.
pm=EvidenceDependencyModel(max_sources=4,max_pairs=1)
pm.observe_trial("p-ok",resolved_hypothesis="A",observations={"a":["A"],"b":["A"]},temporal_index=1)
before=copy.deepcopy(pm.export_state())
try:
    pm.observe_trial("p-cap",resolved_hypothesis="A",observations={"a":["A"],"b":["A"],"c":["A"]},temporal_index=2)
except RuntimeError:
    if before==pm.export_state(): fail_closed.append("pair_capacity")
rows["fail_closed"]=fail_closed

# 7) Inference order invariance and no training from inference.
with tempfile.TemporaryDirectory() as td:
    e=ASMEngine(Path(td)/"x.db",config=ASMConfig(snapshot_every_events=999999,prune_every_events=999999,
                evidence_dependency_min_trials=16,evidence_dependency_min_abs_correlation=.1,evidence_dependency_min_fisher_z=2.0))
    r=random.Random(SEED+6000)
    for t in range(120):
        truth="A" if r.random()<.5 else "B"; x=sense(r,truth)
        e.observe_evidence_dependency_trial(str(t),resolved_hypothesis=truth,
            observations={"a":[x],"b":[x]},temporal_index=t+1)
    batch=[{"source_id":"a","observation":"A","supplied_reliability":.7},
           {"source_id":"b","observation":"B","supplied_reliability":.7},
           {"source_id":"a","observation":"A","supplied_reliability":.7}]
    before=e.evidence_dependency.version
    p1=e.update_belief_from_evidence_batch({"A":.5,"B":.5},evidence=batch).as_dict()
    p2=e.update_belief_from_evidence_batch({"A":.5,"B":.5},evidence=list(reversed(batch))).as_dict()
    after=e.evidence_dependency.version
    rows["inference_contract"]={"posterior_diff":abs(p1["A"]-p2["A"]),"version_before":before,"version_after":after}
    e.close(save_snapshot=False)

# 8) Schema-1 migration: preserve cumulative data exactly and invent no temporal history.
legacy=EvidenceDependencyModel(); r=random.Random(SEED+7000)
for t in range(300):
    truth="A" if r.random()<.5 else "B"; x=sense(r,truth)
    legacy.observe_trial(str(t),resolved_hypothesis=truth,observations={"s":[x]*9})
payload=legacy.export_state(); payload["schema"]=1; payload.pop("temporal",None)
legacy_r=legacy.self_dependency("s")["cumulative_raw_correlation"]
migrated=EvidenceDependencyModel(); migrated.import_state(payload)
rows["migration"]={"trials":migrated.stats()["trials"],"same_r":legacy_r==migrated.self_dependency("s")["cumulative_raw_correlation"],
                   "temporal_views":migrated.stats()["temporal_self_views"],"regimes":len(migrated.dependency_regimes("s"))}

# 9) Recent query remains finite under all partial stationary levels.
finite_partials=True
for i,q in enumerate(qs):
    m=train_self_regimes((q,),SEED+8000+i,phase_trials=300)
    st=m.self_dependency("s"); eff=m.effective_batch(["s"]*9)
    finite_partials = finite_partials and all(math.isfinite(float(v)) for v in (st["raw_correlation"],st["active_correlation"],eff["effective_count"],eff["scale"]))

checks={
    "partial_shifts_detected_both_directions": all(len(x["regimes"])>=2 for x in partial_self) and all(len(x["regimes"])>=2 for x in partial_cross) and partial_levels_ok,
    "stationary_self_zero_false_splits_100": false_self==0,
    "stationary_cross_zero_false_splits_24": false_cross==0,
    "source_count_extremes_and_finite": finite and all((x["effective"]<1.000001 if x["kind"]=="common" else abs(x["effective"]-x["n"])<1e-12) for x in source_extremes),
    "non_temporal_order_invariant_alpha7_semantics": abs(rows["non_temporal_order"]["r1"]-rows["non_temporal_order"]["r2"])<1e-14 and rows["non_temporal_order"]["regimes1"]==0 and rows["non_temporal_order"]["regimes2"]==0,
    "malformed_and_capacity_fail_atomic": fail_closed==["decreasing","nan","bool","string","source_capacity","pair_capacity"],
    "inference_order_invariant_and_read_only": rows["inference_contract"]["posterior_diff"]<1e-14 and rows["inference_contract"]["version_before"]==rows["inference_contract"]["version_after"],
    "schema1_migration_no_fake_temporal_history": rows["migration"]=={"trials":300,"same_r":True,"temporal_views":0,"regimes":0},
    "no_nan_inf": finite_partials,
}
out={"benchmark":"ASM alpha.7.1 dependency regime torture","rows":rows,"checks":checks,"passed":sum(checks.values()),"total":len(checks)}
open("ALPHA71_TORTURE.json","w").write(json.dumps(out,indent=2,sort_keys=True)+"\n")
print(json.dumps({"passed":out["passed"],"total":out["total"],"checks":checks,"summary":{"false_self":false_self,"false_cross":false_cross,"partial_self_regimes":[len(x["regimes"]) for x in partial_self],"partial_cross_regimes":[len(x["regimes"]) for x in partial_cross]}},indent=2,sort_keys=True))
if not all(checks.values()): raise SystemExit(1)
