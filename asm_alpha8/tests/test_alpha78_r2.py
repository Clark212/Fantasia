from __future__ import annotations
import tempfile,unittest
from pathlib import Path
from asm import ASMEngine
from asm.procedure_cortex import ProcedureCortex
from tests.test_alpha76_r3 import activate_context,trust

def key(a,b):return f"{a}\t{b}" if a<b else f"{b}\t{a}"
def rows(names):return [{"source":s,"reliability":1.0,"context":"x","features":{}} for s in names]
def stats_field(names,fn,trials=100):
 out={}
 for i,a in enumerate(names):
  for b in names[i+1:]:out[key(a,b)]={"raw":float(fn(a,b)),"active":0.0,"trials":trials,"p":1.0,"fdr_accepted":False}
 return out
class R2(unittest.TestCase):
 def test_equicorrelated_latent_matches_scaled_design_effect(self):
  names=[f"s{i}" for i in range(12)];stats=stats_field(names,lambda _a,_b:.12)
  with tempfile.TemporaryDirectory() as td:
   c=ProcedureCortex(Path(td)/"p.db",trust_provider=lambda _s:{"reliability":1.0,"version":1},dependency_provider=lambda _s:{"pairwise":{},"pairwise_stats":stats,"version":1});got=sum(c._route_support_weights(rows(names),"latent"));self.assertAlmostEqual(got,12/(1+11*(.12*.85)),places=6);c.close()
 def test_two_factor_direct_weights_are_bounded(self):
  names=[f"s{i}" for i in range(12)];L={s:(.36 if i<8 else 0,.36 if i>=4 else 0) for i,s in enumerate(names)};stats=stats_field(names,lambda a,b:L[a][0]*L[b][0]+L[a][1]*L[b][1])
  with tempfile.TemporaryDirectory() as td:
   c=ProcedureCortex(Path(td)/"p.db",trust_provider=lambda _s:{"reliability":1.0,"version":1},dependency_provider=lambda _s:{"pairwise":{},"pairwise_stats":stats,"version":1});fit=c._route_latent_factor_fit(tuple(sorted(names)),stats);m=c._route_factor_information_weights(tuple(sorted(names)),fit);self.assertIsNotNone(m);self.assertTrue(all(0<=x<=1 for x in m.values()));c.close()
 def test_weak_common_cause_boundary_stops_false_route(self):
  with tempfile.TemporaryDirectory() as td:
   e=ASMEngine(Path(td)/"s.db");trust(e);activate_context(e,"m","left",1);activate_context(e,"m","right",-1);bad=[f"b{i}" for i in range(10)];good="good"
   for s in bad+[good]:trust(e,s)
   stats=stats_field(bad+[good],lambda a,b:.12 if a in bad and b in bad else 0.0);e.procedures.dependency_provider=lambda _s:{"pairwise":{},"pairwise_stats":stats,"version":900}
   for i,s in enumerate(bad):e.observe_procedure_route("m",{"signal":True},"left",evidence_id=f"b{i}",source_id=s)
   e.observe_procedure_route("m",{"signal":True},"right",evidence_id="g",source_id=good)
   old=e.route_procedure_context("m",{"signal":True},epistemic_mode="full_covariance",min_support=1);new=e.route_procedure_context("m",{"signal":True},epistemic_mode="full_latent",min_support=1)
   self.assertEqual((old["status"],old.get("context")),("routed","left"));self.assertNotEqual((new["status"],new.get("context")),("routed","left"));e.close()
 def test_latent_cache_invalidates_on_version_change(self):
  names=[f"s{i}" for i in range(12)];state={"v":1,"stats":stats_field(names,lambda _a,_b:.12)}
  with tempfile.TemporaryDirectory() as td:
   c=ProcedureCortex(Path(td)/"p.db",trust_provider=lambda _s:{"reliability":1.0,"version":1},dependency_provider=lambda _s:{"pairwise":{},"pairwise_stats":state["stats"],"version":state["v"]});r=rows(names);before=sum(c._route_support_weights(r,"latent"));state["v"]=2;state["stats"]=stats_field(names,lambda _a,_b:0.0);after=sum(c._route_support_weights(r,"latent"));self.assertLess(before,8);self.assertAlmostEqual(after,12,places=12);c.close()
