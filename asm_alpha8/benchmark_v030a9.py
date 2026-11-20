from __future__ import annotations
import argparse, hashlib, json, time
from array import array
from pathlib import Path
from asm import __version__
from asm.transition_mechanism import LocalRecurrentTransitionMechanism

ROOT=Path(__file__).resolve().parent
RESULTS=ROOT/'results'; RESULTS.mkdir(exist_ok=True)
MAIN_STAGE=RESULTS/'.alpha9_main_stage.blob'
MAIN_JSON=RESULTS/'alpha9_main_1024.json'
COMP_JSON=RESULTS/'alpha9_component_scaling.json'
LOCK_JSON=RESULTS/'alpha9_fresh_lockbox.json'
FINAL_JSON=RESULTS/'adaptive_multichoice_consolidation_benchmark.json'

N=1024; GS=64
GATES={
 'main_post_min':0.98,
 'main_group_min':60,
 'main_restart_min':0.98,
 'fixed_bytes':43008,
 'full_anchor_max':96,
 'component_1024_min':1.0,
 'component_2048_min':0.99,
 'component_wrong_max':0,
 'legacy_alpha8_1024_max':0.90,
 'gain_over_legacy_min':0.08,
 'fresh_lockbox_min':0.98,
 'fresh_group_min':47,
}

def main_case(i):
 s={'kind':'extreme_machine','mode':i,'bank':i//64,'phase':i%5,'signal':f's{i%29}','parity':i%2,'bucket':(i*7)%31}
 o={'kind':'extreme_machine','result':i,'status':f'z{i%37}','done':True}
 return s,'advance',o

def lock_case(i):
 s={'kind':'fresh_lockbox','index':i,'band':i//48,'phase':i%7,'signal':f'q{(i*11)%41}','flag':bool(i%2),'bucket':(i*17)%43}
 o={'kind':'fresh_lockbox','result':i,'status':f'w{(i*13)%47}','done':True}
 return s,'step',o

def build(name='a9_e2e_1024',seed=53,hidden=16):
 m=LocalRecurrentTransitionMechanism(name,hidden_dim=hidden,train_steps=1,learning_rate=.008,seed=seed,max_outcomes=32,outcome_capacity_limit=1024,retention_anchor_limit=96,retention_anchor_batch_limit=6,consolidation_table_size=1024,consolidation_hashes=3,consolidation_min_support=4,consolidation_max_displacements=24)
 m.replay_batch_limit=3
 return m

def train(m,ids,reps,tag,case_fn):
 for i in ids:
  s,a,o=case_fn(i)
  for r in range(reps): m.observe(entity_id=f'{tag}_{i}_{r}_{m.total_observations}',state=s,action=a,after_state=o)

def evaluate(m,n,group_size,case_fn,tag):
 rows=[]
 for g0 in range(0,n,group_size):
  c=0
  for i in range(g0,min(n,g0+group_size)):
   s,a,o=case_fn(i); c+=int(m.predict(entity_id=f'{tag}_{i}',state=s,action=a).predicted_state==o)
  rows.append(c)
 return rows

def _legacy_alpha8_recall(signatures,reps=4):
 table_size=1024; hashes=3; cells=table_size*hashes
 fps=array('Q',[0])*cells; slots=array('i',[-1])*cells; support=array('H',[0])*cells
 def fp(sig): return int.from_bytes(hashlib.sha256(('fp|'+sig).encode()).digest()[:8],'big') or 1
 def idxs(sig):
  out=[]
  for t in range(hashes):
   raw=hashlib.sha256(f'a8|{t}|{sig}'.encode()).digest(); out.append(t*table_size+int.from_bytes(raw[:8],'big')%table_size)
  return out
 for slot,sig in enumerate(signatures):
  f=fp(sig)
  for _ in range(reps):
   for idx in idxs(sig):
    cf,cs,sup=int(fps[idx]),int(slots[idx]),int(support[idx])
    if cf==f and cs==slot: support[idx]=min(65535,sup+1)
    elif cf==0: fps[idx]=f;slots[idx]=slot;support[idx]=1
    elif sup<=1: fps[idx]=f;slots[idx]=slot;support[idx]=1
    else: support[idx]=sup-1
 ok=wrong=miss=0
 for slot,sig in enumerate(signatures):
  f=fp(sig); found=[]
  for idx in idxs(sig):
   if int(fps[idx])==f and int(support[idx])>=4: found.append(int(slots[idx]))
  if not found: miss+=1
  elif max(set(found),key=found.count)==slot: ok+=1
  else: wrong+=1
 return ok,wrong,miss

def mode_component():
 t=time.perf_counter(); rows={}
 for n in (1024,2048,2560):
  m=build(name=f'a9_component_{n}',hidden=8); m.total_observations=10**6
  m.outcome_to_slot={str(i):i for i in range(n)}; m.slot_to_outcome={i:{'r':i} for i in range(n)}
  signatures=[]
  for i in range(n):
   s,a,_=main_case(i); sig=m._input_signature(s,a,None,1.0); signatures.append(sig)
   fp=m._consolidation_fingerprint(sig)
   for _ in range(4): m._place_consolidation_record(fp,i,1)
  ok=wrong=miss=0
  for i,sig in enumerate(signatures):
   slot,_,_=m._query_consolidation(sig)
   if slot==i: ok+=1
   elif slot is None: miss+=1
   else: wrong+=1
  rows[str(n)]={'ok':ok,'wrong':wrong,'miss':miss,'accuracy':ok/n,'stats':m.stats()}
 signatures=[]; probe=build(name='legacy_sig',hidden=8)
 for i in range(1024):
  s,a,_=main_case(i); signatures.append(probe._input_signature(s,a,None,1.0))
 lok,lwrong,lmiss=_legacy_alpha8_recall(signatures)
 payload={'version':__version__,'rows':rows,'legacy_alpha8_1024':{'ok':lok,'wrong':lwrong,'miss':lmiss,'accuracy':lok/1024},'seconds':time.perf_counter()-t}
 COMP_JSON.write_text(json.dumps(payload,indent=2)); print(json.dumps(payload,indent=2))

def mode_main_train():
 t=time.perf_counter();m=build()
 train(m,range(N),4,'learn',main_case); pre=evaluate(m,N,GS,main_case,'pre'); MAIN_STAGE.write_bytes(m.export_blob())
 print(json.dumps({'version':__version__,'pre':pre,'accuracy':sum(pre)/N,'stats':m.stats(),'seconds':time.perf_counter()-t},indent=2))

def mode_main_hammer():
 if not MAIN_STAGE.exists(): raise SystemExit('run main_train first')
 t=time.perf_counter();m=build();m.import_blob(MAIN_STAGE.read_bytes()); pre=evaluate(m,N,GS,main_case,'pre')
 for rn in range(3):
  train(m,range(14*GS,15*GS),4,f'h14_{rn}',main_case); train(m,range(15*GS,16*GS),4,f'h15_{rn}',main_case)
 post=evaluate(m,N,GS,main_case,'post'); blob=m.export_blob();r=build();r.import_blob(blob);restart=evaluate(r,N,GS,main_case,'restart')
 payload={'version':__version__,'before':pre,'post':post,'restart':restart,'post_accuracy':sum(post)/N,'restart_accuracy':sum(restart)/N,'stats':r.stats(),'seconds':time.perf_counter()-t}
 MAIN_JSON.write_text(json.dumps(payload,indent=2)); print(json.dumps(payload,indent=2))

def mode_lockbox():
 t=time.perf_counter();n=768;gs=48;m=build(name='a9_fresh_lockbox',seed=71,hidden=18)
 train(m,range(n),4,'learn',lock_case)
 for rn in range(2): train(m,range(n-2*gs,n),4,f'hammer_{rn}',lock_case)
 post=evaluate(m,n,gs,lock_case,'post');blob=m.export_blob();r=build(name='a9_fresh_lockbox',seed=71,hidden=18);r.import_blob(blob);restart=evaluate(r,n,gs,lock_case,'restart')
 payload={'version':__version__,'post':post,'restart':restart,'post_accuracy':sum(post)/n,'restart_accuracy':sum(restart)/n,'stats':r.stats(),'seconds':time.perf_counter()-t}
 LOCK_JSON.write_text(json.dumps(payload,indent=2));print(json.dumps(payload,indent=2))

def mode_finalize():
 for p in (COMP_JSON,MAIN_JSON,LOCK_JSON):
  if not p.exists(): raise SystemExit(f'missing {p}')
 comp=json.loads(COMP_JSON.read_text()); main=json.loads(MAIN_JSON.read_text()); lock=json.loads(LOCK_JSON.read_text())
 c1024=comp['rows']['1024']['accuracy']; c2048=comp['rows']['2048']['accuracy']; legacy=comp['legacy_alpha8_1024']['accuracy']
 checks={
  'main_1024_post_retention':main['post_accuracy']>=GATES['main_post_min'],
  'main_each_group':min(main['post'])>=GATES['main_group_min'],
  'main_restart_retention':main['restart_accuracy']>=GATES['main_restart_min'],
  'main_restart_exact':main['restart']==main['post'],
  'same_43008_byte_budget':main['stats']['consolidation_bytes']==GATES['fixed_bytes'],
  'full_anchors_remain_bounded':main['stats']['retention_anchors']<=GATES['full_anchor_max'],
  'component_1024_exact':c1024>=GATES['component_1024_min'],
  'component_2048_near_exact':c2048>=GATES['component_2048_min'],
  'component_no_wrong_recall':max(comp['rows'][k]['wrong'] for k in comp['rows'])<=GATES['component_wrong_max'],
  'legacy_alpha8_pressure_reproduced':legacy<=GATES['legacy_alpha8_1024_max'],
  'material_gain_over_legacy_layout':(c1024-legacy)>=GATES['gain_over_legacy_min'],
  'fresh_lockbox_retention':lock['post_accuracy']>=GATES['fresh_lockbox_min'],
  'fresh_lockbox_each_group':min(lock['post'])>=GATES['fresh_group_min'],
  'fresh_lockbox_restart_exact':lock['restart']==lock['post'],
 }
 payload={'version':__version__,'benchmark':'ASM v0.3.0-alpha.9 Adaptive Multi-Choice Consolidation','gates':GATES,'summary':{'main_post':main['post_accuracy'],'main_restart':main['restart_accuracy'],'component_1024':c1024,'component_2048':c2048,'legacy_alpha8_component_1024':legacy,'fresh_lockbox':lock['post_accuracy'],'bytes':main['stats']['consolidation_bytes'],'used_cells':main['stats']['consolidation_used_cells'],'placement_failures':main['stats']['consolidation_placement_failures']},'checks':checks,'passed':sum(checks.values()),'total':len(checks)}
 FINAL_JSON.write_text(json.dumps(payload,indent=2));MAIN_STAGE.unlink(missing_ok=True);print(json.dumps(payload,indent=2));raise SystemExit(0 if all(checks.values()) else 1)

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--mode',choices=['component','main_train','main_hammer','lockbox','finalize','all'],required=True);a=ap.parse_args()
 if a.mode=='all':
  mode_component();mode_main_train();mode_main_hammer();mode_lockbox();mode_finalize()
 else: globals()[f'mode_{a.mode}']()
