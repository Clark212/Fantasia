from __future__ import annotations
import random,tempfile,unittest
from pathlib import Path
from asm import ASMEngine
from asm.procedure_cortex import ProcedureCortex

def key(a,b):return f"{a}\t{b}" if a<b else f"{b}\t{a}"
def rows(names):return [{"source":s,"reliability":1.0,"context":"x","features":{}} for s in names]
def one_factor(load):
 names=[f"s{i:02d}" for i in range(len(load))];pairs={}
 for i,a in enumerate(names):
  for j,b in enumerate(names[i+1:],i+1):pairs[key(a,b)]=load[i]*load[j]
 return names,pairs
def exact(load):
 inv=[1/(1-x*x) for x in load];den=1+sum(x*x*d for x,d in zip(load,inv));c=sum(x*d for x,d in zip(load,inv))/den
 return [d*(1-x*c) for x,d in zip(load,inv)]
def cortex(td,pairs,stats=None):return ProcedureCortex(Path(td)/"p.db",trust_provider=lambda _s:{"reliability":1.0,"version":1},dependency_provider=lambda _s:{"pairwise":dict(pairs),"pairwise_stats":dict(stats or {}),"version":1})

class R1(unittest.TestCase):
 def test_wide_32_recovers_boundary(self):
  load=[.04+(.39-.04)*i/31 for i in range(32)];names,pairs=one_factor(load);truth=sum(exact(load))
  with tempfile.TemporaryDirectory() as td:
   c=cortex(td,pairs);r=rows(names);old=sum(c._route_support_weights(r,"covariance"));new=sum(c._route_support_weights(r,"wide_covariance"));self.assertLess(old,15);self.assertGreater(truth,15);self.assertAlmostEqual(new,truth,places=9);c.close()
 def test_wide_64_matches_closed_form(self):
  load=[.04+(.18-.04)*i/63 for i in range(64)];names,pairs=one_factor(load);truth=sum(exact(load))
  with tempfile.TemporaryDirectory() as td:
   c=cortex(td,pairs);self.assertAlmostEqual(sum(c._route_support_weights(rows(names),"wide_covariance")),truth,places=8);c.close()
 def test_negative_inverse_falls_back(self):
  load=[.08+(.34-.08)*i/47 for i in range(48)];names,pairs=one_factor(load);self.assertLess(min(exact(load)),0)
  with tempfile.TemporaryDirectory() as td:
   c=cortex(td,pairs);r=rows(names);self.assertEqual(c._route_support_weights(r,"wide_covariance"),c._route_support_weights(r,"dependency"));c.close()
 def test_latent_weak_field(self):
  names=[f"s{i}" for i in range(12)];pairs={};stats={}
  for i,a in enumerate(names):
   for b in names[i+1:]:stats[key(a,b)]={"raw":.12,"active":0.0,"trials":100,"p":1.0,"fdr_accepted":False}
  with tempfile.TemporaryDirectory() as td:
   c=cortex(td,pairs,stats);r=rows(names);self.assertEqual(sum(c._route_support_weights(r,"covariance")),12);self.assertLess(sum(c._route_support_weights(r,"latent")),7);c.close()
 def test_latent_two_overlapping_factors(self):
  names=[f"s{i}" for i in range(12)];L={s:(.36 if i<8 else 0,.36 if i>=4 else 0) for i,s in enumerate(names)};stats={}
  for i,a in enumerate(names):
   for b in names[i+1:]:
    raw=L[a][0]*L[b][0]+L[a][1]*L[b][1];stats[key(a,b)]={"raw":raw,"active":0.0,"trials":100,"p":1.0,"fdr_accepted":False}
  with tempfile.TemporaryDirectory() as td:
   c=cortex(td,{},stats);fit=c._route_latent_factor_fit(tuple(sorted(names)),stats);self.assertIsNotNone(fit);self.assertGreaterEqual(fit["explained_energy"],.65);self.assertLess(sum(c._route_support_weights(rows(names),"latent")),12);c.close()
 def test_sparse_rejected(self):
  names=[f"s{i}" for i in range(12)];stats={}
  for i,a in enumerate(names):
   for b in names[i+1:]:
    ia=int(a[1:]);ib=int(b[1:]);raw=.25 if ia//2==ib//2 else 0;stats[key(a,b)]={"raw":raw,"active":0,"trials":100,"p":1,"fdr_accepted":False}
  with tempfile.TemporaryDirectory() as td:
   c=cortex(td,{},stats);r=rows(names);self.assertEqual(c._route_support_weights(r,"latent"),c._route_support_weights(r,"covariance"));c.close()
 def test_latent_monotone(self):
  names=[f"s{i}" for i in range(10)];pairs={key("s0","s1"):.2};stats={}
  for i,a in enumerate(names):
   for b in names[i+1:]:
    raw=.2 if {a,b}=={"s0","s1"} else .11;stats[key(a,b)]={"raw":raw,"active":pairs.get(key(a,b),0),"trials":100,"p":1,"fdr_accepted":key(a,b) in pairs}
  with tempfile.TemporaryDirectory() as td:
   c=cortex(td,pairs,stats);r=rows(names);base=c._route_support_weights(r,"wide_covariance");lat=c._route_support_weights(r,"latent");self.assertTrue(all(x<=y+1e-12 for x,y in zip(lat,base)));c.close()
 def test_real_hidden_common_cause(self):
  with tempfile.TemporaryDirectory() as td:
   e=ASMEngine(Path(td)/"s.db");rng=random.Random(3);names=[f"s{i}" for i in range(12)]
   for t in range(192):
    p=.8 if rng.random()<.5 else .4;obs={s:["A" if rng.random()<p else "B"] for s in names};e.observe_evidence_dependency_trial(str(t),resolved_hypothesis="A",observations=obs)
   st=e._procedure_dependency_status(names);self.assertEqual(st["pairwise_fdr"]["accepted_pairs"],0);r=rows(names);base=sum(e.procedures._route_support_weights(r,"covariance"));lat=sum(e.procedures._route_support_weights(r,"latent"));self.assertAlmostEqual(base,12,places=10);self.assertLess(abs(lat-12/(1+11/6)),.75);e.close()
 def test_real_independent_rejected(self):
  with tempfile.TemporaryDirectory() as td:
   e=ASMEngine(Path(td)/"s.db");rng=random.Random(0);names=[f"s{i}" for i in range(12)]
   for t in range(192):
    obs={s:["A" if rng.random()<.6 else "B"] for s in names};e.observe_evidence_dependency_trial(str(t),resolved_hypothesis="A",observations=obs)
   r=rows(names);self.assertEqual(e.procedures._route_support_weights(r,"latent"),e.procedures._route_support_weights(r,"covariance"));e.close()
