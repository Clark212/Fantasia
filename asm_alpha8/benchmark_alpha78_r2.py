from __future__ import annotations
import json,random,statistics,tempfile,time
from pathlib import Path
from asm import ASMEngine
from tests.test_alpha76_r3 import activate_context,trust

def key(a,b):return f"{a}\t{b}" if a<b else f"{b}\t{a}"
def train(e,seed,shared,trials):
 rng=random.Random(seed);names=[f"s{i}" for i in range(12)]
 for t in range(trials):
  p=(.8 if rng.random()<.5 else .4) if shared else .6;e.observe_evidence_dependency_trial(str(t),resolved_hypothesis="A",observations={s:["A" if rng.random()<p else "B"] for s in names})
 return names
def cond(shared,trials,seeds):
 act=0;base=[];lat=[]
 for seed in range(seeds):
  with tempfile.TemporaryDirectory() as td:
   e=ASMEngine(Path(td)/"s.db");names=train(e,seed,shared,trials);st=e._procedure_dependency_status(names);r=[{"source":s,"reliability":1.0,"context":"x","features":{}} for s in names];base.append(sum(e.procedures._route_support_weights(r,"covariance")));lat.append(sum(e.procedures._route_support_weights(r,"latent")));act+=e.procedures._route_latent_factor_fit(tuple(sorted(names)),st["pairwise_stats"]) is not None;e.close()
 theory=12/(1+11/6);return {"trials":trials,"seeds":seeds,"activations":act,"activation_rate":act/seeds,"mean_alpha77_support":statistics.fmean(base),"mean_alpha78_support":statistics.fmean(lat),"alpha77_mae_to_theory":statistics.fmean(abs(x-theory) for x in base),"alpha78_mae_to_theory":statistics.fmean(abs(x-theory) for x in lat)}
def attack():
 with tempfile.TemporaryDirectory() as td:
  e=ASMEngine(Path(td)/"s.db");trust(e);activate_context(e,"m","left",1);activate_context(e,"m","right",-1);bad=[f"b{i}" for i in range(10)];good="good"
  for s in bad+[good]:trust(e,s)
  names=bad+[good];stats={}
  for i,a in enumerate(names):
   for b in names[i+1:]:
    raw=.12 if a in bad and b in bad else 0;stats[key(a,b)]={"raw":raw,"active":0,"trials":100,"p":1,"fdr_accepted":False}
  e.procedures.dependency_provider=lambda _s:{"pairwise":{},"pairwise_stats":stats,"version":1}
  for i,s in enumerate(bad):e.observe_procedure_route("m",{"signal":True},"left",evidence_id=f"b{i}",source_id=s)
  e.observe_procedure_route("m",{"signal":True},"right",evidence_id="g",source_id=good);old=e.route_procedure_context("m",{"signal":True},epistemic_mode="full_covariance",min_support=1);new=e.route_procedure_context("m",{"signal":True},epistemic_mode="full_latent",min_support=1);out={"alpha77":{"status":old["status"],"context":old.get("context"),"support":old["support"]},"alpha78":{"status":new["status"],"context":new.get("context"),"support":new["support"]}};e.close();return out
def perf():
 with tempfile.TemporaryDirectory() as td:
  e=ASMEngine(Path(td)/"s.db");names=train(e,7,True,192);r=[{"source":s,"reliability":1.0,"context":"x","features":{}} for s in names];e.procedures._route_support_weights(r,"covariance");e.procedures._route_support_weights(r,"latent")
  def med(m):
   xs=[]
   for _ in range(500):t=time.perf_counter_ns();e.procedures._route_support_weights(r,m);xs.append((time.perf_counter_ns()-t)/1e6)
   return statistics.median(xs)
  x={"alpha77_ms":med("covariance"),"alpha78_ms":med("latent")};e.close();return x
if __name__=="__main__":
 out={"shared_192":cond(True,192,24),"independent_64":cond(False,64,40),"independent_100":cond(False,100,40),"independent_192":cond(False,192,40),"boundary_attack":attack(),"performance":perf()};Path("ALPHA78_R2_BENCHMARK.json").write_text(json.dumps(out,indent=2,sort_keys=True));print(json.dumps(out,indent=2,sort_keys=True))
