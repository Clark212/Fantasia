from __future__ import annotations

import json
import math
import random
from asm.adaptive_evidence import AdaptiveEvidenceModel
from asm.planning import DiscreteBeliefState

SEED=4061
rng=random.Random(SEED)
rows=[]

def check(name, cond, detail):
    rows.append({'name':name,'pass':bool(cond),'detail':detail})
    print(('PASS' if cond else 'FAIL'), name, detail)

# 1) One million resolved updates: 70% correctness pattern, no NaN/inf.
m=AdaptiveEvidenceModel(prior_strength=4.0)
for i in range(1_000_000):
    good = (i % 10) < 7
    m.observe_resolved('million', observation='A' if good else 'B', resolved_hypothesis='A', supplied_reliability=.9)
st=m.status('million', supplied_reliability=.9)
check('million_updates_finite', math.isfinite(st['reliability']) and math.isfinite(st['uncertainty_stddev']), st)
check('million_updates_converge_70', abs(st['reliability']-.7) < 1e-5, st['reliability'])

# 2) Exact wrong 1.0 prior can recover toward zero; exact 0.0 prior can recover toward one.
lo=AdaptiveEvidenceModel(prior_strength=4.0)
for _ in range(5000): lo.observe_resolved('s', observation='B', resolved_hypothesis='A', supplied_reliability=1.0)
hi=AdaptiveEvidenceModel(prior_strength=4.0)
for _ in range(5000): hi.observe_resolved('s', observation='A', resolved_hypothesis='A', supplied_reliability=0.0)
check('exact_one_prior_recovers', lo.reliability('s',supplied_reliability=1.0) < .001, lo.status('s', supplied_reliability=1.0))
check('exact_zero_prior_recovers', hi.reliability('s',supplied_reliability=0.0) > .999, hi.status('s', supplied_reliability=0.0))

# 3) 32 independent sources converge to their deterministic target frequencies.
m=AdaptiveEvidenceModel(max_sources=32, prior_strength=2.0)
errs=[]
for j in range(32):
    target=(j+1)/33.0
    # deterministic 10k schedule approximating target tightly
    good_n=round(target*10000)
    for i in range(10000):
        m.observe_resolved(f's{j}', observation='A' if i<good_n else 'B', resolved_hypothesis='A', supplied_reliability=.5)
    errs.append(abs(m.reliability(f's{j}', supplied_reliability=.5)-target))
check('32_source_scale', max(errs)<2e-4, {'max_error':max(errs)})
try:
    m.status('overflow', supplied_reliability=.5)
    cap=False
except RuntimeError:
    cap=True
check('source_cap_fail_closed', cap, {'sources':32})

# 4) Export/import exact round-trip.
payload=m.export_state(); m2=AdaptiveEvidenceModel(prior_strength=2.0,max_sources=32); m2.import_state(payload)
check('snapshot_roundtrip_exact', m2.export_state()==payload, {'sources':len(payload['sources'])})

# 5) Random Beta posterior sequences match direct counts.
max_err=0.0
for trial in range(250):
    prior=rng.random(); strength=0.25 + rng.random()*12
    mm=AdaptiveEvidenceModel(prior_strength=strength)
    succ=fail=0
    n=rng.randint(1,2000)
    for _ in range(n):
        good=rng.random()<rng.random()  # deliberately irregular stream
        if good: succ+=1
        else: fail+=1
        mm.observe_resolved('x', observation='A' if good else 'B', resolved_hypothesis='A', supplied_reliability=prior)
    a=max(mm.min_shape,prior*strength)+succ
    b=max(mm.min_shape,(1-prior)*strength)+fail
    oracle=a/(a+b)
    max_err=max(max_err,abs(mm.reliability('x', supplied_reliability=prior)-oracle))
check('random_beta_oracle_250', max_err<1e-15, {'max_error':max_err})

# 6) 2..32 hypothesis symmetric likelihood matrices normalize for every hidden state.
worst=0.0
for k in (2,3,4,8,16,32):
    names=tuple(f'H{i}' for i in range(k))
    mm=AdaptiveEvidenceModel()
    for r in (0.0,1e-12,.2,.5,.7,.999999999999,1.0):
        matrix={o:mm.likelihoods(f's{k}_{r}', observation=o, hypotheses=names, supplied_reliability=r) for o in names}
        for h in names:
            worst=max(worst,abs(sum(matrix[o][h] for o in names)-1.0))
check('multiclass_contract_2_to_32', worst<1e-12, {'worst_sum_error':worst})

# 7) Repeated inference cannot alter calibration state.
mm=AdaptiveEvidenceModel()
base=mm.status('readonly', supplied_reliability=.8).copy()
b=DiscreteBeliefState.from_mapping({'A':.5,'B':.5})
for i in range(100000):
    obs='A' if i%2==0 else 'B'
    likes=mm.likelihoods('readonly',observation=obs,hypotheses=('A','B'),supplied_reliability=.8)
    # Deliberately do not chain b forever, avoiding posterior structural effects.
    _=b.update(likes)
after=mm.status('readonly', supplied_reliability=.8)
check('inference_is_read_only', base['alpha']==after['alpha'] and base['beta']==after['beta'] and after['resolved_observations']==0, after)

# 8) Malformed snapshot fails closed.
bad_cases=[
    {'sources':[]},
    {'sources':{'x':{'alpha':float('nan'),'beta':1,'prior_reliability':.5,'prior_strength':4}}},
    {'sources':{'x':{'alpha':1,'beta':-1,'prior_reliability':.5,'prior_strength':4}}},
]
rejected=0
for bad in bad_cases:
    try: AdaptiveEvidenceModel().import_state(bad)
    except (ValueError,TypeError): rejected+=1
check('malformed_snapshot_rejected', rejected==len(bad_cases), {'rejected':rejected,'total':len(bad_cases)})

# 9) Tiny weighted updates remain finite.
mm=AdaptiveEvidenceModel(prior_strength=1e-6, min_shape=1e-12)
for _ in range(10000):
    mm.observe_resolved('tiny',observation='A',resolved_hypothesis='A',supplied_reliability=.5,weight=1e-9)
st=mm.status('tiny',supplied_reliability=.5)
check('tiny_weights_finite', all(math.isfinite(float(st[k])) for k in ('reliability','uncertainty_stddev','alpha','beta')), st)

out={'seed':SEED,'tests':rows,'passed':sum(r['pass'] for r in rows),'total':len(rows)}
with open('results/planning_v040a6_torture.json','w',encoding='utf-8') as f: json.dump(out,f,indent=2)
print('SUMMARY',out['passed'],'/',out['total'])
raise SystemExit(0 if out['passed']==out['total'] else 1)
