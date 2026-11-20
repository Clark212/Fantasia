from __future__ import annotations

import json
import tempfile
from pathlib import Path

from asm import ASMEngine, __version__

rows=[]
def add(name,ok,details=None):
    rows.append({"name":name,"pass":bool(ok),"details":details or {}})

with tempfile.TemporaryDirectory() as td:
    asm=ASMEngine(Path(td)/"chat.db")
    try:
        r=asm.chat("hi")
        add("greeting", "Hey" in r["reply"] and not r["consolidation"]["persist"], {"reply":r["reply"]})

        r=asm.chat("how are you")
        add(
            "functional_wellbeing",
            "internal confidence signal" in r["reply"].lower()
            and "curiosity signal" in r["reply"].lower()
            and "i feel" not in r["reply"].lower(),
            {"reply":r["reply"]},
        )

        r=asm.chat("im angry at u")
        add("negative_affect", "upset" in r["reply"].lower(), {"reply":r["reply"]})

        before=asm.memory.count_events()
        r=asm.chat("buhh hole")
        add(
            "nonsense_transient",
            "not sure what you mean" in r["reply"].lower()
            and asm.memory.count_events()==before,
            {"reply":r["reply"],"consolidation":r["consolidation"]},
        )

        told=asm.chat("Alice believes the gate is open")
        asked=asm.chat("what does Alice believe about the gate?")
        add(
            "belief_conversation",
            "remember" in told["reply"].lower()
            and "alice" in asked["reply"].lower()
            and "gate" in asked["reply"].lower()
            and "open" in asked["reply"].lower(),
            {"told":told["reply"],"asked":asked["reply"]},
        )

        asm.chat("The server crashed after memory pressure")
        r=asm.chat("what did i say about the server?")
        add("persistent_memory_query","server crashed" in r["reply"].lower(),{"reply":r["reply"]})

        asm.chat("The battery became hot")
        r=asm.chat("what did i just say?")
        add("session_followup","The battery became hot" in r["reply"],{"reply":r["reply"]})

        r=asm.chat("who are you")
        add(
            "identity",
            "ASM" in r["reply"]
            and "memory-centric" in r["reply"]
            and "recurrent" in r["reply"],
            {"reply":r["reply"]},
        )

        add("gratitude","welcome" in asm.chat("thanks")["reply"].lower())
        add("farewell","see you" in asm.chat("bye")["reply"].lower())

        status=asm.language_core_status()
        add(
            "dialogue_layer_reported",
            status.get("dialogue",{}).get("ready") is True
            and status.get("dialogue",{}).get("learned_dialogue_classifier") is False,
            {"dialogue":status.get("dialogue")},
        )
    finally:
        asm.close()

summary={"passed":sum(int(x["pass"]) for x in rows),"total":len(rows)}
summary["accuracy_pct"]=round(100*summary["passed"]/max(1,summary["total"]),2)
payload={
    "benchmark":"ASM v0.2.0-alpha.4 conversational behavior",
    "version":__version__,
    "summary":summary,
    "cases":rows,
    "notes":[
        "This tests practical conversation behavior, grounding and memory use.",
        "The conversational surface writer is hybrid/state-grounded, not a learned free-form generator.",
        "This is not an intelligence or AGI benchmark.",
    ],
}
out=Path(__file__).parent / 'results/conversation_benchmark.json'
out.write_text(json.dumps(payload,indent=2),encoding="utf-8")
print(json.dumps(payload,indent=2))
print("RESULT:",out)
