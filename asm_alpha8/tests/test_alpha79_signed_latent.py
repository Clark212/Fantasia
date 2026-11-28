from __future__ import annotations
import random,tempfile,unittest
from pathlib import Path
from asm import ASMEngine
from asm.procedure_cortex import ProcedureCortex
from tests.test_alpha76_r3 import activate_context, trust


def key(a,b): return f"{a}\t{b}" if a<b else f"{b}\t{a}"
def rows(names): return [{"source":s,"reliability":1.0,"context":"x","features":{}} for s in names]
def stats_field(names,fn,trials=192):
    out={}
    for i,a in enumerate(names):
        for b in names[i+1:]:
            out[key(a,b)]={"raw":float(fn(a,b)),"active":0.0,"trials":int(trials),"p":1.0,"fdr_accepted":False}
    return out

def cortex(td,names,stats,state=None):
    if state is None: state={"v":1,"stats":stats}
    return ProcedureCortex(Path(td)/"p.db",trust_provider=lambda _s:{"reliability":1.0,"version":1},
        dependency_provider=lambda _s:{"pairwise":{},"pairwise_stats":state["stats"],"version":state["v"]})

class Alpha79SignedLatentTests(unittest.TestCase):
    def test_signed_hidden_factor_reduces_support(self):
        names=[f"s{i}" for i in range(8)];pol={s:(1 if i<4 else -1) for i,s in enumerate(names)}
        stats=stats_field(names,lambda a,b:.14*pol[a]*pol[b])
        with tempfile.TemporaryDirectory() as td:
            c=cortex(td,names,stats);r=rows(names)
            self.assertAlmostEqual(sum(c._route_support_weights(r,"latent")),8.0,places=12)
            self.assertLess(sum(c._route_support_weights(r,"signed_latent")),5.0);c.close()

    def test_signed_guard_is_monotone_against_alpha78(self):
        names=[f"s{i}" for i in range(8)];pol={s:(1 if i<4 else -1) for i,s in enumerate(names)}
        stats=stats_field(names,lambda a,b:.14*pol[a]*pol[b])
        with tempfile.TemporaryDirectory() as td:
            c=cortex(td,names,stats);base=c._route_support_weights(rows(names),"latent");new=c._route_support_weights(rows(names),"signed_latent")
            self.assertTrue(all(n<=b+1e-12 for n,b in zip(new,base)));c.close()

    def test_sparse_hidden_subgroup_inside_unrelated_sources(self):
        names=[f"s{i}" for i in range(16)];core=set(names[:10])
        stats=stats_field(names,lambda a,b:.13 if a in core and b in core else 0.0)
        with tempfile.TemporaryDirectory() as td:
            c=cortex(td,names,stats);w=dict(zip(names,c._route_support_weights(rows(names),"signed_latent")))
            self.assertTrue(all(w[s]<1.0 for s in names[:10]));self.assertTrue(all(abs(w[s]-1.0)<1e-12 for s in names[10:]));c.close()

    def test_frustrated_signed_graph_falls_back(self):
        names=[f"s{i}" for i in range(8)];rng=random.Random(17)
        signs={}
        for i,a in enumerate(names):
            for b in names[i+1:]: signs[key(a,b)]=1 if rng.random()<.5 else -1
        stats=stats_field(names,lambda a,b:.14*signs[key(a,b)])
        with tempfile.TemporaryDirectory() as td:
            c=cortex(td,names,stats);r=rows(names)
            self.assertEqual(c._route_support_weights(r,"signed_latent"),c._route_support_weights(r,"latent"));c.close()

    def test_overlapping_two_factor_twenty_source_structure(self):
        names=[f"s{i}" for i in range(20)]
        def corr(a,b):
            i=int(a[1:]);j=int(b[1:])
            la=(.35 if i<14 else 0.0,.35 if i>=6 else 0.0);lb=(.35 if j<14 else 0.0,.35 if j>=6 else 0.0)
            return la[0]*lb[0]+la[1]*lb[1]
        stats=stats_field(names,corr)
        with tempfile.TemporaryDirectory() as td:
            c=cortex(td,names,stats);base=sum(c._route_support_weights(rows(names),"latent"));new=sum(c._route_support_weights(rows(names),"signed_latent"))
            self.assertAlmostEqual(base,20.0,places=12);self.assertLess(new,9.0);c.close()

    def test_approximate_null_field_has_no_false_activation_fixed_sweep(self):
        names=tuple(f"s{i}" for i in range(8));rng=random.Random(20261007);sd=(1/(192-3))**0.5
        with tempfile.TemporaryDirectory() as td:
            c=ProcedureCortex(Path(td)/"p.db",trust_provider=lambda _s:{"reliability":1.0,"version":1},dependency_provider=None)
            for seed in range(500):
                stats=stats_field(names,lambda _a,_b:0.0)
                for st in stats.values(): st["raw"]=max(-.95,min(.95,rng.gauss(0,sd)))
                dep={"pairwise":{},"pairwise_stats":stats,"version":seed}
                got=c._route_signed_latent_dependency_weights(names,dep)
                self.assertTrue(all(abs(v-1.0)<1e-12 for v in got.values()))
            c.close()

    def test_real_learned_signed_dependence(self):
        with tempfile.TemporaryDirectory() as td:
            e=ASMEngine(Path(td)/"s.db");rng=random.Random(0);names=[f"s{i}" for i in range(8)]
            for t in range(192):
                truth="A" if rng.random()<.5 else "B";other="B" if truth=="A" else "A";z=rng.random()<.5;obs={}
                for i,s in enumerate(names):
                    target=z if i<4 else (not z);correct=target if rng.random()<.70 else (not target);obs[s]=[truth if correct else other]
                e.observe_evidence_dependency_trial(f"sig-{t}",resolved_hypothesis=truth,observations=obs)
            base=sum(e.procedures._route_support_weights(rows(names),"latent"));new=sum(e.procedures._route_support_weights(rows(names),"signed_latent"))
            self.assertGreater(base,7.0);self.assertLess(new,5.0);e.close()

    def test_real_independent_sources_are_not_discounted(self):
        with tempfile.TemporaryDirectory() as td:
            e=ASMEngine(Path(td)/"s.db");rng=random.Random(0);names=[f"s{i}" for i in range(8)]
            for t in range(192):
                truth="A" if rng.random()<.5 else "B";other="B" if truth=="A" else "A";obs={s:[truth if rng.random()<.6 else other] for s in names}
                e.observe_evidence_dependency_trial(f"ind-{t}",resolved_hypothesis=truth,observations=obs)
            self.assertEqual(e.procedures._route_support_weights(rows(names),"signed_latent"),e.procedures._route_support_weights(rows(names),"latent"));e.close()

    def test_temporal_recovery_does_not_rewrite_route_history(self):
        with tempfile.TemporaryDirectory() as td:
            e=ASMEngine(Path(td)/"s.db");rng=random.Random(44);names=[f"s{i}" for i in range(8)]
            trust(e);activate_context(e,"m","left",1);activate_context(e,"m","right",-1)
            for s in names: trust(e,s)
            for i,s in enumerate(names): e.observe_procedure_route("m",{"x":1},"left" if i<4 else "right",evidence_id=f"r{i}",source_id=s)
            count=e.procedure_route_evidence_status("m")["total_records"]
            for t in range(192):
                truth="A" if rng.random()<.5 else "B";other="B" if truth=="A" else "A";z=rng.random()<.5;obs={}
                for i,s in enumerate(names):
                    target=z if i<4 else not z;correct=target if rng.random()<.70 else not target;obs[s]=[truth if correct else other]
                e.observe_evidence_dependency_trial(f"sig-{t}",resolved_hypothesis=truth,observations=obs,temporal_index=t+1)
            self.assertLess(sum(e.procedures._route_support_weights(rows(names),"signed_latent")),5.0)
            for t in range(192):
                truth="A" if rng.random()<.5 else "B";other="B" if truth=="A" else "A";obs={s:[truth if rng.random()<.6 else other] for s in names}
                e.observe_evidence_dependency_trial(f"rec-{t}",resolved_hypothesis=truth,observations=obs,temporal_index=193+t)
            self.assertAlmostEqual(sum(e.procedures._route_support_weights(rows(names),"signed_latent")),8.0,places=12)
            self.assertEqual(e.procedure_route_evidence_status("m")["total_records"],count);e.close()

    def test_latent_group_migration_recovers_old_sources(self):
        names=[f"s{i}" for i in range(12)]
        def field(group):
            g=set(group);pol={s:(1 if i<len(group)//2 else -1) for i,s in enumerate(group)}
            return stats_field(names,lambda a,b:.14*pol[a]*pol[b] if a in g and b in g else 0.0)
        state={"v":1,"stats":field(names[:8])}
        with tempfile.TemporaryDirectory() as td:
            c=cortex(td,names,state["stats"],state);a=dict(zip(names,c._route_support_weights(rows(names),"signed_latent")))
            state["v"]=2;state["stats"]=field(names[4:12]);b=dict(zip(names,c._route_support_weights(rows(names),"signed_latent")))
            self.assertTrue(all(a[s]<1 for s in names[:8]));self.assertTrue(all(abs(b[s]-1.0)<1e-12 for s in names[:4]));self.assertTrue(all(b[s]<1 for s in names[4:12]));c.close()

    def test_cache_invalidates_on_dependency_version_change(self):
        names=[f"s{i}" for i in range(8)];pol={s:(1 if i<4 else -1) for i,s in enumerate(names)}
        state={"v":1,"stats":stats_field(names,lambda a,b:.14*pol[a]*pol[b])}
        with tempfile.TemporaryDirectory() as td:
            c=cortex(td,names,state["stats"],state);before=sum(c._route_support_weights(rows(names),"signed_latent"))
            state["v"]=2;state["stats"]=stats_field(names,lambda _a,_b:0.0);after=sum(c._route_support_weights(rows(names),"signed_latent"))
            self.assertLess(before,5.0);self.assertAlmostEqual(after,8.0,places=12);c.close()

if __name__=='__main__': unittest.main()
