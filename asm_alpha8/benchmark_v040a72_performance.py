from __future__ import annotations
import json, statistics, tempfile, time
from pathlib import Path
from asm.procedure_cortex import ProcedureCortex

TRUST=lambda source:{'reliability':.99,'version':1}

def make_active(path, auto):
    c=ProcedureCortex(path,trust_provider=TRUST)
    for x in range(3):c.observe('f',{'x':x},2*x+3,evidence_id=f'fit-{x}',source_id='oracle',auto_induce=auto)
    if not auto:c.induce('f')
    for x in range(10,18):c.observe('f',{'x':x},2*x+3,evidence_id=f'val-{x}',source_id='oracle',auto_induce=auto)
    assert c.predict('f',{'x':50})['value']==103
    return c

def steady(auto,n=500):
    times=[];sizes=[]
    for rep in range(5):
        with tempfile.TemporaryDirectory() as d:
            db=Path(d)/'p.db';c=make_active(db,auto)
            t=time.perf_counter()
            for i in range(n):
                x=1000+rep*n+i
                c.observe('f',{'x':x},2*x+3,evidence_id=f's-{rep}-{i}',source_id='oracle',auto_induce=auto)
            times.append(time.perf_counter()-t);c.db.execute('PRAGMA wal_checkpoint(TRUNCATE)');c.close();sizes.append(db.stat().st_size)
    return {'median_s':statistics.median(times),'runs_s':times,'median_db_bytes':int(statistics.median(sizes)),'n':n}

def discovery(auto):
    times=[]
    for rep in range(20):
        with tempfile.TemporaryDirectory() as d:
            c=ProcedureCortex(Path(d)/'p.db',trust_provider=TRUST);t=time.perf_counter()
            for x in range(3):c.observe('f',{'x':x},2*x+3,evidence_id=f'f-{x}',source_id='oracle',auto_induce=auto)
            if not auto:c.induce('f')
            times.append(time.perf_counter()-t);c.close()
    return {'median_s':statistics.median(times),'runs':20}

def main():
    manual=steady(False);auto=steady(True);md=discovery(False);ad=discovery(True)
    report={'benchmark':'alpha.7.2 procedure autonomy performance',
            'steady_manual':manual,'steady_auto':auto,
            'steady_overhead_ratio':auto['median_s']/manual['median_s'],
            'discovery_manual':md,'discovery_auto':ad,
            'discovery_ratio':ad['median_s']/md['median_s']}
    Path('ALPHA72_PERFORMANCE.json').write_text(json.dumps(report,indent=2,sort_keys=True))
    print(json.dumps(report,indent=2,sort_keys=True))
if __name__=='__main__':main()
