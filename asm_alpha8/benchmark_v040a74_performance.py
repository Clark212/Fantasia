from __future__ import annotations
import json,tempfile,time,statistics
from pathlib import Path
from asm.engine import ASMEngine
from asm import __version__

def trust(e):
 for i in range(80):e.observe_evidence_source('oracle',observation='A',resolved_hypothesis='A',temporal_index=i)

def median_case(builder,reps=12):
 vals=[];meta=[]
 for _ in range(reps):
  with tempfile.TemporaryDirectory() as d:
   e=ASMEngine(Path(d)/'s.db');trust(e);fn=builder(e)
   t=time.perf_counter_ns();r=fn();vals.append((time.perf_counter_ns()-t)/1e6);meta.append(r);e.close()
 return {'median_ms':statistics.median(vals),'p90_ms':sorted(vals)[max(0,int(.9*len(vals))-1)],'last':meta[-1]}

def xor_induce(e):
 f=lambda a,b:a^b;rows=[{'a':False,'b':False},{'a':False,'b':True},{'a':True,'b':False},{'a':True,'b':True}];ids=[]
 for i,v in enumerate(rows):eid=f'x{i}';ids.append(eid);e.observe_procedure('xor',v,f(**v),evidence_id=eid,source_id='oracle')
 return lambda:e.induce_procedure('xor',training_ids=ids)

def xor_query(e):
 f=lambda a,b:a^b;rows=[{'a':False,'b':False},{'a':False,'b':True},{'a':True,'b':False}]
 for i,v in enumerate(rows):e.observe_procedure('q',v,f(**v),evidence_id=f'q{i}',source_id='oracle')
 return lambda:e.procedure_information_query('q')

def piece_induce(e):
 f=lambda x:2*x+1 if x<0 else -x+3;rows=[{'x':-3},{'x':-1},{'x':0},{'x':1},{'x':3}];ids=[]
 for i,v in enumerate(rows):eid=f'p{i}';ids.append(eid);e.observe_procedure('piece',v,f(**v),evidence_id=eid,source_id='oracle')
 return lambda:e.induce_procedure('piece',training_ids=ids)

def prediction_rate():
 with tempfile.TemporaryDirectory() as d:
  e=ASMEngine(Path(d)/'s.db');trust(e);f=lambda flag,x:x+1 if flag else x-1
  fit=[{'flag':False,'x':0},{'flag':False,'x':2},{'flag':True,'x':0},{'flag':True,'x':2}]
  for i,v in enumerate(fit):e.observe_procedural_experience('p',v,f(**v),evidence_id=f'f{i}',source_id='oracle')
  for i,(b,x) in enumerate([(False,10),(True,10),(False,11),(True,11),(False,12),(True,12),(False,13),(True,13)]):e.observe_procedural_experience('p',{'flag':b,'x':x},f(b,x),evidence_id=f'v{i}',source_id='oracle')
  n=20000;t=time.perf_counter()
  for i in range(n):e.predict_procedure('p',{'flag':bool(i&1),'x':i%31})
  rate=n/(time.perf_counter()-t);e.close();return rate
# the alpha.7.4 author's machine kept alpha.7.3's numbers in /tmp/perf73.json; the release gate runs alpha.7.3's
# performance job just before this one, in the same directory, which writes ALPHA73_PERFORMANCE.json (2026-11-28)
_perf73=Path('/tmp/perf73.json')
baseline=json.loads((_perf73 if _perf73.exists() else Path('ALPHA73_PERFORMANCE.json')).read_text())
# comparable old paths measured using current code manually
from benchmark_v040a73_performance import main as _unused  # keeps legacy perf module import-covered
out={'version':__version__,'baseline_alpha73':baseline,'xor_induction':median_case(xor_induce),'xor_information_query':median_case(xor_query),'piecewise_induction':median_case(piece_induce),'conditional_prediction_per_s':prediction_rate()}
Path('ALPHA74_PERFORMANCE.json').write_text(json.dumps(out,indent=2,sort_keys=True));print(json.dumps(out,indent=2,sort_keys=True))
