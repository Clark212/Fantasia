from __future__ import annotations
import json, math, random, time
from pathlib import Path
from asm.planning import DiscreteBeliefState, BeliefStateInternalPlanner, StateGoal
OUT=Path('results/planning_v040a5_extreme_torture.json')

def symmetric_likes(labels, obs, acc):
    spill=(1-acc)/(len(labels)-1)
    return {h:(acc if h==obs else spill) for h in labels}

def log_oracle(prior, evidence):
    logs={h:math.log(p) for h,p in prior.items() if p>0}
    for likes in evidence:
        nxt={}
        for h,lp in logs.items():
            l=likes.get(h,0)
            if l>0: nxt[h]=lp+math.log(l)
        logs=nxt
        if not logs: raise ValueError('zero mass')
        m=max(logs.values()); z=m+math.log(sum(math.exp(v-m) for v in logs.values())); logs={h:v-z for h,v in logs.items()}
    probs={h:(math.exp(v) if v>-745 else 0.0) for h,v in logs.items()}
    return probs,logs

def max_log_error(b,logs):
    got=b.as_log_dict(); return max(abs(got[h]-logs[h]) for h in logs)

def reversible_binary(acc,n):
    b=DiscreteBeliefState.from_mapping({'A':.5,'B':.5})
    A={'A':acc,'B':1-acc}; B={'A':1-acc,'B':acc}
    for _ in range(n): b=b.update(A)
    mid_prob=b.as_dict(); mid_log=b.as_log_dict()
    for _ in range(n): b=b.update(B)
    return {'acc':acc,'n_each':n,'mid_prob':mid_prob,'mid_min_log':min(mid_log.values()),'final':b.as_dict(),'final_log':b.as_log_dict(),'error':abs(b.as_dict()['A']-.5)}

def multiway_block_recovery(k,acc,n_each):
    labs=[f'H{i}' for i in range(k)]; prior={h:1/k for h in labs}; b=DiscreteBeliefState.from_mapping(prior)
    for obs in labs:
        likes=symmetric_likes(labs,obs,acc)
        for _ in range(n_each): b=b.update(likes)
    err=max(abs(b.as_dict().get(h,0)-1/k) for h in labs)
    logspread=max(b.as_log_dict().values())-min(b.as_log_dict().values())
    return {'k':k,'acc':acc,'n_each':n_each,'error_uniform':err,'log_spread':logspread,'evidence_count':b.evidence_count}

def million_update(seed=77, chains=100, steps=10000):
    r=random.Random(seed); maxerr=0.0; maxlog=0.0
    for c in range(chains):
        p=r.uniform(.001,.999); prior={'A':p,'B':1-p}; b=DiscreteBeliefState.from_mapping(prior); logs={h:math.log(v) for h,v in prior.items()}
        for i in range(steps):
            # Long runs + variable strength, deliberately including anti-informative evidence.
            a=r.uniform(.01,.99); obs=('A' if ((i//r.randint(1,20))+c)%2==0 else 'B') if r.random()<.7 else r.choice('AB')
            likes={'A':a if obs=='A' else 1-a,'B':a if obs=='B' else 1-a}
            b=b.update(likes)
            for h in 'AB': logs[h]+=math.log(likes[h])
            m=max(logs.values()); z=m+math.log(sum(math.exp(v-m) for v in logs.values())); logs={h:v-z for h,v in logs.items()}
        maxlog=max(maxlog,max(abs(v) for v in logs.values()))
        maxerr=max(maxerr,max_log_error(b,logs))
    return {'updates':chains*steps,'chains':chains,'steps_each':steps,'max_log_error':maxerr,'max_abs_log_posterior_seen':maxlog}

def tiny_prior_recovery():
    prior={'A':1.0,'B':1e-300}; b=DiscreteBeliefState.from_mapping(prior)
    # Favor B strongly until it overtakes A.
    likes={'A':.01,'B':.99}
    steps=0
    while b.most_likely()[0]!='B' and steps<1000:
        b=b.update(likes); steps+=1
    return {'steps_to_B_MAP':steps,'final':b.as_dict(),'logs':b.as_log_dict(),'recovered':b.most_likely()[0]=='B'}

def shuffled_balance(seed,acc,n_each):
    r=random.Random(seed); seq=['A']*n_each+['B']*n_each; r.shuffle(seq)
    b=DiscreteBeliefState.from_mapping({'A':.5,'B':.5})
    for obs in seq: b=b.update({'A':acc if obs=='A' else 1-acc,'B':acc if obs=='B' else 1-acc})
    return abs(b.as_dict()['A']-.5)

class InvalidLikelihoodModel:
    # Two observations each claim likelihood .9 under BOTH hypotheses. Their
    # per-hypothesis likelihood sum is 1.8, which is not a valid observation model.
    def __call__(self, mechanism_type, *, entity_id,state,action,neighborhood=None,dt=1.0,simulation_context=None,top_k=4,empirical_min_support=None):
        if state.get('loc')!='start': outs=[]
        elif action=='sense': outs=[
            {'predicted_state':{'loc':'start'},'observation':'x','hypothesis_likelihoods':{'A':.9,'B':.9}},
            {'predicted_state':{'loc':'start'},'observation':'y','hypothesis_likelihoods':{'A':.9,'B':.9}},]
        elif action=='chooseA': outs=[{'predicted_state':{'loc':'goal'},'observation':'g','hypothesis_likelihoods':{'A':1,'B':0}},{'predicted_state':{'loc':'hazard'},'observation':'h','hypothesis_likelihoods':{'A':0,'B':1}}]
        elif action=='chooseB': outs=[{'predicted_state':{'loc':'goal'},'observation':'g','hypothesis_likelihoods':{'A':0,'B':1}},{'predicted_state':{'loc':'hazard'},'observation':'h','hypothesis_likelihoods':{'A':1,'B':0}}]
        else: outs=[]
        return {'outcomes':outs[:top_k],'unknown_probability':0 if outs else 1,'calibrated':True,'_simulation_context':simulation_context,'_simulation_context_key':''}

def invalid_likelihood_probe():
    p=BeliefStateInternalPlanner(InvalidLikelihoodModel(),max_horizon=2,max_expansions=64,top_k_outcomes=4,risk_aversion=0,unknown_risk_weight=0,cost_weight=0,proximity_weight=0,step_penalty=0,min_goal_probability=0,max_hazard_probability=1,max_unknown_probability=1)
    r=p.plan('bad',entity_id='x',initial_state={'loc':'start'},actions=('sense','chooseA','chooseB'),goal=StateGoal({'loc':'goal'},{'loc':'hazard'}),initial_belief={'A':.5,'B':.5},horizon=2)
    return {'status':r['status'],'goal':r['best']['goal_probability'],'hazard':r['best']['hazard_probability'],'unknown':r['best']['unknown_probability'],'root_action':r['policy_graph'][r['root_node']]['action'],'invalid_likelihood_models':r.get('invalid_likelihood_models',0)}

def rare_branch_probe():
    # Build a posterior where B is ~exp(-920), then ask planner to consider an
    # observation overwhelmingly favoring B. evidence_probability underflows and
    # the branch is deliberately treated as below the planner's 1e-15 cutoff.
    b=DiscreteBeliefState.from_mapping({'A':.5,'B':.5}); A={'A':.99,'B':.01}
    for _ in range(200): b=b.update(A)
    like={'A':0.0,'B':1.0}
    return {'belief_logs':b.as_log_dict(),'next_evidence_probability':b.evidence_probability(like),'next_evidence_log_probability':b.evidence_log_probability(like),'below_planner_branch_cutoff':b.evidence_probability(like)<=1e-15}

def key_distinguishes_underflowed_odds():
    b1=DiscreteBeliefState.from_mapping({'A':.5,'B':.5}); b2=b1
    A={'A':.99,'B':.01}
    for _ in range(170): b1=b1.update(A)
    for _ in range(200): b2=b2.update(A)
    return {'both_public_B_zero':b1.as_dict()['B']==0 and b2.as_dict()['B']==0,'keys_distinct':b1.key()!=b2.key(),'logB_170':b1.as_log_dict()['B'],'logB_200':b2.as_log_dict()['B']}

def main():
    t=time.time(); results={}; checks={}
    rev=[reversible_binary(a,n) for a,n in [(.7,2000),(.8,1500),(.9,1000),(.95,750),(.99,500),(.999,300)]]
    results['extreme_reversible_binary']=rev; checks['six_extreme_reversals_return_50_50']=max(x['error'] for x in rev)<1e-10
    multi=[multiway_block_recovery(k,.97,n) for k,n in [(3,250),(5,180),(8,120),(16,60),(32,30)]]
    results['multiway_block_recovery']=multi; checks['3_to_32_way_block_recovery_uniform']=max(x['error_uniform'] for x in multi)<1e-10
    million=million_update(); results['million_update_log_oracle']=million; checks['one_million_updates_match_log_oracle']=million['max_log_error']<1e-9
    tiny=tiny_prior_recovery(); results['tiny_prior_1e_300_recovery']=tiny; checks['tiny_prior_can_recover_to_MAP']=tiny['recovered'] and tiny['steps_to_B_MAP']<1000
    shuffled=[shuffled_balance(1000+i,.995,400) for i in range(250)]; results['shuffled_balanced_extreme']={'cases':len(shuffled),'max_error':max(shuffled)}; checks['250_shuffled_balanced_sequences_return_prior']=max(shuffled)<1e-10
    key=key_distinguishes_underflowed_odds(); results['memo_key_underflow_odds']=key; checks['memo_key_preserves_distinct_extreme_odds']=key['both_public_B_zero'] and key['keys_distinct']
    rare=rare_branch_probe(); results['rare_branch_cutoff']=rare; checks['rare_branch_cutoff_is_explicitly_exposed']=rare['below_planner_branch_cutoff']
    bad=invalid_likelihood_probe(); results['invalid_likelihood_matrix']=bad; checks['invalid_likelihood_matrix_fails_closed']=bad['invalid_likelihood_models']>=1 and bad['root_action']!='sense'
    # Input sanitation checks
    neg=DiscreteBeliefState.from_mapping({'A':1,'B':-3}).as_dict(); invalid_zero=False
    try: DiscreteBeliefState.from_mapping({'A':0,'B':0})
    except ValueError: invalid_zero=True
    results['input_sanitation']={'negative_clamped':neg,'all_zero_rejected':invalid_zero}; checks['invalid_prior_sanitation']=neg=={'A':1.0} and invalid_zero
    payload={'benchmark':'ASM v0.4.0-alpha.5.1 extreme belief-state torture','runtime_seconds':time.time()-t,'results':results,'checks':checks,'passed':sum(checks.values()),'total':len(checks),
             'known_limitations_exposed':{
                 'likelihood_model_misspecification':'Structurally valid likelihoods can still be factually wrong, stale, correlated, or misspecified; alpha.5.1 does not learn/calibrate the model.',
                 'astronomically_rare_branch_pruning':'Planning intentionally drops evidence branches with probability <=1e-15; log-space belief preserves the hypothesis, but exhaustive planning does not follow such branches.'}}
    OUT.parent.mkdir(exist_ok=True); OUT.write_text(json.dumps(payload,indent=2,sort_keys=True),encoding='utf-8'); print(json.dumps(payload,indent=2,sort_keys=True))
    if not all(checks.values()): raise SystemExit(1)
if __name__=='__main__': main()
