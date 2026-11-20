from __future__ import annotations

import json
import random
import statistics
import tempfile
import time
from pathlib import Path

from asm import ASMEngine
from tests.test_alpha76_r3 import (
    activate_context,
    train_clique_dependency,
    train_exact_reliability,
    train_pair_dependency,
    trust,
)


def make_two(td, mechanism="m"):
    e=ASMEngine(Path(td)/"state.db")
    trust(e)
    activate_context(e,mechanism,"left",1)
    activate_context(e,mechanism,"right",-1)
    return e


def partial_trial(shared,seed):
    with tempfile.TemporaryDirectory() as td:
        e=make_two(td)
        sources=("s1","s2","s3","s4")
        for source in sources: trust(e,source)
        train_pair_dependency(e,"s1","s2",shared=shared,trials=100,seed=seed)
        for i,source in enumerate(sources):
            e.observe_procedure_route("m",{"mode":False},"left",evidence_id=f"r{i}",source_id=source)
        pair=e.evidence_dependency.pair_dependency("s1","s2")
        out={}
        for mode in ("frequency","reliability","dependency","full"):
            r=e.route_procedure_context("m",{"mode":False},epistemic_mode=mode)
            out[mode]={"status":r["status"],"context":r.get("context"),"confidence":r.get("confidence"),
                       "left_support":r.get("support",{}).get("left",0.0)}
        e.close()
        return {"rho":pair["active_correlation"],"modes":out}


def partial_sweep():
    result={}
    for shared in (0.0,0.25,0.5,0.75,1.0):
        xs=[partial_trial(shared,seed) for seed in range(12)]
        result[str(shared)]={
            "mean_active_correlation":statistics.mean(x["rho"] for x in xs),
            "frequency_routes":sum(x["modes"]["frequency"]["status"]=="routed" for x in xs),
            "reliability_routes":sum(x["modes"]["reliability"]["status"]=="routed" for x in xs),
            "dependency_routes":sum(x["modes"]["dependency"]["status"]=="routed" for x in xs),
            "full_routes":sum(x["modes"]["full"]["status"]=="routed" for x in xs),
            "mean_full_support":statistics.mean(x["modes"]["full"]["left_support"] for x in xs),
        }
    return result


def reliability_ablation():
    with tempfile.TemporaryDirectory() as td:
        e=make_two(td)
        lows=[]
        for i in range(6):
            source=f"low{i}";lows.append(source);train_exact_reliability(e,source,162,200)
        train_exact_reliability(e,"high",200,200)
        for i,source in enumerate(lows):
            e.observe_procedure_route("m",{"signal":True},"left",evidence_id=f"l{i}",source_id=source)
        e.observe_procedure_route("m",{"signal":True},"right",evidence_id="h",source_id="high")
        out={}
        for mode in ("frequency","reliability","full"):
            r=e.route_procedure_context("m",{"signal":True},epistemic_mode=mode)
            out[mode]={"status":r["status"],"context":r.get("context"),"confidence":r.get("confidence"),"support":r.get("support")}
        out["low_reliability"]=e.evidence_source_status("low0")["effective_reliability"]
        out["high_reliability"]=e.evidence_source_status("high")["effective_reliability"]
        e.close();return out


def clique_locality():
    with tempfile.TemporaryDirectory() as td:
        e=make_two(td)
        clique=[f"dup{i}" for i in range(16)]; independent=[f"ind{i}" for i in range(3)]
        for source in clique+independent: trust(e,source)
        train_clique_dependency(e,clique)
        for i,source in enumerate(clique+independent):
            e.observe_procedure_route("m",{"mode":False},"left",evidence_id=f"r{i}",source_id=source)
        rows=e.procedures._effective_route_rows("m"); weights=e.procedures._route_support_weights(rows,"dependency")
        per={row["source"]:w for row,w in zip(rows,weights)}
        result={
            "duplicate_cluster_sources":16,
            "duplicate_cluster_effective_support":sum(per[s] for s in clique),
            "independent_weights":[per[s] for s in independent],
            "total_effective_support":sum(weights),
        }
        e.close();return result


def repeated_history():
    with tempfile.TemporaryDirectory() as td:
        e=make_two(td);sources=("s1","s2","s3","s4")
        for source in sources:trust(e,source)
        train_pair_dependency(e,"s1","s2",shared=1.0,trials=100,seed=1)
        for t in range(20):
            for j,source in enumerate(sources):
                e.observe_procedure_route("m",{"mode":False},"left",evidence_id=f"r-{t}-{j}",root_id=f"root-{t}-{j}",source_id=source)
        rows=e.procedures._effective_route_rows("m")
        dep_weights=e.procedures._route_support_weights(rows,"dependency")
        full_weights=e.procedures._route_support_weights(rows,"full")
        giant=e.evidence_dependency.effective_batch([row["source"] for row in rows])
        route=e.route_procedure_context("m",{"mode":False},epistemic_mode="full")
        out={"raw_rows":len(rows),"local_dependency_support":sum(dep_weights),"local_full_support":sum(full_weights),
             "old_global_batch_effective_count":giant["effective_count"],"route_status":route["status"],"route_context":route.get("context")}
        e.close();return out


def drift_trials():
    rows=[]
    for seed in range(8):
        with tempfile.TemporaryDirectory() as td:
            e=make_two(td);sources=("s1","s2","s3","s4")
            for source in sources:trust(e,source)
            train_pair_dependency(e,"s1","s2",shared=1.0,start=0,trials=100,seed=seed+1,temporal=True)
            for i,source in enumerate(sources):e.observe_procedure_route("m",{"mode":False},"left",evidence_id=f"r{i}",source_id=source)
            before=e.route_procedure_context("m",{"mode":False},epistemic_mode="full")
            train_pair_dependency(e,"s1","s2",shared=0.0,start=100,trials=140,seed=seed+100,temporal=True)
            after=e.route_procedure_context("m",{"mode":False},epistemic_mode="full")
            rows.append({"before_status":before["status"],"after_status":after["status"],
                         "before_support":before["support"]["left"],"after_support":after["support"]["left"],
                         "after_rho":e.evidence_dependency.pair_dependency("s1","s2")["active_correlation"]})
            e.close()
    return {
        "trials":len(rows),"routes_before":sum(x["before_status"]=="routed" for x in rows),
        "routes_after":sum(x["after_status"]=="routed" for x in rows),
        "mean_support_before":statistics.mean(x["before_support"] for x in rows),
        "mean_support_after":statistics.mean(x["after_support"] for x in rows),
        "mean_after_correlation":statistics.mean(x["after_rho"] for x in rows),
    }


def adversarial_majority():
    out={}
    for size in (8,16,32):
        with tempfile.TemporaryDirectory() as td:
            e=make_two(td);dup=[f"dup{i}" for i in range(size)];ind=[f"ind{i}" for i in range(3)]
            for source in dup+ind:trust(e,source)
            train_clique_dependency(e,dup,trials=100,seed=7)
            for i,source in enumerate(dup):e.observe_procedure_route("m",{"signal":True},"left",evidence_id=f"d{i}",source_id=source)
            for i,source in enumerate(ind):e.observe_procedure_route("m",{"signal":True},"right",evidence_id=f"i{i}",source_id=source)
            freq=e.route_procedure_context("m",{"signal":True},epistemic_mode="frequency",min_support=1)
            full=e.route_procedure_context("m",{"signal":True},epistemic_mode="full",min_support=1)
            out[str(size)]={"frequency_status":freq["status"],"frequency_context":freq.get("context"),
                            "full_status":full["status"],"full_context":full.get("context"),
                            "full_support":full.get("support")}
            e.close()
    return out


def query_weighting():
    with tempfile.TemporaryDirectory() as td:
        e=make_two(td)
        low_a=[f"la{i}" for i in range(6)]; low_b=[f"lb{i}" for i in range(6)]
        high_a=[f"ha{i}" for i in range(4)]; high_b=[f"hb{i}" for i in range(4)]
        for source in low_a+low_b+high_a+high_b:trust(e,source)
        def clique(sources,prefix):
            rng=random.Random(11)
            for i in range(100):
                truth="A" if rng.random()<.5 else "B";obs=truth if rng.random()<.7 else ("B" if truth=="A" else "A")
                e.observe_evidence_dependency_trial(f"{prefix}-{i}",resolved_hypothesis=truth,observations={s:[obs] for s in sources})
        clique(low_a,"qa");clique(low_b,"qb")
        for i,s in enumerate(low_a):e.observe_procedure_route("m",{"a_bad":False},"left",evidence_id=f"la{i}",source_id=s)
        for i,s in enumerate(low_b):e.observe_procedure_route("m",{"a_bad":True},"right",evidence_id=f"lb{i}",source_id=s)
        for i,s in enumerate(high_a):e.observe_procedure_route("m",{"z_good":False},"left",evidence_id=f"ha{i}",source_id=s)
        for i,s in enumerate(high_b):e.observe_procedure_route("m",{"z_good":True},"right",evidence_id=f"hb{i}",source_id=s)
        before=e.procedure_route_evidence_status("m")["total_records"]
        freq=e.route_procedure_context("m",{},epistemic_mode="frequency")
        full=e.route_procedure_context("m",{},epistemic_mode="full")
        after=e.procedure_route_evidence_status("m")["total_records"]
        out={"frequency_query":freq["information_query"]["feature"],"full_query":full["information_query"]["feature"],
             "frequency_gain":freq["information_query"]["expected_information_gain"],"full_gain":full["information_query"]["expected_information_gain"],
             "state_mutations":after-before}
        e.close();return out


def performance():
    with tempfile.TemporaryDirectory() as td:
        e=make_two(td);sources=("s1","s2","s3","s4")
        for source in sources:trust(e,source)
        train_pair_dependency(e,"s1","s2",shared=.5,trials=100,seed=5)
        for t in range(12):
            for j,source in enumerate(sources):
                e.observe_procedure_route("m",{"mode":False,"other":t%2==0},"left",evidence_id=f"r-{t}-{j}",source_id=source)
        route_ns=[];query_ns=[]
        for _ in range(300):
            t=time.perf_counter_ns();e.route_procedure_context("m",{"mode":False,"other":True},epistemic_mode="full");route_ns.append(time.perf_counter_ns()-t)
            t=time.perf_counter_ns();e.route_procedure_context("m",{},epistemic_mode="full");query_ns.append(time.perf_counter_ns()-t)
        e.close()
        return {"route_latency_ms_median":statistics.median(route_ns)/1e6,"query_decision_ms_median":statistics.median(query_ns)/1e6}


def main():
    result={
        "benchmark":"ASM alpha.7.6 Experimental R3 epistemic procedure routing",
        "partial_hidden_correlation":partial_sweep(),
        "reliability_ablation":reliability_ablation(),
        "large_clique_locality":clique_locality(),
        "repeated_history":repeated_history(),
        "dependency_drift":drift_trials(),
        "adversarial_correlated_majority":adversarial_majority(),
        "information_query_weighting":query_weighting(),
        "performance":performance(),
    }
    print(json.dumps(result,indent=2,sort_keys=True))

if __name__=="__main__":main()
