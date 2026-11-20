from __future__ import annotations
import json, math, random, time, tracemalloc
from pathlib import Path
from asm.planning import DiscreteBeliefState, BeliefStateInternalPlanner, StateGoal
from benchmark_v040a5_mega_stress import categorical_plan, exact_categorical_oracle, assumed_plan, actual_policy_accuracy

OUT=Path('results/planning_v040a51_torture.json')

def reversible(acc,n):
    b=DiscreteBeliefState.from_mapping({'A':.5,'B':.5})
    a={'A':acc,'B':1-acc}; bb={'A':1-acc,'B':acc}
    for _ in range(n): b=b.update(a)
    mid=b.as_dict(); mid_logs=b.as_log_dict().copy()
    for _ in range(n): b=b.update(bb)
    return {'updates':2*n,'mid_public':mid,'mid_min_log':min(mid_logs.values()),'final':b.as_dict(),'err':abs(b.as_dict()['A']-.5),'entropy':b.entropy_bits()}

def repeated_reversal(cycles=100, block=200, acc=.99):
    b=DiscreteBeliefState.from_mapping({'A':.5,'B':.5})
    A={'A':acc,'B':1-acc}; B={'A':1-acc,'B':acc}
    max_abs_log=0.0
    for c in range(cycles):
        for _ in range(block): b=b.update(A if c%2==0 else B)
        max_abs_log=max(max_abs_log,max(abs(v) for v in b.as_log_dict().values()))
    return {'cycles':cycles,'block':block,'updates':cycles*block,'map':b.most_likely()[0],'posterior':b.as_dict(),'max_abs_log':max_abs_log,'entropy':b.entropy_bits()}

def machine_precision_probe():
    tiny=max(5e-324, math.nextafter(0.0,1.0))
    b=DiscreteBeliefState.from_mapping({'A':.5,'B':.5})
    likes={'A':1.0-tiny,'B':tiny}
    b=b.update(likes)
    return {'tiny':tiny,'posterior':b.as_dict(),'logs':b.as_log_dict(),'finite_logs':all(math.isfinite(v) for v in b.as_log_dict().values()),'finite_entropy':math.isfinite(b.entropy_bits())}

def hostile_32way(seed=9,steps=10000):
    r=random.Random(seed); hyps=[f'H{i}' for i in range(32)]
    raw=[10**r.uniform(-300,0) for _ in hyps]; z=sum(raw)
    b=DiscreteBeliefState.from_mapping({h:v/z for h,v in zip(hyps,raw)})
    for _ in range(steps):
        winner=r.randrange(32); acc=r.uniform(.50,.999999); spill=(1-acc)/31
        likes={h:(acc if i==winner else spill) for i,h in enumerate(hyps)}
        b=b.update(likes)
    probs=b.as_dict(); logs=b.as_log_dict()
    return {'hypotheses':32,'steps':steps,'sum_public':sum(probs.values()),'finite_logs':all(math.isfinite(v) for v in logs.values()),'finite_entropy':math.isfinite(b.entropy_bits()),'entropy':b.entropy_bits(),'min_log':min(logs.values()),'max_log':max(logs.values())}

def calibration_binary(assumed,true,m, correlated=False):
    res=assumed_plan(assumed,m); actual=actual_policy_accuracy(res,true,m,correlated)
    claimed=res['best']['goal_probability']
    return {'assumed':assumed,'true':true,'clues':m,'claimed':claimed,'actual':actual,'confidence_gap':claimed-actual,'status':res['status'],'expansions':res['expansions']}

def budget_pressure():
    oracle=exact_categorical_oracle(8,.72,3); rows=[]
    for cap in (16,32,64,128,256,512,1024,2048,4096):
        r=categorical_plan(8,.72,3,max_exp=cap,top_k=8,max_hyp=32)
        rows.append({'budget':cap,'status':r['status'],'search_complete':r.get('search_complete'),'budget_exhausted':r.get('search_budget_exhausted'),'goal':r['best']['goal_probability'],'error_vs_oracle':abs(r['best']['goal_probability']-oracle),'expansions':r['expansions'],'nodes':r['policy_nodes'],'memo_hits':r['belief_merge_hits']})
    return {'oracle':oracle,'rows':rows}

def scale_probe():
    rows=[]
    for n,m in [(2,5),(3,4),(4,4),(8,3),(16,2),(32,1)]:
        t=time.perf_counter(); r=categorical_plan(n,.72,m,max_exp=50000,top_k=n,max_hyp=32); elapsed=time.perf_counter()-t; peak=None
        oracle=exact_categorical_oracle(n,.72,m)
        rows.append({'hypotheses':n,'clues':m,'goal':r['best']['goal_probability'],'oracle':oracle,'error':abs(r['best']['goal_probability']-oracle),'runtime_s':elapsed,'peak_bytes':peak,'expansions':r['expansions'],'memo_hits':r['belief_merge_hits'],'nodes':r['policy_nodes'],'status':r['status'],'cap_reached':r.get('hypothesis_cap_reached')})
    return rows

def memo_boundary(seed=2026,cases=20000):
    r=random.Random(seed); collisions=0; near_half=[]
    seen={}
    for _ in range(cases):
        p=.5+r.uniform(-2e-11,2e-11); b=DiscreteBeliefState.from_mapping({'A':p,'B':1-p}); k=b.key(12)
        action='A' if p>=.5 else 'B'
        if k in seen and seen[k][0]!=action: collisions+=1
        else: seen[k]=(action,p)
        if len(near_half)<5: near_half.append({'p':p,'key':k,'action':action})
    return {'cases':cases,'decision_boundary_key_collisions':collisions,'sample':near_half}

def actual_policy_accuracy_variable(result, true_accs):
    from itertools import product
    graph=result['policy_graph']; root=result['root_node']; m=len(true_accs); total=0.0
    for hidden in 'AB':
        for seq in product('AB', repeat=m):
            pseq=1.0
            for obs,a in zip(seq,true_accs): pseq*=a if obs==hidden else 1-a
            node=root; idx=0
            while True:
                nd=graph[node]; act=nd.get('action')
                if act=='sense':
                    if idx>=m: break
                    obs=seq[idx]; idx+=1
                    matches=[br for br in nd.get('branches',[]) if br.get('observation')==obs]
                    if not matches: break
                    node=matches[0]['next_node']; continue
                if act in ('chooseA','chooseB'):
                    total += .5*pseq*(1.0 if act[-1]==hidden else 0.0)
                break
    return total

class SensorChoiceModel:
    def __call__(self, mechanism_type, *, entity_id,state,action,neighborhood=None,dt=1.0,simulation_context=None,top_k=8,empirical_min_support=None):
        if state.get('loc')!='start': outs=[]
        elif action in ('sense70','sense90'):
            a=.7 if action=='sense70' else .9
            outs=[{'predicted_state':{'loc':'start'},'observation':'A','hypothesis_likelihoods':{'A':a,'B':1-a}}, {'predicted_state':{'loc':'start'},'observation':'B','hypothesis_likelihoods':{'A':1-a,'B':a}}]
        elif action in ('chooseA','chooseB'):
            c=action[-1]; outs=[{'predicted_state':{'loc':'goal'},'observation':'g','hypothesis_likelihoods':{'A':1.0 if c=='A' else 0.0,'B':1.0 if c=='B' else 0.0}}, {'predicted_state':{'loc':'hazard'},'observation':'h','hypothesis_likelihoods':{'A':0.0 if c=='A' else 1.0,'B':0.0 if c=='B' else 1.0}}]
        else: outs=[]
        return {'outcomes':outs[:top_k],'unknown_probability':0 if outs else 1,'calibrated':True,'_simulation_context':simulation_context,'_simulation_context_key':''}

def sensor_choice(cost90):
    p=BeliefStateInternalPlanner(SensorChoiceModel(),max_horizon=2,max_expansions=256,top_k_outcomes=8,risk_aversion=0,unknown_risk_weight=0,cost_weight=1.0,proximity_weight=0,step_penalty=0,min_goal_probability=0,max_hazard_probability=1,max_unknown_probability=1)
    r=p.plan('sensor',entity_id='x',initial_state={'loc':'start'},actions=('sense70','sense90','chooseA','chooseB'),goal=StateGoal({'loc':'goal'},{'loc':'hazard'}),initial_belief={'A':.5,'B':.5},action_costs={'sense70':0.0,'sense90':cost90},horizon=2)
    return {'cost90':cost90,'root_action':r['policy_graph'][r['root_node']]['action'],'goal':r['best']['goal_probability'],'expected_cost':r['best']['expected_cost'],'status':r['status']}

def main():
    t=time.time(); results={}; checks={}
    nums=[]
    for n in (10,100,1000,10000,100000): nums.append(reversible(.99,n))
    # Prior extreme suite already executes 1,000,000 updates; this added feed reaches 200k reversible updates here.
    nums.append(reversible(.99,100000))
    results['reversible_update_scales']=nums
    checks['10_to_200k_reversible_updates_without_nan']=all(x['err']<1e-8 and math.isfinite(x['entropy']) for x in nums)
    rr=repeated_reversal(); results['many_reversals']=rr; checks['many_reversals_finite']=math.isfinite(rr['entropy']) and math.isfinite(rr['max_abs_log'])
    mp=machine_precision_probe(); results['machine_precision']=mp; checks['machine_precision_likelihood_finite']=mp['finite_logs'] and mp['finite_entropy']
    h32=hostile_32way(); results['hostile_32way']=h32; checks['32way_10k_finite']=h32['finite_logs'] and h32['finite_entropy']
    miss=[calibration_binary(.9,.7,5),calibration_binary(.7,.9,5),calibration_binary(.7,.7,5,True),calibration_binary(.8,.2,3)]
    variable=[]
    for name,assumed,true_seq in [('drift',.8,[.9,.8,.7,.6,.55]),('adversarial_flip',.9,[.9,.9,.1,.1,.1]),('broken_after_two',.9,[.9,.9,.5,.5,.5]),('world_change_stale',.8,[.8,.8,.2,.2,.2])]:
        rr=assumed_plan(assumed,len(true_seq)); actual=actual_policy_accuracy_variable(rr,true_seq); claimed=rr['best']['goal_probability']
        variable.append({'case':name,'assumed':assumed,'true_sequence':true_seq,'claimed':claimed,'actual':actual,'confidence_gap':claimed-actual})
    results['model_misspecification']={'fixed_and_correlated':miss,'drift_and_breakage':variable,'automatic_mismatch_detection':False}
    checks['misspecification_remains_visible']=miss[0]['confidence_gap']>0.05 and abs(miss[1]['confidence_gap'])>0.01 and miss[2]['confidence_gap']>0.05 and miss[3]['confidence_gap']>0.5 and any(abs(x['confidence_gap'])>0.1 for x in variable)
    choices=[sensor_choice(0.0),sensor_choice(.25)]
    results['sensor_choice_and_cost']=choices
    checks['sensor_reliability_vs_cost_changes_choice']=choices[0]['root_action']=='sense90' and choices[1]['root_action']=='sense70'
    bp=budget_pressure(); results['budget_pressure']=bp
    checks['budget_status_is_explicit']=all((not row['budget_exhausted']) or row['status']=='budget_exhausted_partial_policy' for row in bp['rows'])
    checks['sufficient_budget_recovers_oracle']=bp['rows'][-1]['error_vs_oracle']<1e-9
    sc=scale_probe(); results['hidden_space_scale']=sc; checks['2_to_32_exact_small_horizons']=max(x['error'] for x in sc)<1e-9
    memo=memo_boundary(); results['memo_decision_boundary']=memo; checks['memo_quantization_no_action_collision_20k']=memo['decision_boundary_key_collisions']==0
    payload={'benchmark':'ASM v0.4.0-alpha.5.1 additional torture feed','runtime_seconds':time.time()-t,'results':results,'checks':checks,'passed':sum(bool(v) for v in checks.values()),'total':len(checks)}
    OUT.parent.mkdir(exist_ok=True); OUT.write_text(json.dumps(payload,indent=2,sort_keys=True),encoding='utf-8'); print(json.dumps(payload,indent=2,sort_keys=True))
    if not all(checks.values()): raise SystemExit(1)
if __name__=='__main__': main()
