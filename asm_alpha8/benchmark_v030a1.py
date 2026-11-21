from __future__ import annotations

import json
import os
import random
import shutil
import statistics
import tempfile
import time
from pathlib import Path

from asm import ASMEngine, ASMConfig, __version__
from asm.semantic_event import Proposition, SemanticDecision, SemanticEvent
from asm.world_model import PersistentWorldModel

ROOT = Path(__file__).resolve().parent
rows=[]

def add(category,name,ok,**details):
    rows.append({"category":category,"name":name,"pass":bool(ok),"details":details})

def dec(kind, epi, holder, surface, truth=True, conf=.9, persistent=True):
    return SemanticDecision(primary=SemanticEvent(
        kind, epi, conf, "benchmark", [holder] if holder else [],
        Proposition.from_surface(surface, polarity=truth), {}, ["benchmark"], persistent
    ))

with tempfile.TemporaryDirectory() as td:
    db=Path(td)/"world.db"
    wm=PersistentWorldModel(db, max_schedule_candidates=5)
    try:
        first=wm.observe(1,dec("belief","believed","Alice","the gate is open"),raw_text="x")
        add("state","new_state_persisted",len(first["states"])==1 and wm.current(holder="alice")[0]["truth"] is True, output=first)
        add("scheduler","changed_state_is_top_priority",bool(first["scheduled"]) and first["scheduled"][0]["dependency_type"]=="state" and first["scheduled"][0]["priority"]==1.0, scheduled=first["scheduled"])
        add("scheduler","scheduler_cap",len(first["scheduled"])<=5, count=len(first["scheduled"]))

        second=wm.observe(2,dec("belief","believed","Alice","the gate is open",truth=False),raw_text="x")
        trans=wm.transitions(state_key=second["states"][0]["state_key"])
        add("transition","truth_revision",trans[0]["transition_kind"]=="truth_revision" and trans[0]["source_event_id"]==1 and trans[0]["target_event_id"]==2, transition=trans[0])
        add("safety","transition_not_causal",all(not x["causal"] for x in trans), transitions=trans)

        wm.observe(3,dec("observation","asserted","__world__","the gate is open",truth=True),raw_text="x")
        current=wm.current(limit=10)
        add("state","belief_reality_separation",len([x for x in current if x["proposition_canonical"]=="gate open"])==2 and {x["event_type"] for x in current if x["proposition_canonical"]=="gate open"}=={"belief","observation"}, current=current)

        nested=SemanticDecision(primary=SemanticEvent("nested_belief","reported",.9,"benchmark",["Bob","Cara"],Proposition.from_surface("the archive is sealed"),{},[],True))
        nested_out=wm.observe(4,nested,raw_text="x")
        add("state","nested_perspective_path_preserved",len(nested_out["states"])==1 and nested_out["states"][0]["holder"]=="bob>cara", states=nested_out["states"])

        q=SemanticDecision(primary=SemanticEvent("question","queried",.99,"benchmark",[],None,{},[],False))
        before=wm.stats()["state_history"]
        qout=wm.observe(5,q,raw_text="Is the gate open?")
        after=wm.stats()["state_history"]
        add("safety","question_no_world_mutation",before==after and not qout["states"], before=before, after=after, output=qout)

        r1=wm.observe(6,dec("goal","desired","Dana","the rover arrives"),raw_text="x")
        r2=wm.observe(7,dec("goal","desired","Dana","the rover arrives"),raw_text="x")
        rt=wm.transitions(state_key=r2["states"][0]["state_key"])[0]
        add("transition","reaffirmation_detected",rt["transition_kind"]=="reaffirm", transition=rt)

        # Same event slot with a changed epistemic label.
        e1=wm.observe(8,dec("belief","believed","Eli","the signal returns"),raw_text="x")
        e2=wm.observe(9,dec("belief","reported","Eli","the signal returns"),raw_text="x")
        et=wm.transitions(state_key=e2["states"][0]["state_key"])[0]
        add("transition","epistemic_shift_detected",et["transition_kind"]=="epistemic_shift", transition=et)

        node=wm._state_node_key(first["states"][0]["state_key"])
        rels={x["relation"] for x in wm.graph_neighbors(node)}
        add("graph","holder_edge", "holds_state" in rels, relations=sorted(rels))
        add("graph","proposition_term_edges", "mentions" in rels, relations=sorted(rels))
        add("query","holder_type_filter",len(wm.current(holder="alice",event_type="belief"))==1, result=wm.current(holder="alice",event_type="belief"))
    finally:
        wm.close()

# Live engine integration.
with tempfile.TemporaryDirectory() as td:
    e=ASMEngine(Path(td)/"engine.db", config=ASMConfig(snapshot_every_events=999999))
    try:
        out=e.process("Mina fears the server will fail")
        ok=(out["world_model_update"] is not None and out["world_model_update"]["states"] and out["world_model_update"]["states"][0]["event_type"]=="fear")
        add("engine","live_semantic_event_updates_world",ok,world=out["world_model_update"])
        add("engine","stats_expose_world_model","world_model" in e.stats() and "current_states" in e.stats()["world_model"],stats=e.stats()["world_model"])
    finally:
        e.close()

# Trained-state migration and idempotent backfill.
with tempfile.TemporaryDirectory() as td:
    src=ROOT/"asm_v030a12_trained.db"
    dst=Path(td)/"migrate.db"
    shutil.copy2(src,dst)
    wm=PersistentWorldModel(dst)
    try:
        before=wm.stats()
        added=wm.backfill_from_semantic_memory(limit=20000)
        after=wm.stats()
        import sqlite3
        c=sqlite3.connect(dst)
        episodic=int(c.execute("select count(*) from events").fetchone()[0])
        semantic=int(c.execute("select count(*) from semantic_event_records").fetchone()[0])
        c.close()
        add("migration","trained_state_preserved",episodic==897 and semantic==897,episodic=episodic,semantic=semantic)
        add("migration","backfill_idempotent",added==0 and before==after,added=added,before=before,after=after)
    finally:
        wm.close()

# Scaling probe: 10k updates, 5k state slots, then bounded filtered queries.
with tempfile.TemporaryDirectory() as td:
    db=Path(td)/"scale.db"
    wm=PersistentWorldModel(db,max_schedule_candidates=8)
    start=time.perf_counter()
    event_id=0
    for phase in range(2):
        truth=(phase==0)
        for i in range(5000):
            event_id += 1
            holder=f"agent{i%250}"
            surface=f"object{i} channel stable"
            wm.observe(event_id,dec("belief","believed",holder,surface,truth=truth),raw_text=surface)
    build_s=time.perf_counter()-start
    stats=wm.stats()
    rng=random.Random(3)
    samples=[]
    correct=0
    for _ in range(200):
        h=f"agent{rng.randrange(250)}"
        t=time.perf_counter()
        got=wm.current(holder=h,event_type="belief",limit=32)
        samples.append((time.perf_counter()-t)*1000)
        if got and all(x["holder"]==h and x["event_type"]=="belief" for x in got):
            correct += 1
    wm.close()
    samples.sort()
    scaling={
        "updates":10000,
        "expected_current_slots":5000,
        "stats":stats,
        "build_seconds":round(build_s,3),
        "query_cases":200,
        "filtered_query_correct":correct,
        "filtered_query_accuracy_pct":round(100*correct/200,2),
        "median_query_ms":round(statistics.median(samples),6),
        "p95_query_ms":round(samples[int(.95*(len(samples)-1))],6),
        "db_bytes":os.path.getsize(db),
    }
    add("scaling","current_slot_count",stats["current_states"]==5000,stats=stats)
    add("scaling","filtered_queries",correct==200,scaling=scaling)

summary={"passed":sum(int(x["pass"]) for x in rows),"total":len(rows)}
summary["accuracy_pct"]=round(100*summary["passed"]/max(1,summary["total"]),2)
payload={
    "benchmark":"ASM v0.3.0-alpha.1 Persistent World State",
    "version":__version__,
    "summary":summary,
    "scaling":scaling,
    "cases":rows,
    "notes":[
        "This is an ASM architecture/regression benchmark, not a standardized intelligence benchmark.",
        "World transitions in alpha.1 are descriptive evidence only; causal is always false.",
        "Scheduler candidates identify local mechanism dependencies but do not yet execute learned mechanisms.",
        "Latency is specific to this execution environment.",
    ]
}
out=ROOT/"results/world_model_benchmark.json"
out.write_text(json.dumps(payload,indent=2),encoding="utf-8")
print(json.dumps({"version":__version__,"summary":summary,"scaling":scaling},indent=2))
print("RESULT:",out)
if summary["passed"] != summary["total"]:
    raise SystemExit(1)
