from __future__ import annotations

import json
import math
import random
import tempfile
from pathlib import Path

from asm import ASMConfig, ASMEngine
from asm.evidence_lineage import EvidenceLineageGraph
from asm.planning import DiscreteBeliefState


def check(name, condition, detail, rows):
    ok = bool(condition)
    rows.append((name, ok, detail))
    print(("PASS" if ok else "FAIL"), name, detail)
    if not ok:
        raise AssertionError(name)


def main():
    rows=[]

    # 1) Deep copy chain: confidence must not grow after the one real root.
    g=EvidenceLineageGraph(max_nodes=12000)
    b=DiscreteBeliefState.from_mapping({'A':.5,'B':.5})
    r=g.register('root',source_id='camera')
    b=b.update_weighted({'A':.7,'B':.3},evidence_roots=r.roots)
    prev='root'
    for i in range(1,10000):
        eid=f'c{i}'
        row=g.register(eid,source_id='relay',parent_ids=[prev])
        w=g.novelty(b.evidence_roots(),row.roots)
        b=b.update_weighted({'A':.7,'B':.3},evidence_weight=w,evidence_roots=row.roots)
        prev=eid
    check('copy_chain_10000_no_confidence_inflation',abs(b.as_dict()['A']-.7)<1e-14,{'posterior_A':b.as_dict()['A'],'roots':len(b.evidence_roots())},rows)

    # 2) 1000 randomized independent sequences must exactly match ordinary Bayes.
    rng=random.Random(8765); maxerr=0.0; ranks=0
    for seq in range(1000):
        ordinary=DiscreteBeliefState.from_mapping({'A':.5,'B':.5})
        lineaged=DiscreteBeliefState.from_mapping({'A':.5,'B':.5})
        graph=EvidenceLineageGraph(max_nodes=64)
        for i in range(32):
            obs='A' if rng.random()<.5 else 'B'; rel=rng.uniform(.500001,.999999)
            likes={'A':rel if obs=='A' else 1-rel,'B':rel if obs=='B' else 1-rel}
            ordinary=ordinary.update(likes)
            rec=graph.register(f'{seq}:{i}',source_id=f's{i}')
            lineaged=lineaged.update_weighted(likes,evidence_weight=graph.novelty(lineaged.evidence_roots(),rec.roots),evidence_roots=rec.roots)
        maxerr=max(maxerr,max(abs(ordinary.as_dict()[h]-lineaged.as_dict()[h]) for h in ('A','B')))
        ranks += ordinary.most_likely()[0] == lineaged.most_likely()[0]
    check('independent_random_1000_exact',maxerr==0.0 and ranks==1000,{'max_error':maxerr,'rank_matches':ranks},rows)

    # 3) 32-hypothesis duplicate evidence remains a single update.
    names=[f'h{i}' for i in range(32)]
    prior={h:1/32 for h in names}; likes={h:.01/31 for h in names}; likes['h7']=.99
    graph=EvidenceLineageGraph(max_nodes=64)
    b=DiscreteBeliefState.from_mapping(prior)
    root=graph.register('mroot',source_id='sensor')
    b=b.update_weighted(likes,evidence_roots=root.roots)
    one=b.as_dict()['h7']
    for i in range(31):
        rec=graph.register(f'mcopy{i}',source_id='relay',parent_ids=['mroot'])
        b=b.update_weighted(likes,evidence_weight=graph.novelty(b.evidence_roots(),rec.roots),evidence_roots=rec.roots)
    check('multiclass_32_copy_safe',abs(b.as_dict()['h7']-one)<1e-14 and all(math.isfinite(v) for v in b.as_dict().values()),{'h7':b.as_dict()['h7']},rows)

    # 4) Partial overlap is bounded and finite under long alternating updates.
    b=DiscreteBeliefState.from_mapping({'A':.5,'B':.5}); graph=EvidenceLineageGraph(max_nodes=3000,max_roots_per_item=4)
    for i in range(1000):
        roots=['shared',f'u{i}']
        rec=graph.register(f'p{i}',source_id='s',root_ids=roots)
        obs='A' if i%2==0 else 'B'; likes={'A':.8 if obs=='A' else .2,'B':.8 if obs=='B' else .2}
        b=b.update_weighted(likes,evidence_weight=graph.novelty(b.evidence_roots(),rec.roots),evidence_roots=rec.roots)
    check('partial_overlap_1000_finite',all(math.isfinite(v) for v in b.as_log_dict().values()),{'posterior':b.as_dict(),'roots':len(b.evidence_roots())},rows)

    # 5) Node capacity fails closed.
    graph=EvidenceLineageGraph(max_nodes=2)
    graph.register('a',source_id='s'); graph.register('b',source_id='s')
    rejected=False
    try: graph.register('c',source_id='s')
    except RuntimeError: rejected=True
    check('graph_capacity_fail_closed',rejected,{},rows)

    # 6) Per-item root capacity fails closed.
    graph=EvidenceLineageGraph(max_roots_per_item=2)
    rejected=False
    try: graph.register('a',source_id='s',root_ids=['r1','r2','r3'])
    except RuntimeError: rejected=True
    check('item_root_capacity_fail_closed',rejected,{},rows)

    # 7) Unknown ancestry / cycles / malformed snapshot are rejected.
    bad=[
        {'schema':1,'records':[{'evidence_id':'x','source_id':'s','parent_ids':['missing'],'roots':['r']}]},
        {'schema':1,'records':[{'evidence_id':'a','source_id':'s','parent_ids':['b'],'roots':['r']},{'evidence_id':'b','source_id':'s','parent_ids':['a'],'roots':['r']}]},
        {'schema':1,'records':[{'evidence_id':'a','source_id':'s','parent_ids':[],'roots':[]}]},
    ]; rejects=0
    for payload in bad:
        try: EvidenceLineageGraph().import_state(payload)
        except ValueError: rejects+=1
    check('malformed_lineage_snapshots_rejected',rejects==len(bad),{'rejected':rejects,'total':len(bad)},rows)

    # 8) Engine per-belief capacity fails closed rather than forgetting roots.
    with tempfile.TemporaryDirectory() as td:
        e=ASMEngine(Path(td)/'x.db',config=ASMConfig(evidence_lineage_max_roots_per_belief=16,snapshot_every_events=999999,prune_every_events=999999))
        b={'A':.5,'B':.5}
        for i in range(16):
            b=e.update_belief_from_source(b,source_id='s',observation='A',supplied_reliability=.7,evidence_id=f'e{i}')
        rejected=False
        try: e.update_belief_from_source(b,source_id='s',observation='A',supplied_reliability=.7,evidence_id='overflow')
        except RuntimeError: rejected=True
        check('belief_root_capacity_fail_closed',rejected,{'roots':len(b.evidence_roots())},rows)
        e.close(save_snapshot=False)

    # 9) Conflicting reuse of evidence ID is rejected, idempotent exact reuse is accepted.
    graph=EvidenceLineageGraph(); a=graph.register('e',source_id='s'); b2=graph.register('e',source_id='s')
    rejected=False
    try: graph.register('e',source_id='other')
    except ValueError: rejected=True
    check('evidence_id_idempotent_but_conflicts_rejected',a==b2 and rejected,{},rows)

    # 10) 100 independent roots each repeated ten times should equal 100 independent updates exactly.
    rng=random.Random(42)
    ordinary=DiscreteBeliefState.from_mapping({'A':.5,'B':.5}); dep=DiscreteBeliefState.from_mapping({'A':.5,'B':.5}); graph=EvidenceLineageGraph(max_nodes=2000)
    for group in range(100):
        obs='A' if rng.random()<.55 else 'B'; rel=.61
        likes={'A':rel if obs=='A' else 1-rel,'B':rel if obs=='B' else 1-rel}
        ordinary=ordinary.update(likes)
        root=f'r{group}'; rec=graph.register(root,source_id='sensor'); dep=dep.update_weighted(likes,evidence_roots=rec.roots)
        for c in range(9):
            rec=graph.register(f'{root}:c{c}',source_id='relay',parent_ids=[root]); dep=dep.update_weighted(likes,evidence_weight=graph.novelty(dep.evidence_roots(),rec.roots),evidence_roots=rec.roots)
    err=max(abs(ordinary.as_dict()[h]-dep.as_dict()[h]) for h in ('A','B'))
    check('100_roots_x10_equivalent_to_100_independent',err==0.0,{'max_error':err,'raw_evidence_count':dep.evidence_count,'roots':len(dep.evidence_roots())},rows)

    result={'passed':sum(ok for _,ok,_ in rows),'total':len(rows),'checks':[{'name':n,'pass':ok,'detail':detail} for n,ok,detail in rows]}
    Path('ALPHA62_TORTURE.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print('SUMMARY',result['passed'],'/',result['total'])

if __name__=='__main__': main()
