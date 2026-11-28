from __future__ import annotations

import hashlib
import json
import math
import statistics
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch
from torch import nn

from asm import __version__
from asm.transition_mechanism import TransitionMechanismBank, _RecurrentTransitionNet

ROOT = Path(__file__).resolve().parent

DOOR = [
    ({"kind":"door","mode":"closed"}, "open", {"kind":"door","mode":"open"}),
    ({"kind":"door","mode":"open"}, "close", {"kind":"door","mode":"closed"}),
    ({"kind":"door","mode":"closed"}, "lock", {"kind":"door","mode":"locked"}),
    ({"kind":"door","mode":"locked"}, "unlock", {"kind":"door","mode":"closed"}),
    ({"kind":"door","mode":"locked"}, "open", {"kind":"door","mode":"locked"}),
]
SWITCH = [
    ({"kind":"switch","on":False}, "toggle", {"kind":"switch","on":True}),
    ({"kind":"switch","on":True}, "toggle", {"kind":"switch","on":False}),
    ({"kind":"switch","on":False}, "set_on", {"kind":"switch","on":True}),
    ({"kind":"switch","on":True}, "set_off", {"kind":"switch","on":False}),
]
CONTAINER = [
    ({"kind":"container","open":False,"filled":False}, "open", {"kind":"container","open":True,"filled":False}),
    ({"kind":"container","open":True,"filled":False}, "close", {"kind":"container","open":False,"filled":False}),
    ({"kind":"container","open":True,"filled":False}, "insert", {"kind":"container","open":True,"filled":True}),
    ({"kind":"container","open":True,"filled":True}, "remove", {"kind":"container","open":True,"filled":False}),
    ({"kind":"container","open":False,"filled":False}, "insert", {"kind":"container","open":False,"filled":False}),
]
HISTORY_STATE = {"kind":"history","signal":"neutral"}


def scalar(value: Any) -> str:
    if isinstance(value, bool): return "true" if value else "false"
    if value is None: return "null"
    if isinstance(value, float): return f"{value:.6g}"
    return str(value).strip().lower()


def features(state: dict[str,Any], action: str, neighborhood=None, dt: float=1.0) -> list[str]:
    out=[f"action={str(action).strip().lower()}"]
    for k,v in sorted(state.items()): out.append(f"state:{str(k).lower()}={scalar(v)}")
    for k,v in sorted((neighborhood or {}).items()): out.append(f"neighbor:{str(k).lower()}={scalar(v)}")
    bucket="zero" if dt<=0 else "short" if dt<.5 else "unit" if dt<2 else "medium" if dt<10 else "long"
    out.append(f"dt={bucket}")
    return out


def vectorize(fs: list[str], dim=128):
    vec=torch.zeros(dim,dtype=torch.float32)
    for f in fs:
        raw=hashlib.sha256(f.encode()).digest(); idx=int.from_bytes(raw[:4],"big")%dim; sign=1.0 if raw[4]&1 else -1.0; vec[idx]+=sign
    n=torch.linalg.vector_norm(vec)
    if float(n)>0: vec/=n
    return vec.unsqueeze(0)


def canon(state): return json.dumps(state,sort_keys=True,separators=(",",":"))
def input_sig(state,action,neighborhood=None,dt=1.0): return "|".join(features(state,action,neighborhood,dt))
def stratum(state,neighborhood=None):
    return "state["+",".join(sorted(state))+ "]::neighbor["+",".join(sorted((neighborhood or {})))+"]"

class _FF(nn.Module):
    def __init__(self, input_dim=128, hidden=64, max_outcomes=32):
        super().__init__(); self.net=nn.Sequential(nn.Linear(input_dim,hidden),nn.Tanh(),nn.Linear(hidden,max_outcomes))
    def forward(self,x): return self.net(x)

class FeedForwardBaseline:
    def __init__(self, seed=17, hidden=64, lr=.008, train_steps=4, replay_limit=256, batch_limit=14):
        torch.manual_seed(seed); self.net=_FF(128,hidden,32); self.opt=torch.optim.Adam(self.net.parameters(),lr=lr)
        self.train_steps=train_steps; self.replay=[]; self.replay_limit=replay_limit; self.batch_limit=batch_limit
        self.o2s={}; self.s2o={}
    def _slot(self,out):
        c=canon(out)
        if c not in self.o2s: self.o2s[c]=len(self.o2s); self.s2o[self.o2s[c]]=json.loads(c)
        return self.o2s[c]
    def _trim(self):
        while len(self.replay)>self.replay_limit:
            counts={}
            for x in self.replay: counts[x['stratum']]=counts.get(x['stratum'],0)+1
            big=max(counts,key=lambda k:(counts[k],k)); idx=next(i for i,x in enumerate(self.replay) if x['stratum']==big); self.replay.pop(idx)
    def _batch(self,current):
        by={}
        for x in self.replay[:-1]: by.setdefault(x['stratum'],[]).append(x)
        chosen=[by[k][-1] for k in sorted(by)][:self.batch_limit-1]
        pool=self.replay[:-1]; stride=max(1,len(pool)//max(1,self.batch_limit-1))
        for x in pool[::stride]:
            if len(chosen)>=self.batch_limit-1: break
            if x not in chosen: chosen.append(x)
        return chosen+[current]
    def observe(self,entity,state,action,after):
        slot=self._slot(after); item={'state':dict(state),'action':action,'slot':slot,'stratum':stratum(state)}; self.replay.append(item); self._trim(); batch=self._batch(item)
        self.net.train()
        for _ in range(self.train_steps):
            self.opt.zero_grad(); losses=[]
            for x in batch:
                logits=self.net(vectorize(features(x['state'],x['action']))); t=torch.tensor([x['slot']]); losses.append(torch.nn.functional.cross_entropy(logits,t))
            loss=torch.stack(losses).mean(); loss.backward(); self.opt.step()
    def predict(self,entity,state,action):
        if not self.o2s:return None
        with torch.no_grad():
            logits=self.net(vectorize(features(state,action))); p=torch.softmax(logits[0,:len(self.o2s)],0); slot=int(torch.argmax(p))
        return dict(self.s2o[slot])
    def reset(self,entity): pass
    def params(self): return sum(p.numel() for p in self.net.parameters())

class DetachedGRUBaseline(FeedForwardBaseline):
    def __init__(self,seed=17,hidden=64,lr=.008,train_steps=4,replay_limit=256,batch_limit=14):
        torch.manual_seed(seed); self.net=_RecurrentTransitionNet(128,hidden,32); self.opt=torch.optim.Adam(self.net.parameters(),lr=lr)
        self.hidden_dim=hidden; self.train_steps=train_steps; self.replay=[]; self.replay_limit=replay_limit; self.batch_limit=batch_limit; self.o2s={}; self.s2o={}; self.hidden={}
    def _h(self,e): return self.hidden.get(e,torch.zeros((1,self.hidden_dim))).detach().clone()
    def observe(self,entity,state,action,after):
        slot=self._slot(after); sig=input_sig(state,action); item={'state':dict(state),'action':action,'slot':slot,'stratum':stratum(state),'sig':sig}; self.replay.append(item); self._trim(); batch=self._batch(item)
        initial=self._h(entity); self.net.train()
        # identify visible ambiguity in replay
        amb={}
        for x in self.replay: amb.setdefault(x.get('sig') or input_sig(x['state'],x['action']),set()).add(x['slot'])
        for _ in range(self.train_steps):
            self.opt.zero_grad(); losses=[]; zero=torch.zeros((1,self.hidden_dim))
            for x in batch:
                xs=x.get('sig') or input_sig(x['state'],x['action'])
                if len(amb.get(xs,set()))>1: continue
                logits,_=self.net(vectorize(features(x['state'],x['action'])),zero); losses.append(torch.nn.functional.cross_entropy(logits,torch.tensor([x['slot']])))
            logits,_=self.net(vectorize(features(state,action)),initial)
            losses.append((1.0 if len(amb.get(sig,set()))>1 else .25)*torch.nn.functional.cross_entropy(logits,torch.tensor([slot])))
            loss=torch.stack(losses).mean(); loss.backward(); self.opt.step()
        with torch.no_grad(): _,h=self.net(vectorize(features(state,action)),initial)
        self.hidden[entity]=h.detach()
    def predict(self,entity,state,action):
        if not self.o2s:return None
        with torch.no_grad():
            logits,_=self.net(vectorize(features(state,action)),self._h(entity)); p=torch.softmax(logits[0,:len(self.o2s)],0); slot=int(torch.argmax(p))
        return dict(self.s2o[slot])
    def reset(self,entity): self.hidden.pop(entity,None)
    def params(self): return sum(p.numel() for p in self.net.parameters())

class ASMLearner:
    def __init__(self, path):
        self.bank=TransitionMechanismBank(path,hidden_dim=64,train_steps=4,learning_rate=.008,seed=17)
    def observe(self,entity,state,action,after): self.bank.observe('generic_transition',entity_id=entity,state=state,action=action,after_state=after)
    def predict(self,entity,state,action): return self.bank.predict('generic_transition',entity_id=entity,state=state,action=action)['predicted_state']
    def reset(self,entity): self.bank.reset_context('generic_transition',entity)
    def params(self):
        m=self.bank._get('generic_transition',create=False); return sum(p.numel() for p in m.net.parameters()) if m else 0
    def close(self): self.bank.close()


def train_static(model,cases,prefix,epochs=4):
    for _ in range(epochs):
        for i in range(2):
            for st,a,out in cases: model.observe(f'{prefix}_{i}',st,a,out)

def eval_static(model,cases,entity):
    details=[]
    for st,a,out in cases:
        pred=model.predict(entity,st,a); details.append({'state':st,'action':a,'expected':out,'predicted':pred,'correct':pred==out})
    return {'correct':sum(x['correct'] for x in details),'total':len(details),'cases':details}

def train_history(model,epochs=25):
    for _ in range(epochs):
        for entity,prime,bit in [('hl','prime_left',0),('hr','prime_right',1),('hl2','prime_left',0),('hr2','prime_right',1)]:
            model.observe(entity,HISTORY_STATE,prime,HISTORY_STATE)
            model.observe(entity,HISTORY_STATE,'read',{'kind':'history','bit':bit})

def eval_history(model):
    details=[]
    for entity,prime,bit in [('hnew_l','prime_left',0),('hnew_r','prime_right',1)]:
        model.reset(entity); model.observe(entity,HISTORY_STATE,prime,HISTORY_STATE); pred=model.predict(entity,HISTORY_STATE,'read'); expected={'kind':'history','bit':bit}; details.append({'prime':prime,'expected':expected,'predicted':pred,'correct':pred==expected})
    return {'correct':sum(x['correct'] for x in details),'total':len(details),'cases':details}

def run_model(name,model):
    started=time.perf_counter(); checkpoints=[]
    train_static(model,DOOR,'door',4); checkpoints.append({'after':'door','door':eval_static(model,DOOR,'door_new')})
    train_static(model,SWITCH,'switch',4); checkpoints.append({'after':'switch','door':eval_static(model,DOOR,'door_new2'),'switch':eval_static(model,SWITCH,'switch_new')})
    train_static(model,CONTAINER,'container',4); checkpoints.append({'after':'container','door':eval_static(model,DOOR,'door_new3'),'switch':eval_static(model,SWITCH,'switch_new2'),'container':eval_static(model,CONTAINER,'container_new')})
    before_history={'door':eval_static(model,DOOR,'door_pre_hist'),'switch':eval_static(model,SWITCH,'switch_pre_hist'),'container':eval_static(model,CONTAINER,'container_pre_hist')}
    train_history(model,25)
    final={'door':eval_static(model,DOOR,'door_final'),'switch':eval_static(model,SWITCH,'switch_final'),'container':eval_static(model,CONTAINER,'container_final'),'history':eval_history(model)}
    static_correct=sum(final[k]['correct'] for k in ('door','switch','container')); static_total=sum(final[k]['total'] for k in ('door','switch','container'))
    return {'name':name,'parameters':model.params(),'seconds':time.perf_counter()-started,'checkpoints':checkpoints,'before_history':before_history,'final':final,'static_retention':{'correct':static_correct,'total':static_total},'all_final':{'correct':static_correct+final['history']['correct'],'total':static_total+final['history']['total']}}

results=[]
ff=FeedForwardBaseline(); results.append(run_model('feed_forward_balanced_replay',ff))
gru=DetachedGRUBaseline(); results.append(run_model('detached_gru_balanced_replay',gru))
with tempfile.TemporaryDirectory() as td:
    asm=ASMLearner(Path(td)/'asm.db')
    try: results.append(run_model('asm_alpha3',asm))
    finally: asm.close()

asm_result=next(x for x in results if x['name']=='asm_alpha3')
checks=[]
def check(name,ok,details=None): checks.append({'name':name,'pass':bool(ok),'details':details})
check('one_shared_mechanism_retains_all_three_static_domains',asm_result['static_retention']['correct']==asm_result['static_retention']['total'],asm_result['final'])
check('unseen_history_branches_both_correct',asm_result['final']['history']['correct']==2,asm_result['final']['history'])
check('final_combined_accuracy_100pct',asm_result['all_final']['correct']==asm_result['all_final']['total'],asm_result['all_final'])
# At least one simpler ablation should reveal why alpha.3 additions exist; no claim this is a standardized baseline.
check('ablation_distinguishes_alpha3',any(x['all_final']['correct']<x['all_final']['total'] for x in results if x['name']!='asm_alpha3'),{x['name']:x['all_final'] for x in results})

payload={
 'benchmark':'ASM v0.3.0-alpha.3 Multi-Domain Mechanism Learning',
 'version':__version__,
 'domains':['doors','switches','containers','history-dependent machine'],
 'same_experience_stream':True,
 'results':results,
 'checks':checks,
 'summary':{'passed':sum(int(x['pass']) for x in checks),'total':len(checks)},
 'notes':[
   'This is a controlled architecture benchmark, not a standardized intelligence benchmark.',
   'All three learners receive the same ordered transition stream and hashed structured inputs.',
   'The feed-forward and detached-GRU baselines are local exploratory ablations, not optimized literature baselines.',
   'Alpha.3 uses balanced structural replay and bounded truncated recurrent credit assignment.',
   'No planner, causal inference, representation discovery, or program compilation is tested here.',
 ]
}
payload['summary']['accuracy_pct']=100*payload['summary']['passed']/max(1,payload['summary']['total'])
out=ROOT/'results/multidomain_mechanism_benchmark.json'; out.write_text(json.dumps(payload,indent=2),encoding='utf-8')
print(json.dumps({'version':__version__,'summary':payload['summary'],'model_results':[{k:r[k] for k in ('name','parameters','seconds','static_retention','all_final')} | {'history':r['final']['history']['correct']} for r in results]},indent=2))
print('RESULT:',out)
if payload['summary']['passed']!=payload['summary']['total']: raise SystemExit(1)
