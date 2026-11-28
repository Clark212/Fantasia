from __future__ import annotations
import json, tempfile, time, statistics
from pathlib import Path
from asm import __version__
from asm.transition_mechanism import TransitionMechanismBank

ROOT=Path(__file__).resolve().parent
DOMAINS={
'door_dyn':[
 ({'kind':'door','mode':'closed'},'open',{'kind':'door','mode':'open'}),
 ({'kind':'door','mode':'open'},'close',{'kind':'door','mode':'closed'}),
 ({'kind':'door','mode':'closed'},'lock',{'kind':'door','mode':'locked'}),
 ({'kind':'door','mode':'locked'},'unlock',{'kind':'door','mode':'closed'}),
 ({'kind':'door','mode':'locked'},'open',{'kind':'door','mode':'locked'}),
],
'switch_dyn':[
 ({'kind':'switch','on':False},'toggle',{'kind':'switch','on':True}),
 ({'kind':'switch','on':True},'toggle',{'kind':'switch','on':False}),
 ({'kind':'switch','on':False},'set_on',{'kind':'switch','on':True}),
 ({'kind':'switch','on':True},'set_off',{'kind':'switch','on':False}),
],
'container_dyn':[
 ({'kind':'container','open':False,'filled':False},'open',{'kind':'container','open':True,'filled':False}),
 ({'kind':'container','open':True,'filled':False},'close',{'kind':'container','open':False,'filled':False}),
 ({'kind':'container','open':True,'filled':False},'insert',{'kind':'container','open':True,'filled':True}),
 ({'kind':'container','open':True,'filled':True},'remove',{'kind':'container','open':True,'filled':False}),
 ({'kind':'container','open':False,'filled':False},'insert',{'kind':'container','open':False,'filled':False}),
],
'counter_dyn':[
 ({'kind':'counter','value':0},'inc',{'kind':'counter','value':1}),
 ({'kind':'counter','value':1},'reset',{'kind':'counter','value':0}),
],
'valve_dyn':[
 ({'kind':'valve','open':False},'open',{'kind':'valve','open':True}),
 ({'kind':'valve','open':True},'close',{'kind':'valve','open':False}),
],
'light_dyn':[
 ({'kind':'light','level':0},'brighten',{'kind':'light','level':1}),
 ({'kind':'light','level':1},'dim',{'kind':'light','level':0}),
],
}

with tempfile.TemporaryDirectory() as td:
    path=Path(td)/'sched.db'
    bank=TransitionMechanismBank(path,hidden_dim=32,train_steps=4,learning_rate=.012,seed=17,
                                 scheduler_max_calls=1,scheduler_min_relevance=.45,
                                 scheduler_recovery_uncertainty=.72)
    train_start=time.perf_counter()
    for mechanism,cases in DOMAINS.items():
        for _ in range(8):
            for e in range(2):
                for state,action,after in cases:
                    bank.observe(mechanism,entity_id=f'{mechanism}_{e}',state=state,action=action,after_state=after)
    train_seconds=time.perf_counter()-train_start

    rows=[]; dense_correct=seismic_correct=0; dense_calls=seismic_calls=0
    for mechanism,cases in DOMAINS.items():
        for i,(state,action,after) in enumerate(cases):
            dense=bank.predict_routed(entity_id=f'dense_{mechanism}_{i}',state=state,action=action,mode='dense')
            seismic=bank.predict_routed(entity_id=f'seis_{mechanism}_{i}',state=state,action=action,mode='seismic')
            dp=dense['chosen']['prediction']['predicted_state'] if dense['chosen'] else None
            sp=seismic['chosen']['prediction']['predicted_state'] if seismic['chosen'] else None
            dense_correct += int(dp==after); seismic_correct += int(sp==after)
            dense_calls += dense['calls']; seismic_calls += seismic['calls']
            rows.append({
                'mechanism':mechanism,'state':state,'action':action,'expected':after,
                'dense_prediction':dp,'seismic_prediction':sp,
                'dense_calls':dense['calls'],'seismic_calls':seismic['calls'],
                'selected':seismic['chosen']['mechanism_type'] if seismic['chosen'] else None,
                'fallback':seismic['fallback'],
            })

    # Wall-clock routing probe. This includes relevance lookup + actual mechanism calls.
    dense_times=[]; seismic_times=[]
    timing_cases=[(m,*case[:2]) for m,cases in DOMAINS.items() for case in cases]
    for rep in range(8):
        for j,(mechanism,state,action) in enumerate(timing_cases):
            t0=time.perf_counter_ns(); bank.predict_routed(entity_id=f"td_{rep}_{j}",state=state,action=action,mode="dense"); dense_times.append((time.perf_counter_ns()-t0)/1e6)
            t0=time.perf_counter_ns(); bank.predict_routed(entity_id=f"ts_{rep}_{j}",state=state,action=action,mode="seismic"); seismic_times.append((time.perf_counter_ns()-t0)/1e6)
    def pct95(xs):
        ys=sorted(xs); return ys[min(len(ys)-1, max(0, int(len(ys)*.95)-1))]
    timing={
        "samples_per_mode":len(dense_times),
        "dense_median_ms":statistics.median(dense_times),
        "dense_p95_ms":pct95(dense_times),
        "seismic_median_ms":statistics.median(seismic_times),
        "seismic_p95_ms":pct95(seismic_times),
    }
    timing["median_latency_reduction"]=1.0-(timing["seismic_median_ms"]/timing["dense_median_ms"])

    # Novel/OOD query must widen instead of starving mechanisms.
    fallback=bank.predict_routed(entity_id='ood',state={'kind':'unknown_device','phase':3},action='pulse',mode='seismic')

    # Force an unusually strict uncertainty budget to exercise bounded widening.
    old_threshold=bank.scheduler_recovery_uncertainty
    bank.scheduler_recovery_uncertainty=0.0
    sample=DOMAINS['door_dyn'][0]
    recovery=bank.predict_routed(entity_id='recovery_probe',state=sample[0],action=sample[1],mode='seismic',recover=True)
    bank.scheduler_recovery_uncertainty=old_threshold

    # Profiles are persistent, not session-only routing hints.
    bank.close()
    bank=TransitionMechanismBank(path,hidden_dim=32,train_steps=4,learning_rate=.012,seed=17,
                                 scheduler_max_calls=1,scheduler_min_relevance=.45)
    persisted=bank.route(state=sample[0],action=sample[1],mode='seismic')
    scheduler_stats=bank.stats()['scheduler']
    bank.close()

n=sum(len(x) for x in DOMAINS.values())
reduction=1.0-(seismic_calls/dense_calls)
checks=[]
def add(name,ok,**details): checks.append({'name':name,'pass':bool(ok),'details':details})
add('dense_predictions_100pct',dense_correct==n,correct=dense_correct,total=n)
add('seismic_predictions_match_dense_and_100pct',seismic_correct==dense_correct==n,dense=dense_correct,seismic=seismic_correct,total=n)
add('seismic_reduces_mechanism_calls_at_least_75pct',reduction>=.75,dense_calls=dense_calls,seismic_calls=seismic_calls,reduction=reduction)
add('seismic_reduces_median_wall_clock_latency',timing['seismic_median_ms']<timing['dense_median_ms'],timing=timing)
add('seismic_routes_to_expected_mechanism',all(r['selected']==r['mechanism'] for r in rows),mismatches=[r for r in rows if r['selected']!=r['mechanism']])
add('ood_query_falls_back_to_dense',fallback['fallback'] and fallback['calls']==fallback['total_mechanisms'],calls=fallback['calls'],total=fallback['total_mechanisms'],reason=fallback['reason'])
add('high_uncertainty_can_widen_execution',recovery['calls']>1,calls=recovery['calls'],total=recovery['total_mechanisms'])
add('applicability_profiles_persist',persisted['selected'] and persisted['selected'][0]['mechanism_type']=='door_dyn',route=persisted)

payload={
 'benchmark':'ASM v0.3.0-alpha.4 Selective Seismic Scheduling',
 'version':__version__,
 'domains':list(DOMAINS),
 'cases':n,
 'training_seconds':train_seconds,
 'dense':{'correct':dense_correct,'total':n,'mechanism_calls':dense_calls},
 'seismic':{'correct':seismic_correct,'total':n,'mechanism_calls':seismic_calls,'call_reduction':reduction},
 'timing':timing,
 'fallback_probe':fallback,
 'recovery_probe':{'calls':recovery['calls'],'total_mechanisms':recovery['total_mechanisms'],'recoveries_exercised':recovery['calls']>1},
 'scheduler_stats_after_reload':scheduler_stats,
 'checks':checks,
 'summary':{'passed':sum(int(x['pass']) for x in checks),'total':len(checks)},
 'notes':[
  'Controlled architecture benchmark; not a standardized intelligence benchmark.',
  'Mechanism identities are supplied for this v0.3 scheduling experiment; representation discovery is intentionally deferred.',
  'Applicability is learned from observed structured transition features; no domain-specific routing rules are hardcoded.',
  'Dense and seismic modes use the same learned mechanism bank and answer-selection rule; only execution breadth differs.',
 ]
}
payload['summary']['accuracy_pct']=100*payload['summary']['passed']/payload['summary']['total']
out=ROOT/'results/selective_seismic_scheduler_benchmark.json'; out.write_text(json.dumps(payload,indent=2),encoding='utf-8')
print(json.dumps({'version':__version__,'summary':payload['summary'],'dense':payload['dense'],'seismic':payload['seismic'],'timing':payload['timing'],'fallback_calls':fallback['calls'],'recovery_calls':recovery['calls']},indent=2))
print('RESULT:',out)
if payload['summary']['passed']!=payload['summary']['total']: raise SystemExit(1)
