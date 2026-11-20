from __future__ import annotations
import json, random, statistics, time, math
from asm.evidence_dependency import EvidenceDependencyModel

SEED=471710

def flip(x): return 'B' if x=='A' else 'A'
def sense(r,t): return t if r.random()<.7 else flip(t)

def train(trials:int, sources:int, temporal:bool) -> tuple[float,EvidenceDependencyModel]:
    r=random.Random(SEED+trials*3+sources+(100 if temporal else 0)); m=EvidenceDependencyModel(); names=[f's{i}' for i in range(sources)]
    t0=time.perf_counter()
    for i in range(trials):
        truth='A' if r.random()<.5 else 'B'
        if sources==1:
            x=sense(r,truth); rows={'s0':[x]*9}
        else:
            common=sense(r,truth) if r.random()<.5 else None
            rows={s:[common if common is not None else sense(r,truth)] for s in names}
        kw={'temporal_index':i+1} if temporal else {}
        m.observe_trial(str(i),resolved_hypothesis=truth,observations=rows,**kw)
    return time.perf_counter()-t0,m

def median_runtime(trials,sources,temporal,reps=3):
    vals=[]; last=None
    for _ in range(reps):
        dt,last=train(trials,sources,temporal); vals.append(dt)
    return statistics.median(vals),vals,last

# Warm-up imports/bytecode.
train(50,1,False); train(50,1,True)

rows={}
for sources in (1,9):
    base,base_runs,_=median_runtime(1000,sources,False)
    temp,temp_runs,_=median_runtime(1000,sources,True)
    rows[f'{sources}_source_1000']={
        'non_temporal_seconds_median':base,'temporal_seconds_median':temp,
        'temporal_overhead_x':temp/base if base else None,
        'non_temporal_runs':base_runs,'temporal_runs':temp_runs,
    }

long_dt,long_model=train(3000,9,True)
rows['9_source_3000_temporal']={'seconds':long_dt,'trials_per_second':3000.0/long_dt}

# O(1) query vs a faithful 192-item rescan reference over the same recent self window.
_,m=train(1000,1,True)
state=m.export_state()['temporal']['self']['s0']['recent']['items']

def rescan_corr(items):
    n=0; sx=sy=sx2=sy2=sxy=0.0
    for item in items:
        s=item['stats']; n+=int(s['n']); sx+=s['sum_x']; sy+=s['sum_y']; sx2+=s['sum_x2']; sy2+=s['sum_y2']; sxy+=s['sum_xy']
    if n<2: return 0.0
    nf=float(n); vx=sx2-sx*sx/nf; vy=sy2-sy*sy/nf
    if vx<=1e-15 or vy<=1e-15: return 0.0
    return max(-1.0,min(1.0,(sxy-sx*sy/nf)/math.sqrt(vx*vy)))

loops=10000
t0=time.perf_counter()
for _ in range(loops): m.self_dependency('s0')
o1=time.perf_counter()-t0
t0=time.perf_counter()
for _ in range(loops): rescan_corr(state)
scan=time.perf_counter()-t0
rows['query_profile']={
    'loops':loops,'recent_items':len(state),'o1_seconds':o1,'rescan_reference_seconds':scan,
    'rescan_over_o1_x':scan/o1 if o1 else None,
    'note':'Reference rescan emulates the rejected bounded-window rescanning cost; it is not a recovered copy of the interrupted WIP implementation.'
}

out={'benchmark':'ASM alpha.7.1 O(1) dependency performance profile','rows':rows}
open('ALPHA71_PERFORMANCE.json','w').write(json.dumps(out,indent=2,sort_keys=True)+'\n')
print(json.dumps(out,indent=2,sort_keys=True))
