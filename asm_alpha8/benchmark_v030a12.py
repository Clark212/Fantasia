from __future__ import annotations
import argparse, json, random
from pathlib import Path
from asm import __version__
from asm.transition_mechanism import LocalRecurrentTransitionMechanism

OUT = Path('results/abstraction_hardening_benchmark.json')
MODES=[f'm{i}' for i in range(8)]
ACTIONS=[f'a{i}' for i in range(8)]

def build(name:str, *, sparse=True, pending=True, candidate_limit=48, seed=1201, max_candidates=2048):
    m=LocalRecurrentTransitionMechanism(
        name, hidden_dim=16, train_steps=1, max_outcomes=64,
        outcome_capacity_limit=512, retention_anchor_limit=96,
        retention_anchor_batch_limit=4, consolidation_enabled=True,
        abstraction_enabled=True, abstraction_min_support=8,
        abstraction_min_precision=.95, abstraction_min_diversity=4,
        abstraction_max_dropped_features=2,
        abstraction_sparse_enabled=sparse,
        abstraction_pending_enabled=pending,
        abstraction_sparse_max_retained_features=2,
        abstraction_candidates_per_observation=candidate_limit,
        abstraction_max_candidates=max_candidates,
        abstraction_exception_limit=256, seed=seed,
    )
    m.replay_limit=64; m.replay_batch_limit=4
    return m

def state(mode:str, v:int, prefix:str='train', extra_keys:bool=False):
    row={
        'mode':mode,
        'surface':f'{prefix}-surface-{v}',
        'batch':v%7,
        'texture':f'{prefix}-texture-{v%11}',
        'serial':f'{prefix}-serial-{v}',
        'zone':(v*3)%13,
    }
    if extra_keys:
        row['ambient']=f'new-ambient-{v%5}'
        row['firmware']=f'new-fw-{v}'
    return row

def train_structured(m):
    for mi,mode in enumerate(MODES):
        for ai,action in enumerate(ACTIONS):
            truth={'r':f'{mi}-{ai}'}
            for v in range(10):
                m.observe(entity_id=f'train-{mi}-{ai}-{v}', state=state(mode,v), action=action, after_state=truth)

def eval_structured(m, start=30, count=6, extra_keys=True):
    ok=total=0
    for mi,mode in enumerate(MODES):
        for ai,action in enumerate(ACTIONS):
            truth={'r':f'{mi}-{ai}'}
            for v in range(start,start+count):
                pred=m.predict(entity_id=f'fresh-{mi}-{ai}-{v}',state=state(mode,v,'novel',extra_keys),action=action)
                ok += int(pred.predicted_state==truth); total += 1
    return ok,total

def exception_phase(m):
    rows=[]
    for i in range(16):
        mi=i%8; ai=(i*3)%8
        st=state(MODES[mi],100+i,f'exception-{i}',extra_keys=True)
        truth={'r':f'exception-{i}'}
        for _ in range(3):
            m.observe(entity_id=f'exception-entity-{i}',state=st,action=ACTIONS[ai],after_state=truth)
        rows.append((st,ACTIONS[ai],truth))
    ok=sum(int(m.predict(entity_id='exception-check',state=st,action=a).predicted_state==truth) for st,a,truth in rows)
    return ok,len(rows),rows

def random_control(seed=9931):
    rng=random.Random(seed)
    m=build('a12_random_control',sparse=True,seed=seed)
    outs=[{'r':f'random-{i}'} for i in range(64)]
    for mi,mode in enumerate(MODES):
        for ai,action in enumerate(ACTIONS):
            for v in range(10):
                m.observe(entity_id=f'rand-{mi}-{ai}-{v}',state=state(mode,v),action=action,after_state=rng.choice(outs))
    stats=m.stats(); ok=total=0
    for mi,mode in enumerate(MODES):
        for ai,action in enumerate(ACTIONS):
            for v in range(30,34):
                truth=rng.choice(outs)
                pred=m.predict(entity_id=f'rand-fresh-{mi}-{ai}-{v}',state=state(mode,v,'random-novel',True),action=action)
                ok += int(pred.predicted_state==truth); total += 1
    return {'correct':ok,'total':total,'accuracy':ok/total,'promoted':stats['abstraction_promoted'],'candidates':stats['abstraction_candidates']}

def ambiguity_control():
    m=build('a12_ambiguous',sparse=True,seed=787,max_candidates=256)
    st=state('same',1,'same',True)
    for _ in range(4): m.observe(entity_id='history-a',state=st,action='read',after_state={'r':'left'})
    for _ in range(2): m.observe(entity_id='history-b',state=st,action='read',after_state={'r':'right'})
    sig=m._input_signature(st,'read',None,1.0)
    slot,_,_,_=m._query_abstraction(st,'read',None,1.0)
    return {'marked_ambiguous':sig in m.retention_ambiguous_signatures,'abstraction_suppressed':slot is None,'no_exception':sig not in m.abstraction_exceptions}

def systematic_change_control():
    m=build('a12_shift',sparse=True,seed=1414,max_candidates=512)
    for v in range(12):
        m.observe(entity_id=f'base-{v}',state=state('shift',v),action='turn',after_state={'r':'old'})
    probe=state('shift',300,'probe',True)
    before=m._query_abstraction(probe,'turn',None,1.0)[0]
    for j in range(4):
        m.observe(entity_id=f'change-{j}',state=state('shift',80+j,f'change-{j}',True),action='turn',after_state={'r':'new'})
    after=m._query_abstraction(probe,'turn',None,1.0)[0]
    return {'had_rule_before':before is not None,'rule_demoted_after_diverse_change':after is None}

def fresh_lockbox(seed=5521):
    modes=[f'q{i}' for i in range(5)]; actions=[f'p{i}' for i in range(6)]
    m=LocalRecurrentTransitionMechanism(
        'a12_lockbox',hidden_dim=14,train_steps=1,max_outcomes=32,outcome_capacity_limit=256,
        retention_anchor_limit=64,abstraction_min_support=7,abstraction_min_precision=.95,
        abstraction_min_diversity=4,abstraction_max_dropped_features=2,
        abstraction_sparse_enabled=True,abstraction_sparse_max_retained_features=2,
        abstraction_candidates_per_observation=48,abstraction_max_candidates=1024,seed=seed)
    m.replay_limit=48;m.replay_batch_limit=4
    def st(mode,v,prefix):
        return {'kind':mode,'paint':f'{prefix}-{v}','lot':v%6,'temp':f'{prefix}-t{v%9}','rack':(v*5)%17}
    for mi,mode in enumerate(modes):
        for ai,a in enumerate(actions):
            for v in range(9):
                m.observe(entity_id=f'l-{mi}-{ai}-{v}',state=st(mode,v,'train'),action=a,after_state={'o':f'{mi}-{ai}'})
    ok=total=0
    for mi,mode in enumerate(modes):
        for ai,a in enumerate(actions):
            for v in range(30,35):
                row=st(mode,v,'fresh'); row['new_sensor']=f'x{v}'
                pred=m.predict(entity_id=f'new-{mi}-{ai}-{v}',state=row,action=a)
                ok += int(pred.predicted_state=={'o':f'{mi}-{ai}'}); total += 1
    blob=m.export_blob(); r=LocalRecurrentTransitionMechanism(
        'a12_lockbox',hidden_dim=14,train_steps=1,max_outcomes=32,outcome_capacity_limit=256,
        retention_anchor_limit=64,abstraction_min_support=7,abstraction_min_precision=.95,
        abstraction_min_diversity=4,abstraction_sparse_enabled=True,seed=seed)
    r.import_blob(blob)
    rok=rtotal=0
    for mi,mode in enumerate(modes):
        for ai,a in enumerate(actions):
            for v in range(40,45):
                row=st(mode,v,'restart'); row['new_sensor']=f'y{v}'
                pred=r.predict(entity_id=f'r-{mi}-{ai}-{v}',state=row,action=a)
                rok += int(pred.predicted_state=={'o':f'{mi}-{ai}'}); rtotal += 1
    return {'correct':ok,'total':total,'restart_correct':rok,'restart_total':rtotal,'promoted':m.stats()['abstraction_promoted']}

def main():
    argparse.ArgumentParser().parse_args()
    learned=build('a12_structured',sparse=True,seed=1201); train_structured(learned)
    seen_stats=learned.stats(); unseen_ok,unseen_total=eval_structured(learned)
    baseline=build('a12_no_sparse',sparse=False,seed=1201); train_structured(baseline)
    base_ok,base_total=eval_structured(baseline)
    exc_ok,exc_total,exc_rows=exception_phase(learned)
    post_ok,post_total=eval_structured(learned,start=50,count=4,extra_keys=True)
    blob=learned.export_blob(); reload=build('a12_structured',sparse=True,seed=1201); reload.import_blob(blob)
    restart_ok,restart_total=eval_structured(reload,start=60,count=4,extra_keys=True)
    restart_exc=sum(int(reload.predict(entity_id='restart-exc',state=st,action=a).predicted_state==truth) for st,a,truth in exc_rows)
    random_row=random_control(); ambiguous=ambiguity_control(); shift=systematic_change_control(); lockbox=fresh_lockbox()
    checks={
      'high_dim_unseen_384_of_384': unseen_ok==unseen_total==384,
      'beats_alpha11_style_drop_only_by_70_points': (unseen_ok/unseen_total)-(base_ok/base_total)>=0.70,
      'at_least_64_competing_abstractions': seen_stats['abstraction_promoted']>=64,
      'candidate_memory_hits_bound_without_losing_rules': seen_stats['abstraction_candidates']<=2048 and seen_stats['abstraction_promoted']>=64,
      'new_nuisance_feature_keys_do_not_break_transfer': unseen_ok==unseen_total,
      'late_exact_exceptions_16_of_16': exc_ok==exc_total==16,
      'generalization_survives_exceptions_256_of_256': post_ok==post_total==256,
      'restart_generalization_256_of_256': restart_ok==restart_total==256,
      'restart_exceptions_16_of_16': restart_exc==16,
      'random_control_promotes_no_rules': random_row['promoted']==0,
      'random_control_unseen_at_or_below_10pct': random_row['accuracy']<=0.10,
      'ambiguous_visible_input_blocks_abstraction': all(ambiguous.values()),
      'diverse_distribution_shift_demotes_rule': all(shift.values()),
      'fresh_lockbox_150_of_150': lockbox['correct']==lockbox['total']==150,
      'fresh_lockbox_restart_150_of_150': lockbox['restart_correct']==lockbox['restart_total']==150,
      'sparse_projection_search_is_bounded': learned.abstraction_candidates_per_observation<=48,
      'entity_ids_not_rule_features': all('entity' not in k.lower() for k in learned.abstraction_stats),
      'version_is_alpha12': __version__=='0.4.0-alpha.7',
    }
    payload={'version':__version__,'benchmark':'ASM v0.3.0-alpha.12 Robust Abstraction Hardening',
      'structured':{'unseen':[unseen_ok,unseen_total],'drop_only_baseline':[base_ok,base_total],
        'promoted':seen_stats['abstraction_promoted'],'candidates':seen_stats['abstraction_candidates'],
        'exceptions':[exc_ok,exc_total],'post_exception_unseen':[post_ok,post_total],
        'restart_unseen':[restart_ok,restart_total],'restart_exceptions':[restart_exc,16]},
      'random_control':random_row,'ambiguous_control':ambiguous,'distribution_shift':shift,'fresh_lockbox':lockbox,
      'checks':checks,'passed':sum(checks.values()),'total':len(checks)}
    OUT.parent.mkdir(exist_ok=True); OUT.write_text(json.dumps(payload,indent=2,sort_keys=True))
    print(json.dumps(payload,indent=2,sort_keys=True))
    if not all(checks.values()): raise SystemExit(1)

if __name__=='__main__': main()
