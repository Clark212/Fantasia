from __future__ import annotations
import json,tempfile
from pathlib import Path
from asm.engine import ASMEngine

BASELINE_SHA='421527405b0e9f9d7eb87a291e76f988e81fd4c35d01be4107cc1a9ac2b033f9'

def trust(e,source='oracle'):
    for i in range(80):e.observe_evidence_source(source,observation='A',resolved_hypothesis='A',temporal_index=i)

def feed(e,m,rows,fn,tag):
    out=[]
    for i,v in enumerate(rows):out.append(e.observe_procedural_experience(m,v,fn(**v),evidence_id=f'{m}-{tag}-{i}',source_id='oracle'))
    return out

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
    a=feed(e,m,fit,fn,'fit')[-1]['auto_induction'];a,_=resolve_queries(e,m,a,fn,'resolve');feed(e,m,val,fn,'val');return a

def xor_case():
    with tempfile.TemporaryDirectory() as d:
        e=ASMEngine(Path(d)/'s.db');trust(e);f=lambda a,b:a^b
        first=[{'a':False,'b':False},{'a':False,'b':True},{'a':True,'b':False}]
        pre=feed(e,'xor',first,f,'fit')[-1]['auto_induction'];explicit=e.procedure_information_query('xor')
        last=feed(e,'xor',[{'a':True,'b':True}],f,'fit4')[-1]['auto_induction']
        truth=[{'a':a,'b':b} for a in (False,True) for b in (False,True)];feed(e,'xor',truth,f,'val')
        preds=[e.predict_procedure('xor',v).get('value') for v in truth];out={'pre':pre,'explicit_query':explicit,'proposal':last,'predictions':preds,'versions':e.procedure_versions('xor')};e.close();return out

def predicate_case():
    with tempfile.TemporaryDirectory() as d:
        e=ASMEngine(Path(d)/'s.db');trust(e);f=lambda x:x<0
        auto=activate(e,'neg',[{'x':-3},{'x':-1},{'x':2}],[{'x':x} for x in (-10,-8,-6,-4,1,3,5,7)],f)
        preds={x:e.predict_procedure('neg',{'x':x}).get('value') for x in (-9,-2,0,4,12)};e.close();return {'auto':auto,'predictions':preds}

def piecewise_case():
    with tempfile.TemporaryDirectory() as d:
        e=ASMEngine(Path(d)/'s.db');trust(e);f=lambda x:2*x+1 if x<0 else -x+3
        auto=activate(e,'piece',[{'x':-3},{'x':-1},{'x':1},{'x':3}],[{'x':x} for x in (-10,-8,-6,-4,2,4,6,8)],f)
        grid=range(-30,31);correct=sum(e.predict_procedure('piece',{'x':x}).get('value')==f(x) for x in grid);v=e.procedure_versions('piece')[-1];e.close();return {'auto':auto,'correct':correct,'total':61,'version':v}

def selector_case():
    with tempfile.TemporaryDirectory() as d:
        e=ASMEngine(Path(d)/'s.db');trust(e);f=lambda flag,x:x+1 if flag else x-1
        fit=[{'flag':False,'x':0},{'flag':False,'x':2},{'flag':True,'x':0},{'flag':True,'x':2}]
        val=[{'flag':b,'x':x} for x in range(10,14) for b in (False,True)]
        auto=activate(e,'sel',fit,val,f);rows=[{'flag':b,'x':x} for x in range(-12,13) for b in (False,True)]
        correct=sum(e.predict_procedure('sel',v).get('value')==f(**v) for v in rows);e.close();return {'auto':auto,'correct':correct,'total':len(rows)}

def drift_case():
    with tempfile.TemporaryDirectory() as d:
        e=ASMEngine(Path(d)/'s.db');trust(e)
        f1=lambda x:2*x+1 if x<0 else -x+3;f2=lambda x:-x+5 if x<0 else 3*x-2
        activate(e,'drift',[{'x':-3},{'x':-1},{'x':1},{'x':3}],[{'x':x} for x in (-10,-8,-6,-4,2,4,6,8)],f1)
        r2=feed(e,'drift',[{'x':-9},{'x':-7},{'x':5},{'x':7}],f2,'bfit')[-1]['auto_induction'];r2,_=resolve_queries(e,'drift',r2,f2,'bresolve');feed(e,'drift',[{'x':x} for x in (-20,-18,-16,-14,10,12,14,16)],f2,'bval')
        p2=e.predict_procedure('drift',{'x':6})
        r3=feed(e,'drift',[{'x':-13},{'x':-11},{'x':9}],f1,'cfit')[-1]['auto_induction'];r3,_=resolve_queries(e,'drift',r3,f1,'cresolve');feed(e,'drift',[{'x':x} for x in (-30,-28,-26,-24,20,22,24,26)],f1,'cval')
        p3=e.predict_procedure('drift',{'x':6});versions=e.procedure_versions('drift');e.close();return {'drift':r2,'drift_prediction':p2,'reversal':r3,'reversal_prediction':p3,'versions':versions}

def readonly_case():
    with tempfile.TemporaryDirectory() as d:
        e=ASMEngine(Path(d)/'s.db');trust(e);f=lambda a,b:a^b
        rows=[{'a':False,'b':False},{'a':False,'b':True},{'a':True,'b':False}]
        for i,v in enumerate(rows):e.observe_procedure('q',v,f(**v),evidence_id=f'q-{i}',source_id='oracle')
        db=e.procedures.db
        before=tuple(db.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in ('procedure_evidence','procedure_versions','procedure_audit','procedure_auto_state'))
        q=e.procedure_information_query('q');after=tuple(db.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in ('procedure_evidence','procedure_versions','procedure_audit','procedure_auto_state'))
        e.close();return {'query':q,'before':before,'after':after}

def main():
    baseline=json.loads(Path('BASELINE_ALPHA73_CONDITIONAL.json').read_text())
    xor=xor_case();pred=predicate_case();piece=piecewise_case();selector=selector_case();drift=drift_case();ro=readonly_case()
    checks={
      'baseline_is_exact_alpha73':baseline.get('sha256')==BASELINE_SHA and baseline.get('version')=='0.4.0-alpha.7.3',
      'baseline_lacks_alpha74_capabilities':not baseline['xor']['versions'] and not baseline['piecewise']['versions'] and not baseline['selector']['versions'] and not baseline['xor']['has_information_query'],
      'disagreement_query_picks_missing_xor_case':xor['pre'].get('information_query',{}).get('input')=={'a':True,'b':True} and xor['explicit_query'].get('input')=={'a':True,'b':True},
      'xor_learned_and_validated':xor['predictions']==[False,True,True,False] and xor['versions'][-1]['state']=='active',
      'integer_predicate_learned':pred['predictions']=={-9:True,-2:True,0:False,4:False,12:False},
      'piecewise_affine_generalizes':piece['correct']==piece['total'] and piece['version']['state']=='active' and piece['auto']['candidate_count']<=512,
      'mixed_bool_integer_selector_generalizes':selector['correct']==selector['total'] and selector['auto']['candidate_count']<=512,
      'conditional_drift_revision':drift['drift'].get('version')==2 and drift['drift_prediction'].get('value')==16,
      'conditional_reversal_revalidation':drift['reversal'].get('mode')=='revalidation' and drift['reversal'].get('version')==3 and drift['reversal_prediction'].get('value')==-3,
      'information_query_is_read_only':ro['query'].get('read_only') is True and ro['before']==ro['after'],
      'no_direct_query_authority':ro['query'].get('status')=='query_suggested' and 'answer' not in ro['query'],
    }
    report={'benchmark':'ASM v0.4.0-alpha.7.4 conditional procedures and active information gathering','before':baseline,'after':{'xor':xor,'predicate':pred,'piecewise':piece,'selector':selector,'drift':drift,'read_only':ro},'checks':checks,'passed':sum(checks.values()),'total':len(checks)}
    Path('ALPHA74_BEFORE_AFTER.json').write_text(json.dumps(report,indent=2,sort_keys=True));print(json.dumps(report,indent=2,sort_keys=True));raise SystemExit(0 if all(checks.values()) else 1)
if __name__=='__main__':main()
