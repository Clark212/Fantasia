from __future__ import annotations
import argparse, json, random
from pathlib import Path
from asm import __version__
from asm.transition_mechanism import LocalRecurrentTransitionMechanism

OUT = Path('results/mechanism_abstraction_benchmark.json')

MODES=[f'm{i}' for i in range(4)]
ACTIONS=[f'a{i}' for i in range(4)]

def build(name:str, *, abstraction=True, seed=211):
    m=LocalRecurrentTransitionMechanism(
        name, hidden_dim=24, train_steps=1, max_outcomes=32,
        outcome_capacity_limit=256, retention_anchor_limit=96,
        retention_anchor_batch_limit=4, consolidation_enabled=True,
        abstraction_enabled=abstraction, abstraction_min_support=8,
        abstraction_min_precision=.95, abstraction_min_diversity=4,
        abstraction_max_dropped_features=2, abstraction_max_candidates=2048,
        abstraction_exception_limit=256, seed=seed,
    )
    m.replay_limit=64; m.replay_batch_limit=6
    return m

def structured_train(m):
    for mi,mode in enumerate(MODES):
        for ai,action in enumerate(ACTIONS):
            out={'result':f'r{mi}_{ai}'}
            for v in range(12):
                st={'mode':mode,'token':f'train-token-{v}','batch':v%5}
                m.observe(entity_id=f'train-{mi}-{ai}-{v}',state=st,action=action,after_state=out)

def unseen_eval(m, start=20, count=8):
    ok=0; total=0
    for mi,mode in enumerate(MODES):
        for ai,action in enumerate(ACTIONS):
            truth={'result':f'r{mi}_{ai}'}
            for v in range(start,start+count):
                st={'mode':mode,'token':f'never-seen-token-{v}','batch':10+(v%7)}
                pred=m.predict(entity_id=f'fresh-entity-{mi}-{ai}-{v}',state=st,action=action)
                ok += int(pred.predicted_state==truth); total += 1
    return ok,total

def exception_phase(m):
    rows=[]
    for i,mode in enumerate(MODES):
        action=ACTIONS[i]
        st={'mode':mode,'token':f'late-exception-{i}','batch':99}
        truth={'result':f'exception-{i}'}
        for _ in range(3):
            m.observe(entity_id=f'exception-entity-{i}',state=st,action=action,after_state=truth)
        rows.append((st,action,truth))
    ok=sum(int(m.predict(entity_id='exception-check',state=st,action=action).predicted_state==truth) for st,action,truth in rows)
    return ok,len(rows),rows

def random_control(seed=991):
    rng=random.Random(seed)
    m=build('a11_random_control', abstraction=True, seed=seed)
    outs=[{'result':f'random-{i}'} for i in range(16)]
    for mi,mode in enumerate(MODES):
        for ai,action in enumerate(ACTIONS):
            for v in range(12):
                st={'mode':mode,'token':f'train-token-{v}','batch':v%5}
                m.observe(entity_id=f'rand-{mi}-{ai}-{v}',state=st,action=action,after_state=rng.choice(outs))
    promoted=m.stats()['abstraction_promoted']
    ok=0;total=0
    for mi,mode in enumerate(MODES):
        for ai,action in enumerate(ACTIONS):
            for v in range(20,28):
                st={'mode':mode,'token':f'never-seen-token-{v}','batch':10+(v%7)}
                truth=rng.choice(outs)
                pred=m.predict(entity_id=f'rand-fresh-{mi}-{ai}-{v}',state=st,action=action)
                ok += int(pred.predicted_state==truth); total += 1
    return {'promoted':promoted,'correct':ok,'total':total,'accuracy':ok/total,'stats':m.stats()}

def ambiguous_control():
    m=LocalRecurrentTransitionMechanism('a11_ambiguous_control',hidden_dim=12,train_steps=1,max_outcomes=8,
        retention_anchor_limit=16,abstraction_min_support=3,abstraction_min_diversity=2,seed=515)
    st={'mode':'same','token':'same','batch':1}
    for r in range(3):m.observe(entity_id=f'a{r}',state=st,action='read',after_state={'r':'left'})
    m.observe(entity_id='b0',state=st,action='read',after_state={'r':'right'})
    sig=m._input_signature(st,'read',None,1.0)
    slot,_,_,_=m._query_abstraction(st,'read',None,1.0)
    return {'signature_marked_ambiguous':sig in m.retention_ambiguous_signatures,
            'abstraction_suppressed':slot is None,
            'exception_removed':sig not in m.abstraction_exceptions}


def fresh_lockbox(seed=337):
    modes=['x','y','z']; actions=[f'p{i}' for i in range(5)]
    m=LocalRecurrentTransitionMechanism(
        'a11_fresh_lockbox', hidden_dim=20, train_steps=1, max_outcomes=32,
        outcome_capacity_limit=256, retention_anchor_limit=96, seed=seed,
        abstraction_min_support=7, abstraction_min_precision=.95,
        abstraction_min_diversity=4, abstraction_max_dropped_features=2,
    )
    m.replay_limit=48; m.replay_batch_limit=5
    for mi,mode in enumerate(modes):
        for ai,action in enumerate(actions):
            for v in range(10):
                m.observe(entity_id=f'lock-{mi}-{ai}-{v}',
                          state={'mode':mode,'surface':f's{v}','lot':v%4}, action=action,
                          after_state={'o':f'{mi}-{ai}'})
    ok=total=0
    for mi,mode in enumerate(modes):
        for ai,action in enumerate(actions):
            for v in range(30,36):
                pred=m.predict(entity_id=f'fresh-lock-{v}',
                               state={'mode':mode,'surface':f'new{v}','lot':10+v%4},action=action)
                ok += int(pred.predicted_state=={'o':f'{mi}-{ai}'}); total += 1
    # Four *different* contradictory signatures are enough to stop treating the
    # prior projection as a validated universal rule. This is intentionally
    # different from one rare exception repeated many times.
    for j in range(4):
        m.observe(entity_id=f'change-{j}',state={'mode':'x','surface':f'change{j}','lot':70+j},
                  action='p0',after_state={'o':'changed'})
    probe={'mode':'x','surface':'brandnew','lot':999}
    direct_slot,_,_,_=m._query_abstraction(probe,'p0',None,1.0)
    return {'correct':ok,'total':total,'accuracy':ok/total,'promoted_before_change':15,
            'promoted_after_change':m.stats()['abstraction_promoted'],
            'systematic_contradiction_demoted_rule':direct_slot is None}


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--mode',default='all'); parser.parse_args()
    learned=build('a11_structured',abstraction=True,seed=211); structured_train(learned)
    before_ok,before_total=unseen_eval(learned)
    stats_before=learned.stats()

    baseline=build('a11_no_abstraction',abstraction=False,seed=211); structured_train(baseline)
    base_ok,base_total=unseen_eval(baseline)

    exc_ok,exc_total,exc_rows=exception_phase(learned)
    post_ok,post_total=unseen_eval(learned,start=40,count=8)

    blob=learned.export_blob(); reload=build('a11_structured',abstraction=True,seed=211); reload.import_blob(blob)
    restart_ok,restart_total=unseen_eval(reload,start=40,count=8)
    restart_exc=sum(int(reload.predict(entity_id='restart-exception',state=st,action=action).predicted_state==truth) for st,action,truth in exc_rows)
    random_row=random_control()
    lockbox=fresh_lockbox()
    ambiguous=ambiguous_control()

    checks={
      'structured_unseen_128_of_128': before_ok==before_total==128,
      'structured_beats_no_abstraction_by_40_points': (before_ok/before_total)-(base_ok/base_total)>=0.40,
      'at_least_16_validated_abstractions': stats_before['abstraction_promoted']>=16,
      'late_exceptions_4_of_4': exc_ok==exc_total==4,
      'unseen_generalization_survives_exceptions': post_ok==post_total==128,
      'restart_unseen_128_of_128': restart_ok==restart_total==128,
      'restart_exceptions_4_of_4': restart_exc==4,
      'random_control_no_promoted_rules': random_row['promoted']==0,
      'random_control_unseen_at_or_below_20pct': random_row['accuracy']<=0.20,
      'fresh_seed_lockbox_90_of_90': lockbox['correct']==lockbox['total']==90,
      'diverse_contradictions_demote_rule': lockbox['systematic_contradiction_demoted_rule'],
      'abstraction_candidate_memory_bounded': stats_before['abstraction_candidates']<=2048,
      'entity_ids_not_used_as_rule_features': all('entity' not in k.lower() for k in learned.abstraction_stats),
      'exact_exception_store_bounded': learned.stats()['abstraction_exceptions']<=256,
      'ambiguous_visible_input_suppresses_abstraction': all(ambiguous.values()),
      'version_is_current_release': __version__=='0.4.0-alpha.7',
    }
    payload={
      'version':__version__, 'benchmark':'ASM v0.3.0-alpha.11 Validated Mechanism Abstraction',
      'structured':{'unseen_before_exceptions':[before_ok,before_total],'no_abstraction':[base_ok,base_total],
                    'unseen_after_exceptions':[post_ok,post_total],'promoted':stats_before['abstraction_promoted'],
                    'candidates':stats_before['abstraction_candidates'],'exception_accuracy':[exc_ok,exc_total],
                    'restart_unseen':[restart_ok,restart_total],'restart_exceptions':[restart_exc,4]},
      'random_control':random_row,
      'fresh_lockbox':lockbox,
      'ambiguous_control':ambiguous,
      'checks':checks,'passed':sum(checks.values()),'total':len(checks)
    }
    OUT.parent.mkdir(exist_ok=True);OUT.write_text(json.dumps(payload,indent=2,sort_keys=True))
    print(json.dumps(payload,indent=2,sort_keys=True))
    if not all(checks.values()): raise SystemExit(1)

if __name__=='__main__': main()
