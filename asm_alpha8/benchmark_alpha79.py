from __future__ import annotations
import json,random,tempfile,time,statistics
from pathlib import Path
from asm import ASMEngine
from asm.procedure_cortex import ProcedureCortex

OUT=Path(__file__).with_name('ALPHA79_BENCHMARK.json')
def key(a,b):return f'{a}\t{b}' if a<b else f'{b}\t{a}'
def rows(names):return [{'source':s,'reliability':1.0,'context':'x','features':{}} for s in names]
def stats_field(names,fn,trials=192):
 out={}
 for i,a in enumerate(names):
  for b in names[i+1:]:out[key(a,b)]={'raw':float(fn(a,b)),'active':0.0,'trials':trials,'p':1.0,'fdr_accepted':False}
 return out

def approximate_null():
 names=tuple(f's{i}' for i in range(8));rng=random.Random(20261007);sd=(1/(192-3))**.5;false=0;N=20000
 with tempfile.TemporaryDirectory() as td:
  c=ProcedureCortex(Path(td)/'p.db',trust_provider=lambda _s:{'reliability':1.0,'version':1},dependency_provider=None)
  for seed in range(N):
   stats=stats_field(names,lambda _a,_b:0.0)
   for st in stats.values():st['raw']=max(-.95,min(.95,rng.gauss(0,sd)))
   got=c._route_signed_latent_dependency_weights(names,{'pairwise':{},'pairwise_stats':stats,'version':seed})
   false+=int(any(v<.999999999 for v in got.values()))
  c.close()
 return {'trials':N,'false_activations':false,'rate':false/N}

def train_real(seed,signed):
 with tempfile.TemporaryDirectory() as td:
  e=ASMEngine(Path(td)/'s.db');rng=random.Random(seed);names=[f's{i}' for i in range(8)]
  for t in range(192):
   truth='A' if rng.random()<.5 else 'B';other='B' if truth=='A' else 'A';obs={}
   if signed:
    z=rng.random()<.5
    for i,s in enumerate(names):
     target=z if i<4 else not z;correct=target if rng.random()<.70 else not target;obs[s]=[truth if correct else other]
   else:
    for s in names:obs[s]=[truth if rng.random()<.6 else other]
   e.observe_evidence_dependency_trial(f'{seed}-{t}',resolved_hypothesis=truth,observations=obs)
  base=sum(e.procedures._route_support_weights(rows(names),'latent'));new=sum(e.procedures._route_support_weights(rows(names),'signed_latent'))
  e.close();return base,new

def real_runs():
 independent=[train_real(s,False) for s in range(12)];signed=[train_real(s,True) for s in range(12)]
 return {
  'independent_runs':12,'independent_false_detections':sum(n<b-1e-9 for b,n in independent),
  'signed_runs':12,'signed_detections':sum(n<b-1e-9 for b,n in signed),
  'signed_alpha78_mean_support':statistics.mean(b for b,n in signed),
  'signed_alpha79_mean_support':statistics.mean(n for b,n in signed),
  'signed_per_seed':[{'seed':i,'alpha78':b,'alpha79':n} for i,(b,n) in enumerate(signed)]
 }

def overlap():
 names=[f's{i}' for i in range(20)]
 def corr(a,b):
  i=int(a[1:]);j=int(b[1:]);la=(.35 if i<14 else 0,.35 if i>=6 else 0);lb=(.35 if j<14 else 0,.35 if j>=6 else 0)
  return la[0]*lb[0]+la[1]*lb[1]
 stats=stats_field(names,corr)
 with tempfile.TemporaryDirectory() as td:
  c=ProcedureCortex(Path(td)/'p.db',trust_provider=lambda _s:{'reliability':1.0,'version':1},dependency_provider=lambda _s:{'pairwise':{},'pairwise_stats':stats,'version':1})
  b=sum(c._route_support_weights(rows(names),'latent'));n=sum(c._route_support_weights(rows(names),'signed_latent'));c.close()
 return {'sources':20,'alpha78_support':b,'alpha79_support':n}

def migration():
 names=[f's{i}' for i in range(12)]
 def field(group):
  g=set(group);pol={s:(1 if i<len(group)//2 else -1) for i,s in enumerate(group)}
  return stats_field(names,lambda a,b:.14*pol[a]*pol[b] if a in g and b in g else 0.0)
 state={'v':1,'stats':field(names[:8])}
 with tempfile.TemporaryDirectory() as td:
  c=ProcedureCortex(Path(td)/'p.db',trust_provider=lambda _s:{'reliability':1.0,'version':1},dependency_provider=lambda _s:{'pairwise':{},'pairwise_stats':state['stats'],'version':state['v']})
  a=dict(zip(names,c._route_support_weights(rows(names),'signed_latent')));state['v']=2;state['stats']=field(names[4:12]);b=dict(zip(names,c._route_support_weights(rows(names),'signed_latent')));c.close()
 return {'old_group_before':{s:a[s] for s in names[:4]},'old_group_after':{s:b[s] for s in names[:4]},'new_group_after':{s:b[s] for s in names[8:12]}}

def latency():
 names=[f's{i}' for i in range(20)]
 def corr(a,b):
  i=int(a[1:]);j=int(b[1:]);la=(.35 if i<14 else 0,.35 if i>=6 else 0);lb=(.35 if j<14 else 0,.35 if j>=6 else 0);return la[0]*lb[0]+la[1]*lb[1]
 stats=stats_field(names,corr);dep={'pairwise':{},'pairwise_stats':stats,'version':1}
 with tempfile.TemporaryDirectory() as td:
  c=ProcedureCortex(Path(td)/'p.db',trust_provider=lambda _s:{'reliability':1.0,'version':1},dependency_provider=lambda _s:dep);r=rows(names)
  c._route_support_weights(r,'latent');c._route_support_weights(r,'signed_latent')
  old=[];new=[]
  for _ in range(200):
   t=time.perf_counter();c._route_support_weights(r,'latent');old.append((time.perf_counter()-t)*1000)
   t=time.perf_counter();c._route_support_weights(r,'signed_latent');new.append((time.perf_counter()-t)*1000)
  c.close()
 return {'alpha78_median_ms':statistics.median(old),'alpha79_median_ms':statistics.median(new)}

def main():
 result={'version':'0.4.0-alpha.7.9-experimental','approximate_null':approximate_null(),'real_learned':real_runs(),'overlap':overlap(),'migration':migration(),'latency':latency()}
 OUT.write_text(json.dumps(result,indent=2,sort_keys=True));print(json.dumps(result,indent=2,sort_keys=True))
if __name__=='__main__':main()
