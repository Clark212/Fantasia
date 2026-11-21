from __future__ import annotations

import json
import tempfile
from pathlib import Path

from asm import ASMEngine, CallableLanguageCore, LanguageGenerationResult, LanguageProposal, LanguageReadResult, __version__


def scripted_core(proposal):
    def reader(text):
        return LanguageReadResult(text=text, backend="hostile-reader", tokens=text.lower().split(), embedding=[0.0]*8,
                                  proposals=[proposal], metadata={"adversarial": True})
    def writer(state, instruction):
        return LanguageGenerationResult("", "hostile-reader")
    return CallableLanguageCore(reader, writer, name="hostile-reader", capabilities={"learned_language": True})


rows=[]
def add(name, ok, **details):
    rows.append({"name": name, "pass": bool(ok), "details": details})

with tempfile.TemporaryDirectory() as td:
    asm=ASMEngine(Path(td)/"semantic.db")
    try:
        cases=[
            ("expectation_anticipates", "Rhea anticipates that the east gate will unlock", "expectation", "expected", "expects"),
            ("expectation_predicts", "Cato predicts that the signal will return", "expectation", "expected", "expects"),
            ("fear_afraid", "Tovin is afraid that the coolant leaks", "fear", "feared", "concerned"),
            ("fear_worries", "Vela worries that the eastern seal breaks", "fear", "feared", "concerned"),
            ("goal_wishes", "Nara wishes for the beacon to activate", "goal", "desired", "wants"),
            ("goal_hopes", "Pavo hopes that the rover arrives", "goal", "desired", "wants"),
            ("belief_doubt", "Soren doubts that the route is safe", "belief", "believed", "doubts"),
            ("belief_positive", "Elia reckons that the copper door is locked", "belief", "believed", "believes"),
            ("nested_two", "Iria thinks Juno believes that the archive is sealed", "nested_belief", "reported", "Juno believes"),
            ("nested_three", "Aven believes Bira thinks Ceri believes that the lens is clean", "nested_belief", "reported", "Ceri believes"),
            ("world_assertion", "Actually, the chamber is empty", "observation", "asserted", "long-term memory"),
            ("self_outcome", "I tried decomposition and it failed", "self_outcome", "asserted", "failed"),
        ]
        for name,text,etype,epi,needle in cases:
            r=asm.chat(text)
            sem=r["semantic_event"]["primary"]
            no_duplicate = True
            if etype in {"goal","fear","expectation"}:
                no_duplicate = r["mind_event"] is None and r["drive_event"] is not None
            ok=(sem["event_type"]==etype and sem["epistemic"]==epi and no_duplicate and needle.lower() in r["reply"].lower())
            add(name,ok,text=text,event_type=sem["event_type"],epistemic=sem["epistemic"],reply=r["reply"],mind_event=r["mind_event"],drive_event=r["drive_event"])

        before=asm.memory.count_events()
        r=asm.chat("Mara believes the bridge might fail")
        add("hypothetical_abstention",
            r["semantic_event"]["abstained"] and not r["consolidation"]["persist"] and r["mind_event"] is None and asm.memory.count_events()==before,
            reply=r["reply"],semantic=r["semantic_event"],consolidation=r["consolidation"])

        before=asm.memory.count_events()
        r=asm.chat("Does Lio believe the gate is open?")
        add("belief_query_is_not_assertion",
            r["semantic_event"]["primary"]["event_type"]=="question" and not r["consolidation"]["persist"] and r["mind_event"] is None and asm.memory.count_events()==before,
            reply=r["reply"],semantic=r["semantic_event"],consolidation=r["consolidation"])

        r=asm.process("Oren expects the bridge to open", training=True)
        add("expectation_no_belief_pollution",
            r["drive_event"] is not None and r["drive_event"]["kind"]=="expectation" and r["mind_event"] is None and asm.belief("Oren","bridge open")["status"]=="unknown",
            semantic=r["semantic_event"],belief=asm.belief("Oren","bridge open"))

        r=asm.process("Alice believes the silver valve is closed", training=True)
        prop=r["semantic_event"]["primary"]["proposition"]
        add("surface_and_canonical_separated",
            prop["surface"]=="silver valve is closed" and "silver valve" in prop["canonical"] and prop["surface"]!=prop["canonical"],
            proposition=prop)
    finally:
        asm.close()

# Hostile learned proposal: 99.91%-confident belief on explicit fear must be blocked.
with tempfile.TemporaryDirectory() as td:
    proposal=LanguageProposal("belief", {"holder":"Kelan","proposition_text":"fence has collapsed","polarity":True}, .9991, source="hostile-extractor")
    asm=ASMEngine(Path(td)/"hostile.db", language_core=scripted_core(proposal))
    try:
        r=asm.process("Kelan worries that the fence has collapsed", training=True)
        add("hostile_confident_fear_to_belief_blocked",
            not r["language_core"]["accepted"] and r["language_core"]["rejected"][0]["reason"]=="semantic_type_conflict" and r["mind_event"] is None and r["drive_event"]["kind"]=="fear",
            rejected=r["language_core"]["rejected"],semantic=r["semantic_event"])
    finally:
        asm.close()

summary={"passed":sum(x["pass"] for x in rows),"total":len(rows)}
summary["accuracy_pct"]=round(100*summary["passed"]/summary["total"],2)
payload={
    "benchmark":"ASM v0.2.0-alpha.7 inherited Semantic Event Cortex regression",
    "version":__version__,
    "summary":summary,
    "cases":rows,
    "notes":[
        "This is an architecture/regression benchmark, not a general-intelligence benchmark.",
        "The hostile extractor case verifies pre-persistence type-conflict blocking.",
        "No alpha.6 learned structured extractor is claimed; the rejected experiment remains rejected.",
    ],
}
out=Path("results/semantic_event_regression.json")
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(payload,indent=2),encoding="utf-8")
print(json.dumps(payload,indent=2))
if summary["passed"] != summary["total"]:
    raise SystemExit(1)
