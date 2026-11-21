from __future__ import annotations
import argparse, hashlib, io, json, time
from array import array
from pathlib import Path
from asm import __version__
from asm.transition_mechanism import LocalRecurrentTransitionMechanism

ROOT=Path(__file__).resolve().parent
RESULTS=ROOT/'results';RESULTS.mkdir(exist_ok=True)
COMP=RESULTS/'alpha10_packed_component.json'
STAGE=RESULTS/'.alpha10_main_stage.blob'
MAIN=RESULTS/'alpha10_main_1536.json'
FINAL=RESULTS/'packed_high_load_consolidation_benchmark.json'
N=1536;GS=96
GATES={
 'fixed_bytes':43008,
 'physical_cells':3584,
 'component_2560_min':1.0,
 'component_2800_min':0.995,
 'component_3072_min':0.96,
 'wrong_max':0,
 'legacy_a9_2560_max':0.99,
 'gain_2560_min':0.01,
 'bounded_limit_3300_max':0.99,
 'main_post_min':0.99,
 'main_group_min':92,
 'restart_min':0.99,
 'anchors_max':96,
}

def case(i):
 s={'kind':'packed_machine','mode':i,'bank':i//96,'phase':i%7,'signal':f'p{i%41}','parity':i%2,'bucket':(i*13)%47}
 o={'kind':'packed_machine','result':i,'status':f'v{i%53}','done':True}
 return s,'advance',o

def build(name='a10_main',seed=83,hidden=12):
 m=LocalRecurrentTransitionMechanism(name,hidden_dim=hidden,train_steps=1,learning_rate=.008,seed=seed,max_outcomes=32,outcome_capacity_limit=4096,retention_anchor_limit=96,retention_anchor_batch_limit=6,consolidation_table_size=1024,consolidation_hashes=3,consolidation_min_support=4,consolidation_max_displacements=24)
 m.replay_batch_limit=2
 return m

def train(m,ids,reps,tag):
 for i in ids:
  s,a,o=case(i)
  for r in range(reps):m.observe(entity_id=f'{tag}_{i}_{r}_{m.total_observations}',state=s,action=a,after_state=o)

def evaluate(m):
 rows=[]
 for g0 in range(0,N,GS):
  c=0
  for i in range(g0,min(N,g0+GS)):
   s,a,o=case(i);c+=int(m.predict(entity_id=f'eval_{i}',state=s,action=a).predicted_state==o)
  rows.append(c)
 return rows

def legacy_a9_recall(n:int):
 # Exact alpha.9 logical layout: 3072 cells, Q+i+H = 43,008 bytes,
 # one-copy multi-choice placement with bounded displacement.
 hashes=3;cells=1024*3;max_disp=24
 fps=array('Q',[0])*cells;slots=array('i',[-1])*cells;sup=array('H',[0])*cells
 def fp(sig):return int.from_bytes(hashlib.sha256(('fp|'+sig).encode()).digest()[:8],'big') or 1
 def idxs(f):
  raw_fp=int(f).to_bytes(8,'big');out=[]
  for choice in range(hashes):
   person=f'asm-a9-{choice}'.encode()[:16]
   raw=hashlib.blake2b(raw_fp,digest_size=8,person=person).digest();idx=int.from_bytes(raw,'big')%cells
   if idx not in out:out.append(idx)
  return out
 def place(f,slot,support=1):
  support=max(1,min(65535,support));cand=idxs(f)
  for idx in cand:
   if int(fps[idx])==f and int(slots[idx])==slot:sup[idx]=min(65535,int(sup[idx])+support);return True
  for idx in cand:
   if int(fps[idx])==0:fps[idx]=f;slots[idx]=slot;sup[idx]=support;return True
  current=(f,slot,support);idx=min(cand,key=lambda j:(int(sup[j]),j));visited=set()
  for _ in range(max_disp):
   ev=(int(fps[idx]),int(slots[idx]),int(sup[idx]));fps[idx]=current[0];slots[idx]=current[1];sup[idx]=current[2];current=ev
   if current[0]==0:return True
   alts=idxs(current[0])
   for alt in alts:
    if int(fps[alt])==0:fps[alt]=current[0];slots[alt]=current[1];sup[alt]=current[2];return True
   alternatives=[a for a in alts if a!=idx]
   if not alternatives:break
   idx=min(alternatives,key=lambda j:(int(sup[j]),j));marker=(current[0],idx)
   if marker in visited:break
   visited.add(marker)
  return False
 probe=build('sigprobe',hidden=8);sigs=[]
 for i in range(n):
  s,a,_=case(i);sig=probe._input_signature(s,a,None,1.0);sigs.append(sig);f=fp(sig)
  for _ in range(4):place(f,i,1)
 ok=wrong=0
 for i,sig in enumerate(sigs):
  f=fp(sig);found=None
  for idx in idxs(f):
   if int(fps[idx])==f and int(sup[idx])>=4:found=int(slots[idx]);break
  ok+=found==i;wrong+=found is not None and found!=i
 return ok,wrong,n-ok-wrong

def component_one(n):
 m=build(f'a10_comp_{n}',hidden=8);m.total_observations=10**6
 m.outcome_to_slot={str(i):i for i in range(n)};m.slot_to_outcome={i:{'r':i} for i in range(n)}
 sigs=[]
 for i in range(n):
  s,a,_=case(i);sig=m._input_signature(s,a,None,1.0);sigs.append(sig);f=m._consolidation_fingerprint(sig)
  for _ in range(4):m._place_consolidation_record(f,i,1)
 ok=wrong=0
 for i,sig in enumerate(sigs):
  slot,_,_=m._query_consolidation(sig);ok+=slot==i;wrong+=slot is not None and slot!=i
 return {'ok':ok,'wrong':wrong,'miss':n-ok-wrong,'accuracy':ok/n,'stats':m.stats()}

def mode_component():
 t=time.perf_counter();rows={str(n):component_one(n) for n in (2048,2560,2800,3072,3300)}
 lok,lwrong,lmiss=legacy_a9_recall(2560)
 payload={'version':__version__,'rows':rows,'legacy_alpha9_2560':{'ok':lok,'wrong':lwrong,'miss':lmiss,'accuracy':lok/2560},'seconds':time.perf_counter()-t}
 COMP.write_text(json.dumps(payload,indent=2));print(json.dumps(payload,indent=2))

def mode_main_train():
 t=time.perf_counter();m=build();train(m,range(N),4,'learn');pre=evaluate(m);STAGE.write_bytes(m.export_blob())
 print(json.dumps({'version':__version__,'pre':pre,'accuracy':sum(pre)/N,'stats':m.stats(),'seconds':time.perf_counter()-t},indent=2))

def mode_main_hammer():
 if not STAGE.exists():raise SystemExit('run main_train first')
 t=time.perf_counter();m=build();m.import_blob(STAGE.read_bytes())
 for rn in range(2):
  train(m,range(14*GS,15*GS),4,f'h14_{rn}');train(m,range(15*GS,16*GS),4,f'h15_{rn}')
 post=evaluate(m);blob=m.export_blob();r=build();r.import_blob(blob);restart=evaluate(r)
 payload={'version':__version__,'post':post,'restart':restart,'post_accuracy':sum(post)/N,'restart_accuracy':sum(restart)/N,'stats':r.stats(),'seconds':time.perf_counter()-t}
 MAIN.write_text(json.dumps(payload,indent=2));print(json.dumps(payload,indent=2))

def mode_finalize():
 for p in (COMP,MAIN):
  if not p.exists():raise SystemExit(f'missing {p}')
 comp=json.loads(COMP.read_text());main=json.loads(MAIN.read_text());rows=comp['rows'];legacy=comp['legacy_alpha9_2560']['accuracy']
 checks={
  'same_43008_byte_budget':rows['2560']['stats']['consolidation_bytes']==GATES['fixed_bytes'],
  'packed_cell_count':rows['2560']['stats']['consolidation_cells']==GATES['physical_cells'],
  'component_2560_exact':rows['2560']['accuracy']>=GATES['component_2560_min'],
  'component_2800_near_exact':rows['2800']['accuracy']>=GATES['component_2800_min'],
  'component_3072_still_strong':rows['3072']['accuracy']>=GATES['component_3072_min'],
  'no_wrong_exact_key_recall':max(v['wrong'] for v in rows.values())<=GATES['wrong_max'],
  'alpha9_high_load_failure_reproduced':legacy<=GATES['legacy_a9_2560_max'],
  'material_gain_over_alpha9_at_2560':rows['2560']['accuracy']-legacy>=GATES['gain_2560_min'],
  'bounded_table_still_has_limit':rows['3300']['accuracy']<=GATES['bounded_limit_3300_max'],
  'main_1536_post_retention':main['post_accuracy']>=GATES['main_post_min'],
  'main_each_group_retained':min(main['post'])>=GATES['main_group_min'],
  'main_restart_retention':main['restart_accuracy']>=GATES['restart_min'],
  'main_restart_exact':main['restart']==main['post'],
  'full_anchors_still_bounded':main['stats']['retention_anchors']<=GATES['anchors_max'],
  'main_same_fixed_bytes':main['stats']['consolidation_bytes']==GATES['fixed_bytes'],
 }
 payload={'version':__version__,'benchmark':'ASM v0.3.0-alpha.10 Packed High-Load Consolidation','gates':GATES,'summary':{'component_2560':rows['2560']['accuracy'],'component_2800':rows['2800']['accuracy'],'component_3072':rows['3072']['accuracy'],'component_3300':rows['3300']['accuracy'],'legacy_alpha9_2560':legacy,'main_post':main['post_accuracy'],'main_restart':main['restart_accuracy'],'bytes':main['stats']['consolidation_bytes'],'cells':main['stats']['consolidation_cells']},'checks':checks,'passed':sum(checks.values()),'total':len(checks)}
 FINAL.write_text(json.dumps(payload,indent=2));STAGE.unlink(missing_ok=True);print(json.dumps(payload,indent=2));raise SystemExit(0 if all(checks.values()) else 1)

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--mode',choices=['component','main_train','main_hammer','finalize','all'],required=True);a=ap.parse_args()
 if a.mode=='all':mode_component();mode_main_train();mode_main_hammer();mode_finalize()
 else:globals()[f'mode_{a.mode}']()
