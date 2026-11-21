from __future__ import annotations
import json, random
from asm.procedure_cortex import ExperimentalProcedureCortex


def main():
    rng=random.Random(6107)
    affine_ok=0
    for task in range(100):
        a=rng.choice([i for i in range(-5,6) if i!=0]); b=rng.randint(-9,9)
        c=ExperimentalProcedureCortex(min_support=5)
        xs=rng.sample(range(-20,21),5)
        for j,x in enumerate(xs): c.record('f',(x,),a*x+b,evidence_id=f'e{j}')
        v=c.induce_affine('f')
        q=rng.randint(-30,30)
        if v and c.execute('f',(q,))['value']==a*q+b: affine_ok+=1

    boolean_ops=['and','or','xor']
    bool_ok=0
    rows=[(False,False),(False,True),(True,False),(True,True)]
    for task in range(100):
        op=rng.choice(boolean_ops); c=ExperimentalProcedureCortex(min_support=4)
        fn={'and':lambda a,b:a and b,'or':lambda a,b:a or b,'xor':lambda a,b:a^b}[op]
        for j,x in enumerate(rows): c.record('b',x,fn(*x),evidence_id=f'e{j}')
        v=c.induce_boolean('b')
        if v and all(c.execute('b',x)['value']==fn(*x) for x in rows): bool_ok+=1

    context_ok=0
    for task in range(50):
        a1,b1=rng.randint(1,4),rng.randint(-5,5); a2,b2=rng.randint(1,4),rng.randint(-5,5)
        if (a1,b1)==(a2,b2): b2+=1
        c=ExperimentalProcedureCortex(min_support=4)
        for x in range(4): c.record('f',(x,),a1*x+b1,evidence_id=f'd{x}',context='c1')
        v1=c.induce_affine('f',context='c1')
        for x in range(4): c.record('f',(x,),a2*x+b2,evidence_id=f'n{x}',context='c2')
        v2=c.induce_affine('f',context='c2')
        if v1 and v2 and c.execute('f',(7,),context='c1')['value']==a1*7+b1 and c.execute('f',(7,),context='c2')['value']==a2*7+b2:
            context_ok+=1

    disagreement_ok=0
    for task in range(100):
        c=ExperimentalProcedureCortex(min_support=10)
        b1,b2=rng.sample(range(-10,11),2)
        c.propose('f',('add',('var',0),('const',b1)),input_arity=1)
        c.propose('f',('add',('var',0),('const',b2)),input_arity=1)
        r=c.disagreement_probe('f',[(rng.randint(-20,20),) for _ in range(5)])
        disagreement_ok += int(r['status']=='disagreement')

    out={
        'experimental':True,
        'affine_generalization':{'passed':affine_ok,'total':100},
        'boolean_truth_tables':{'passed':bool_ok,'total':100},
        'context_version_retention':{'passed':context_ok,'total':50},
        'disagreement_probe':{'passed':disagreement_ok,'total':100},
        'claim_boundary':'Tiny supplied DSL and bounded inductors; not general program synthesis and not yet integrated into ASMEngine.'
    }
    print(json.dumps(out,indent=2,sort_keys=True))

if __name__=='__main__': main()
