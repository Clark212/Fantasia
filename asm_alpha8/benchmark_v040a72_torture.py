from __future__ import annotations
import json, random, tempfile
from pathlib import Path
from asm.engine import ASMEngine


def trust(e, source='oracle'):
    for i in range(80):
        e.observe_evidence_source(source, observation='A', resolved_hypothesis='A', temporal_index=i)


def obs(e,m,eid,x,y,**kw):
    return e.observe_procedural_experience(m,{'x':x},y,evidence_id=eid,source_id='oracle',**kw)


def activate(e,m,tag,fn,fit=(0,1,2),val=range(10,18)):
    last=None
    for x in fit:last=obs(e,m,f'{tag}-f-{x}',x,fn(x))
    for x in val:last=obs(e,m,f'{tag}-v-{x}',x,fn(x))
    return last


def check_many_affine():
    rng=random.Random(40720);fail=[]
    with tempfile.TemporaryDirectory() as d:
        e=ASMEngine(Path(d)/'s.db');trust(e)
        pairs=[]
        while len(pairs)<32:
            p=(rng.randint(-8,8),rng.randint(-8,8))
            if p not in pairs:pairs.append(p)
        for i,(a,b) in enumerate(pairs):
            m=f'm{i}';fn=lambda x,a=a,b=b:a*x+b
            activate(e,m,f't{i}',fn)
            p=e.predict_procedure(m,{'x':97})
            if p.get('value')!=fn(97):fail.append((i,a,b,p))
        e.close()
    return {'passed':not fail,'cases':32,'failures':fail[:3]}


def check_drift_and_reversal():
    fail=[]
    for seed in range(20):
        rng=random.Random(5000+seed)
        choices=[]
        while len(choices)<2:
            p=(rng.randint(-8,8),rng.randint(-8,8))
            if p not in choices:choices.append(p)
        (a,b),(c,d)=choices
        f1=lambda x,a=a,b=b:a*x+b;f2=lambda x,c=c,d=d:c*x+d
        with tempfile.TemporaryDirectory() as td:
            e=ASMEngine(Path(td)/'s.db');trust(e)
            activate(e,'f','a',f1)
            for x in range(20,23):obs(e,'f',f'b-f-{x}',x,f2(x))
            for x in range(30,38):obs(e,'f',f'b-v-{x}',x,f2(x))
            p2=e.predict_procedure('f',{'x':91})
            for x in range(40,43):r=obs(e,'f',f'c-f-{x}',x,f1(x))
            mode=r['auto_induction'].get('mode')
            for x in range(50,58):obs(e,'f',f'c-v-{x}',x,f1(x))
            p3=e.predict_procedure('f',{'x':91})
            if p2.get('value')!=f2(91) or p3.get('value')!=f1(91) or mode!='revalidation':fail.append(seed)
            e.close()
    return {'passed':not fail,'runs':20,'failures':fail}


def check_random_no_false_active():
    false=[]
    for seed in range(50):
        rng=random.Random(9000+seed)
        with tempfile.TemporaryDirectory() as td:
            e=ASMEngine(Path(td)/'s.db');trust(e)
            for x in range(20):
                y=rng.randint(-500,500)
                obs(e,'noise',f'n-{x}',x,y)
            if any(v['state']=='active' for v in e.procedure_versions('noise')):false.append(seed)
            e.close()
    return {'passed':not false,'runs':50,'false_active':false}


def check_root_and_trust_guards():
    with tempfile.TemporaryDirectory() as td:
        e=ASMEngine(Path(td)/'s.db');trust(e)
        for x in range(64):obs(e,'copy',f'c-{x}',x,x+1,root_id='one-root')
        same=len(e.procedure_versions('copy'))
        e.close()
    with tempfile.TemporaryDirectory() as td:
        e=ASMEngine(Path(td)/'s.db')
        for x in range(64):
            e.observe_procedural_experience('weak',{'x':x},x+1,evidence_id=f'w-{x}',source_id='weak')
        weak=len(e.procedure_versions('weak'));e.close()
    return {'passed':same==0 and weak==0,'same_root_versions':same,'low_trust_versions':weak}


def check_outlier_recovery():
    with tempfile.TemporaryDirectory() as td:
        e=ASMEngine(Path(td)/'s.db');trust(e);fn=lambda x:2*x+3
        activate(e,'f','a',fn)
        obs(e,'f','outlier',20,999)
        abstained=e.predict_procedure('f',{'x':50})['status']=='abstained'
        # Three clean recent roots make the old structure eligible as a new hypothesis.
        rows=[]
        for x in range(21,24):rows.append(obs(e,'f',f'r-{x}',x,fn(x)))
        mode=rows[-1]['auto_induction'].get('mode')
        for x in range(30,38):obs(e,'f',f'rv-{x}',x,fn(x))
        p=e.predict_procedure('f',{'x':50});versions=e.procedure_versions('f');e.close()
    return {'passed':abstained and mode=='revalidation' and p.get('value')==103,
            'temporary_abstention':abstained,'recovery_mode':mode,'versions':len(versions)}


def check_restart_mid_validation():
    with tempfile.TemporaryDirectory() as td:
        db=Path(td)/'s.db';e=ASMEngine(db);trust(e)
        for x in range(3):obs(e,'f',f'f-{x}',x,4*x-2)
        state=e.procedure_autonomy_status('f');e.close()
        e=ASMEngine(db)
        for x in range(10,18):obs(e,'f',f'v-{x}',x,4*x-2)
        p=e.predict_procedure('f',{'x':90});state2=e.procedure_autonomy_status('f');e.close()
    return {'passed':state['attempts']==1 and p.get('value')==358 and state2['attempts']==1,
            'before_attempts':state['attempts'],'after_attempts':state2['attempts']}


def check_capacity_fail_closed():
    with tempfile.TemporaryDirectory() as td:
        e=ASMEngine(Path(td)/'s.db');trust(e);e.procedures.MAX_VERSIONS=2
        activate(e,'f','a',lambda x:x+1)
        for x in range(20,23):obs(e,'f',f'b-{x}',x,2*x+2)
        for x in range(30,38):obs(e,'f',f'bv-{x}',x,2*x+2)
        for x in range(40,43):r=obs(e,'f',f'c-{x}',x,3*x+3)
        versions=e.procedure_versions('f');e.close()
    return {'passed':r['auto_induction']['status']=='blocked' and len(versions)==2,
            'status':r['auto_induction']['status'],'versions':len(versions)}


def check_manual_compatibility():
    with tempfile.TemporaryDirectory() as td:
        e=ASMEngine(Path(td)/'s.db');trust(e)
        for x in range(3):e.observe_procedure('f',{'x':x},5*x-4,evidence_id=f'f-{x}',source_id='oracle')
        q=e.induce_procedure('f')
        for x in range(10,18):e.observe_procedure('f',{'x':x},5*x-4,evidence_id=f'v-{x}',source_id='oracle')
        p=e.predict_procedure('f',{'x':100});e.close()
    return {'passed':q['status']=='proposed' and p.get('value')==496,'prediction':p}


def main():
    checks={
        '32_affine_rules':check_many_affine(),
        '20_drift_reversal_runs':check_drift_and_reversal(),
        '50_random_no_false_active':check_random_no_false_active(),
        'root_and_trust_guards':check_root_and_trust_guards(),
        'single_outlier_recovery':check_outlier_recovery(),
        'restart_mid_validation':check_restart_mid_validation(),
        'capacity_fail_closed':check_capacity_fail_closed(),
        'manual_compatibility':check_manual_compatibility(),
    }
    report={'benchmark':'alpha.7.2 autonomous procedure torture','checks':checks,
            'passed':sum(v['passed'] for v in checks.values()),'total':len(checks)}
    Path('ALPHA72_TORTURE.json').write_text(json.dumps(report,indent=2,sort_keys=True))
    print(json.dumps(report,indent=2,sort_keys=True))
    raise SystemExit(0 if all(v['passed'] for v in checks.values()) else 1)
if __name__=='__main__':main()
