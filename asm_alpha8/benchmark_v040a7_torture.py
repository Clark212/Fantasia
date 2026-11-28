from __future__ import annotations
import json, math, random, statistics, tempfile
from pathlib import Path
from asm import ASMConfig, ASMEngine
from asm.evidence_dependency import EvidenceDependencyModel
from asm.planning import DiscreteBeliefState

SEED=40771

def flip(x): return 'B' if x=='A' else 'A'
def sense(rng,truth,r=.7): return truth if rng.random()<r else flip(truth)

def infer(seq, sources, dep=None, reliabilities=None):
    b=DiscreteBeliefState.from_mapping({'A':.5,'B':.5})
    scale=1.0 if dep is None else dep.effective_batch(sources)['scale']
    for i,(obs,source) in enumerate(zip(seq,sources)):
        r=.7 if reliabilities is None else reliabilities[i]
        likes={'A':r if obs=='A' else 1-r,'B':r if obs=='B' else 1-r}
        b=b.update_weighted(likes,evidence_weight=scale)
    p=b.as_dict(); pred=max(p,key=p.get)
    return pred,float(p[pred])

def metric(rows):
    acc=statistics.fmean(1.0 if ok else 0.0 for ok,c in rows)
    conf=statistics.fmean(c for ok,c in rows)
    return {'accuracy':acc,'confidence':conf,'calibration_gap':abs(acc-conf)}

def partial_self(q, *, train=1500, evaluate=12000):
    rng=random.Random(SEED+int(q*1000)); m=EvidenceDependencyModel()
    for t in range(train):
        truth='A' if rng.random()<.5 else 'B'
        if rng.random()<q:
            x=sense(rng,truth); seq=[x]*9
        else: seq=[sense(rng,truth) for _ in range(9)]
        m.observe_trial(f'p{q}-{t}',resolved_hypothesis=truth,observations={'s':seq})
    before=[]; after=[]; rr=random.Random(SEED+9000+int(q*1000))
    for _ in range(evaluate):
        truth='A' if rr.random()<.5 else 'B'
        if rr.random()<q:
            x=sense(rr,truth); seq=[x]*9
        else: seq=[sense(rr,truth) for _ in range(9)]
        p,c=infer(seq,['s']*9,None); before.append((p==truth,c))
        p,c=infer(seq,['s']*9,m); after.append((p==truth,c))
    return {'q':q,'learned':m.self_dependency('s'),'effective':m.effective_batch(['s']*9),'before':metric(before),'after':metric(after)}

rows={}
rows['partial_self']=[partial_self(q) for q in (.25,.5,.75)]

# 32-way extremes: full common noise should collapse to ~one clue; independent should remain ordinary Bayes.
for kind in ('common','independent'):
    rng=random.Random(SEED+(1 if kind=='common' else 2)); m=EvidenceDependencyModel(); names=[f's{i}' for i in range(32)]
    for t in range(500):
        truth='A' if rng.random()<.5 else 'B'
        if kind=='common':
            x=sense(rng,truth); obs={s:[x] for s in names}
        else: obs={s:[sense(rng,truth)] for s in names}
        m.observe_trial(f'{kind}-{t}',resolved_hypothesis=truth,observations=obs)
    eff=m.effective_batch(names)
    rows[f'32_{kind}']={'effective':eff,'stats':m.stats(),'pair_0_1':m.pair_dependency('s0','s1')}

# Random permutation invariance over mixed observations.
rng=random.Random(SEED+3); m=EvidenceDependencyModel(min_trials=16,min_abs_correlation=.1,min_fisher_z=2.0)
for t in range(100):
    truth='A' if rng.random()<.5 else 'B'; x=sense(rng,truth)
    m.observe_trial(f'o-{t}',resolved_hypothesis=truth,observations={'a':[x]*3,'b':[x],'c':[sense(rng,truth)]})
base_seq=['A','B','A','A','B']; base_sources=['a','b','a','c','a']; reliabilities=[.7,.7,.7,.7,.7]
p0,c0=infer(base_seq,base_sources,m,reliabilities)
max_diff=0.0
for _ in range(1000):
    idx=list(range(len(base_seq))); rng.shuffle(idx)
    p,c=infer([base_seq[i] for i in idx],[base_sources[i] for i in idx],m,[reliabilities[i] for i in idx])
    if p!=p0: max_diff=1.0
    max_diff=max(max_diff,abs(c-c0))
rows['order_invariance']={'permutations':1000,'max_probability_or_decision_difference':max_diff}

# False-positive stress with 16 independent sources and repeated independent readings.
false_self=0; false_pair=0; pair_tests=0
for seed in range(25):
    rr=random.Random(SEED+100+seed); dep=EvidenceDependencyModel(); names=[f's{i}' for i in range(16)]
    for t in range(300):
        truth='A' if rr.random()<.5 else 'B'
        obs={s:[sense(rr,truth),sense(rr,truth),sense(rr,truth)] for s in names}
        dep.observe_trial(f'{seed}-{t}',resolved_hypothesis=truth,observations=obs)
    false_self += sum(dep.correlation(s,s)>0 for s in names)
    for i,a in enumerate(names):
        for b in names[i+1:]:
            pair_tests+=1; false_pair += dep.correlation(a,b)>0
rows['false_positive_16_sources']={'runs':25,'trials_each':300,'self_tests':25*16,'false_self':false_self,'pair_tests':pair_tests,'false_pair':false_pair}

# Capacity and malformed-state hardening.
failures=[]
try:
    dep=EvidenceDependencyModel(max_trials=2,min_trials=8)
    dep.observe_trial('1',resolved_hypothesis='A',observations={'s':['A']}); dep.observe_trial('2',resolved_hypothesis='A',observations={'s':['A']}); dep.observe_trial('3',resolved_hypothesis='A',observations={'s':['A']})
except RuntimeError: failures.append('trial_capacity')
try:
    EvidenceDependencyModel().import_state({'schema':99})
except ValueError: failures.append('bad_schema')
try:
    EvidenceDependencyModel(max_sources=1,min_trials=8).observe_trial('x',resolved_hypothesis='A',observations={'a':['A'],'b':['A']})
except RuntimeError: failures.append('source_capacity')
rows['fail_closed']=sorted(failures)

checks={
 'partial_25_not_worse':rows['partial_self'][0]['after']['calibration_gap'] <= rows['partial_self'][0]['before']['calibration_gap'],
 'partial_50_improves':rows['partial_self'][1]['after']['calibration_gap'] < rows['partial_self'][1]['before']['calibration_gap']*.5,
 'partial_75_improves':rows['partial_self'][2]['after']['calibration_gap'] < rows['partial_self'][2]['before']['calibration_gap']*.25,
 'partial_decisions_preserved':all(abs(x['before']['accuracy']-x['after']['accuracy'])<1e-15 for x in rows['partial_self']),
 '32_common_collapses':abs(rows['32_common']['effective']['effective_count']-1.0)<1e-8,
 '32_independent_preserved':abs(rows['32_independent']['effective']['effective_count']-32.0)<1e-12,
 'order_invariant':max_diff<1e-14,
 'no_false_dependencies':false_self==0 and false_pair==0,
 'fail_closed':rows['fail_closed']==['bad_schema','source_capacity','trial_capacity'],
}
out={'benchmark':'ASM alpha.7 dependency torture','seed':SEED,'rows':rows,'checks':checks,'passed':sum(checks.values()),'total':len(checks)}
open('ALPHA7_TORTURE.json','w').write(json.dumps(out,indent=2,sort_keys=True)+'\n')
print(json.dumps(out,indent=2,sort_keys=True))
if not all(checks.values()): raise SystemExit(1)
