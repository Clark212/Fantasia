from __future__ import annotations

import json, math, random, statistics, tempfile, time
from pathlib import Path
from asm import ASMEngine
from tests.test_alpha76_r3 import activate_context, trust
from tests.test_alpha76_r4 import train_independent_dependency_set


def scale_false_discovery():
    out={}
    for sources,seeds in ((16,300),(32,200),(64,80)):
        base_any=accepted_any=base_pairs=accepted_pairs=suppressed=0
        for seed in range(seeds):
            with tempfile.TemporaryDirectory() as td:
                e=ASMEngine(Path(td)/"state.db")
                names=train_independent_dependency_set(e,sources=sources,seed=seed)
                status=e._procedure_dependency_status(names)["pairwise_fdr"]
                base_any += status["base_active_pairs"]>0
                accepted_any += status["accepted_pairs"]>0
                base_pairs += status["base_active_pairs"]
                accepted_pairs += status["accepted_pairs"]
                suppressed += status["suppressed_pairs"]
                e.close()
        out[str(sources)]={
            "runs":seeds,"base_any":base_any,"accepted_any":accepted_any,
            "base_pairs":base_pairs,"accepted_pairs":accepted_pairs,"suppressed_pairs":suppressed,
            "base_any_rate":base_any/seeds,"accepted_any_rate":accepted_any/seeds,
        }
    return out


def covariance_design_effect():
    cases=[]
    sq_errors=[];linear_errors=[]
    for k in (2,4,8,16,32):
        for rho in (0.1,0.25,0.5,0.75,1.0):
            exact=k/(1.0+(k-1)*rho)
            square=k/(1.0+(k-1)*rho*rho)
            linear=k/(1.0+(k-1)*rho)
            sq=abs(square-exact); li=abs(linear-exact)
            sq_errors.append(sq);linear_errors.append(li)
            cases.append({"k":k,"rho":rho,"covariance_neff":exact,"r3_rho2":square,"r4_rho":linear,
                          "r3_abs_error":sq,"r4_abs_error":li})
    return {"cases":cases,"mean_abs_error_r3":statistics.mean(sq_errors),
            "mean_abs_error_r4":statistics.mean(linear_errors),"max_abs_error_r3":max(sq_errors)}


def accepted_false_pairs(seed,sources=32):
    with tempfile.TemporaryDirectory() as td:
        e=ASMEngine(Path(td)/"state.db")
        names=train_independent_dependency_set(e,sources=sources,seed=seed)
        status=e._procedure_dependency_status(names)
        accepted=[k for k,v in status["pairwise"].items() if v>0]
        meta=status["pairwise_fdr"]
        e.close();return accepted,meta


def false_belief_recovery():
    # These are deterministic FDR-surviving false-pair seeds in the first 200
    # 32-source independent experiments under this exact generator.
    seeds=(73,139,159,164)
    rows=[]
    for seed in seeds:
        with tempfile.TemporaryDirectory() as td:
            e=ASMEngine(Path(td)/"state.db")
            trust(e); activate_context(e,"m","left",1); activate_context(e,"m","right",-1)
            names=train_independent_dependency_set(e,sources=32,seed=seed)
            status=e._procedure_dependency_status(names)
            accepted=[k for k,v in status["pairwise"].items() if v>0]
            if len(accepted)!=1:
                rows.append({"seed":seed,"accepted":accepted,"error":"expected_one_false_pair"});e.close();continue
            a,b=accepted[0].split("\t")
            third=next(s for s in names if s not in (a,b))
            for s in names: trust(e,s)
            chosen={a,b,third}
            for s in names:
                e.observe_procedure_route("m",{"mode":False if s in chosen else True},
                                          "left" if s in chosen else "right",
                                          evidence_id=f"route-{s}",source_id=s)
            before=e.route_procedure_context("m",{"mode":False},epistemic_mode="dependency")
            before_count=e.procedure_route_evidence_status("m")["total_records"]
            rng=random.Random(9000+seed); recovered=None; last=None
            for t in range(1,129):
                truth="A" if rng.random()<.5 else "B"
                def noisy(): return truth if rng.random()<.7 else ("B" if truth=="A" else "A")
                e.observe_evidence_dependency_trial(f"recover-{seed}-{t}",resolved_hypothesis=truth,
                    observations={a:[noisy()],b:[noisy()]},temporal_index=t)
                last=e.route_procedure_context("m",{"mode":False},epistemic_mode="dependency")
                if last.get("status")=="routed" and last.get("context")=="left":
                    recovered=t;break
            rows.append({"seed":seed,"pair":accepted[0],"before_status":before.get("status"),
                         "before_support":before.get("support",{}).get("left"),"recovered_at_trials":recovered,
                         "after_status":None if last is None else last.get("status"),
                         "route_history_mutations":e.procedure_route_evidence_status("m")["total_records"]-before_count})
            e.close()
    delays=[r["recovered_at_trials"] for r in rows if isinstance(r.get("recovered_at_trials"),int)]
    return {"cases":rows,"recovered":len(delays),"total":len(rows),
            "mean_recovery_trials":statistics.mean(delays) if delays else None,
            "max_recovery_trials":max(delays) if delays else None}


def true_dependency_sensitivity():
    out={}
    # Bounded sample: one real dependent pair embedded among 31 unrelated sources.
    for shared in (0.5,0.75,1.0):
        detected=base=0; trials=24
        for seed in range(trials):
            with tempfile.TemporaryDirectory() as td:
                e=ASMEngine(Path(td)/"state.db"); rng=random.Random(10000+seed)
                names=[f"s{i}" for i in range(32)]
                for t in range(100):
                    truth="A" if rng.random()<.5 else "B"
                    def noisy(): return truth if rng.random()<.7 else ("B" if truth=="A" else "A")
                    if rng.random()<shared:
                        x=noisy(); obs={"s0":[x],"s1":[x]}
                    else: obs={"s0":[noisy()],"s1":[noisy()]}
                    for i in range(2,32):obs[f"s{i}"]=[noisy()]
                    e.observe_evidence_dependency_trial(f"t{t}",resolved_hypothesis=truth,observations=obs)
                d=e.evidence_dependency.pair_dependency("s0","s1")
                base += d["active_correlation"]>0
                status=e._procedure_dependency_status(names)
                detected += status["pairwise"].get("s0\ts1",0)>0
                e.close()
        out[str(shared)]={"runs":trials,"base_active":base,"fdr_accepted":detected}
    return out


def performance():
    with tempfile.TemporaryDirectory() as td:
        e=ASMEngine(Path(td)/"state.db");trust(e);activate_context(e,"m","left",1);activate_context(e,"m","right",-1)
        names=[f"s{i}" for i in range(32)]
        for s in names:trust(e,s)
        rng=random.Random(42)
        for t in range(100):
            truth="A" if rng.random()<.5 else "B";obs={}
            for s in names:obs[s]=[truth if rng.random()<.7 else ("B" if truth=="A" else "A")]
            e.observe_evidence_dependency_trial(f"p{t}",resolved_hypothesis=truth,observations=obs)
        for i,s in enumerate(names):
            e.observe_procedure_route("m",{"mode":False if i<4 else True},"left" if i<4 else "right",
                                      evidence_id=f"r{i}",source_id=s)
        lat=[]
        for _ in range(300):
            st=time.perf_counter_ns();e.route_procedure_context("m",{"mode":False},epistemic_mode="full");lat.append(time.perf_counter_ns()-st)
        e.close();return {"route_ms_median":statistics.median(lat)/1e6,"route_ms_p95":sorted(lat)[int(.95*len(lat))-1]/1e6}


def main():
    result={
        "benchmark":"ASM alpha.7.6 Experimental R4 false-dependency and covariance hardening",
        "scale_false_discovery":scale_false_discovery(),
        "covariance_design_effect":covariance_design_effect(),
        "false_belief_recovery":false_belief_recovery(),
        "true_dependency_sensitivity":true_dependency_sensitivity(),
        "performance":performance(),
    }
    print(json.dumps(result,indent=2,sort_keys=True))

if __name__=="__main__": main()
