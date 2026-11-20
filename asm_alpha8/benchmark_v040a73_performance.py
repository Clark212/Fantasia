from __future__ import annotations
import json, statistics, tempfile, time
from pathlib import Path
from asm.procedure_cortex import ProcedureCortex
TRUST=lambda source:{'reliability':.99,'version':1}

def measure_case(kind,reps=30):
    times=[];counts=[];evals=[]
    for rep in range(reps):
        with tempfile.TemporaryDirectory() as d:
            c=ProcedureCortex(Path(d)/'p.db',trust_provider=TRUST)
            if kind=='affine':
                rows=[({'x':0,'y':0},5),({'x':1,'y':0},7),({'x':0,'y':1},8),({'x':2,'y':3},18)]
            elif kind=='product':
                rows=[({'x':0,'y':2},0),({'x':1,'y':5},5),({'x':3,'y':-2},-6),({'x':2,'y':4},8)]
            elif kind=='x2_plus_y':
                rows=[({'x':0,'y':2},2),({'x':1,'y':5},6),({'x':3,'y':-2},7),({'x':2,'y':4},8)]
            else:raise ValueError(kind)
            result=None;t=time.perf_counter()
            for i,(v,y) in enumerate(rows):result=c.observe(kind,v,y,evidence_id=f'e-{i}',source_id='oracle',auto_induce=True)
            times.append(time.perf_counter()-t)
            a=result['auto_induction'];counts.append(a.get('candidate_count',0));evals.append(a.get('evaluator_calls',0));c.close()
    return {'reps':reps,'median_s':statistics.median(times),'p90_s':sorted(times)[int(.9*(len(times)-1))],
            'median_candidates':statistics.median(counts),'median_evaluator_calls':statistics.median(evals)}

def prediction_speed(n=20000):
    with tempfile.TemporaryDirectory() as d:
        c=ProcedureCortex(Path(d)/'p.db',trust_provider=TRUST)
        fit=[({'x':0,'y':0},5),({'x':1,'y':0},7),({'x':0,'y':1},8),({'x':2,'y':3},18)]
        for i,(v,y) in enumerate(fit):c.observe('f',v,y,evidence_id=f'f-{i}',source_id='oracle',auto_induce=True)
        for i in range(8):
            v={'x':10+i,'y':2*i+1};c.observe('f',v,2*v['x']+3*v['y']+5,evidence_id=f'v-{i}',source_id='oracle',auto_induce=True)
        assert c.predict('f',{'x':9,'y':4})['value']==35
        t=time.perf_counter()
        for i in range(n):c.predict('f',{'x':i%100,'y':(i*3)%100})
        elapsed=time.perf_counter()-t;c.close()
    return {'n':n,'elapsed_s':elapsed,'predictions_per_s':n/elapsed}

def main():
    report={'benchmark':'alpha.7.3 bounded synthesis performance',
            'affine':measure_case('affine',40),'product':measure_case('product',30),'x2_plus_y':measure_case('x2_plus_y',30),
            'active_prediction':prediction_speed()}
    Path('ALPHA73_PERFORMANCE.json').write_text(json.dumps(report,indent=2,sort_keys=True));print(json.dumps(report,indent=2,sort_keys=True))
if __name__=='__main__':main()
