from __future__ import annotations
import json, random, statistics
from asm.adaptive_evidence import AdaptiveEvidenceModel


def sample(rng, p):
    truth = 'A' if rng.random() < .5 else 'B'
    ok = rng.random() < p
    obs = truth if ok else ('B' if truth == 'A' else 'A')
    return truth, obs


def stationary(rate, seed, n=3000):
    rng=random.Random(seed); m=AdaptiveEvidenceModel()
    for i in range(n):
        truth,obs=sample(rng,rate)
        m.observe_resolved('s',observation=obs,resolved_hypothesis=truth,supplied_reliability=rate,temporal_index=i)
    s=m.status('s',supplied_reliability=rate)
    return s['regime_count'],s['effective_reliability']


def return_cycle(seed):
    rng=random.Random(seed); m=AdaptiveEvidenceModel(); crossings=[]
    schedule=[(.9,400),(.1,400),(.9,400)]
    i=0
    for stage,(rate,n) in enumerate(schedule):
        crossed=None
        for j in range(n):
            truth,obs=sample(rng,rate)
            m.observe_resolved('s',observation=obs,resolved_hypothesis=truth,supplied_reliability=.9,temporal_index=i)
            r=m.reliability('s',supplied_reliability=.9)
            target=(r<.5) if stage==1 else (r>.5)
            if stage>0 and crossed is None and target: crossed=j+1
            i+=1
        if stage>0: crossings.append(crossed)
    s=m.status('s',supplied_reliability=.9)
    return {'regimes':s['regime_count'],'down_recovery':crossings[0],'up_recovery':crossings[1],
            'final_effective_r':s['effective_reliability']}


def main():
    rates={}
    for rate in [.1,.3,.5,.7,.9]:
        rows=[stationary(rate,10000+int(rate*1000)+seed) for seed in range(20)]
        rates[str(rate)]={'seeds':20,'false_split_seeds':sum(1 for c,_ in rows if c>1),
                          'mean_regimes':statistics.mean(c for c,_ in rows),
                          'mean_effective_r':statistics.mean(r for _,r in rows)}
    cycles=[return_cycle(20000+s) for s in range(20)]
    result={'stationary_by_rate':rates,
            'return_90_10_90':{'seeds':20,'mean_regimes':statistics.mean(r['regimes'] for r in cycles),
                               'down_recovery_mean':statistics.mean(r['down_recovery'] for r in cycles if r['down_recovery'] is not None),
                               'up_recovery_mean':statistics.mean(r['up_recovery'] for r in cycles if r['up_recovery'] is not None),
                               'all_recovered_down':all(r['down_recovery'] is not None for r in cycles),
                               'all_recovered_up':all(r['up_recovery'] is not None for r in cycles),
                               'mean_final_effective_r':statistics.mean(r['final_effective_r'] for r in cycles)},
            'claim_boundary':'Synthetic binary source-reliability stress; does not test correlated evidence or latent-cause discovery.'}
    print(json.dumps(result,indent=2,sort_keys=True))
if __name__=='__main__': main()
