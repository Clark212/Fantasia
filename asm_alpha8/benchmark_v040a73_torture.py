from __future__ import annotations
import json, random, tempfile
from pathlib import Path
from asm.engine import ASMEngine


def trust(e):
    for i in range(80):e.observe_evidence_source('oracle',observation='A',resolved_hypothesis='A',temporal_index=i)

def put(e,m,tag,rows,fn,root=None):
    out=[]
    for i,v in enumerate(rows):
        kw={}
        if root is not None:kw['root_id']=root
        out.append(e.observe_procedural_experience(m,v,fn(**v),evidence_id=f'{m}-{tag}-{i}',source_id='oracle',**kw))
    return out

def basis(names):
    rows=[{k:0 for k in names}]
    for name in names:
        v={k:0 for k in names};v[name]=1;rows.append(v)
    return rows

def check_random_affine():
    rng=random.Random(4073001);fail=[];cases=0
    with tempfile.TemporaryDirectory() as d:
        e=ASMEngine(Path(d)/'s.db');trust(e)
        for dim in (2,3,4):
            names=tuple(chr(ord('a')+i) for i in range(dim))
            for j in range(16):
                coeff=[rng.randint(-12,12) for _ in names];bias=rng.randint(-12,12)
                if not any(coeff):coeff[0]=1
                fn=lambda coeff=coeff,bias=bias,**v:sum(c*v[k] for c,k in zip(coeff,names))+bias
                m=f'aff{dim}_{j}';fit=basis(names)+[{k:(2 if idx==0 else idx+1) for idx,k in enumerate(names)}]
                put(e,m,'fit',fit,fn)
                val=[];seen=set()
                while len(val)<8:
                    row={k:rng.randint(-20,20) for k in names};key=tuple(sorted(row.items()))
                    if key in seen:continue
                    seen.add(key);val.append(row)
                put(e,m,'val',val,fn)
                for _ in range(32):
                    x={k:rng.randint(-100,100) for k in names};p=e.predict_procedure(m,x)
                    if p.get('value')!=fn(**x):fail.append((m,coeff,bias,x,p));break
                cases+=1
        e.close()
    return {'passed':not fail,'cases':cases,'failures':fail[:3]}

def check_primitives():
    specs=[
      ('prod',lambda x,y:x*y),('minimum',lambda x,y:min(x,y)),('maximum',lambda x,y:max(x,y)),
      ('x2_plus_y',lambda x,y:x*x+y),('xy_plus_x',lambda x,y:x*y+x),
    ]
    fail=[];details=[]
    with tempfile.TemporaryDirectory() as d:
        e=ASMEngine(Path(d)/'s.db');trust(e)
        fit=[{'x':0,'y':2},{'x':1,'y':5},{'x':3,'y':-2},{'x':2,'y':4}]
        val=[{'x':i,'y':7-i} for i in range(10,18)]
        for m,fn in specs:
            auto=put(e,m,'fit',fit,fn)[-1]['auto_induction'];put(e,m,'val',val,fn)
            p=e.predict_procedure(m,{'x':7,'y':-4});details.append((m,auto.get('candidate_count'),auto.get('origin')))
            if p.get('value')!=fn(7,-4) or auto.get('candidate_count',513)>512:fail.append((m,auto,p))
        e.close()
    return {'passed':not fail,'cases':len(specs),'details':details,'failures':fail}

def check_donor_composition():
    fail=[];origins=[]
    with tempfile.TemporaryDirectory() as d:
        e=ASMEngine(Path(d)/'s.db');trust(e)
        put(e,'square','fit',[{'x':0},{'x':1},{'x':2}],lambda x:x*x);put(e,'square','val',[{'x':i} for i in range(10,18)],lambda x:x*x)
        put(e,'inc','fit',[{'x':0},{'x':1},{'x':2}],lambda x:x+1);put(e,'inc','val',[{'x':i} for i in range(20,28)],lambda x:x+1)
        tasks=[
          ('sqx_y',lambda x,y:x*x+y),('sqy_x',lambda x,y:y*y+x),
          ('sqx_incy',lambda x,y:x*x+y+1),('sqx_sqy',lambda x,y:x*x+y*y),
        ]
        fit=[{'x':0,'y':2},{'x':1,'y':5},{'x':2,'y':1},{'x':3,'y':4}]
        val=[{'x':i,'y':2*i+1} for i in range(30,38)]
        for m,fn in tasks:
            auto=put(e,m,'fit',fit,fn)[-1]['auto_induction'];put(e,m,'val',val,fn);p=e.predict_procedure(m,{'x':7,'y':3})
            origins.append((m,auto.get('origin'),auto.get('candidate_count')))
            if p.get('value')!=fn(7,3) or 'donor:' not in auto.get('origin',''):fail.append((m,auto,p))
        e.close()
    return {'passed':not fail,'cases':4,'origins':origins,'failures':fail}

def check_drift_reversal():
    fail=[]
    for seed in range(20):
        rng=random.Random(73000+seed)
        c1=[rng.randint(-8,8),rng.randint(-8,8),rng.randint(-8,8)]
        c2=[rng.randint(-8,8),rng.randint(-8,8),rng.randint(-8,8)]
        if c1==c2:c2[0]+=1
        f1=lambda x,y,c=c1:c[0]*x+c[1]*y+c[2]
        f2=lambda x,y,c=c2:c[0]*x+c[1]*y+c[2]
        with tempfile.TemporaryDirectory() as d:
            e=ASMEngine(Path(d)/'s.db');trust(e)
            fit=[{'x':0,'y':0},{'x':1,'y':0},{'x':0,'y':1},{'x':2,'y':3}]
            put(e,'f','af',fit,f1);put(e,'f','av',[{'x':i,'y':i+2} for i in range(10,18)],f1)
            b=put(e,'f','bf',[{'x':20,'y':2},{'x':21,'y':0},{'x':19,'y':3},{'x':22,'y':5}],f2)[-1]['auto_induction']
            put(e,'f','bv',[{'x':i,'y':2*i-3} for i in range(30,38)],f2);p2=e.predict_procedure('f',{'x':9,'y':4})
            c=put(e,'f','cf',[{'x':40,'y':2},{'x':41,'y':0},{'x':39,'y':3},{'x':42,'y':5}],f1)[-1]['auto_induction']
            put(e,'f','cv',[{'x':i,'y':i-7} for i in range(50,58)],f1);p3=e.predict_procedure('f',{'x':9,'y':4})
            if b.get('version')!=2 or p2.get('value')!=f2(9,4) or c.get('mode')!='revalidation' or p3.get('value')!=f1(9,4):fail.append(seed)
            e.close()
    return {'passed':not fail,'runs':20,'failures':fail}

def check_random_noise():
    false=[]
    for seed in range(40):
        rng=random.Random(99000+seed)
        with tempfile.TemporaryDirectory() as d:
            e=ASMEngine(Path(d)/'s.db');trust(e)
            for i in range(24):
                e.observe_procedural_experience('noise',{'x':i,'y':i*2+1},rng.randint(-5000,5000),evidence_id=f'n-{i}',source_id='oracle')
            if any(v['state']=='active' for v in e.procedure_versions('noise')):false.append(seed)
            e.close()
    return {'passed':not false,'runs':40,'false_active':false}

def check_rank_and_guards():
    out={}
    with tempfile.TemporaryDirectory() as d:
        e=ASMEngine(Path(d)/'s.db');trust(e)
        rows=put(e,'rank','fit',[{'x':0,'y':0},{'x':1,'y':1},{'x':2,'y':2},{'x':3,'y':3}],lambda x,y:2*x+3*y+5)
        a=rows[-1]['auto_induction'];out['rank']={'status':a['status'],'candidates':a.get('candidate_count'),'versions':len(e.procedure_versions('rank'))};e.close()
    with tempfile.TemporaryDirectory() as d:
        e=ASMEngine(Path(d)/'s.db');trust(e)
        rows=put(e,'dup','fit',[{'x':i,'y':i+1} for i in range(20)],lambda x,y:x+y,root='one')
        out['dup']={'roots':rows[-1]['auto_induction'].get('trusted_independent_roots'),'versions':len(e.procedure_versions('dup'))};e.close()
    with tempfile.TemporaryDirectory() as d:
        e=ASMEngine(Path(d)/'s.db')
        rows=[]
        for i in range(20):rows.append(e.observe_procedural_experience('weak',{'x':i,'y':i+1},2*i+1,evidence_id=f'w-{i}',source_id='weak'))
        out['weak']={'roots':rows[-1]['auto_induction'].get('trusted_independent_roots'),'versions':len(e.procedure_versions('weak'))};e.close()
    passed=out['rank']['status']=='unresolved' and out['rank']['candidates']<=512 and out['rank']['versions']==0 and out['dup']=={'roots':1,'versions':0} and out['weak']=={'roots':0,'versions':0}
    return {'passed':passed,**out}

def check_unary_regression():
    with tempfile.TemporaryDirectory() as d:
        e=ASMEngine(Path(d)/'s.db');trust(e)
        a=put(e,'legacy','fit',[{'x':0},{'x':1},{'x':2}],lambda x:5*x-4)[-1]['auto_induction'];put(e,'legacy','val',[{'x':i} for i in range(10,18)],lambda x:5*x-4)
        p=e.predict_procedure('legacy',{'x':100});e.close()
    return {'passed':a.get('origin')=='grammar' and p.get('value')==496,'auto':a,'prediction':p}

def main():
    checks={
      '48_random_affine_2_4_inputs':check_random_affine(),
      'bounded_nonlinear_primitives':check_primitives(),
      'validated_donor_composition':check_donor_composition(),
      '20_multiinput_drift_reversals':check_drift_reversal(),
      '40_random_no_false_active':check_random_noise(),
      'rank_root_trust_guards':check_rank_and_guards(),
      'unary_alpha72_regression':check_unary_regression(),
    }
    report={'benchmark':'alpha.7.3 compositional multi-input torture','checks':checks,'passed':sum(v['passed'] for v in checks.values()),'total':len(checks)}
    Path('ALPHA73_TORTURE.json').write_text(json.dumps(report,indent=2,sort_keys=True))
    print(json.dumps(report,indent=2,sort_keys=True));raise SystemExit(0 if all(v['passed'] for v in checks.values()) else 1)
if __name__=='__main__':main()
