from __future__ import annotations
import json, random, statistics
from asm.evidence_dependency import EvidenceDependencyModel
from asm.planning import DiscreteBeliefState

def flip(x): return 'B' if x=='A' else 'A'
def sense(r,t): return t if r.random()<.7 else flip(t)
def make_seq(r,truth,corr):
    if corr:
        x=sense(r,truth); return [x]*9
    return [sense(r,truth) for _ in range(9)]
def infer(seq,dep):
    b=DiscreteBeliefState.from_mapping({'A':.5,'B':.5}); scale=dep.effective_batch(['s']*9)['scale']
    for o in seq:
        b=b.update_weighted({'A':.7 if o=='A' else .3,'B':.7 if o=='B' else .3},evidence_weight=scale)
    p=b.as_dict(); k=max(p,key=p.get); return k,p[k]
def run(first_corr,second_corr,seed):
    r=random.Random(seed); d=EvidenceDependencyModel()
    for phase,corr in enumerate((first_corr,second_corr)):
        for t in range(1000):
            truth='A' if r.random()<.5 else 'B'; seq=make_seq(r,truth,corr)
            d.observe_trial(f'{phase}-{t}',resolved_hypothesis=truth,observations={'s':seq})
    rr=random.Random(seed+9999); rows=[]
    for _ in range(10000):
        truth='A' if rr.random()<.5 else 'B'; seq=make_seq(rr,truth,second_corr); p,c=infer(seq,d); rows.append((p==truth,c))
    acc=statistics.fmean(ok for ok,c in rows); conf=statistics.fmean(c for ok,c in rows)
    return {'raw_correlation':d.self_dependency('s')['raw_correlation'],'effective':d.effective_batch(['s']*9),'tail_accuracy':acc,'tail_confidence':conf,'calibration_gap':abs(acc-conf)}
out={
 'correlated_then_independent':run(True,False,7001),
 'independent_then_correlated':run(False,True,7002),
 'interpretation':'alpha.7 uses cumulative dependency statistics; dependency regime changes remain a known limitation.',
}
open('ALPHA7_DEPENDENCY_DRIFT_LIMIT.json','w').write(json.dumps(out,indent=2,sort_keys=True)+'\n')
print(json.dumps(out,indent=2,sort_keys=True))
