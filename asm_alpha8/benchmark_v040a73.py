from __future__ import annotations
import json, tempfile, random
from pathlib import Path
from asm.engine import ASMEngine

BASELINE_SHA='6e8fbe1dce3c8af332e3b5be3693aa664418c76d2c667d4a87450230734236de'

def trust(e, source='oracle'):
    for i in range(80):e.observe_evidence_source(source,observation='A',resolved_hypothesis='A',temporal_index=i)

def obs(e,m,tag,rows,fn,source='oracle'):
    out=[]
    for i,v in enumerate(rows):
        out.append(e.observe_procedural_experience(m,v,fn(**v),evidence_id=f'{m}-{tag}-{i}',source_id=source))
    return out

def activate(e,m,fit,val,fn):
    a=obs(e,m,'fit',fit,fn)[-1]['auto_induction']
    obs(e,m,'val',val,fn)
    return a

def unseen_accuracy(e,m,rows,fn):
    ok=pred=0
    for v in rows:
        r=e.predict_procedure(m,v)
        if r['status']=='predicted':pred+=1;ok+=int(r['value']==fn(**v))
    return {'predicted':pred,'correct':ok,'accuracy':ok/pred if pred else None}

def case_affine2():
    with tempfile.TemporaryDirectory() as d:
        e=ASMEngine(Path(d)/'s.db');trust(e)
        fit=[{'x':0,'y':0},{'x':1,'y':0},{'x':0,'y':1},{'x':2,'y':3}]
        val=[{'x':i,'y':2*i+1} for i in range(10,18)]
        auto=activate(e,'aff2',fit,val,lambda x,y:2*x+3*y+5)
        grid=[{'x':x,'y':y} for x in range(-10,11) for y in range(-5,6)]
        out={'auto':auto,'prediction':e.predict_procedure('aff2',{'x':9,'y':4}),
             'unseen':unseen_accuracy(e,'aff2',grid,lambda x,y:2*x+3*y+5)};e.close();return out

def case_product():
    with tempfile.TemporaryDirectory() as d:
        e=ASMEngine(Path(d)/'s.db');trust(e)
        fit=[{'x':0,'y':2},{'x':1,'y':5},{'x':3,'y':-2},{'x':2,'y':4}]
        val=[{'x':i,'y':i-4} for i in range(10,18)]
        auto=activate(e,'prod',fit,val,lambda x,y:x*y)
        grid=[{'x':x,'y':y} for x in range(-8,9) for y in range(-8,9)]
        out={'auto':auto,'prediction':e.predict_procedure('prod',{'x':7,'y':-4}),
             'unseen':unseen_accuracy(e,'prod',grid,lambda x,y:x*y)};e.close();return out

def case_affine3():
    with tempfile.TemporaryDirectory() as d:
        e=ASMEngine(Path(d)/'s.db');trust(e)
        fit=[{'a':0,'b':0,'c':0},{'a':1,'b':0,'c':0},{'a':0,'b':1,'c':0},{'a':0,'b':0,'c':1},{'a':1,'b':1,'c':1}]
        val=[{'a':i,'b':i+1,'c':2-i} for i in range(10,18)]
        auto=activate(e,'aff3',fit,val,lambda a,b,c:2*a-3*b+4*c+7)
        rng=random.Random(73);grid=[{'a':rng.randint(-20,20),'b':rng.randint(-20,20),'c':rng.randint(-20,20)} for _ in range(256)]
        out={'auto':auto,'unseen':unseen_accuracy(e,'aff3',grid,lambda a,b,c:2*a-3*b+4*c+7)};e.close();return out

def case_composition():
    with tempfile.TemporaryDirectory() as d:
        e=ASMEngine(Path(d)/'s.db');trust(e)
        activate(e,'square',[{'x':0},{'x':1},{'x':2}],[{'x':i} for i in range(10,18)],lambda x:x*x)
        activate(e,'inc',[{'x':0},{'x':1},{'x':2}],[{'x':i} for i in range(20,28)],lambda x:x+1)
        fit=[{'x':0,'y':2},{'x':1,'y':5},{'x':2,'y':1},{'x':3,'y':4}]
        val=[{'x':i,'y':2*i+1} for i in range(30,38)]
        auto=activate(e,'combo',fit,val,lambda x,y:x*x+y+1)
        p=e.predict_procedure('combo',{'x':7,'y':3})
        v=e.procedure_versions('combo')[-1]
        out={'auto':auto,'prediction':p,'version':v};e.close();return out

def case_drift_reversal():
    with tempfile.TemporaryDirectory() as d:
        e=ASMEngine(Path(d)/'s.db');trust(e)
        f1=lambda x,y:2*x+y+3;f2=lambda x,y:-x+4*y+2
        fit1=[{'x':0,'y':0},{'x':1,'y':0},{'x':0,'y':1}]
        activate(e,'drift',fit1,[{'x':i,'y':i+1} for i in range(10,18)],f1)
        r2=obs(e,'drift','bfit',[{'x':20,'y':2},{'x':21,'y':0},{'x':19,'y':3},{'x':22,'y':5}],f2)[-1]['auto_induction']
        obs(e,'drift','bval',[{'x':i,'y':2*i-3} for i in range(30,38)],f2)
        p2=e.predict_procedure('drift',{'x':8,'y':2})
        r3=obs(e,'drift','cfit',[{'x':40,'y':2},{'x':41,'y':0},{'x':39,'y':3},{'x':42,'y':5}],f1)[-1]['auto_induction']
        obs(e,'drift','cval',[{'x':i,'y':i-7} for i in range(50,58)],f1)
        p3=e.predict_procedure('drift',{'x':8,'y':2})
        out={'drift_auto':r2,'drift_prediction':p2,'reversal_auto':r3,'reversal_prediction':p3,'versions':e.procedure_versions('drift')};e.close();return out

def safety():
    out={}
    with tempfile.TemporaryDirectory() as d:
        e=ASMEngine(Path(d)/'s.db');trust(e)
        rows=[]
        for i in range(20):
            rows.append(e.observe_procedural_experience('dup',{'x':i,'y':i+1},2*i+1,evidence_id=f'd-{i}',root_id='same',source_id='oracle'))
        out['duplicate_root']={'versions':len(e.procedure_versions('dup')),'last':rows[-1]['auto_induction']};e.close()
    with tempfile.TemporaryDirectory() as d:
        e=ASMEngine(Path(d)/'s.db');rng=random.Random(40473);trust(e)
        for i in range(24):
            e.observe_procedural_experience('noise',{'x':i,'y':i+3},rng.randint(-999,999),evidence_id=f'n-{i}',source_id='oracle')
        out['noise_active']=sum(v['state']=='active' for v in e.procedure_versions('noise'));e.close()
    return out

def main():
    baseline=json.loads(Path('BASELINE_ALPHA72_MULTIINPUT.json').read_text())
    a2=case_affine2();prod=case_product();a3=case_affine3();comp=case_composition();dr=case_drift_reversal();safe=safety()
    checks={
      'baseline_is_exact_alpha72':baseline.get('sha256')==BASELINE_SHA,
      'baseline_lacks_multiinput':all(not baseline[k]['versions'] and baseline[k]['last_auto']['status']=='unsupported' for k in ('two_input_affine','two_input_product','three_input_affine')),
      'two_input_affine_learned':a2['prediction'].get('value')==35 and a2['unseen']['accuracy']==1.0 and a2['unseen']['predicted']==231,
      'bounded_product_composition':prod['prediction'].get('value')==-28 and prod['unseen']['accuracy']==1.0 and prod['auto']['candidate_count']<=512,
      'three_input_affine_learned':a3['unseen']['accuracy']==1.0 and a3['unseen']['predicted']==256,
      'validated_structure_reuse':comp['prediction'].get('value')==53 and 'donor:' in comp['auto']['origin'] and comp['version']['support']>=8,
      'multiinput_drift_revision':dr['drift_auto'].get('version')==2 and dr['drift_prediction'].get('value')==2,
      'multiinput_reversal_revalidation':dr['reversal_auto'].get('mode')=='revalidation' and dr['reversal_auto'].get('version')==3 and dr['reversal_prediction'].get('value')==21,
      'duplicate_root_guard_preserved':safe['duplicate_root']['versions']==0 and safe['duplicate_root']['last'].get('trusted_independent_roots')==1,
      'random_outputs_no_false_active':safe['noise_active']==0,
    }
    report={'benchmark':'ASM v0.4.0-alpha.7.3 multi-input compositional induction',
            'before':baseline,'after':{'affine2':a2,'product':prod,'affine3':a3,'composition':comp,'drift_reversal':dr,'safety':safe},
            'checks':checks,'passed':sum(checks.values()),'total':len(checks)}
    Path('ALPHA73_BEFORE_AFTER.json').write_text(json.dumps(report,indent=2,sort_keys=True))
    print(json.dumps(report,indent=2,sort_keys=True))
    raise SystemExit(0 if all(checks.values()) else 1)
if __name__=='__main__':main()
