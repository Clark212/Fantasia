from __future__ import annotations
import json, tempfile, time, statistics
from pathlib import Path
from asm.engine import ASMEngine


def trust(e,source='oracle'):
    for i in range(80):e.observe_evidence_source(source,observation='A',resolved_hypothesis='A',temporal_index=i)

def activate(e,m,c,delta):
    f=lambda x:x+delta
    for i,x in enumerate((0,1,2)):e.observe_procedural_experience(m,{'x':x},f(x),evidence_id=f'{m}-{c}-f{i}',source_id='oracle',context=c)
    for i,x in enumerate(range(10,18)):e.observe_procedural_experience(m,{'x':x},f(x),evidence_id=f'{m}-{c}-v{i}',source_id='oracle',context=c)

def make():
    td=tempfile.TemporaryDirectory();e=ASMEngine(Path(td.name)/'state.db');trust(e);return td,e

results={}
# two-context routing
_td,e=make();activate(e,'two','A',1);activate(e,'two','B',-1)
for i in range(6):
    e.observe_procedure_route('two',{'mode':False},'A',evidence_id=f'a{i}',source_id='oracle')
    e.observe_procedure_route('two',{'mode':True},'B',evidence_id=f'b{i}',source_id='oracle')
correct=sum(e.route_procedure_context('two',{'mode':m})['context']==('B' if m else 'A') for m in [False,True]*100)
results['two_context_accuracy']=correct/200
results['ambiguous_status']=e.route_procedure_context('two',{})['status']
e.close();_td.cleanup()

# 4-context sequential information plan
_td,e=make();patterns={'A':(False,False),'B':(False,True),'C':(True,False),'D':(True,True)}
for i,c in enumerate(patterns):activate(e,'four',c,i+1)
for c,(a,b) in patterns.items():
    for i in range(8):e.observe_procedure_route('four',{'bit1':a,'bit2':b},c,evidence_id=f'{c}-{i}',source_id='oracle')
plan=e.plan_procedure_route_queries('four',{},max_depth=2)
leaves=[]
for b1 in plan['tree'].get('branches',[]):
    for b2 in b1['next'].get('branches',[]):leaves.append(b2['next'])
results['query_tree_nodes']=plan['nodes']
results['query_tree_resolved_contexts']=sorted({x.get('context') for x in leaves if x.get('status')=='routed'})
results['query_tree_all_leaves_routed']=len(leaves)==4 and all(x.get('status')=='routed' for x in leaves)
e.close();_td.cleanup()

# temporal drift/reversal
_td,e=make();activate(e,'drift','A',1);activate(e,'drift','B',-1);t=0
for phase,c,n in [('p1','A',6),('p2','B',4),('p3','A',4)]:
    for i in range(n):e.observe_procedure_route('drift',{'signal':True},c,evidence_id=f'{phase}-{i}',source_id='oracle',temporal_index=t);t+=1
    results[f'drift_{phase}_context']=e.route_procedure_context('drift',{'signal':True}).get('context')
results['drift_history_records']=e.procedure_route_evidence_status('drift')['total_records']
e.close();_td.cleanup()

# random/no-pattern safety
_td,e=make();activate(e,'noise','A',1);activate(e,'noise','B',-1)
for i in range(40):e.observe_procedure_route('noise',{'signal':True},'A' if i%2==0 else 'B',evidence_id=f'n{i}',source_id='oracle')
r=e.route_procedure_context('noise',{'signal':True})
results['noise_status']=r['status'];results['noise_false_routed']=r['status']=='routed'
e.close();_td.cleanup()

# performance
_td,e=make();activate(e,'perf','A',1);activate(e,'perf','B',-1)
for i in range(16):
    e.observe_procedure_route('perf',{'mode':False,'aux':i%2==0},'A',evidence_id=f'pa{i}',source_id='oracle')
    e.observe_procedure_route('perf',{'mode':True,'aux':i%2==0},'B',evidence_id=f'pb{i}',source_id='oracle')
lat=[]
for _ in range(500):
    t0=time.perf_counter_ns();e.route_procedure_context('perf',{'mode':False});lat.append((time.perf_counter_ns()-t0)/1e6)
qlat=[]
for _ in range(100):
    t0=time.perf_counter_ns();e.plan_procedure_route_queries('perf',{},max_depth=2);qlat.append((time.perf_counter_ns()-t0)/1e6)
results['route_latency_ms_median']=statistics.median(lat)
results['query_plan_latency_ms_median']=statistics.median(qlat)
e.close();_td.cleanup()

results['all_checks_pass']=all([
    results['two_context_accuracy']==1.0,
    results['ambiguous_status']=='needs_information',
    results['query_tree_all_leaves_routed'],
    results['drift_p1_context']=='A',results['drift_p2_context']=='B',results['drift_p3_context']=='A',
    results['drift_history_records']==14,
    not results['noise_false_routed'],
])
print(json.dumps(results,indent=2,sort_keys=True))
Path('ALPHA75_PARALLEL_BENCHMARK.json').write_text(json.dumps(results,indent=2,sort_keys=True)+'\n')
