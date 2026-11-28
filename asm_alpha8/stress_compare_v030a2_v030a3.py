from __future__ import annotations
import importlib.util, json, sys, tempfile, time
from pathlib import Path
from asm.transition_mechanism import TransitionMechanismBank as Alpha3Bank

ROOT=Path(__file__).resolve().parent
ALPHA2=ROOT.parent/'ASM_v0.3.0-alpha.2'/'asm'/'transition_mechanism.py'
spec=importlib.util.spec_from_file_location('asm_alpha2_transition_mechanism_stress',ALPHA2)
mod=importlib.util.module_from_spec(spec); sys.modules[spec.name]=mod; spec.loader.exec_module(mod)
Alpha2Bank=mod.TransitionMechanismBank

DOOR=[({'kind':'door','mode':'closed'},'open',{'kind':'door','mode':'open'}),({'kind':'door','mode':'open'},'close',{'kind':'door','mode':'closed'}),({'kind':'door','mode':'closed'},'lock',{'kind':'door','mode':'locked'}),({'kind':'door','mode':'locked'},'unlock',{'kind':'door','mode':'closed'}),({'kind':'door','mode':'locked'},'open',{'kind':'door','mode':'locked'})]
SW=[({'kind':'switch','on':False},'toggle',{'kind':'switch','on':True}),({'kind':'switch','on':True},'toggle',{'kind':'switch','on':False}),({'kind':'switch','on':False},'set_on',{'kind':'switch','on':True}),({'kind':'switch','on':True},'set_off',{'kind':'switch','on':False})]
CONT=[({'kind':'container','open':False,'filled':False},'open',{'kind':'container','open':True,'filled':False}),({'kind':'container','open':True,'filled':False},'close',{'kind':'container','open':False,'filled':False}),({'kind':'container','open':True,'filled':False},'insert',{'kind':'container','open':True,'filled':True}),({'kind':'container','open':True,'filled':True},'remove',{'kind':'container','open':True,'filled':False}),({'kind':'container','open':False,'filled':False},'insert',{'kind':'container','open':False,'filled':False})]
HS={'kind':'history','signal':'neutral'}

def run(label,cls):
  with tempfile.TemporaryDirectory() as td:
    b=cls(Path(td)/'x.db',hidden_dim=64,train_steps=4,learning_rate=.008,seed=17,max_outcomes=32); t=time.perf_counter()
    for cases,prefix in [(DOOR,'door'),(SW,'switch'),(CONT,'container')]:
      for _ in range(4):
        for i in range(2):
          for s,a,o in cases:b.observe('generic_transition',entity_id=f'{prefix}{i}',state=s,action=a,after_state=o)
    before={}
    for name,cases in [('door',DOOR),('switch',SW),('container',CONT)]:
      before[name]=sum(b.predict('generic_transition',entity_id=f'{name}_pre',state=s,action=a)['predicted_state']==o for s,a,o in cases)
    for _ in range(25):
      for e,p,bit in [('hl','prime_left',0),('hr','prime_right',1)]:
        b.observe('generic_transition',entity_id=e,state=HS,action=p,after_state=HS)
        b.observe('generic_transition',entity_id=e,state=HS,action='read',after_state={'kind':'history','bit':bit})
    after={}
    for name,cases in [('door',DOOR),('switch',SW),('container',CONT)]:
      after[name]=sum(b.predict('generic_transition',entity_id=f'{name}_after',state=s,action=a)['predicted_state']==o for s,a,o in cases)
    hist=0; hcases=[]
    for e,p,bit in [('new_l','prime_left',0),('new_r','prime_right',1)]:
      b.reset_context('generic_transition',e); b.observe('generic_transition',entity_id=e,state=HS,action=p,after_state=HS); pred=b.predict('generic_transition',entity_id=e,state=HS,action='read')['predicted_state']; expected={'kind':'history','bit':bit}; ok=pred==expected; hist+=ok; hcases.append({'prime':p,'expected':expected,'predicted':pred,'correct':ok})
    stats=b.stats(); b.close()
    return {'label':label,'before_history':before,'after_history':after,'history_correct':hist,'history_total':2,'history_cases':hcases,'seconds':time.perf_counter()-t,'stats':stats}

payload={'benchmark':'alpha.2 vs alpha.3 stress curriculum','results':[run('alpha2',Alpha2Bank),run('alpha3',Alpha3Bank)]}
a2,a3=payload['results']
payload['checks']={
 'alpha3_static_retention_full':sum(a3['after_history'].values())==14,
 'alpha3_history_full':a3['history_correct']==2,
 'alpha3_improves_stress_over_alpha2':(sum(a3['after_history'].values())+a3['history_correct']) > (sum(a2['after_history'].values())+a2['history_correct']),
}
out=ROOT/'results/alpha2_alpha3_stress_comparison.json'; out.write_text(json.dumps(payload,indent=2),encoding='utf-8')
print(json.dumps({'alpha2':{'after':a2['after_history'],'history':a2['history_correct']},'alpha3':{'after':a3['after_history'],'history':a3['history_correct']},'checks':payload['checks']},indent=2))
print('RESULT:',out)
if not all(payload['checks'].values()): raise SystemExit(1)
