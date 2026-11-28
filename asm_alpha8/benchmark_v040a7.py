from __future__ import annotations
import json, math, random, statistics
from dataclasses import asdict, dataclass
from asm.evidence_dependency import EvidenceDependencyModel
from asm.planning import DiscreteBeliefState

SEED=4070
TRAIN=500
EVAL=10000
CLUES=9

@dataclass
class Metrics:
    accuracy: float
    confidence: float
    calibration_gap: float
    brier: float

def score(rows):
    acc=statistics.fmean(1.0 if ok else 0.0 for ok,c in rows)
    conf=statistics.fmean(c for ok,c in rows)
    return Metrics(acc,conf,abs(acc-conf),statistics.fmean((c-(1.0 if ok else 0.0))**2 for ok,c in rows))

def flip(x): return 'B' if x=='A' else 'A'
def sensor(rng,truth,r=.7): return truth if rng.random()<r else flip(truth)

def infer(seq, source_ids, dep=None, r=.7):
    b=DiscreteBeliefState.from_mapping({'A':.5,'B':.5})
    scale=1.0 if dep is None else dep.effective_batch(source_ids)['scale']
    for obs,sid in zip(seq,source_ids):
        likes={'A':r if obs=='A' else 1-r,'B':r if obs=='B' else 1-r}
        b=b.update_weighted(likes,evidence_weight=scale)
    p=b.as_dict(); pred=max(p,key=p.get)
    return pred,float(p[pred])

def train_self(kind):
    rng=random.Random(SEED+1+(0 if kind=='corr' else 10))
    m=EvidenceDependencyModel()
    for t in range(TRAIN):
        truth='A' if rng.random()<.5 else 'B'
        if kind=='corr':
            base=sensor(rng,truth); seq=[base]*CLUES
        else: seq=[sensor(rng,truth) for _ in range(CLUES)]
        m.observe_trial(f'{kind}-{t}',resolved_hypothesis=truth,observations={'s':seq})
    return m

def train_cross(kind):
    rng=random.Random(SEED+2+(0 if kind=='corr' else 10)); m=EvidenceDependencyModel()
    names=[f's{i}' for i in range(CLUES)]
    for t in range(TRAIN):
        truth='A' if rng.random()<.5 else 'B'
        if kind=='corr':
            base=sensor(rng,truth); rows={s:[base] for s in names}
        else: rows={s:[sensor(rng,truth)] for s in names}
        m.observe_trial(f'{kind}-{t}',resolved_hypothesis=truth,observations=rows)
    return m

def evaluate(kind,dep=None,cross=False):
    rng=random.Random(SEED+100+(1 if kind=='corr' else 2)+(10 if cross else 0)); rows=[]
    names=[f's{i}' for i in range(CLUES)] if cross else ['s']*CLUES
    for _ in range(EVAL):
        truth='A' if rng.random()<.5 else 'B'
        if kind=='corr':
            base=sensor(rng,truth); seq=[base]*CLUES
        else: seq=[sensor(rng,truth) for _ in range(CLUES)]
        pred,conf=infer(seq,names,dep)
        rows.append((pred==truth,conf))
    return asdict(score(rows))

self_corr=train_self('corr'); self_ind=train_self('ind')
cross_corr=train_cross('corr'); cross_ind=train_cross('ind')
results={
 'self_correlated':{'before':evaluate('corr',None,False),'after':evaluate('corr',self_corr,False),'learned':self_corr.self_dependency('s')},
 'self_independent':{'before':evaluate('ind',None,False),'after':evaluate('ind',self_ind,False),'learned':self_ind.self_dependency('s')},
 'cross_correlated':{'before':evaluate('corr',None,True),'after':evaluate('corr',cross_corr,True),'learned_pair':cross_corr.pair_dependency('s0','s1')},
 'cross_independent':{'before':evaluate('ind',None,True),'after':evaluate('ind',cross_ind,True),'learned_pair':cross_ind.pair_dependency('s0','s1')},
}
# False-positive stress across stationary independent worlds.
false_active=0; total_pairs=0; self_false=0
for seed in range(40):
    rng=random.Random(9000+seed); m=EvidenceDependencyModel(); names=[f's{i}' for i in range(8)]
    for t in range(300):
        truth='A' if rng.random()<.5 else 'B'
        rows={s:[sensor(rng,truth),sensor(rng,truth),sensor(rng,truth)] for s in names}
        m.observe_trial(f'{seed}-{t}',resolved_hypothesis=truth,observations=rows)
    self_false += sum(1 for s in names if m.correlation(s,s)>0)
    for i,a in enumerate(names):
        for b in names[i+1:]:
            total_pairs+=1
            if m.correlation(a,b)>0: false_active+=1
results['false_positive_stress']={'runs':40,'trials_per_run':300,'self_tests':40*8,'active_self_false':self_false,'pair_tests':total_pairs,'active_pair_false':false_active}
# Full-correlation detection latency, checked after each resolved trial.
rng=random.Random(12345); m=EvidenceDependencyModel(); activated=None
for t in range(1,201):
    truth='A' if rng.random()<.5 else 'B'; base=sensor(rng,truth)
    m.observe_trial(f'd-{t}',resolved_hypothesis=truth,observations={'s':[base]*CLUES})
    if activated is None and m.correlation('s','s')>0: activated=t
results['detection_latency_full_copy']={'trials_to_active':activated,'minimum_trials':m.min_trials}
checks={
 'self_corr_gap_below_1pct':results['self_correlated']['after']['calibration_gap']<.01,
 'self_corr_improves_gap_20x':results['self_correlated']['before']['calibration_gap']>20*results['self_correlated']['after']['calibration_gap'],
 'self_independent_unchanged':abs(results['self_independent']['before']['confidence']-results['self_independent']['after']['confidence'])<1e-12,
 'cross_corr_gap_below_1pct':results['cross_correlated']['after']['calibration_gap']<.01,
 'cross_independent_unchanged':abs(results['cross_independent']['before']['confidence']-results['cross_independent']['after']['confidence'])<1e-12,
 'no_false_dependencies':self_false==0 and false_active==0,
 'full_copy_detected':activated is not None and activated<=80,
}
out={'benchmark':'ASM alpha.7 hidden evidence dependency learning','seed':SEED,'train_trials':TRAIN,'eval_trials':EVAL,'clues':CLUES,'results':results,'checks':checks,'passed':sum(checks.values()),'total':len(checks)}
print(json.dumps(out,indent=2,sort_keys=True))
open('ALPHA7_BEFORE_AFTER.json','w').write(json.dumps(out,indent=2,sort_keys=True)+'\n')
if not all(checks.values()): raise SystemExit(1)
