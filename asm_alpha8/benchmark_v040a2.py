from __future__ import annotations

import collections
import json
import random
from pathlib import Path

from asm import __version__
from asm.planning import BoundedInternalPlanner, StateGoal
from asm.transition_mechanism import LocalRecurrentTransitionMechanism

OUT = Path('results/planning_v040a2_benchmark.json')
ACTIONS = ('U','D','L','R')
DELTA = {'U':(0,-1),'D':(0,1),'L':(-1,0),'R':(1,0)}


class GridPredictor:
    def __init__(self, walls, size):
        self.walls=set(walls); self.size=int(size)
    def __call__(self, mechanism_type, *, entity_id, state, action,
                 neighborhood=None, dt=1.0, simulation_context=None):
        x,y=int(state['x']),int(state['y']); dx,dy=DELTA[action]; nxt=(x+dx,y+dy)
        if (nxt[0] < 0 or nxt[1] < 0 or nxt[0] >= self.size or nxt[1] >= self.size or nxt in self.walls):
            nxt=(x,y)
        return {
            'mechanism_type':mechanism_type,
            'predicted_state':{'x':nxt[0],'y':nxt[1]},
            'confidence':.99,'uncertainty':.01,
            '_simulation_context':simulation_context,
            '_simulation_context_key':'',
        }


class ContextPredictor:
    def __call__(self, mechanism_type, *, entity_id, state, action,
                 neighborhood=None, dt=1.0, simulation_context=None):
        phase=int((simulation_context or {}).get('phase',0))
        if action == 'prime':
            nxt={'door':'closed'}; phase=1
        elif action == 'open':
            nxt={'door':'open' if phase == 1 else 'jammed'}; phase=0
        else:
            nxt=dict(state)
        return {
            'mechanism_type':mechanism_type,'predicted_state':nxt,
            'confidence':.97,'uncertainty':.03,
            '_simulation_context':{'phase':phase},
            '_simulation_context_key':f'p{phase}',
        }


def shortest(walls, size):
    goal=(size-1,size-1)
    q=collections.deque([((0,0),0)]); seen={(0,0)}
    while q:
        pos,d=q.popleft()
        if pos == goal: return d
        for dx,dy in DELTA.values():
            nxt=(pos[0]+dx,pos[1]+dy)
            if 0 <= nxt[0] < size and 0 <= nxt[1] < size and nxt not in walls and nxt not in seen:
                seen.add(nxt); q.append((nxt,d+1))
    return None


def generate_mazes(size, count, density, horizon, seed):
    rng=random.Random(seed); cases=[]
    while len(cases) < count:
        walls={
            (x,y) for x in range(size) for y in range(size)
            if (x,y) not in ((0,0),(size-1,size-1)) and rng.random() < density
        }
        d=shortest(walls,size)
        if d is not None and d <= horizon:
            cases.append((walls,d))
    return cases


def maze_feed(size, count, density, horizon, max_expansions, seed):
    solved=0; expansions=[]; rescues=0; rescue_expansions=0
    for i,(walls,shortest_path) in enumerate(generate_mazes(size,count,density,horizon,seed)):
        planner=BoundedInternalPlanner(
            GridPredictor(walls,size), max_horizon=horizon,
            beam_width=4, adaptive_beam_max=8, max_expansions=max_expansions,
            uncertainty_penalty=.1, step_penalty=.002, proximity_weight=.2,
        )
        result=planner.plan(
            'grid', entity_id=f'maze-{size}-{i}', initial_state={'x':0,'y':0},
            actions=ACTIONS, goal=StateGoal({'x':size-1,'y':size-1}), horizon=horizon,
        )
        solved += int(result['status']=='goal_reached')
        expansions.append(result['expansions'])
        rescues += int(result['rescue_used'])
        rescue_expansions += int(result['rescue_expansions'])
    return {
        'size':size,'cases':count,'solved':solved,'accuracy':solved/count,
        'average_expansions':sum(expansions)/len(expansions),
        'max_expansions_used':max(expansions),
        'rescue_cases':rescues,'rescue_expansions':rescue_expansions,
        'beam_width':4,'adaptive_beam_max':8,'configured_max_expansions':max_expansions,
    }


def learned_line_feed():
    m=LocalRecurrentTransitionMechanism(
        'v040a2_line',hidden_dim=16,train_steps=1,max_outcomes=16,
        outcome_capacity_limit=64,retention_anchor_limit=96,seed=404,
        abstraction_min_support=8,abstraction_min_precision=.95,
        abstraction_min_diversity=4,abstraction_sparse_enabled=True,
        abstraction_sparse_max_retained_features=2,
    )
    m.replay_limit=64; m.replay_batch_limit=4
    for pos in range(8):
        for action in ('left','right'):
            nxt=max(0,min(7,pos+(1 if action=='right' else -1)))
            for variant in range(12):
                m.observe(
                    entity_id=f'train-{pos}-{action}-{variant}',
                    state={'position':pos,'token':f't{variant}','noise':variant%5},
                    action=action, after_state={'position':nxt},
                )
    planner=BoundedInternalPlanner(
        lambda mechanism_type, **kw: m.predict_simulated(**kw),
        max_horizon=8,beam_width=4,adaptive_beam_max=8,max_expansions=128,
        uncertainty_penalty=.35,step_penalty=.01,
    )
    before=m.stats().copy(); solved=0; failures=[]
    for start in range(8):
        for goal in range(8):
            if start == goal: continue
            result=planner.plan(
                'v040a2_line',entity_id=f'probe-{start}-{goal}',
                initial_state={'position':start,'token':'unseen','noise':99},
                actions=('left','right'),goal=StateGoal({'position':goal}),horizon=8,
            )
            good=(result['status']=='goal_reached' and result['best']['predicted_state']=={'position':goal})
            solved += int(good)
            if not good: failures.append({'start':start,'goal':goal,'status':result['status']})
    after=m.stats().copy()
    return {
        'cases':56,'solved':solved,'failures':failures,
        'observations_before':before['observations'],'observations_after':after['observations'],
        'abstraction_hits_before':before['abstraction_hits'],'abstraction_hits_after':after['abstraction_hits'],
        'abstraction_misses_before':before['abstraction_misses'],'abstraction_misses_after':after['abstraction_misses'],
    }


def main():
    line=learned_line_feed()
    maze5=maze_feed(5,1000,.30,18,300,5001)
    maze10=maze_feed(10,250,.27,32,1200,10001)
    context=BoundedInternalPlanner(ContextPredictor(),max_horizon=2,beam_width=4,
                                   adaptive_beam_max=4,max_expansions=16).plan(
        'door',entity_id='ctx',initial_state={'door':'closed'},
        actions=('open','prime','wait'),goal=StateGoal({'door':'open'}),horizon=2,
    )
    checks={
        'version_is_v040a2': __version__.startswith('0.4.0-alpha.7'),
        'learned_line_all_56_unseen_goals': line['solved']==56,
        'planning_does_not_add_observations': line['observations_before']==line['observations_after'],
        'planning_does_not_touch_abstraction_telemetry': (
            line['abstraction_hits_before']==line['abstraction_hits_after'] and
            line['abstraction_misses_before']==line['abstraction_misses_after']
        ),
        'branch_local_context_solves_hidden_history': context['status']=='goal_reached' and context['best']['actions']==['prime','open'],
        'five_by_five_feed_1000_of_1000': maze5['solved']==maze5['cases']==1000,
        'ten_by_ten_feed_250_of_250': maze10['solved']==maze10['cases']==250,
        'ten_by_ten_stays_inside_budget': maze10['max_expansions_used']<=maze10['configured_max_expansions'],
    }
    payload={
        'version':__version__,
        'benchmark':'ASM v0.4.0-alpha.3 Robust Branching Simulation & Search',
        'learned_line':line,'maze_5x5':maze5,'maze_10x10':maze10,
        'context_branch_plan':context,
        'checks':checks,'passed':sum(checks.values()),'total':len(checks),
        'notes':[
            'Maze feeds use deterministic local transition oracles to isolate planner search behavior from model-learning accuracy.',
            'The learned-line feed uses ASM LocalRecurrentTransitionMechanism predictions on unseen nuisance features.',
            'Goal proximity is a search heuristic only; exact StateGoal.satisfied remains the success predicate.',
            'This is an internal architecture benchmark, not a standardized intelligence or AGI benchmark.',
        ],
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(payload,indent=2,sort_keys=True),encoding='utf-8')
    print(json.dumps({
        'version':__version__,'passed':payload['passed'],'total':payload['total'],
        'learned_line':f"{line['solved']}/{line['cases']}",
        'maze_5x5':f"{maze5['solved']}/{maze5['cases']}",
        'maze_10x10':f"{maze10['solved']}/{maze10['cases']}",
        'maze_10x10_rescues':maze10['rescue_cases'],
        'maze_10x10_max_expansions_used':maze10['max_expansions_used'],
    },indent=2))
    if not all(checks.values()): raise SystemExit(1)

if __name__=='__main__': main()
