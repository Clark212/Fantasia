from __future__ import annotations

import json, math, random, statistics, tempfile, time
from pathlib import Path

try:
    import numpy as np
except Exception:
    np = None

from asm import ASMEngine
from asm.procedure_cortex import ProcedureCortex
from tests.test_alpha76_r3 import activate_context, trust, train_pair_dependency, train_clique_dependency


def key(a,b):
    return f"{a}\t{b}" if a < b else f"{b}\t{a}"


def evaluate_matrix(R):
    n=len(R)
    sources=[f"s{i}" for i in range(n)]
    pairs={key(sources[i],sources[j]):float(R[i][j]) for i in range(n) for j in range(i+1,n) if R[i][j] > 0}
    with tempfile.TemporaryDirectory() as td:
        c=ProcedureCortex(Path(td)/"p.db",trust_provider=lambda _s:{"reliability":1.0,"version":1},
                          dependency_provider=lambda _s:{"pairwise":pairs,"version":1})
        rows=[{"source":s,"reliability":1.0,"context":"x","features":{}} for s in sources]
        local=sum(c._route_support_weights(rows,"dependency"))
        cov=sum(c._route_support_weights(rows,"covariance"))
        c.close()
    if np is None:
        exact=cov
    else:
        exact=float(np.ones(n) @ np.linalg.solve(np.array(R,dtype=float),np.ones(n)))
    return local,cov,exact


def synthetic_matrix_benchmark():
    rows=[]
    # Equicorrelation and AR(1) are guaranteed positive definite for these ranges.
    for n in range(3,17):
        for rho in (0.05,0.10,0.20,0.30,0.40,0.50,0.60,0.70):
            R=[[1.0 if i==j else rho for j in range(n)] for i in range(n)]
            rows.append(("equi",n,rho,*evaluate_matrix(R)))
        for rho in (0.10,0.20,0.35,0.50,0.65,0.80):
            R=[[rho**abs(i-j) for j in range(n)] for i in range(n)]
            rows.append(("ar1",n,rho,*evaluate_matrix(R)))
    # Valid star cases restricted to non-negative/non-amplifying inverse weights.
    for n in range(4,13):
        for rho in (0.05,0.10,0.15,0.20,0.25):
            R=[[0.0]*n for _ in range(n)]
            for i in range(n):R[i][i]=1.0
            for j in range(1,n):R[0][j]=R[j][0]=rho
            if np is not None:
                eig=float(np.linalg.eigvalsh(np.array(R)).min())
                w=np.linalg.solve(np.array(R),np.ones(n))
                if eig<=1e-10 or (w < -1e-10).any() or (w > 1+1e-10).any():
                    continue
            rows.append(("star",n,rho,*evaluate_matrix(R)))
    local_abs=[];cov_abs=[];local_dec=0;cov_dec=0;local_false_route=0;cov_false_route=0;decisions=0
    worst_local=None;worst_cov=None
    for family,n,rho,local,cov,exact in rows:
        le=abs(local-exact);ce=abs(cov-exact)
        local_abs.append(le);cov_abs.append(ce)
        if worst_local is None or le>worst_local[0]:worst_local=(le,family,n,rho,local,exact)
        if worst_cov is None or ce>worst_cov[0]:worst_cov=(ce,family,n,rho,cov,exact)
        for threshold in range(1,n+1):
            truth=exact+1e-12>=threshold
            l=local+1e-12>=threshold
            c=cov+1e-12>=threshold
            decisions+=1
            local_dec+=l!=truth;cov_dec+=c!=truth
            local_false_route+=l and not truth;cov_false_route+=c and not truth
    return {
        "cases":len(rows),"decisions":decisions,
        "local_mean_abs_error":statistics.fmean(local_abs),"covariance_mean_abs_error":statistics.fmean(cov_abs),
        "local_max_abs_error":max(local_abs),"covariance_max_abs_error":max(cov_abs),
        "local_wrong_decisions":local_dec,"covariance_wrong_decisions":cov_dec,
        "local_false_routes":local_false_route,"covariance_false_routes":cov_false_route,
        "worst_local":worst_local,"worst_covariance":worst_cov,
    }


def real_dependency_benchmark():
    out={}
    # Drift: learned duplicate pair -> independent pair, route history untouched.
    with tempfile.TemporaryDirectory() as td:
        e=ASMEngine(Path(td)/"state.db");trust(e);activate_context(e,"m","left",1);activate_context(e,"m","right",-1)
        sources=("s1","s2","s3","s4")
        for s in sources:trust(e,s)
        train_pair_dependency(e,"s1","s2",shared=1.0,start=0,trials=100,seed=1,temporal=True)
        for i,s in enumerate(sources):e.observe_procedure_route("m",{"mode":False},"left",evidence_id=f"r{i}",source_id=s)
        before_records=e.procedure_route_evidence_status("m")["total_records"]
        before=e.route_procedure_context("m",{"mode":False},epistemic_mode="full_covariance")
        train_pair_dependency(e,"s1","s2",shared=0.0,start=100,trials=140,seed=2,temporal=True)
        after=e.route_procedure_context("m",{"mode":False},epistemic_mode="full_covariance")
        out["drift"]={"before_status":before["status"],"before_support":before["support"]["left"],
                      "after_status":after["status"],"after_context":after.get("context"),"after_support":after["support"]["left"],
                      "route_history_unchanged":before_records==e.procedure_route_evidence_status("m")["total_records"]}
        e.close()
    # Duplicate-majority adversary.
    with tempfile.TemporaryDirectory() as td:
        e=ASMEngine(Path(td)/"state.db");trust(e);activate_context(e,"m","left",1);activate_context(e,"m","right",-1)
        dup=[f"dup{i}" for i in range(16)];ind=[f"ind{i}" for i in range(3)]
        for s in dup+ind:trust(e,s)
        train_clique_dependency(e,dup)
        for i,s in enumerate(dup):e.observe_procedure_route("m",{"signal":True},"left",evidence_id=f"d{i}",source_id=s)
        for i,s in enumerate(ind):e.observe_procedure_route("m",{"signal":True},"right",evidence_id=f"i{i}",source_id=s)
        freq=e.route_procedure_context("m",{"signal":True},epistemic_mode="frequency",min_support=1)
        cov=e.route_procedure_context("m",{"signal":True},epistemic_mode="full_covariance",min_support=1)
        out["duplicate_majority"]={"frequency":freq["status"],"frequency_context":freq.get("context"),
                                   "covariance":cov["status"],"covariance_context":cov.get("context"),
                                   "cov_left_support":cov["support"]["left"],"cov_right_support":cov["support"]["right"]}
        e.close()
    # Query selection: duplicated bait vs independent useful feature.
    with tempfile.TemporaryDirectory() as td:
        e=ASMEngine(Path(td)/"state.db");trust(e);activate_context(e,"m","left",1);activate_context(e,"m","right",-1)
        low_a=[f"la{i}" for i in range(6)];low_b=[f"lb{i}" for i in range(6)];high_a=[f"ha{i}" for i in range(4)];high_b=[f"hb{i}" for i in range(4)]
        for s in low_a+low_b+high_a+high_b:trust(e,s)
        def clique(sources,prefix):
            rng=random.Random(11)
            for i in range(100):
                truth="A" if rng.random()<0.5 else "B";obs=truth if rng.random()<0.7 else ("B" if truth=="A" else "A")
                e.observe_evidence_dependency_trial(f"{prefix}-{i}",resolved_hypothesis=truth,observations={s:[obs] for s in sources})
        clique(low_a,"qa");clique(low_b,"qb")
        for i,s in enumerate(low_a):e.observe_procedure_route("m",{"a_bad":False},"left",evidence_id=f"la-{i}",source_id=s)
        for i,s in enumerate(low_b):e.observe_procedure_route("m",{"a_bad":True},"right",evidence_id=f"lb-{i}",source_id=s)
        for i,s in enumerate(high_a):e.observe_procedure_route("m",{"z_good":False},"left",evidence_id=f"ha-{i}",source_id=s)
        for i,s in enumerate(high_b):e.observe_procedure_route("m",{"z_good":True},"right",evidence_id=f"hb-{i}",source_id=s)
        freq=e.route_procedure_context("m",{},epistemic_mode="frequency")
        cov=e.route_procedure_context("m",{},epistemic_mode="full_covariance")
        out["query"]={"frequency_feature":freq.get("information_query",{}).get("feature"),"covariance_feature":cov.get("information_query",{}).get("feature")}
        e.close()
    return out


def performance_benchmark():
    with tempfile.TemporaryDirectory() as td:
        e=ASMEngine(Path(td)/"state.db");trust(e);activate_context(e,"m","left",1);activate_context(e,"m","right",-1)
        sources=[f"s{i}" for i in range(32)]
        for s in sources:trust(e,s)
        # AR-like exact provider to exercise covariance solve/cache without training cost.
        pairs={}
        for i,a in enumerate(sources):
            for j,b in enumerate(sources[i+1:],i+1):
                rho=0.55**abs(i-j)
                if rho>0.01:pairs[key(a,b)]=rho
        e.procedures.dependency_provider=lambda _s:{"pairwise":pairs,"version":777}
        for i,s in enumerate(sources[:16]):e.observe_procedure_route("m",{"signal":True},"left",evidence_id=f"l{i}",source_id=s)
        for i,s in enumerate(sources[16:]):e.observe_procedure_route("m",{"signal":False},"right",evidence_id=f"r{i}",source_id=s)
        # warm cache
        e.route_procedure_context("m",{"signal":True},epistemic_mode="dependency",min_support=1)
        e.route_procedure_context("m",{"signal":True},epistemic_mode="covariance",min_support=1)
        def med(mode):
            vals=[]
            for _ in range(300):
                t=time.perf_counter_ns();e.route_procedure_context("m",{"signal":True},epistemic_mode=mode,min_support=1);vals.append((time.perf_counter_ns()-t)/1e6)
            return statistics.median(vals)
        out={"local_median_ms":med("dependency"),"covariance_median_ms":med("covariance")}
        e.close();return out

if __name__=="__main__":
    result={"synthetic":synthetic_matrix_benchmark(),"real":real_dependency_benchmark(),"performance":performance_benchmark()}
    print(json.dumps(result,indent=2,sort_keys=True))
