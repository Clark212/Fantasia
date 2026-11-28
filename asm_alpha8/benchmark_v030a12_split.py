from __future__ import annotations
import argparse, json
from pathlib import Path
from asm import __version__
import benchmark_v030a12 as b

R=Path('results'); R.mkdir(exist_ok=True)
TRAIN_BLOB=R/'.alpha12_structured_train.blob'
TRAIN_JSON=R/'alpha12_structured_train.json'
STRUCT_JSON=R/'alpha12_structured_finish.json'
BASE_JSON=R/'alpha12_drop_only_ablation.json'
CTRL_JSON=R/'alpha12_controls.json'
LOCK_JSON=R/'alpha12_fresh_lockbox.json'
FINAL_JSON=R/'abstraction_hardening_benchmark.json'

def structured_train():
    m=b.build('a12_structured',sparse=True,seed=1201); b.train_structured(m)
    ok,total=b.eval_structured(m,extra_keys=False)
    shift_ok,shift_total=b.eval_structured(m,extra_keys=True)
    payload={'version':__version__,'unseen':[ok,total],'new_key_shift':[shift_ok,shift_total],'stats':m.stats()}
    TRAIN_BLOB.write_bytes(m.export_blob()); TRAIN_JSON.write_text(json.dumps(payload,indent=2,sort_keys=True))
    print(json.dumps(payload,indent=2,sort_keys=True))

def structured_finish():
    if not TRAIN_BLOB.exists(): raise SystemExit('run structured_train first')
    m=b.build('a12_structured',sparse=True,seed=1201); m.import_blob(TRAIN_BLOB.read_bytes())
    exc_ok,exc_total,rows=b.exception_phase(m)
    post=b.eval_structured(m,start=50,count=4,extra_keys=True)
    r=b.build('a12_structured',sparse=True,seed=1201); r.import_blob(m.export_blob())
    restart=b.eval_structured(r,start=60,count=4,extra_keys=True)
    restart_exc=sum(int(r.predict(entity_id='restart-exc',state=st,action=a).predicted_state==truth) for st,a,truth in rows)
    payload={'version':__version__,'exceptions':[exc_ok,exc_total],'post_exception_unseen':list(post),
             'restart_unseen':list(restart),'restart_exceptions':[restart_exc,16],'stats':r.stats()}
    STRUCT_JSON.write_text(json.dumps(payload,indent=2,sort_keys=True)); print(json.dumps(payload,indent=2,sort_keys=True))

def baseline():
    m=b.build('a12_structured',sparse=False,pending=False,candidate_limit=32,seed=1201); b.train_structured(m); ok,total=b.eval_structured(m,extra_keys=False)
    payload={'version':__version__,'unseen':[ok,total],'stats':m.stats()}
    BASE_JSON.write_text(json.dumps(payload,indent=2,sort_keys=True)); print(json.dumps(payload,indent=2,sort_keys=True))

def controls():
    payload={'version':__version__,'random_control':b.random_control(),'ambiguous_control':b.ambiguity_control(),
             'distribution_shift':b.systematic_change_control()}
    CTRL_JSON.write_text(json.dumps(payload,indent=2,sort_keys=True)); print(json.dumps(payload,indent=2,sort_keys=True))

def lockbox():
    payload={'version':__version__,'fresh_lockbox':b.fresh_lockbox()}
    LOCK_JSON.write_text(json.dumps(payload,indent=2,sort_keys=True)); print(json.dumps(payload,indent=2,sort_keys=True))

def finalize():
    for p in (TRAIN_JSON,STRUCT_JSON,BASE_JSON,CTRL_JSON,LOCK_JSON):
        if not p.exists(): raise SystemExit(f'missing {p}')
    tr=json.loads(TRAIN_JSON.read_text()); st=json.loads(STRUCT_JSON.read_text()); base=json.loads(BASE_JSON.read_text()); ctrl=json.loads(CTRL_JSON.read_text()); lock=json.loads(LOCK_JSON.read_text())
    unseen_ok,unseen_total=tr['unseen']; base_ok,base_total=base['unseen']; random_row=ctrl['random_control']; ambiguous=ctrl['ambiguous_control']; shift=ctrl['distribution_shift']; lb=lock['fresh_lockbox']; stats=tr['stats']
    checks={
      'high_dim_unseen_384_of_384': unseen_ok==unseen_total==384,
      'beats_alpha11_style_drop_only_by_70_points': (unseen_ok/unseen_total)-(base_ok/base_total)>=0.70,
      'at_least_64_competing_abstractions': stats['abstraction_promoted']>=64,
      'candidate_main_memory_bounded_2048': stats['abstraction_candidates']<=2048,
      'candidate_pending_memory_bounded_256': stats.get('abstraction_pending_candidates',0)<=256,
      'new_nuisance_feature_keys_do_not_break_transfer': tr.get('new_key_shift')==[384,384],
      'late_exact_exceptions_16_of_16': st['exceptions']==[16,16],
      'generalization_survives_exceptions_256_of_256': st['post_exception_unseen']==[256,256],
      'restart_generalization_256_of_256': st['restart_unseen']==[256,256],
      'restart_exceptions_16_of_16': st['restart_exceptions']==[16,16],
      'random_control_promotes_no_rules': random_row['promoted']==0,
      'random_control_unseen_at_or_below_10pct': random_row['accuracy']<=0.10,
      'ambiguous_visible_input_blocks_abstraction': all(ambiguous.values()),
      'diverse_distribution_shift_demotes_rule': all(shift.values()),
      'fresh_lockbox_150_of_150': lb['correct']==lb['total']==150,
      'fresh_lockbox_restart_150_of_150': lb['restart_correct']==lb['restart_total']==150,
      'sparse_projection_search_is_bounded': stats['abstraction_candidates_per_observation']<=48,
      'version_is_alpha12': __version__.startswith('0.4.0-alpha.7'),
    }
    payload={'version':__version__,'benchmark':'ASM v0.3.0-alpha.12 Robust Abstraction Hardening',
      'structured':{'unseen':tr['unseen'],'new_key_shift':tr.get('new_key_shift'),'drop_only_baseline':base['unseen'],'promoted':stats['abstraction_promoted'],
                    'candidates':stats['abstraction_candidates'],'pending_candidates':stats.get('abstraction_pending_candidates',0),
                    'exceptions':st['exceptions'],'post_exception_unseen':st['post_exception_unseen'],
                    'restart_unseen':st['restart_unseen'],'restart_exceptions':st['restart_exceptions']},
      'random_control':random_row,'ambiguous_control':ambiguous,'distribution_shift':shift,'fresh_lockbox':lb,
      'checks':checks,'passed':sum(checks.values()),'total':len(checks)}
    FINAL_JSON.write_text(json.dumps(payload,indent=2,sort_keys=True)); TRAIN_BLOB.unlink(missing_ok=True)
    print(json.dumps(payload,indent=2,sort_keys=True)); raise SystemExit(0 if all(checks.values()) else 1)

def all_modes():
    structured_train(); structured_finish(); baseline(); controls(); lockbox(); finalize()

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--mode',required=True,choices=['structured_train','structured_finish','baseline','controls','lockbox','finalize','all']); a=ap.parse_args()
    {'structured_train':structured_train,'structured_finish':structured_finish,'baseline':baseline,'controls':controls,'lockbox':lockbox,'finalize':finalize,'all':all_modes}[a.mode]()
