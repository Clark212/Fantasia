"""0.4.9 closure check: do the Stage 4 components work together? (main roadmap; owner-approved design 2026-11-28)

A family of partially observable worlds. A hidden cause H in {A, B} decides which of two doors leads to the goal; the
other leads to a hazard. Before acting, ASM gets one report each from several evidence sources whose reliabilities vary
(some are anti-informative) and some of which secretly copy another source. It may also query a `probe` sensor, at a
cost, any number of times. Everything ASM uses is learned from resolved training episodes of the same world:
  - how the world moves under each hypothesis (learn_world_transition; 0.4.0-0.4.1 simulation of learned mechanics);
  - each source's reliability (observe_evidence_source; 0.4.6) and which sources are redundant
    (observe_evidence_dependency_trial; 0.4.7-0.4.8);
then, in test episodes, ASM fuses the reports (update_belief_from_evidence_batch), plans with the belief-state planner
(0.4.2-0.4.5: branching, probabilistic futures, information gathering, belief-state planning) and acts in the true
world, re-planning after each observation.
Arms: full; no_reliability (sources' reliability not learned: one supplied prior); no_dependency (redundancy not
learned); no_probe (planning without the probe); no_planning (act on the most likely door); oracle (true parameters,
same planner).
Usage: python benchmarks/stage4_closure.py <out.jsonl> --worlds=a:b [--train=N] [--test=M]
"""
import json
import os
import random
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")  # one thread per process: parallel worlds otherwise thrash the CPUs
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from asm import ASMConfig, ASMEngine  # noqa: E402
from asm.planning import DiscreteBeliefState  # noqa: E402

H = ("A", "B")
ACTIONS = ("probe", "open_A", "open_B")
ARMS = ("full", "no_reliability", "no_dependency", "no_probe", "no_planning", "oracle")
PRIOR_RELIABILITY = 0.75  # what an arm that does not learn reliability is told about every source
MAX_STEPS = 6


def world(seed: int) -> dict:
    """One world: sources (reliability, or the index of the source it copies), the probe's reliability and cost."""
    rnd = random.Random(seed)
    n = rnd.randint(4, 8)
    rel = [round(rnd.choice([rnd.uniform(0.55, 0.95), rnd.uniform(0.55, 0.95), rnd.uniform(0.15, 0.4)]), 3) for _ in range(n)]
    copies = {}
    for j in rnd.sample(range(n), rnd.randint(1, max(1, n // 2))):
        k = rnd.randrange(n)
        if k != j and k not in copies and j not in copies.values():
            copies[j] = k
    return {"seed": seed, "reliability": rel, "copies": copies, "probe": round(rnd.uniform(0.7, 0.9), 3),
            "probe_cost": round(rnd.uniform(0.02, 0.08), 3)}


def reports(w: dict, h: str, rnd) -> dict:
    """One report per source: a reliable-or-not reading of h; a copy repeats its original's report."""
    other = {"A": "B", "B": "A"}
    out = {f"s{i}": (h if rnd.random() < r else other[h]) for i, r in enumerate(w["reliability"]) if i not in w["copies"]}
    for j, k in w["copies"].items():
        out[f"s{j}"] = out[f"s{k}"] if f"s{k}" in out else (h if rnd.random() < w["reliability"][k] else other[h])
    return out


def step(w: dict, h: str, state: dict, action: str, rnd) -> dict:
    if action == "probe":
        return {"loc": "start", "probe": h if rnd.random() < w["probe"] else {"A": "B", "B": "A"}[h]}
    return {"loc": "goal" if action == f"open_{h}" else "hazard"}


def train(e: ASMEngine, w: dict, n: int, rnd, arm: str):
    """Resolved training episodes: random behaviour, the truth revealed at the end."""
    for t in range(n):
        h = rnd.choice(H)
        rep = reports(w, h, rnd)
        if arm != "no_reliability":
            for s, obs in rep.items():
                e.observe_evidence_source(s, observation=obs, resolved_hypothesis=h, supplied_reliability=PRIOR_RELIABILITY)
        if arm != "no_dependency":
            e.observe_evidence_dependency_trial(f"t{t}", resolved_hypothesis=h, observations={s: [o] for s, o in rep.items()})
        state = {"loc": "start"}
        for _ in range(rnd.randint(1, 3)):
            action = rnd.choice(ACTIONS) if state["loc"] == "start" else None
            if action is None:
                break
            after = step(w, h, state, action, rnd)
            for mech in ("doors", f"doors|{h}"):
                e.learn_world_transition(mech, entity_id="agent", state=state, action=action, after_state=after)
            if action == "probe":
                e.observe_evidence_source("probe", observation=after["probe"], resolved_hypothesis=h, supplied_reliability=PRIOR_RELIABILITY)
            state = after


def learned_likelihood(e: ASMEngine):
    """P(outcome | hypothesis) from the per-hypothesis learned mechanisms; a probe reading from the probe's learned
    reliability."""
    def provider(belief, before_state, action, observation, predicted_state):
        if action == "probe" and predicted_state.get("probe") in H:
            return e.adaptive_evidence_likelihoods("probe", observation=predicted_state["probe"], hypotheses=list(H),
                                                   supplied_reliability=PRIOR_RELIABILITY)
        out = {}
        for hyp in H:
            d = e.transition_mechanisms.predict_distribution_simulated(f"doors|{hyp}", entity_id="agent", state=before_state, action=action)
            out[hyp] = sum(o["probability"] for o in d.get("outcomes", []) if o["predicted_state"] == predicted_state)
        return out if any(out.values()) else None
    return provider


def oracle_likelihood(w: dict):
    def provider(belief, before_state, action, observation, predicted_state):
        if action == "probe":
            r = w["probe"]
            return {hyp: r if predicted_state.get("probe") == hyp else 1 - r for hyp in H}
        return {hyp: 1.0 if predicted_state.get("loc") == ("goal" if action == f"open_{hyp}" else "hazard") else 0.0 for hyp in H}
    return provider


def prior(e: ASMEngine, w: dict, rep: dict, arm: str) -> DiscreteBeliefState:
    if arm == "oracle":  # exact Bayes over the independent roots with the true reliabilities
        b = {hyp: 0.5 for hyp in H}
        for i, r in enumerate(w["reliability"]):
            if i in w["copies"]:
                continue
            for hyp in H:
                b[hyp] *= r if rep[f"s{i}"] == hyp else 1 - r
        z = sum(b.values())
        return DiscreteBeliefState.from_mapping({k: v / z for k, v in b.items()})
    batch = [{"source_id": s, "observation": o, "supplied_reliability": PRIOR_RELIABILITY} for s, o in sorted(rep.items())]
    return e.update_belief_from_evidence_batch({hyp: 0.5 for hyp in H}, evidence=batch)


def act(e: ASMEngine, w: dict, h: str, belief: DiscreteBeliefState, arm: str, rnd) -> dict:
    state, probes = {"loc": "start"}, 0
    provider = oracle_likelihood(w) if arm == "oracle" else learned_likelihood(e)
    for _ in range(MAX_STEPS):
        if arm == "no_planning":
            p = belief.as_dict()
            action = f"open_{max(H, key=lambda x: (p.get(x, 0), x))}"
        else:
            actions = tuple(a for a in ACTIONS if arm != "no_probe" or a != "probe")
            r = e.plan_world_actions_belief("doors", entity_id="agent", initial_state=state, actions=actions,
                                            goal={"loc": "goal"}, avoid={"loc": "hazard"}, initial_belief=belief,
                                            likelihood_provider=provider, action_costs={"probe": w["probe_cost"]}, horizon=4)
            action = (r.get("best") or {}).get("action")
            if action is None or r.get("status") not in ("belief_contingent_plan_found", "budget_exhausted_partial_policy"):
                return {"outcome": "declined", "probes": probes}  # no policy met the planner's goal and risk thresholds
        after = step(w, h, state, action, rnd)
        if action == "probe":
            probes += 1
            like = provider(belief, state, "probe", after["probe"], after)
            belief = belief.update(like)
            state = {"loc": "start"}  # the reading is in the belief; the planner starts from the visible state again
            continue
        return {"outcome": "goal" if after["loc"] == "goal" else "hazard", "probes": probes}
    return {"outcome": "timeout", "probes": probes}


def run_world(seed: int, n_train: int, n_test: int) -> dict:
    w, out = world(seed), {}
    for arm in ARMS:
        rnd = random.Random(seed * 1000 + 7)  # the same training draws for every arm
        with tempfile.TemporaryDirectory() as td:
            e = ASMEngine(Path(td) / "w.db", config=ASMConfig(snapshot_every_events=10 ** 9))
            t0 = time.monotonic()
            train(e, w, n_train, rnd, arm)
            t1 = time.monotonic()
            res = []
            for i in range(n_test):  # every arm meets the same hidden causes, reports and probe readings
                ep = random.Random(f"{seed}:{i}")
                h = ep.choice(H)
                res.append(act(e, w, h, prior(e, w, reports(w, h, ep), arm), arm, random.Random(f"{seed}:{i}:noise")))
            e.close(save_snapshot=False)
        n = len(res)
        out[arm] = {"goal": sum(r["outcome"] == "goal" for r in res) / n, "hazard": sum(r["outcome"] == "hazard" for r in res) / n,
                    "other": sum(r["outcome"] not in ("goal", "hazard") for r in res) / n,
                    "probes": sum(r["probes"] for r in res) / n, "train_s": round(t1 - t0, 1), "test_s": round(time.monotonic() - t1, 1),
                    "episodes": "".join(r["outcome"][0].upper() + str(min(r["probes"], 9)) for r in res)}  # e.g. G0 H1 D0 T6
    return {"world": w, "arms": out}


def main():
    out = Path(sys.argv[1])
    arg = lambda k, d: next((a.split("=", 1)[1] for a in sys.argv if a.startswith(f"--{k}=")), d)  # noqa: E731
    a, b = (int(x) for x in arg("worlds", "0:1").split(":"))
    n_train, n_test = int(arg("train", "300")), int(arg("test", "100"))
    with out.open("a") as fh:
        for seed in range(a, b):
            rec = run_world(seed, n_train, n_test)
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            print(json.dumps({"seed": seed} | {k: (v["goal"], v["hazard"], v["probes"]) for k, v in rec["arms"].items()}), flush=True)


if __name__ == "__main__":
    main()
