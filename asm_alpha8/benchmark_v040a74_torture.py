from __future__ import annotations
import json,random,tempfile
from pathlib import Path
from asm.engine import ASMEngine


def trust(e):
    for i in range(80):e.observe_evidence_source('oracle',observation='A',resolved_hypothesis='A',temporal_index=i)

def feed(e,m,rows,fn,tag):
    last=None
    for i,v in enumerate(rows):last=e.observe_procedural_experience(m,v,fn(**v),evidence_id=f'{m}-{tag}-{i}',source_id='oracle')
    return last

def resolve_queries(e,m,auto,fn,tag,max_steps=8):
    asked=[]
    for step in range(max_steps):
        q=auto.get('information_query') if isinstance(auto,dict) else None
        if not q or q.get('status')!='query_suggested':break
        values=q['input'];asked.append(dict(values))
        row=e.observe_procedural_experience(m,values,fn(**values),evidence_id=f'{m}-{tag}-query-{step}',source_id='oracle')
        auto=row['auto_induction']
    return auto,asked


def activate(e,m,fit,val,fn):
    a=feed(e,m,fit,fn,'fit')['auto_induction'];a,_=resolve_queries(e,m,a,fn,'resolve');feed(e,m,val,fn,'val');return a

def boolean_family():
    funcs={
      'and':lambda a,b:a and b,'or':lambda a,b:a or b,'xor':lambda a,b:a^b,
      'nand':lambda a,b:not(a and b),'nor':lambda a,b:not(a or b),'xnor':lambda a,b:a==b,
      'imp':lambda a,b:(not a) or b,
    }
    rows=[{'a':a,'b':b} for a in (False,True) for b in (False,True)];ok={}
    for name,fn in funcs.items():
      with tempfile.TemporaryDirectory() as d:
        e=ASMEngine(Path(d)/'s.db');trust(e);activate(e,'b',rows,rows,fn);ok[name]=all(e.predict_procedure('b',r).get('value')==fn(**r) for r in rows);e.close()
    with tempfile.TemporaryDirectory() as d:
      e=ASMEngine(Path(d)/'s.db');trust(e);f=lambda a,b,c:(a+b+c)>=2;rows3=[{'a':a,'b':b,'c':c} for a in (False,True) for b in (False,True) for c in (False,True)]
      # Auto may propose after 5 roots; feed the whole fit table through manual evidence then induce on all 8 for a fair grammar stress.
      for i,r in enumerate(rows3):e.observe_procedure('maj',r,f(**r),evidence_id=f'm-{i}',source_id='oracle')
      ids=[f'm-{i}' for i in range(8)];p=e.induce_procedure('maj',training_ids=ids);feed(e,'maj',rows3,f,'val');ok['majority3']=p.get('status')=='proposed' and all(e.predict_procedure('maj',r).get('value')==f(**r) for r in rows3);e.close()
    return ok

def thresholds():
    rng=random.Random(7401);passed=0
    for case in range(32):
      threshold=rng.randint(-20,20);fn=lambda x,t=threshold:x<t
      with tempfile.TemporaryDirectory() as d:
        e=ASMEngine(Path(d)/'s.db');trust(e)
        fit=[{'x':threshold-3},{'x':threshold-1},{'x':threshold+2}]
        activate(e,'thr',fit,[{'x':threshold+x} for x in (-10,-8,-6,-4,1,3,5,7)],fn)
        passed+=int(all(e.predict_procedure('thr',{'x':x}).get('value')==fn(x) for x in range(threshold-25,threshold+26)))
        e.close()
    return passed

def random_conditionals():
    rng=random.Random(7402);passed=0
    for case in range(32):
      t=rng.randint(-8,8);a1=rng.choice([-3,-2,-1,1,2,3]);b1=rng.randint(-5,5);a2=rng.choice([-3,-2,-1,1,2,3]);b2=rng.randint(-5,5)
      fn=lambda x,t=t,a1=a1,b1=b1,a2=a2,b2=b2:a1*x+b1 if x<t else a2*x+b2
      with tempfile.TemporaryDirectory() as d:
        e=ASMEngine(Path(d)/'s.db');trust(e)
        fit=[{'x':t-4},{'x':t-2},{'x':t+2},{'x':t+4}]
        # Some rules coincide on the first compact window; extra externally resolved roots let the conditional gate expand safely.
        auto=None
        for j,x in enumerate((t-4,t-2,t+2,t+4,t-6,t+6)):
          r=e.observe_procedural_experience('pc',{'x':x},fn(x),evidence_id=f'f-{case}-{j}',source_id='oracle');auto=r['auto_induction']
          if auto.get('status') in ('needs_information','proposed'):break
        if auto is not None:auto,_=resolve_queries(e,'pc',auto,fn,f'pc-resolve-{case}')
        val=[{'x':t+x} for x in (-20,-18,-16,-14,10,12,14,16)];feed(e,'pc',val,fn,'val')
        passed+=int(all(e.predict_procedure('pc',{'x':x}).get('value')==fn(x) for x in range(t-20,t+21)))
        e.close()
    return passed

def drift_reversal():
    passed=0
    for seed in range(20):
      with tempfile.TemporaryDirectory() as d:
        e=ASMEngine(Path(d)/'s.db');trust(e);off=seed%5
        f1=lambda x,o=off:2*x+1+o if x<0 else -x+3+o;f2=lambda x,o=off:-x+5-o if x<0 else 3*x-2-o
        activate(e,'d',[{'x':-3},{'x':-1},{'x':1},{'x':3}],[{'x':x} for x in (-10,-8,-6,-4,2,4,6,8)],f1)
        r2=feed(e,'d',[{'x':-9},{'x':-7},{'x':5},{'x':7}],f2,'bf')['auto_induction'];r2,_=resolve_queries(e,'d',r2,f2,f'bresolve-{seed}');feed(e,'d',[{'x':x} for x in (-20,-18,-16,-14,10,12,14,16)],f2,'bv')
        mid=e.predict_procedure('d',{'x':6}).get('value')==f2(6)
        r=feed(e,'d',[{'x':-13},{'x':-11},{'x':9}],f1,'cf')['auto_induction'];r,_=resolve_queries(e,'d',r,f1,f'cresolve-{seed}');feed(e,'d',[{'x':x} for x in (-30,-28,-26,-24,20,22,24,26)],f1,'cv')
        passed+=int(mid and r.get('mode')=='revalidation' and e.predict_procedure('d',{'x':6}).get('value')==f1(6));e.close()
    return passed

def random_noise():
    rng=random.Random(7404);active=0
    for case in range(40):
      with tempfile.TemporaryDirectory() as d:
        e=ASMEngine(Path(d)/'s.db');trust(e)
        for i,x in enumerate(range(-12,12)):
          e.observe_procedural_experience('noise',{'x':x},bool(rng.getrandbits(1)),evidence_id=f'n-{case}-{i}',source_id='oracle')
        active+=sum(v['state']=='active' for v in e.procedure_versions('noise'));e.close()
    return active

def query_stress():
    with tempfile.TemporaryDirectory() as d:
      e=ASMEngine(Path(d)/'s.db');trust(e);f=lambda a,b:a^b
      rows=[{'a':False,'b':False},{'a':False,'b':True},{'a':True,'b':False}]
      for i,r in enumerate(rows):e.observe_procedure('q',r,f(**r),evidence_id=f'q{i}',source_id='oracle')
      db=e.procedures.db;before=tuple(db.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in ('procedure_evidence','procedure_versions','procedure_audit','procedure_auto_state'))
      qs=[e.procedure_information_query('q') for _ in range(100)]
      after=tuple(db.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in ('procedure_evidence','procedure_versions','procedure_audit','procedure_auto_state'))
      e.close();return all(q.get('input')=={'a':True,'b':True} for q in qs),before==after

def guards():
    with tempfile.TemporaryDirectory() as d:
      e=ASMEngine(Path(d)/'s.db');trust(e);f=lambda a,b:a^b
      for i,r in enumerate([{'a':False,'b':False},{'a':False,'b':True},{'a':True,'b':False}]):e.observe_procedure('g',r,f(**r),evidence_id=f'g{i}',root_id='same',source_id='oracle')
      q=e.procedure_information_query('g');dup=(q.get('reason')=='insufficient_trusted_independent_evidence');e.close()
    return dup

def main():
    bf=boolean_family();thr=thresholds();cond=random_conditionals();dr=drift_reversal();noise=random_noise();qok,qro=query_stress();dup=guards()
    checks={
      'boolean_family_8_of_8':sum(bf.values())==8,
      'random_thresholds_32_of_32':thr==32,
      'random_piecewise_affine_32_of_32':cond==32,
      'conditional_drift_reversal_20_of_20':dr==20,
      'random_boolean_noise_zero_final_active':noise==0,
      'information_query_100_of_100_stable':qok,
      'information_query_100_calls_read_only':qro,
      'duplicate_root_guard_applies_to_queries':dup,
    }
    report={'benchmark':'alpha.7.4 conditional/query torture','details':{'boolean_family':bf,'thresholds_passed':thr,'conditionals_passed':cond,'drift_reversal_passed':dr,'noise_final_active':noise,'query_stable':qok,'query_read_only':qro,'duplicate_guard':dup},'checks':checks,'passed':sum(checks.values()),'total':len(checks)}
    Path('ALPHA74_TORTURE.json').write_text(json.dumps(report,indent=2,sort_keys=True));print(json.dumps(report,indent=2,sort_keys=True));raise SystemExit(0 if all(checks.values()) else 1)
if __name__=='__main__':main()
