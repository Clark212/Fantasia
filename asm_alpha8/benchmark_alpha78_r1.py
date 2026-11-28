from __future__ import annotations
import json,random,statistics,tempfile,time
from pathlib import Path
from asm import ASMEngine

def train(e,seed,shared,trials):
 rng=random.Random(seed);names=[f"s{i}" for i in range(12)]
 for t in range(trials):
  p=(.8 if rng.random()<.5 else .4) if shared else .6;obs={s:["A" if rng.random()<p else "B"] for s in names};e.observe_evidence_dependency_trial(str(t),resolved_hypothesis="A",observations=obs)
 return names
def cond(shared,trials,seeds):
 acts=0;base=[];lat=[];acc=[];means=[]
 for seed in range(seeds):
  with tempfile.TemporaryDirectory() as td:
   e=ASMEngine(Path(td)/"s.db");names=train(e,seed,shared,trials);st=e._procedure_dependency_status(names);raw=[v["raw"] for v in st["pairwise_stats"].values()];r=[{"source":s,"reliability":1.0,"context":"x","features":{}} for s in names]
   b=sum(e.procedures._route_support_weights(r,"covariance"));l=sum(e.procedures._route_support_weights(r,"latent"));fit=e.procedures._route_latent_factor_fit(tuple(sorted(names)),st["pairwise_stats"]);acts+=fit is not None;base.append(b);lat.append(l);acc.append(st["pairwise_fdr"]["accepted_pairs"]);means.append(statistics.fmean(raw));e.close()
 return {"trials":trials,"seeds":seeds,"activation_rate":acts/seeds,"activations":acts,"mean_raw":statistics.fmean(means),"mean_fdr_pairs":statistics.fmean(acc),"mean_alpha77_support":statistics.fmean(base),"mean_alpha78_support":statistics.fmean(lat),"min_alpha78_support":min(lat),"max_alpha78_support":max(lat)}
def perf():
 with tempfile.TemporaryDirectory() as td:
  e=ASMEngine(Path(td)/"s.db");names=train(e,7,True,192);r=[{"source":s,"reliability":1.0,"context":"x","features":{}} for s in names];e.procedures._route_support_weights(r,"covariance");e.procedures._route_support_weights(r,"latent")
  def med(mode):
   xs=[]
   for _ in range(300):
    t=time.perf_counter_ns();e.procedures._route_support_weights(r,mode);xs.append((time.perf_counter_ns()-t)/1e6)
   return statistics.median(xs)
  x={"alpha77_ms":med("covariance"),"alpha78_ms":med("latent")};e.close();return x
if __name__=="__main__":
 out={"shared_192":cond(True,192,24),"independent_64":cond(False,64,40),"independent_100":cond(False,100,40),"independent_192":cond(False,192,40),"performance":perf()};Path("ALPHA78_R1_BENCHMARK.json").write_text(json.dumps(out,indent=2,sort_keys=True));print(json.dumps(out,indent=2,sort_keys=True))
