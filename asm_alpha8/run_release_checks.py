"""Run ASM v0.4.0-alpha.7.7 release gates.

Default mode runs the current/fast regression surface. Use --full to additionally
rerun the very heavy inherited alpha.8-alpha.10 long-stream stress gates.
"""
from __future__ import annotations
import argparse, json, os, re, subprocess, sys, time
from pathlib import Path

ROOT=Path(__file__).resolve().parent
RESULTS=ROOT/'results'; RESULTS.mkdir(exist_ok=True)
env=dict(os.environ,OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',PYTHONWARNINGS='ignore')

BASE_JOBS=[
 ('unit_legacy_a',['-m','unittest','tests/test_v01110.py','tests/test_v0114.py','tests/test_v0115.py','-q']),
 ('unit_legacy_b',['-m','unittest','tests/test_v0116.py','tests/test_v0117.py','tests/test_v0118.py','tests/test_v0119.py','-q']),
 ('unit_v02_a',['-m','unittest','tests/test_v020a1.py','tests/test_v020a2.py','tests/test_v020a3.py','-q']),
 ('unit_v02_b',['-m','unittest','tests/test_v020a4.py','tests/test_v020a5.py','tests/test_v020a6.py','tests/test_v020a7.py','-q']),
 ('unit_v03_a',['-m','unittest','tests/test_v030a1.py','tests/test_v030a2.py','tests/test_v030a3.py','tests/test_v030a4.py','tests/test_v030a5.py','-q']),
 ('unit_v03_b',['-m','unittest','tests/test_v030a6.py','tests/test_v030a7.py','tests/test_v030a8.py','tests/test_v030a9.py','tests/test_v030a10.py','tests/test_v030a11.py','tests/test_v030a12.py','-q']),
 ('unit_v04_a',['-m','unittest','tests/test_v040a1.py','tests/test_v040a2.py','tests/test_v040a3.py','tests/test_v040a4.py','tests/test_v040a5.py','tests/test_v040a51.py','tests/test_v040a51_contract.py','tests/test_v040a52.py','tests/test_v040a6.py','tests/test_v040a61.py','tests/test_v040a62.py','tests/test_v040a7.py','tests/test_v040a71.py','tests/test_v040a72.py','tests/test_v040a73.py','tests/test_v040a74.py','tests/test_alpha71_astra_graft.py','-q']),
 ('hard_regression',['hard_benchmark_v030a5_regression.py']),
 ('semantic_event',['benchmark_v020a6_regression.py']),
 ('semantic_memory',['benchmark_v020a7.py']),
 ('world_state',['benchmark_v030a1.py']),
 ('transition_alpha2',['benchmark_v030a2.py']),
 ('transition_alpha3',['benchmark_v030a3.py']),
 ('scheduler_alpha4',['benchmark_v030a4.py']),
 ('scheduler_alpha5',['benchmark_v030a5.py']),
 ('retention_alpha6',['benchmark_v030a6.py']),
 ('capacity_alpha7',['benchmark_v030a7.py']),
 ('abstraction_alpha11',['benchmark_v030a11.py','--mode','all']),
 ('alpha12_structured_train',['benchmark_v030a12_split.py','--mode','structured_train']),
 ('alpha12_structured_finish',['benchmark_v030a12_split.py','--mode','structured_finish']),
 ('alpha12_baseline',['benchmark_v030a12_split.py','--mode','baseline']),
 ('alpha12_controls',['benchmark_v030a12_split.py','--mode','controls']),
 ('alpha12_lockbox',['benchmark_v030a12_split.py','--mode','lockbox']),
 ('alpha12_finalize',['benchmark_v030a12_split.py','--mode','finalize']),
 ('planning_alpha1_preservation',['benchmark_v040a1.py']),
 ('planning_alpha2',['benchmark_v040a2.py']),
 ('planning_alpha3',['benchmark_v040a3.py']),
 ('planning_alpha4',['benchmark_v040a4.py']),
 ('planning_alpha4_stress',['benchmark_v040a4_stress.py']),
 ('planning_alpha5',['benchmark_v040a5.py']),
 ('planning_alpha5_stress',['benchmark_v040a5_stress.py']),
 ('planning_alpha5_mega',['benchmark_v040a5_mega_stress.py']),
 ('planning_alpha5_extreme',['benchmark_v040a5_extreme_torture.py']),
 ('planning_alpha6',['benchmark_v040a6.py']),
 ('planning_alpha6_torture',['benchmark_v040a6_torture.py']),
 ('planning_alpha61_current',['benchmark_v040a61_current_gate.py']),
 ('planning_alpha61_stationary',['benchmark_v040a61_stationary_torture.py']),
 ('planning_alpha62',['benchmark_v040a62.py']),
 ('planning_alpha62_torture',['benchmark_v040a62_torture.py']),
 ('planning_alpha7',['benchmark_v040a7.py']),
 ('planning_alpha7_torture',['benchmark_v040a7_torture.py']),
 ('planning_alpha71',['benchmark_v040a71.py']),
 ('planning_alpha71_torture',['benchmark_v040a71_torture.py']),
 ('planning_alpha71_performance',['benchmark_v040a71_performance.py']),
 ('procedure_alpha72',['benchmark_v040a72.py']),
 ('procedure_alpha72_torture',['benchmark_v040a72_torture.py']),
 ('procedure_alpha72_performance',['benchmark_v040a72_performance.py']),
 ('procedure_alpha73',['benchmark_v040a73.py']),
 ('procedure_alpha73_torture',['benchmark_v040a73_torture.py']),
 ('procedure_alpha73_performance',['benchmark_v040a73_performance.py']),
 ('procedure_alpha74',['benchmark_v040a74.py']),
 ('procedure_alpha74_torture',['benchmark_v040a74_torture.py']),
 ('procedure_alpha74_performance',['benchmark_v040a74_performance.py']),
 ('writer',['benchmark_v020a5.py']),
 ('smoke',['smoke_test.py']),
]
FULL_JOBS=[
 ('long_horizon_alpha8',['benchmark_v030a8.py','--mode','all']),
 ('multichoice_alpha9',['benchmark_v030a9.py','--mode','all']),
 ('packed_alpha10',['benchmark_v030a10.py','--mode','all']),
]

def run_job(name,args):
    t=time.perf_counter(); p=subprocess.run([sys.executable,*args],cwd=ROOT,env=env,capture_output=True,text=True)
    out=p.stdout+p.stderr; (RESULTS/f'{name}.log').write_text(out,encoding='utf-8')
    row={'name':name,'returncode':p.returncode,'pass':p.returncode==0,'elapsed_seconds':round(time.perf_counter()-t,3),'command':[sys.executable,*args]}
    m=re.search(r'Ran (\d+) tests',out)
    if m: row['tests']=int(m.group(1))
    print(json.dumps(row),flush=True)
    if p.returncode != 0:
        tail='\n'.join(out.splitlines()[-40:])
        print(f'--- {name} failure output (last 40 lines) ---', flush=True)
        print(tail, flush=True)
        print(f'--- end {name} failure output ---', flush=True)
    return row

def trained_state_check():
    from asm import ASMEngine
    path=ROOT/'asm_v030a12_trained.db'; row={'name':'trained_state','pass':False}
    if not path.exists(): return row
    a=ASMEngine(path)
    try:
        st=a.stats(); w=st.get('world_model',{}); m=st.get('transition_mechanisms',{})
        row['pass']=(st.get('episodic_events')==897 and st.get('semantic_memory_vectors')==897 and st.get('semantic_event_records')==897 and w.get('state_history')==50 and w.get('current_states')==24 and m.get('mechanisms')==0 and m.get('experiences')==0)
        row['stats']=st
    finally: a.close(save_snapshot=False)
    return row

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--full',action='store_true'); ap.add_argument('--planning-only',action='store_true'); a=ap.parse_args()
    if a.planning_only:
        names={'unit_v04_a','planning_alpha1_preservation','planning_alpha2','planning_alpha3','planning_alpha4','planning_alpha4_stress','planning_alpha5','planning_alpha5_stress','planning_alpha5_mega','planning_alpha5_extreme','planning_alpha6','planning_alpha6_torture','planning_alpha61_current','planning_alpha61_stationary','planning_alpha62','planning_alpha62_torture','planning_alpha7','planning_alpha7_torture','planning_alpha71','planning_alpha71_torture','planning_alpha71_performance','procedure_alpha72','procedure_alpha72_torture','procedure_alpha72_performance','procedure_alpha73','procedure_alpha73_torture','procedure_alpha73_performance','procedure_alpha74','procedure_alpha74_torture','procedure_alpha74_performance','smoke'}
        jobs=[job for job in BASE_JOBS if job[0] in names]
    else:
        jobs=BASE_JOBS
    rows=[run_job(n,args) for n,args in jobs]
    if a.full and not a.planning_only: rows.extend(run_job(n,args) for n,args in FULL_JOBS)
    tr=trained_state_check(); rows.append(tr); print(json.dumps({'name':'trained_state','pass':tr['pass']},flush=True))
    payload={'version':'0.4.0-alpha.7.7','full':a.full,'planning_only':a.planning_only,'unit_tests':sum(int(r.get('tests',0)) for r in rows),'checks':rows,'pass':all(r['pass'] for r in rows)}
    (RESULTS/'release_checks_v040a74.json').write_text(json.dumps(payload,indent=2),encoding='utf-8')
    raise SystemExit(0 if payload['pass'] else 1)

if __name__=='__main__': main()
