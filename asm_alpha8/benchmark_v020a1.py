from __future__ import annotations

import json
import math
import tempfile
import time
from pathlib import Path

from asm import (
    ASMEngine,
    CallableLanguageCore,
    LanguageGenerationResult,
    LanguageProposal,
    LanguageReadResult,
    __version__,
)
from asm.language_core import LanguageCore


class BrokenCore(LanguageCore):
    name = "broken"
    def read(self, text):
        raise RuntimeError("benchmark failure")
    def generate(self, state, *, instruction=""):
        return LanguageGenerationResult("", self.name)


def core_with(proposals=(), *, name="mock", response="mock output"):
    def read(text):
        return LanguageReadResult(
            text=text,
            backend=name,
            tokens=["opaque"],
            embedding=[0.5, -0.5, 0.5, -0.5],
            proposals=list(proposals),
        )
    def write(state, instruction):
        return LanguageGenerationResult(
            response + (f":{instruction}" if instruction else ""),
            name,
            0.9,
            {"state_seen": bool(state)},
        )
    return CallableLanguageCore(read, write, name=name, capabilities={"learned_language": True})


rows=[]
def add(name, ok, details=None):
    rows.append({"name": name, "pass": bool(ok), "details": details or {}})

with tempfile.TemporaryDirectory() as td:
    td=Path(td)

    asm=ASMEngine(td/"fallback.db")
    t0=time.perf_counter()
    vectors=[asm.embed_text("practice improves skill") for _ in range(100)]
    embed_ms=(time.perf_counter()-t0)*1000/100
    v=vectors[0]
    add("fallback_embedding_contract", len(v)==asm.cfg.language_core_embedding_dims and abs(math.sqrt(sum(x*x for x in v))-1)<1e-6, {"dims":len(v),"mean_ms":embed_ms})
    r=asm.process("Alice suspects Bob thinks the key is hidden",training=True)
    add("fallback_native_compatibility", asm.nested_belief(["Alice","Bob"],"key is hidden")["truth"] is True and r["language_core"]["backend"]=="fallback")
    asm.close()

    high=LanguageProposal("belief",{"holder":"Nova","proposition_text":"reactor is safe","polarity":True},0.94,"benchmark")
    asm=ASMEngine(td/"high.db",language_core=core_with([high]))
    r=asm.process("opaque",training=True)
    add("high_confidence_proposal_accepted", asm.belief("Nova","reactor is safe")["truth"] is True and len(r["language_core"]["accepted"])==1)
    asm.close()

    low=LanguageProposal("belief",{"holder":"Nova","proposition_text":"reactor is unsafe","polarity":True},0.25,"benchmark")
    asm=ASMEngine(td/"low.db",language_core=core_with([low]))
    r=asm.process("opaque",training=True)
    add("low_confidence_proposal_rejected", asm.belief("Nova","reactor is unsafe")["status"]=="unknown" and r["language_core"]["rejected"][0]["reason"]=="below_confidence_gate")
    asm.close()

    nested=LanguageProposal("nested_belief",{"path":["A","B"],"proposition_text":"door is locked","polarity":True},0.91,"benchmark")
    asm=ASMEngine(td/"nested.db",language_core=core_with([nested]))
    asm.process("opaque",training=True)
    add("external_nested_belief_route", asm.nested_belief(["A","B"],"door is locked")["truth"] is True)
    asm.close()

    outcome=LanguageProposal("self_outcome",{"task_family":"reasoning","strategy":"simulation","success":True,"score":0.9},0.93,"benchmark")
    asm=ASMEngine(td/"self.db",language_core=core_with([outcome],response="writer-ok"))
    asm.process("opaque",training=True)
    add("external_self_model_route", asm.capability("reasoning")["attempts"]==1)
    generated=asm.generate_text("explain")
    add("writer_routing", generated["backend"]=="mock" and generated["text"]=="writer-ok:explain")
    asm.close()

    asm=ASMEngine(td/"broken.db",language_core=BrokenCore())
    r=asm.process("Alice suspects Bob thinks the key is hidden",training=True)
    add("backend_fail_open", r["language_core"]["backend"]=="fallback" and r["language_core"]["metadata"].get("failover_from")=="broken")
    asm.close()

passed=sum(int(x["pass"]) for x in rows)
payload={
    "benchmark":"ASM v0.2.0-alpha.1 Language Cortex Interface",
    "version":__version__,
    "passed":passed,
    "total":len(rows),
    "accuracy_pct":round(100*passed/max(1,len(rows)),2),
    "cases":rows,
    "notes":[
        "This tests the cortex/ASM boundary, not learned language quality.",
        "The fallback embedding is a deterministic hashed placeholder, not a neural semantic embedding.",
        "No RWKV or Mamba checkpoint is bundled in alpha.1.",
    ],
}
out=Path('/mnt/data/ASM_v0.2.0-alpha.1_language_core_benchmark.json')
out.write_text(json.dumps(payload,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in payload.items() if k!='cases'},indent=2))
print('RESULT:',out)
