from __future__ import annotations

import json
import os
import statistics
import tempfile
import time
from pathlib import Path

from asm import ASMEngine, ASMConfig, __version__
from asm.transition_mechanism import TransitionMechanismBank

ROOT = Path(__file__).resolve().parent
rows=[]

def add(category,name,ok,**details):
    rows.append({"category":category,"name":name,"pass":bool(ok),"details":details})

BASE=[
    ({"mode":"closed"},"open",{"mode":"open"}),
    ({"mode":"open"},"close",{"mode":"closed"}),
    ({"mode":"closed"},"lock",{"mode":"locked"}),
    ({"mode":"locked"},"unlock",{"mode":"closed"}),
    ({"mode":"locked"},"open",{"mode":"locked"}),
]

with tempfile.TemporaryDirectory() as td:
    db=Path(td)/"mechanisms.db"
    bank=TransitionMechanismBank(db, hidden_dim=48, train_steps=6, learning_rate=.01, seed=17)
    cold=bank.predict("door_state",entity_id="door_x",state={"mode":"closed"},action="open")
    add("cold","unknown_mechanism_abstains",cold["predicted_state"] is None and cold["uncertainty"]==1.0,output=cold)

    curve=[]
    for epoch in range(8):
        correct=0
        total=0
        losses=[]
        started=time.perf_counter()
        for entity in ("door_a","door_b","door_c"):
            for state,action,after in BASE:
                out=bank.observe("door_state",entity_id=entity,state=state,action=action,after_state=after)
                correct += int(out["correct_before_learning"])
                total += 1
                losses.append(out["loss"])
        curve.append({
            "epoch":epoch+1,
            "correct_before_learning":correct,
            "total":total,
            "accuracy_pct":round(100*correct/total,2),
            "mean_loss":round(statistics.mean(losses),6),
            "seconds":round(time.perf_counter()-started,4),
        })
    add("learning","training_accuracy_improves",curve[-1]["accuracy_pct"]>curve[0]["accuracy_pct"] and curve[-1]["accuracy_pct"]>=93.0,curve=curve)

    transfer=[]
    for state,action,after in BASE:
        out=bank.predict("door_state",entity_id="door_d",state=state,action=action)
        transfer.append({"state":state,"action":action,"expected":after,"prediction":out,"correct":out["predicted_state"]==after})
    transfer_correct=sum(int(x["correct"]) for x in transfer)
    add("transfer","unseen_entity_transfer",transfer_correct==len(BASE),correct=transfer_correct,total=len(BASE),cases=transfer)

    jam_state={"mode":"closed","jammed":True}
    pre=bank.predict("door_state",entity_id="door_j",state=jam_state,action="open")
    first=bank.observe("door_state",entity_id="door_j",state=jam_state,action="open",after_state={"mode":"closed","jammed":True})
    shocked=first["after_training_prediction"]
    add("uncertainty","surprise_raises_uncertainty",shocked["uncertainty"]>pre["uncertainty"]+.25,before=pre,after_first_failure=shocked)

    adaptation=[]
    for i in range(12):
        out=bank.observe("door_state",entity_id="door_j",state=jam_state,action="open",after_state={"mode":"closed","jammed":True})
        pred=bank.predict("door_state",entity_id="door_j",state=jam_state,action="open")
        adaptation.append({"step":i+1,"prediction":pred,"correct":pred["predicted_state"]=={"mode":"closed","jammed":True}})
    adapted=adaptation[-1]["prediction"]
    add("adaptation","jammed_exception_learned",adapted["predicted_state"]=={"mode":"closed","jammed":True},adaptation=adaptation)
    add("uncertainty","uncertainty_recovers_after_learning",adapted["uncertainty"]<shocked["uncertainty"],shocked=shocked["uncertainty"],adapted=adapted["uncertainty"])

    ordinary=bank.predict("door_state",entity_id="door_e",state={"mode":"closed"},action="open")
    add("retention","exception_does_not_erase_general_rule",ordinary["predicted_state"]=={"mode":"open"},prediction=ordinary)

    stats_before=bank.stats()
    bank.close()
    bank=TransitionMechanismBank(db, hidden_dim=48, train_steps=6, learning_rate=.01, seed=17)
    reloaded=bank.predict("door_state",entity_id="door_z",state={"mode":"locked"},action="unlock")
    add("persistence","weights_survive_reload",reloaded["predicted_state"]=={"mode":"closed"} and reloaded["support"]>0,prediction=reloaded,stats=bank.stats())
    bank.close()

# Prove the recurrent context is computationally consequential. Same visible READ
# input maps to different outcomes after different prior prime actions.
with tempfile.TemporaryDirectory() as td:
    bank=TransitionMechanismBank(Path(td)/"history.db",hidden_dim=48,train_steps=8,learning_rate=.01,seed=17)
    for _ in range(30):
        for entity,prime,bit in (("left","prime_left",0),("right","prime_right",1)):
            bank.observe("history_gate",entity_id=entity,state={"signal":"neutral"},action=prime,after_state={"signal":"neutral"})
            bank.observe("history_gate",entity_id=entity,state={"signal":"neutral"},action="read",after_state={"bit":bit})
    recurrent_cases=[]
    for entity,prime,bit in (("fresh_l","prime_left",0),("fresh_r","prime_right",1)):
        bank.reset_context("history_gate",entity)
        bank.observe("history_gate",entity_id=entity,state={"signal":"neutral"},action=prime,after_state={"signal":"neutral"})
        pred=bank.predict("history_gate",entity_id=entity,state={"signal":"neutral"},action="read")
        recurrent_cases.append({"prime":prime,"expected":{"bit":bit},"prediction":pred,"correct":pred["predicted_state"]=={"bit":bit}})
    add("recurrence","history_changes_prediction",all(x["correct"] for x in recurrent_cases),cases=recurrent_cases)
    bank.close()

# Engine-level structured API and isolation between two mechanism types.
with tempfile.TemporaryDirectory() as td:
    engine=ASMEngine(Path(td)/"engine.db",config=ASMConfig(snapshot_every_events=999999,transition_hidden_dim=32,transition_train_steps=4))
    try:
        for _ in range(10):
            engine.learn_world_transition("switch_state",entity_id="s1",state={"on":False},action="toggle",after_state={"on":True})
            engine.learn_world_transition("switch_state",entity_id="s1",state={"on":True},action="toggle",after_state={"on":False})
        switch=engine.predict_world_transition("switch_state",entity_id="s2",state={"on":False},action="toggle")
        add("engine","structured_learning_api",switch["predicted_state"]=={"on":True},prediction=switch)
        status=engine.language_core_status()["transition_mechanisms"]
        add("engine","status_exposes_mechanisms",status["mechanisms"]>=1 and status["experiences"]>=20,status=status)
    finally:
        engine.close()

summary={"passed":sum(int(x["pass"]) for x in rows),"total":len(rows)}
summary["accuracy_pct"]=round(100*summary["passed"]/max(1,summary["total"]),2)
payload={
    "benchmark":"ASM v0.3.0-alpha.2 Local Recurrent Transition Mechanisms",
    "version":__version__,
    "summary":summary,
    "learning_curve":curve,
    "transfer":{"correct":transfer_correct,"total":len(BASE)},
    "mechanism_stats":stats_before,
    "cases":rows,
    "notes":[
        "This is an architecture benchmark, not a standardized intelligence benchmark.",
        "The door environment is deliberately small and structured to isolate transition learning and transfer.",
        "Entity identifiers are not input features; transfer comes from shared mechanism weights.",
        "Bounded replay is part of alpha.2 and is measured by the retention test.",
        "Recurrent-state usefulness is tested with identical visible READ inputs whose correct outcomes depend on prior prime actions.",
    ],
}
out=ROOT/"results/transition_mechanism_benchmark.json"
out.write_text(json.dumps(payload,indent=2),encoding="utf-8")
print(json.dumps({"version":__version__,"summary":summary,"learning_curve":curve,"transfer":payload["transfer"],"mechanism_stats":stats_before},indent=2))
print("RESULT:",out)
if summary["passed"] != summary["total"]:
    raise SystemExit(1)
