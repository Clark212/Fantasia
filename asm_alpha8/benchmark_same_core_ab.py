from __future__ import annotations
import json, math, tempfile
from pathlib import Path
from asm import ASMEngine, ASMConfig

AGENTS = ["Aria","Bram","Cora","Dax","Eli","Faye","Gio","Hana","Iris","Jace","Kira","Luca"]
ITEMS = ["cobalt key","amber disk","silver card","green map","black token","white badge","violet ring","orange chip","bronze tag","blue note","red seal","gold pin"]
PLACES = ["locker seven","drawer three","cabinet nine","shelf two","box eleven","case five","room four","desk eight","vault six","rack ten","bin one","folder twelve"]

def cosine(a,b):
    dot=sum(x*y for x,y in zip(a,b)); na=math.sqrt(sum(x*x for x in a)); nb=math.sqrt(sum(y*y for y in b))
    return dot/(na*nb) if na and nb else 0.0

def main():
    with tempfile.TemporaryDirectory() as td:
        cfg=ASMConfig(snapshot_every_events=999999)
        e=ASMEngine(Path(td)/"ab.db",config=cfg)
        facts=[]; vectors=[]
        for agent,item,place in zip(AGENTS,ITEMS,PLACES):
            text=f"{agent} believes the {item} is in {place}."
            facts.append(text)
            vectors.append(e.embed_text(text))
            e.process(text,training=True)
        vector_ok=0; asm_ok=0; rows=[]
        for idx,(agent,item,place) in enumerate(zip(AGENTS,ITEMS,PLACES)):
            query=f"What does {agent} believe about the {item}?"
            qv=e.embed_text(query)
            sims=[cosine(qv,v) for v in vectors]
            vi=max(range(len(sims)),key=lambda i:sims[i])
            vector_hit=vi==idx
            recalled=e.recall_events(query,limit=1)
            asm_hit=bool(recalled) and recalled[0].get("text")==facts[idx]
            vector_ok+=int(vector_hit); asm_ok+=int(asm_hit)
            rows.append({"query":query,"vector_hit":vector_hit,"asm_hit":asm_hit,"vector_top":facts[vi],"asm_top":recalled[0].get("text") if recalled else None})
        out={"benchmark":"same frozen language core: plain vector memory vs ASM structured event memory","cases":len(rows),"vector_correct":vector_ok,"asm_correct":asm_ok,"vector_accuracy":vector_ok/len(rows),"asm_accuracy":asm_ok/len(rows),"rows":rows,"claim_boundary":"Measures retrieval on this controlled belief-memory task only; it is not a general intelligence benchmark."}
        print(json.dumps(out,indent=2))
        e.close()
if __name__=="__main__": main()
