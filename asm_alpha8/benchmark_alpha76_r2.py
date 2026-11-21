import tempfile,random,json,statistics
from pathlib import Path
from asm import ASMEngine
from benchmark_alpha76_novelty import active,trust

def train_pair(e,a,b,shared,seed,temporal=False,start=0):
 r=random.Random(seed)
 for i in range(80):
  truth='A' if r.random()<.5 else 'B'
  def noisy(): return truth if r.random()<.7 else ('B' if truth=='A' else 'A')
  if r.random()<shared:
   o=noisy(); oa=ob=o
  else: oa,ob=noisy(),noisy()
  kw={'temporal_index':start+i} if temporal else {}
  e.observe_evidence_dependency_trial(f'd-{seed}-{start}-{i}',resolved_hypothesis=truth,observations={a:[oa],b:[ob]},**kw)

def trial(shared,seed):
 td=tempfile.TemporaryDirectory();e=ASMEngine(Path(td.name)/'x.db');trust(e,'oracle')
 for c in ('left','right'):active(e,'m',c)
 for s in ('s1','s2','s3','s4'):trust(e,s)
 train_pair(e,'s1','s2',shared,seed)
 for i,s in enumerate(('s1','s2','s3','s4')):e.observe_procedure_route('m',{'mode':False},'left',evidence_id=f'e{i}',source_id=s,root_id=f'r{i}')
 rows=e.procedures._effective_route_rows('m'); w=e.procedures._route_support_weights(rows,'full')
 dep=e.evidence_dependency.effective_batch(['s1','s2','s3','s4'])
 f=e.route_procedure_context('m',{'mode':False},epistemic_mode='frequency',min_support=4)
 full=e.route_procedure_context('m',{'mode':False},epistemic_mode='full',min_support=4)
 out={'eff':dep['effective_count'],'corr':e.evidence_dependency.pair_dependency('s1','s2')['active_correlation'],
      'weights':dict(zip([r['source'] for r in rows],w)),'frequency':f['status'],'full':full['status']}
 e.close();td.cleanup();return out

res={}
for shared in (0,.25,.5,.75,1):
 xs=[trial(shared,s) for s in range(8)]
 res[str(shared)]={'mean_eff':statistics.mean(x['eff'] for x in xs),'min_eff':min(x['eff'] for x in xs),'max_eff':max(x['eff'] for x in xs),
                   'mean_corr':statistics.mean(x['corr'] for x in xs),'full_routes':sum(x['full']=='routed' for x in xs),
                   'freq_routes':sum(x['frequency']=='routed' for x in xs),
                   'mean_w_corr':statistics.mean((x['weights']['s1']+x['weights']['s2'])/2 for x in xs),
                   'mean_w_ind':statistics.mean((x['weights']['s3']+x['weights']['s4'])/2 for x in xs)}
print(json.dumps(res,indent=2,sort_keys=True))
