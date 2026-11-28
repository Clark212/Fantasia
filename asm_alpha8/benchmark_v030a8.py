from __future__ import annotations
import argparse, json, time
from pathlib import Path
from asm import __version__
from asm.transition_mechanism import LocalRecurrentTransitionMechanism

ROOT=Path(__file__).resolve().parent
RESULTS=ROOT/'results'; RESULTS.mkdir(exist_ok=True)
MAIN_STAGE=RESULTS/'.alpha8_main_stage.blob'
MAIN_JSON=RESULTS/'alpha8_main_consolidation.json'
ABLATION_JSON=RESULTS/'alpha8_no_consolidation_ablation.json'
LOCKBOX_JSON=RESULTS/'alpha8_fresh_lockbox.json'
FINAL_JSON=RESULTS/'long_horizon_consolidation_benchmark.json'

GROUP_SIZE=32
MAIN_GROUPS=[tuple(range(i,i+32)) for i in range(0,256,32)]
LOCK_GROUPS=[tuple(range(i,i+32)) for i in range(0,192,32)]

GATES={
 'main_post_hammer_overall_min':0.95,
 'main_each_group_min':28,
 'main_restart_overall_min':0.95,
 'anchor_limit_max':96,
 'fixed_consolidation_bytes':43008,
 'ablation_overall_max':0.80,
 'gain_over_ablation_min':0.15,
 'fresh_lockbox_overall_min':0.95,
 'fresh_lockbox_each_group_min':28,
}

def main_case(i):
    s={'kind':'stress_machine','mode':i,'bank':i//32,'phase':i%4,'signal':f's{i%13}','parity':i%2}
    o={'kind':'stress_machine','mode':i,'done':True,'result':i,'class':f'c{i%17}'}
    return s,'advance',o

def lock_case(i):
    s={'kind':'lockbox_unit','index':i,'band':i//24,'phase':i%7,'signal':f'q{(i*5)%23}','odd':bool(i%2),'bucket':(i*11)%19}
    o={'kind':'lockbox_unit','result':i,'status':f'z{(i*7)%29}','done':True}
    return s,'step',o

def build(name='a7_hardfeed_shared', enabled=True, seed=29):
    return LocalRecurrentTransitionMechanism(
        name, hidden_dim=48, train_steps=2, learning_rate=.008, seed=seed,
        max_outcomes=32, outcome_capacity_limit=256,
        retention_anchor_limit=96, retention_anchor_batch_limit=8,
        consolidation_enabled=enabled, consolidation_table_size=1024,
        consolidation_hashes=3, consolidation_min_support=4,
    )

def train(m, ids, reps, tag, case_fn):
    for i in ids:
        s,a,o=case_fn(i)
        for r in range(reps):
            m.observe(entity_id=f'{tag}_{i}_{r}_{m.total_observations}',state=s,action=a,after_state=o)

def evaluate(m, groups, case_fn, tag):
    rows=[]
    for gi,g in enumerate(groups):
        c=0
        for i in g:
            s,a,o=case_fn(i)
            c += int(m.predict(entity_id=f'{tag}_{gi}_{i}',state=s,action=a).predicted_state==o)
        rows.append(c)
    return rows

def mode_main_train():
    t=time.perf_counter(); m=build()
    for gi,g in enumerate(MAIN_GROUPS): train(m,g,8,f'learn{gi}',main_case)
    before=evaluate(m,MAIN_GROUPS,main_case,'pre')
    MAIN_STAGE.write_bytes(m.export_blob())
    print(json.dumps({'mode':'main_train','groups':before,'stats':m.stats(),'seconds':time.perf_counter()-t},indent=2))

def mode_main_hammer():
    if not MAIN_STAGE.exists(): raise SystemExit('run --mode main_train first')
    t=time.perf_counter(); m=build(); m.import_blob(MAIN_STAGE.read_bytes())
    before=evaluate(m,MAIN_GROUPS,main_case,'pre')
    for rn in range(3):
        train(m,MAIN_GROUPS[6],8,f'hammer6_{rn}',main_case)
        train(m,MAIN_GROUPS[7],8,f'hammer7_{rn}',main_case)
    post=evaluate(m,MAIN_GROUPS,main_case,'post')
    blob=m.export_blob(); r=build(); r.import_blob(blob)
    restart=evaluate(r,MAIN_GROUPS,main_case,'restart')
    payload={'version':__version__,'before_hammer':before,'post_hammer':post,'restart':restart,'stats':r.stats(),'seconds':time.perf_counter()-t}
    MAIN_JSON.write_text(json.dumps(payload,indent=2),encoding='utf-8')
    print(json.dumps(payload,indent=2))

def mode_ablation():
    t=time.perf_counter(); m=build(enabled=False)
    for gi,g in enumerate(MAIN_GROUPS): train(m,g,8,f'learn{gi}',main_case)
    groups=evaluate(m,MAIN_GROUPS,main_case,'ablation')
    blob=m.export_blob(); r=build(enabled=False); r.import_blob(blob)
    restart=evaluate(r,MAIN_GROUPS,main_case,'ablation_restart')
    payload={'version':__version__,'groups':groups,'restart':restart,'stats':r.stats(),'seconds':time.perf_counter()-t}
    ABLATION_JSON.write_text(json.dumps(payload,indent=2),encoding='utf-8')
    print(json.dumps(payload,indent=2))

def mode_lockbox():
    t=time.perf_counter(); m=build(name='a8_fresh_lockbox',enabled=True,seed=41)
    for gi,g in enumerate(LOCK_GROUPS): train(m,g,6,f'learn{gi}',lock_case)
    before=evaluate(m,LOCK_GROUPS,lock_case,'pre')
    for rn in range(2):
        train(m,LOCK_GROUPS[-2],6,f'hammerA{rn}',lock_case)
        train(m,LOCK_GROUPS[-1],6,f'hammerB{rn}',lock_case)
    post=evaluate(m,LOCK_GROUPS,lock_case,'post')
    blob=m.export_blob(); r=build(name='a8_fresh_lockbox',enabled=True,seed=41); r.import_blob(blob)
    restart=evaluate(r,LOCK_GROUPS,lock_case,'restart')
    payload={'version':__version__,'before_hammer':before,'post_hammer':post,'restart':restart,'stats':r.stats(),'seconds':time.perf_counter()-t}
    LOCKBOX_JSON.write_text(json.dumps(payload,indent=2),encoding='utf-8')
    print(json.dumps(payload,indent=2))

def mode_finalize():
    for p in (MAIN_JSON,ABLATION_JSON,LOCKBOX_JSON):
        if not p.exists(): raise SystemExit(f'missing {p}; run component modes first')
    main=json.loads(MAIN_JSON.read_text()); abl=json.loads(ABLATION_JSON.read_text()); lock=json.loads(LOCKBOX_JSON.read_text())
    main_post=sum(main['post_hammer'])/256; main_restart=sum(main['restart'])/256
    abl_acc=sum(abl['groups'])/256; lock_post=sum(lock['post_hammer'])/192; lock_restart=sum(lock['restart'])/192
    checks={
      'main_overall_retention': main_post >= GATES['main_post_hammer_overall_min'],
      'main_each_group_retention': min(main['post_hammer']) >= GATES['main_each_group_min'],
      'main_restart_retention': main_restart >= GATES['main_restart_overall_min'],
      'main_restart_exact': main['restart']==main['post_hammer'],
      'full_anchor_budget_stays_96': main['stats']['retention_anchors'] <= GATES['anchor_limit_max'],
      'consolidation_storage_is_fixed_43008_bytes': main['stats']['consolidation_bytes']==GATES['fixed_consolidation_bytes'],
      'alpha7_style_ablation_reproduced': abl_acc <= GATES['ablation_overall_max'],
      'consolidation_material_gain': (main_post-abl_acc) >= GATES['gain_over_ablation_min'],
      'fresh_lockbox_overall': lock_post >= GATES['fresh_lockbox_overall_min'],
      'fresh_lockbox_each_group': min(lock['post_hammer']) >= GATES['fresh_lockbox_each_group_min'],
      'fresh_lockbox_restart_exact': lock['restart']==lock['post_hammer'],
      'fixed_bytes_same_across_192_and_256_outcomes': lock['stats']['consolidation_bytes']==main['stats']['consolidation_bytes'],
    }
    payload={'version':__version__,'benchmark':'ASM v0.3.0-alpha.8 Long-Horizon Consolidation','gates':GATES,'summary':{'main_post_hammer':main_post,'main_restart':main_restart,'ablation':abl_acc,'gain':main_post-abl_acc,'fresh_lockbox_post':lock_post,'fresh_lockbox_restart':lock_restart,'full_anchors':main['stats']['retention_anchors'],'consolidation_bytes':main['stats']['consolidation_bytes'],'consolidation_used_cells':main['stats']['consolidation_used_cells']},'checks':checks,'passed':sum(checks.values()),'total':len(checks)}
    FINAL_JSON.write_text(json.dumps(payload,indent=2),encoding='utf-8')
    MAIN_STAGE.unlink(missing_ok=True)
    print(json.dumps(payload,indent=2))
    raise SystemExit(0 if all(checks.values()) else 1)

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--mode',choices=['main_train','main_hammer','ablation','lockbox','finalize','all'],required=True); args=ap.parse_args()
    if args.mode=='all':
        mode_main_train(); mode_main_hammer(); mode_ablation(); mode_lockbox(); mode_finalize()
    else:
        globals()[f'mode_{args.mode}']()
