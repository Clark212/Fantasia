from __future__ import annotations
import json, math, random, time
from itertools import product
from pathlib import Path
from asm.planning import BeliefStateInternalPlanner, DiscreteBeliefState, StateGoal

OUT=Path('results/planning_v040a5_mega_stress.json')

def norm(d):
    z=sum(d.values()); return {k:v/z for k,v in d.items()}

def update_oracle(prior, likes):
    return norm({h:prior[h]*likes.get(h,0.0) for h in prior})

def entropy(d):
    return -sum(p*math.log2(p) for p in d.values() if p>0)

class CategoricalModel:
    def __init__(self,n,accuracy, *, top_outputs=None):
        self.n=n; self.a=float(accuracy); self.hyps=[f'H{i}' for i in range(n)]; self.top_outputs=top_outputs
    def likes(self,obs):
        spill=(1-self.a)/(self.n-1) if self.n>1 else 0
        return {h:(self.a if h==obs else spill) for h in self.hyps}
    def __call__(self, mechanism_type, *, entity_id, state, action, neighborhood=None,dt=1.0,simulation_context=None,top_k=64,empirical_min_support=None):
        if state.get('loc')!='start': outs=[]; residual=0.0
        elif action=='sense':
            names=self.hyps[:min(top_k, self.top_outputs or self.n)]
            outs=[{'predicted_state':{'loc':'start'},'observation':o,'probability':1/self.n,'hypothesis_likelihoods':self.likes(o)} for o in names]
            # For symmetric uniform-prior feed this is exact omitted observation mass at root; deeper planner recomputes residual via out_mass too.
            residual=max(0.0,1-len(names)/self.n)
        elif action.startswith('choose'):
            chosen=action[6:]
            outs=[
                {'predicted_state':{'loc':'goal'},'observation':'goal','probability':1/self.n,'hypothesis_likelihoods':{h:(1.0 if h==chosen else 0.0) for h in self.hyps}},
                {'predicted_state':{'loc':'hazard'},'observation':'hazard','probability':1-1/self.n,'hypothesis_likelihoods':{h:(0.0 if h==chosen else 1.0) for h in self.hyps}},
            ]; residual=0.0
        else: outs=[]; residual=1.0
        return {'outcomes':outs[:top_k],'unknown_probability':residual,'calibrated':True,'_simulation_context':simulation_context,'_simulation_context_key':''}

def exact_categorical_oracle(n,a,m):
    hyps=[f'H{i}' for i in range(n)]
    model=CategoricalModel(n,a)
    total=0.0
    for seq in product(hyps, repeat=m):
        joint={h:1/n for h in hyps}
        for obs in seq:
            likes=model.likes(obs)
            for h in hyps: joint[h]*=likes[h]
        total += max(joint.values())
    return total

def categorical_plan(n,a,m,max_exp=20000, top_k=None, max_hyp=32):
    model=CategoricalModel(n,a,top_outputs=top_k)
    planner=BeliefStateInternalPlanner(model,max_horizon=m+1,max_expansions=max_exp,top_k_outcomes=(top_k or max(n,2)),risk_aversion=0,unknown_risk_weight=0,cost_weight=0,proximity_weight=0,step_penalty=1e-7,min_goal_probability=0,max_hazard_probability=1,max_unknown_probability=1,max_hypotheses=max_hyp,memo_limit=50000)
    actions=('sense',)+tuple('choose'+h for h in model.hyps)
    return planner.plan('cat',entity_id='x',initial_state={'loc':'start'},actions=actions,goal=StateGoal({'loc':'goal'},{'loc':'hazard'}),initial_belief={h:1/n for h in model.hyps},horizon=m+1)

class StepDriftBinary:
    def __init__(self, accuracies): self.acc=list(map(float,accuracies))
    def likes(self,obs,a): return {'A':a if obs=='A' else 1-a,'B':a if obs=='B' else 1-a}
    def __call__(self, mechanism_type, *, entity_id,state,action,neighborhood=None,dt=1.0,simulation_context=None,top_k=4,empirical_min_support=None):
        step=int((simulation_context or {}).get('step',0)); loc=state.get('loc')
        if loc!='start': outs=[]
        elif action=='sense':
            a=self.acc[min(step,len(self.acc)-1)]
            ctx={'step':step+1}
            outs=[{'predicted_state':{'loc':'start'},'observation':o,'hypothesis_likelihoods':self.likes(o,a),'_simulation_context':ctx,'_simulation_context_key':str(step+1)} for o in 'AB']
        elif action in ('chooseA','chooseB'):
            c=action[-1]
            outs=[{'predicted_state':{'loc':'goal'},'observation':'goal','hypothesis_likelihoods':{'A':1.0 if c=='A' else 0.0,'B':1.0 if c=='B' else 0.0}}, {'predicted_state':{'loc':'hazard'},'observation':'hazard','hypothesis_likelihoods':{'A':0.0 if c=='A' else 1.0,'B':0.0 if c=='B' else 1.0}}]
        else: outs=[]
        return {'outcomes':outs[:top_k],'unknown_probability':0.0 if outs else 1.0,'calibrated':True,'_simulation_context':simulation_context,'_simulation_context_key':str(step)}

def drift_oracle(accs):
    total=0.0
    for seq in product('AB', repeat=len(accs)):
        joint={'A':.5,'B':.5}
        for obs,a in zip(seq,accs):
            l={'A':a if obs=='A' else 1-a,'B':a if obs=='B' else 1-a}
            for h in 'AB': joint[h]*=l[h]
        total+=max(joint.values())
    return total

def drift_plan(accs):
    p=BeliefStateInternalPlanner(StepDriftBinary(accs),max_horizon=len(accs)+1,max_expansions=2048,top_k_outcomes=4,risk_aversion=0,unknown_risk_weight=0,cost_weight=0,proximity_weight=0,step_penalty=1e-7,min_goal_probability=0,max_hazard_probability=1,max_unknown_probability=1)
    return p.plan('drift',entity_id='x',initial_state={'loc':'start'},actions=('sense','chooseA','chooseB'),goal=StateGoal({'loc':'goal'},{'loc':'hazard'}),initial_belief={'A':.5,'B':.5},horizon=len(accs)+1)

class BinaryAssumedModel:
    def __init__(self, assumed=.7): self.a=assumed
    def __call__(self, mechanism_type, *, entity_id,state,action,neighborhood=None,dt=1.0,simulation_context=None,top_k=4,empirical_min_support=None):
        a=self.a
        if state.get('loc')!='start': outs=[]
        elif action=='sense': outs=[{'predicted_state':{'loc':'start'},'observation':'A','hypothesis_likelihoods':{'A':a,'B':1-a}}, {'predicted_state':{'loc':'start'},'observation':'B','hypothesis_likelihoods':{'A':1-a,'B':a}}]
        elif action in ('chooseA','chooseB'):
            c=action[-1]; outs=[{'predicted_state':{'loc':'goal'},'observation':'goal','hypothesis_likelihoods':{'A':1 if c=='A' else 0,'B':1 if c=='B' else 0}}, {'predicted_state':{'loc':'hazard'},'observation':'hazard','hypothesis_likelihoods':{'A':0 if c=='A' else 1,'B':0 if c=='B' else 1}}]
        else: outs=[]
        return {'outcomes':outs[:top_k],'unknown_probability':0 if outs else 1,'calibrated':True,'_simulation_context':simulation_context,'_simulation_context_key':''}

def assumed_plan(assumed,m):
    p=BeliefStateInternalPlanner(BinaryAssumedModel(assumed),max_horizon=m+1,max_expansions=4096,top_k_outcomes=4,risk_aversion=0,unknown_risk_weight=0,cost_weight=0,proximity_weight=0,step_penalty=1e-7,min_goal_probability=0,max_hazard_probability=1,max_unknown_probability=1)
    return p.plan('mis',entity_id='x',initial_state={'loc':'start'},actions=('sense','chooseA','chooseB'),goal=StateGoal({'loc':'goal'},{'loc':'hazard'}),initial_belief={'A':.5,'B':.5},horizon=m+1)

def actual_policy_accuracy(result,true_acc,m, correlated=False):
    graph=result['policy_graph']; root=result['root_node']
    total=0.0
    # hidden prior .5
    for hidden in 'AB':
        if correlated:
            # first draw is repeated for every sensing step
            for first,pobs in ((hidden,true_acc),('B' if hidden=='A' else 'A',1-true_acc)):
                node=root; used=0
                while True:
                    nd=graph[node]; act=nd.get('action')
                    if act is None: break
                    if act=='sense':
                        used+=1; obs=first
                        matches=[b for b in nd['branches'] if b.get('observation')==obs]
                        if not matches: break
                        node=matches[0]['next_node']; continue
                    if act in ('chooseA','chooseB'):
                        total += .5*pobs*(1.0 if act[-1]==hidden else 0.0); break
                    break
        else:
            for seq in product('AB',repeat=m):
                pseq=1.0
                for obs in seq: pseq*= true_acc if obs==hidden else 1-true_acc
                node=root; idx=0
                while True:
                    nd=graph[node]; act=nd.get('action')
                    if act is None: break
                    if act=='sense':
                        if idx>=m: break
                        obs=seq[idx]; idx+=1
                        matches=[b for b in nd['branches'] if b.get('observation')==obs]
                        if not matches: break
                        node=matches[0]['next_node']; continue
                    if act in ('chooseA','chooseB'):
                        total += .5*pseq*(1.0 if act[-1]==hidden else 0.0); break
                    break
    return total

def logspace_long_chain(seed=1,steps=1000):
    r=random.Random(seed); prior={'A':r.random(),'B':0}; prior['B']=1-prior['A']
    b=DiscreteBeliefState.from_mapping(prior); logs={h:math.log(p) for h,p in prior.items()}
    for _ in range(steps):
        a=r.uniform(.5001,.9999); obs=r.choice('AB')
        likes={'A':a if obs=='A' else 1-a,'B':a if obs=='B' else 1-a}
        b=b.update(likes)
        for h in 'AB': logs[h]+=math.log(likes[h])
        mx=max(logs.values()); z=sum(math.exp(v-mx) for v in logs.values()); oracle={h:math.exp(v-mx)/z for h,v in logs.items()}
    err=max(abs(b.as_dict()[h]-oracle[h]) for h in 'AB')
    return err,b.as_dict(),oracle

def run():
    t0=time.time(); rows={}; checks={}
    # 1) Posterior numerical stability, 50 independent 1000-step chains
    errs=[]
    for s in range(50): errs.append(logspace_long_chain(10000+s,1000)[0])
    rows['long_chain_50x1000']={'max_abs_error':max(errs),'mean_abs_error':sum(errs)/len(errs)}
    checks['posterior_50k_updates_logspace_match']=max(errs)<1e-10

    # 2) hostile/skewed priors + random variable sensor likelihoods, 10k updates total
    r=random.Random(5150); maxerr=0.0
    for case in range(200):
        x=10**r.uniform(-9,0); prior={'A':x,'B':1.0}; prior=norm(prior); b=DiscreteBeliefState.from_mapping(prior); o=dict(prior)
        for _ in range(50):
            a=r.uniform(.05,.95); obs=r.choice('AB'); likes={'A':a if obs=='A' else 1-a,'B':a if obs=='B' else 1-a}
            b=b.update(likes); o=update_oracle(o,likes)
        maxerr=max(maxerr,max(abs(b.as_dict()[h]-o[h]) for h in 'AB'))
    rows['skew_prior_variable_sensor_200x50']={'max_abs_error':maxerr}
    checks['skew_priors_variable_reliability_stable']=maxerr<1e-12

    # 3) anti-informative sensors (<50%) should be interpreted, not blindly followed
    anti=[]
    for a in (.49,.4,.25,.1):
        res=categorical_plan(2,a,3,max_exp=2048,top_k=2); oracle=exact_categorical_oracle(2,a,3)
        anti.append({'accuracy':a,'claimed':res['best']['goal_probability'],'oracle':oracle,'error':abs(res['best']['goal_probability']-oracle),'root':res['best']['action'] if 'action' in res['best'] else None,'expansions':res['expansions']})
    rows['anti_informative_binary']=anti
    checks['anti_informative_sensors_match_oracle']=max(x['error'] for x in anti)<1e-10

    # 4) Known reliability drift, including inversion midstream
    drift_sets=[[.9,.8,.7,.6],[.9,.2,.9,.2],[.55,.95,.55,.95],[.8,.5,.2,.9]]
    drift=[]
    for accs in drift_sets:
        res=drift_plan(accs); oracle=drift_oracle(accs); drift.append({'acc':accs,'claimed':res['best']['goal_probability'],'oracle':oracle,'error':abs(res['best']['goal_probability']-oracle),'expansions':res['expansions'],'merges':res['belief_merge_hits']})
    rows['known_sensor_drift']=drift
    checks['known_sensor_drift_matches_oracle']=max(x['error'] for x in drift)<1e-10

    # 5) Larger latent spaces under exact model
    scale=[]
    for n,m in [(3,4),(5,3),(8,3),(16,2),(32,1)]:
        st=time.time(); res=categorical_plan(n,.72,m,max_exp=40000,top_k=n,max_hyp=32); oracle=exact_categorical_oracle(n,.72,m)
        scale.append({'hypotheses':n,'clues':m,'claimed':res['best']['goal_probability'],'oracle':oracle,'error':abs(res['best']['goal_probability']-oracle),'expansions':res['expansions'],'nodes':res['policy_nodes'],'unique_beliefs':res['unique_belief_states'],'merges':res['belief_merge_hits'],'status':res['status'],'seconds':time.time()-st})
    rows['hypothesis_scaling']=scale
    checks['up_to_32_hypotheses_exact_small_horizons']=max(x['error'] for x in scale)<1e-9

    # 6) Hard 8-way deeper planning at bounded budgets to locate scaling cliff
    budget=[]
    oracle83=exact_categorical_oracle(8,.72,3)
    for cap in (128,256,512,1024,2048,4096,8192):
        res=categorical_plan(8,.72,3,max_exp=cap,top_k=8,max_hyp=32)
        budget.append({'budget':cap,'status':res['status'],'goal':res['best']['goal_probability'],'error_vs_oracle':abs(res['best']['goal_probability']-oracle83),'expansions':res['expansions'],'nodes':res['policy_nodes']})
    rows['search_budget_8way_3clue']=budget
    checks['8way_eventually_recovers_oracle']=budget[-1]['error_vs_oracle']<1e-9

    # 7) max hypothesis bound
    accepted32=False; rejected33=False
    try:
        _=DiscreteBeliefState.from_mapping({f'H{i}':1 for i in range(32)}); categorical_plan(32,.7,1,max_exp=10000,top_k=32,max_hyp=32); accepted32=True
    except Exception: pass
    try:
        model=CategoricalModel(33,.7); p=BeliefStateInternalPlanner(model,max_hypotheses=32)
        p.plan('x',entity_id='x',initial_state={'loc':'start'},actions=('sense',),goal=StateGoal({'loc':'goal'}),initial_belief={f'H{i}':1/33 for i in range(33)},horizon=1)
    except ValueError: rejected33=True
    rows['hypothesis_bound']={'accept_32':accepted32,'reject_33':rejected33}
    checks['hypothesis_bound_enforced']=accepted32 and rejected33

    # 8) Neutral information should not improve probability
    neutral=categorical_plan(2,.5,5,max_exp=2048,top_k=2)
    rows['neutral_sensor']={'goal':neutral['best']['goal_probability'],'root_action':neutral['policy_graph'][neutral['root_node']]['action'],'expansions':neutral['expansions'],'merges':neutral['belief_merge_hits']}
    checks['neutral_sensor_no_fake_information_gain']=abs(neutral['best']['goal_probability']-.5)<1e-12

    # 9) top-k truncation should expose unknown instead of silently renormalizing
    trunc=categorical_plan(8,.72,2,max_exp=4096,top_k=4,max_hyp=32)
    rows['topk_truncation_8_to_4']={'status':trunc['status'],'goal':trunc['best']['goal_probability'],'unknown':trunc['best']['unknown_probability'],'expansions':trunc['expansions'],'nodes':trunc['policy_nodes']}
    checks['topk_truncation_keeps_unknown_mass']=trunc['best']['unknown_probability']>0

    # 10) model misspecification: planner believes 90% sensor, world is 70%
    mis=assumed_plan(.9,5); actual=actual_policy_accuracy(mis,.7,5,False)
    rows['misspecified_likelihood_90_assumed_70_true']={'claimed':mis['best']['goal_probability'],'actual':actual,'overconfidence':mis['best']['goal_probability']-actual,'expansions':mis['expansions']}
    checks['misspecification_detected_as_failure']=mis['best']['goal_probability']-actual>0.05

    # 11) correlation misspecification: repeated observation is one correlated draw, planner assumes 5 independent draws
    corr=assumed_plan(.7,5); actual_corr=actual_policy_accuracy(corr,.7,5,True)
    rows['correlated_evidence_assumed_independent']={'claimed':corr['best']['goal_probability'],'actual':actual_corr,'overconfidence':corr['best']['goal_probability']-actual_corr,'expansions':corr['expansions']}
    checks['correlated_evidence_exposes_independence_assumption']=corr['best']['goal_probability']-actual_corr>0.05

    # 12) stale model after regime flip: assumed 0.8 but real sensor is 0.2
    stale=assumed_plan(.8,3); actual_stale=actual_policy_accuracy(stale,.2,3,False)
    rows['stale_sensor_model_flip']={'claimed':stale['best']['goal_probability'],'actual':actual_stale,'calibration_gap':stale['best']['goal_probability']-actual_stale}
    checks['regime_flip_exposes_stale_likelihood_model']=stale['best']['goal_probability']-actual_stale>0.5

    # 13) belief-key collision pressure at default precision
    r=random.Random(9001); seen={}; collisions=0
    for _ in range(100000):
        vals=[r.random() for _ in range(4)]; z=sum(vals); d={f'H{i}':vals[i]/z for i in range(4)}; b=DiscreteBeliefState.from_mapping(d); k=b.key(12)
        if k in seen and any(abs(seen[k][h]-d[h])>1e-12 for h in d): collisions+=1
        else: seen[k]=d
    rows['belief_key_100k']={'keys':len(seen),'material_collisions_gt_1e-12':collisions}
    checks['belief_key_no_material_collision_in_100k']=collisions==0

    # 14) impossible evidence should fail closed
    impossible=False
    try: DiscreteBeliefState.from_mapping({'A':1,'B':0}).update({'A':0,'B':1})
    except ValueError: impossible=True
    rows['impossible_evidence']={'raises_value_error':impossible}
    checks['impossible_evidence_fails_closed']=impossible

    payload={'benchmark':'ASM v0.4.0-alpha.5 mega hard feed','runtime_seconds':time.time()-t0,'results':rows,'checks':checks,'passed':sum(checks.values()),'total':len(checks),
             'interpretation':{'robustness_checks_are_expected_true':[k for k in checks if not ('misspecification' in k or 'correlated' in k or 'regime_flip' in k)],'deliberate_limitation_probes':['misspecification_detected_as_failure','correlated_evidence_exposes_independence_assumption','regime_flip_exposes_stale_likelihood_model']}}
    OUT.parent.mkdir(exist_ok=True); OUT.write_text(json.dumps(payload,indent=2,sort_keys=True),encoding='utf-8')
    print(json.dumps(payload,indent=2,sort_keys=True))
    return payload

if __name__=='__main__': run()
