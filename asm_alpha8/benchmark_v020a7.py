from __future__ import annotations

import json
import statistics
import tempfile
import time
from pathlib import Path

from asm import ASMEngine, __version__
from asm.event_memory import SemanticEventMemory
from asm.memory import EpisodicMemory
from asm.semantic_event import Proposition, SemanticDecision, SemanticEvent


rows=[]
def add(category,name,ok,**details):
    rows.append({"category":category,"name":name,"pass":bool(ok),"details":details})

with tempfile.TemporaryDirectory() as td:
    asm=ASMEngine(Path(td)/"semantic_memory2.db")
    try:
        # Mental-state separation with distractors.
        facts=[
            "Oren expects the bridge to open",
            "Oren believes the tunnel is blocked",
            "Mina fears the server will fail",
            "Mina wants the backup to finish",
            "Tessa believes the lantern is broken",
            "Rhea expects the east gate to unlock",
        ]
        for text in facts:
            asm.process(text,training=True)

        query_cases=[
            ("expectation_agent","what does Oren expect?","expectation","oren","bridge"),
            ("belief_agent","what does Oren believe?","belief","oren","tunnel"),
            ("fear_agent","what does Mina fear?","fear","mina","server"),
            ("goal_agent","what does Mina want?","goal","mina","backup"),
            ("other_agent_isolation","does Mina believe the lantern is broken?",None,"mina",None),
        ]
        for name,q,etype,agent,needle in query_cases:
            found=asm.event_memory.recall(q,limit=5)
            if etype is None:
                ok=found==[]
            else:
                ok=bool(found and found[0]["event_type"]==etype and agent in found[0]["agents"] and needle in found[0]["text"].lower())
            add("typed_retrieval",name,ok,query=q,top=(found[0] if found else None))

        # Revision semantics.
        first=asm.process("Alice believes the gate is open",training=True)
        second=asm.process("Alice doubts the gate is open",training=True)
        links=asm.event_memory.links_for(second["event_id"])
        rels={x["relation"] for x in links}
        found=asm.event_memory.recall("what does Alice believe about the gate?",limit=2)
        add("revision","contradiction_links",
            {"revises","contradicts","agent_next","proposition_next"}.issubset(rels),links=links)
        add("revision","latest_revision_ranks_first",
            bool(found and found[0]["id"]==second["event_id"] and found[0]["truth"] is False),top=(found[0] if found else None))
        add("revision","no_fake_causality",
            not any(x["relation"] in {"causes","caused_by","causal"} for x in links),links=links)

        # Reaffirmation.
        third=asm.process("Alice doubts the gate is open",training=True)
        rel3={x["relation"] for x in asm.event_memory.links_for(third["event_id"])}
        add("revision","reaffirmation","reaffirms" in rel3 and "contradicts" not in rel3,relations=sorted(rel3))

        # Generic proposition-term memory.
        asm.process("The battery became hot after charging",training=True)
        generic=asm.event_memory.recall("what did i say about the battery?",limit=3)
        add("topic_retrieval","generic_event_topic",
            bool(generic and "battery" in generic[0]["text"].lower()),top=(generic[0] if generic else None))

        # Live question recall must be transient but grounded.
        before=asm.memory.count_events()
        q=asm.chat("what does Oren expect?")
        add("conversation","question_transient_and_grounded",
            asm.memory.count_events()==before and not q["consolidation"]["persist"] and "Oren expects the bridge to open" in q["reply"],
            reply=q["reply"],recalled=q["recalled"][:2])

        # Existing ANN remains populated alongside structured memory.
        add("architecture","parallel_memory_paths",
            asm.event_memory.count()==asm.memory.count_events() and asm.semantic_memory.count()==asm.memory.count_events(),
            episodic=asm.memory.count_events(),event_records=asm.event_memory.count(),semantic_vectors=asm.semantic_memory.count())
    finally:
        asm.close()

# Bounded scaling test of the structured index itself.  This avoids conflating
# event-index latency with the much heavier full cognitive training pipeline.
scaling={}
with tempfile.TemporaryDirectory() as td:
    db=Path(td)/"scale.db"
    epi=EpisodicMemory(db)
    sem=SemanticEventMemory(db)
    try:
        n=10_000
        started=time.perf_counter()
        for i in range(n):
            agent=f"agent{i%200}"
            kind=("belief","expectation","fear","goal")[i%4]
            epi_state={"belief":"believed","expectation":"expected","fear":"feared","goal":"desired"}[kind]
            topic=f"device{i%500} state {i%17}"
            eid=epi.add_event(
                f"{agent} {kind} {topic}",
                {f"STEM:device{i%500}":1.0},[],0.2,0.3,
            )
            event=SemanticEvent(kind,epi_state,.9,"scale",[agent],Proposition.from_surface(topic))
            sem.add(eid,SemanticDecision(event),raw_text=f"{agent} {kind} {topic}")
        build_s=time.perf_counter()-started
        times=[]; correct=0
        for j in range(200):
            idx=(j*37)%n
            agent=f"agent{idx%200}"
            kind=("belief","expectation","fear","goal")[idx%4]
            verb={"belief":"believe","expectation":"expect","fear":"fear","goal":"want"}[kind]
            q=f"what does {agent} {verb}?"
            t0=time.perf_counter()
            got=sem.recall(q,limit=3)
            times.append((time.perf_counter()-t0)*1000)
            correct += int(bool(got and got[0]["event_type"]==kind and agent in got[0]["agents"]))
        ordered=sorted(times)
        scaling={
            "records":n,
            "build_seconds":round(build_s,3),
            "query_cases":len(times),
            "typed_top1_correct":correct,
            "typed_top1_accuracy_pct":round(100*correct/len(times),2),
            "median_query_ms":round(statistics.median(times),6),
            "p95_query_ms":round(ordered[int(.95*(len(ordered)-1))],6),
            "db_bytes":db.stat().st_size,
            "event_memory_stats":sem.stats(),
        }
        add("scaling","10k_typed_query_correct",correct==len(times),**scaling)
    finally:
        sem.close(); epi.close()

passed=sum(int(x["pass"]) for x in rows)
total=len(rows)
payload={
    "benchmark":"ASM v0.2.0-alpha.7 Semantic Memory 2.0",
    "version":__version__,
    "summary":{"passed":passed,"total":total,"accuracy_pct":round(100*passed/max(1,total),2)},
    "scaling":scaling,
    "cases":rows,
    "notes":[
        "This is an architecture/regression benchmark, not an AGI or general-intelligence score.",
        "Structured links are temporal/revision evidence only; no causal relationship is claimed.",
        "The 10k timing isolates the SQLite structured event index and is environment-specific.",
    ],
}
out=Path(__file__).parent/"results/semantic_memory2_benchmark.json"
out.write_text(json.dumps(payload,indent=2),encoding="utf-8")
print(json.dumps({"version":__version__,"summary":payload["summary"],"scaling":scaling},indent=2))
print("RESULT:",out)
if passed != total:
    raise SystemExit(1)
