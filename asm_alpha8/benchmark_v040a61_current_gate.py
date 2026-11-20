from __future__ import annotations
import json, random, statistics
from asm.adaptive_evidence import AdaptiveEvidenceModel

def sample_case(rng, reliability):
    truth='A' if rng.random()<.5 else 'B'; correct=rng.random()<reliability
    return truth, truth if correct else ('B' if truth=='A' else 'A')

def run_seed(seed):
    rng=random.Random(seed); m=AdaptiveEvidenceModel(prior_strength=4.0,drift_window=32,drift_min_abs_change=.25,drift_min_zscore=3.0)
    first=None; tail=[]
    for i,true_r in enumerate([.9]*500+[.1]*500):
        truth,obs=sample_case(rng,true_r); r=m.reliability('s',supplied_reliability=.9)
        pred=obs if r>=.5 else ('B' if obs=='A' else 'A')
        if i>=800: tail.append(int(pred==truth))
        m.observe_resolved('s',observation=obs,resolved_hypothesis=truth,supplied_reliability=.9,temporal_index=i)
        if first is None and i>=500 and m.reliability('s',supplied_reliability=.9)<.5: first=i-500+1
    st=m.status('s',supplied_reliability=.9)
    return {'recovery':first,'tail_accuracy':statistics.fmean(tail),'regimes':st['regime_count'],'effective_r':st['effective_reliability']}

runs=[run_seed(i) for i in range(30)]
out={'benchmark':'alpha6.1 current drift gate rerun under alpha7.1','recovered':sum(x['recovery'] is not None for x in runs),'total':30,
     'mean_recovery':statistics.fmean(x['recovery'] for x in runs if x['recovery'] is not None),
     'mean_tail_accuracy':statistics.fmean(x['tail_accuracy'] for x in runs),'runs':runs}
out['pass']=out['recovered']==30 and out['mean_tail_accuracy']>.85
open('ALPHA61_CURRENT_RERUN_ALPHA71.json','w').write(json.dumps(out,indent=2,sort_keys=True)+'\n')
print(json.dumps({k:v for k,v in out.items() if k!='runs'},indent=2,sort_keys=True))
if not out['pass']: raise SystemExit(1)
