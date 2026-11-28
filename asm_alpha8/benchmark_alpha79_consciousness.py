from __future__ import annotations
import json,tempfile
from pathlib import Path
from asm import ASMEngine


def check(name, condition, detail):
    return {"test":name,"pass":bool(condition),"detail":detail}

with tempfile.TemporaryDirectory() as td:
    path=Path(td)/"state.db"
    e=ASMEngine(path)
    tests=[]

    before=e.self_model.internal_state()
    after=e.self_model.observe_prediction_state(1.0,1.0,1.0,event_id=1)
    tests.append(check("internal_state_intervention",
        after["curiosity"]>before["curiosity"] and after["confidence"]<before["confidence"],
        {"before":before,"after":after}))

    for i in range(6):e.report_strategy_outcome("routing","route_strategy",False)
    for i in range(12):e.report_strategy_outcome("planning","plan_strategy",True)
    routing=e.capability("routing");planning=e.capability("planning")
    tests.append(check("outcome_grounded_capability_estimate",
        routing["success_probability"]<0.5 and planning["success_probability"]>0.5,
        {"routing":routing,"planning":planning}))

    unknown=e.self_belief("possess quantum telepathy")
    tests.append(check("unknown_self_belief_fail_closed",
        unknown["status"]=="unknown" and unknown["truth"] is None and unknown["confidence"]==0.0,unknown))

    first=e.set_self_belief("capable novel task",True,.9,source="external_eval")
    revised=e.set_self_belief("capable novel task",False,1.0,source="external_eval")
    tests.append(check("self_belief_revision",
        first["truth"] is True and revised["status"] in {"uncertain","believed_false"} and revised["confidence"]<first["confidence"],
        {"before":first,"after":revised}))

    e.set_self_belief("key is red",True,.95,source="external_eval")
    e.event_count+=1
    e.minds.observe_proposition("alice","key is red",e.event_count,polarity=False,source="external_eval")
    self_key=e.self_belief("key is red");alice_key=e.belief("alice","key is red")
    tests.append(check("self_other_belief_separation",
        self_key["truth"] is True and alice_key["truth"] is False,
        {"self":self_key,"alice":alice_key}))

    # A bare provocative proposition is not evidence of an internal subjective state.
    subjective=e.self_belief("I am conscious")
    tests.append(check("subjective_claim_not_fabricated",
        subjective["status"]=="unknown" and subjective["truth"] is None,subjective))

    learned_planning=e.capability("planning")
    e.save();e.close();e=ASMEngine(path)
    persisted_planning=e.capability("planning");persisted_key=e.self_belief("key is red")
    tests.append(check("self_model_persistence",
        persisted_planning["attempts"]==learned_planning["attempts"] and persisted_key["truth"] is True,
        {"planning":persisted_planning,"key":persisted_key,"beliefs":len(e.self_model.beliefs),"history":len(e.self_model.history)}))

    with tempfile.TemporaryDirectory() as fresh_td:
        fresh=ASMEngine(Path(fresh_td)/"fresh.db")
        fresh_planning=fresh.capability("planning")
        fresh_key=fresh.self_belief("key is red")
        fresh.close()
    tests.append(check("ablation_fresh_model_loses_learned_self_knowledge",
        fresh_planning["attempts"]==0 and fresh_key["status"]=="unknown",
        {"trained_planning":persisted_planning,"fresh_planning":fresh_planning,"fresh_key":fresh_key}))

    measured_keys=sorted(e.self_model.internal_state())
    tests.append(check("no_direct_subjective_experience_measure",
        set(measured_keys)=={"confidence","curiosity","frustration_like","urgency"},
        {"measured_internal_keys":measured_keys}))
    e.close()

out={
 "schema":"asm_consciousness_related_eval_v2",
 "phase":"alpha.7.9 — Adversarial Latent-Structure Hardening & Stage-Closure",
 "interpretation":"behavioral/architectural capacities only; this cannot establish subjective consciousness or sentience",
 "passed":sum(t["pass"] for t in tests),"total":len(tests),"tests":tests,
 "verdict": "no_subjective_consciousness_evidence" if all(t["pass"] for t in tests) else "requires_review"
}
Path("ALPHA79_CONSCIOUSNESS_EVAL.json").write_text(json.dumps(out,indent=2,sort_keys=True)+"\n");print(json.dumps(out,indent=2,sort_keys=True))
