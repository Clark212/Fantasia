from __future__ import annotations

import json
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from asm import ASMEngine, __version__

rows=[]
def add(name,ok,details=None):
    rows.append({"name":name,"pass":bool(ok),"details":details or {}})

with tempfile.TemporaryDirectory() as td:
    asm=ASMEngine(Path(td)/"bench.db")
    try:
        for text in ("hi","how are you","buhh hole","im angry at u"):
            before_events=asm.memory.count_events()
            before_nodes=len(asm.field.nodes)
            r=asm.process(text)
            add(
                f"transient:{text}",
                (not r["consolidation"]["persist"])
                and asm.memory.count_events()==before_events
                and len(asm.field.nodes)==before_nodes,
                r["consolidation"],
            )

        r=asm.process("signal triggers alarm")
        add(
            "structured_overrides_social_probe",
            r["consolidation"]["persist"] and r["structure"]["supported"],
            r["consolidation"],
        )

        for text in ("hello","pressure increases temperature","thanks","practice increases skill"):
            asm.process(text)
        nested=[k for k in asm.field.nodes if k.startswith("ATTEND:ATTEND:")]
        add("no_attention_recursion",not nested,{"nodes":nested})

        asm.process("Alice believes the gate is open",training=True)
        asm.process("Bob believes the lamp is on",training=True)
        read=asm._read_language("Alice thinks the gate is open")
        sem=asm.semantic_memory.recall(read.embedding,limit=2,tag="belief")
        add(
            "typed_ann_belief_paraphrase",
            bool(sem) and sem[0]["text"]=="Alice believes the gate is open",
            {"matches":[{"text":x["text"],"similarity":x.get("semantic_similarity")} for x in sem]},
        )

        times=[]
        for _ in range(100):
            t0=time.perf_counter()
            asm.semantic_memory.recall(read.embedding,limit=5,tag="belief")
            times.append((time.perf_counter()-t0)*1000)
        latency={
            "median_ms":statistics.median(times),
            "p95_ms":sorted(times)[94],
        }
    finally:
        asm.close()

with tempfile.TemporaryDirectory() as td:
    db=Path(td)/"cli.db"
    proc=subprocess.run(
        [sys.executable,"main.py","--empty","--db",str(db)],
        cwd=ROOT,input="/embed\n/quit\n",text=True,capture_output=True,timeout=30,
    )
    asm=ASMEngine(db)
    try:
        add(
            "incomplete_command_not_learned",
            proc.returncode==0
            and "Use: /embed <text>" in proc.stdout
            and asm.memory.count_events()==0,
            {"events":asm.memory.count_events()},
        )
    finally:
        asm.close()

summary={
    "passed":sum(int(x["pass"]) for x in rows),
    "total":len(rows),
}
summary["accuracy_pct"]=round(100*summary["passed"]/max(1,summary["total"]),2)
payload={
    "benchmark":"ASM v0.2.0-alpha.3 real-session regression",
    "version":__version__,
    "summary":summary,
    "semantic_ann_latency":latency,
    "cases":rows,
    "notes":[
        "Derived from failures observed in a real alpha.2 interactive session.",
        "Not a standardized intelligence or AGI benchmark.",
        "ANN is typed and thresholded because the small recurrent embedding is not a broad pretrained semantic model.",
    ],
}
out=Path("/mnt/data/ASM_v0.2.0-alpha.3_realworld_benchmark.json")
out.write_text(json.dumps(payload,indent=2),encoding="utf-8")
print(json.dumps({"summary":summary,"semantic_ann_latency":latency},indent=2))
print("RESULT:",out)
