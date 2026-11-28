import tempfile, random, json
from pathlib import Path
from asm import ASMEngine, ASMConfig
from asm.procedure_program import Program

def active(e,m,c):
    fn=(lambda x:x+1) if c=="left" else (lambda x:x-1)
    for i,x in enumerate((0,1,2)):
        e.observe_procedural_experience(m,{"x":x},fn(x),evidence_id=f"{m}-{c}-fit-{i}",source_id="oracle",context=c)
    for i,x in enumerate(range(10,18)):
        e.observe_procedural_experience(m,{"x":x},fn(x),evidence_id=f"{m}-{c}-val-{i}",source_id="oracle",context=c)

def trust(e,s):
    for i in range(80): e.observe_evidence_source(s,observation="A",resolved_hypothesis="A")

def learn_corr(e,a,b,seed=1):
    r=random.Random(seed)
    for i in range(96):
        truth='A' if r.random()<.5 else 'B'
        # identical noisy observation => strong hidden common dependence
        obs=truth if r.random()<.7 else ('B' if truth=='A' else 'A')
        e.observe_evidence_dependency_trial(f'd{i}',resolved_hypothesis=truth,observations={a:[obs],b:[obs]})

def case(correlated=True):
    td=tempfile.TemporaryDirectory(); path=Path(td.name)/'a.db'; e=ASMEngine(path)
    trust(e,'oracle')
    for c in ('left','right'): active(e,'m',c)
    for s in ('s1','s2','s3','s4'): trust(e,s)
    if correlated: learn_corr(e,'s1','s2')
    # four rows supporting left, two are correlated; distinct roots
    for i,s in enumerate(('s1','s2','s3','s4')):
        e.observe_procedure_route('m',{'mode':False},'left',evidence_id=f'e{i}',source_id=s,root_id=f'r{i}')
    out={}
    for mode in ('frequency','reliability','dependency','full'):
        out[mode]=e.route_procedure_context('m',{'mode':False},epistemic_mode=mode,min_support=4)
    dep=e.evidence_dependency.effective_batch(['s1','s2','s3','s4'])
    e.close(); td.cleanup(); return dep,out

res={}
for label,c in [('independent',False),('mixed_hidden_correlation',True)]:
    dep,out=case(c);res[label]={'dependency':dep,'modes':{m:{k:v for k,v in r.items() if k in ('status','context','confidence','support','reason','exact_support')} for m,r in out.items()}}
print(json.dumps(res,indent=2,sort_keys=True))
