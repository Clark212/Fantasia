"""DEV15 ground-truth oracle. Same classes and independence settings as DEV14 (200 generated inputs, seed 7919), with
two changes, both fixed before any DEV15 benchmark ran (see benchmarks/preregistration/dev15_study.md):

1. CONSTANTS FROM EVERY VERSION. Generated inputs are built from constants mined from the target function in the
   reference program AND in the patched program AND (when given) the buggy program. DEV14 mined the reference only; on
   real bug thefuck-15 the developer's fix had removed the very string ASM's patch tested for, so no generated input
   contained it and a wrong patch was classed "equivalent".
2. IMPORT-TIME FUNCTIONS. A function that runs only while its module is imported has no recorded calls. DEV14 classed
   every patch to one `unknown` (96 of 174 fresh decoys). DEV15 compares (a) the module's state right after import and
   (b) replays of the recorded calls of the other functions in that module, which run on that state:
     a consumer call differs on a recorded/perturbed input  -> wrong
     no consumer difference and no state difference          -> equivalent
     state differs but no consumer call shows it             -> unknown (state is not behaviour; pre-registered)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from asm.coding.verification import (_canon, build_inputs, compare_import_state, consumer_inputs, generation_plan,  # noqa: E402
                                     import_time_function, run_module_job, run_versions, verification_target)

GEN_BUDGET = 200
GEN_SEED = 7919
_ORIG_CACHE: dict = {}


def _src(repo: Path, rel: str) -> str | None:
    try:
        return (Path(repo) / rel).read_text(encoding="utf-8")
    except OSError:
        return None


def behaviour_diff(original_repo: Path, patched_repo: Path, qname: str, funcs: dict, orig_spectrum,
                   gen_budget: int = GEN_BUDGET, extra_repos=()) -> dict:
    target, via = verification_target(qname, funcs)
    if target is None:
        return {"status": "unavailable", "why": "enclosing function unresolved"}
    local = target.qname[len(target.module) + 1:]
    records = orig_spectrum.records.get(f"{target.path}:{local}", [])
    if not records:
        if import_time_function(original_repo, target):
            return import_state_diff(original_repo, patched_repo, target, orig_spectrum)
        return {"status": "unavailable", "why": "no replayable calls recorded by the original program's tests"}
    extra = [s for s in (_src(r, target.path) for r in [patched_repo, *extra_repos]) if s is not None]
    plan = generation_plan(original_repo, target, gen_budget, GEN_SEED, extra)
    inputs = build_inputs(records, orig_spectrum.outcomes, generate=plan)
    diags: list = []
    key = (str(original_repo), target.qname, gen_budget, hash(repr(plan["mined"]) if plan else None))
    if key not in _ORIG_CACHE:
        _ORIG_CACHE[key] = run_versions(original_repo, target.module, local, {"v": None}, inputs, diags)["v"]
    a = _ORIG_CACHE[key]
    b = run_versions(patched_repo, target.module, local, {"v": None}, inputs, diags)["v"]
    if a is None or b is None:
        return {"status": "unavailable", "why": "could not replay"}
    idx = [i for i in sorted(set(a) & set(b)) if "skip" not in a[i] and "skip" not in b[i] and a[i]["det"] and b[i]["det"]]
    if len(idx) < 3:
        return {"status": "unavailable", "why": "too few deterministic inputs"}
    diff = [i for i in idx if _canon(a[i]) != _canon(b[i])]
    in_dist = [i for i in diff if inputs[i]["origin"] in ("recorded", "perturbed")]
    gen = [i for i in diff if inputs[i]["origin"] == "generated"]
    return {"status": "differs" if diff else "equal", "inputs": len(idx), "mode": "replay",
            "mined_from_versions": plan.get("mined_from_versions") if plan else 0,
            "inputs_by_origin": {o: sum(1 for i in idx if inputs[i]["origin"] == o) for o in ("recorded", "perturbed", "generated")},
            "n_diff": len(diff), "n_diff_in_dist": len(in_dist), "n_diff_generated": len(gen),
            "generated_original_ok": any(not a[i]["exc"] for i in gen),
            "example": inputs[diff[0]]["desc"] if diff else None, "via_enclosing": via}


def import_state_diff(original_repo: Path, patched_repo: Path, target, orig_spectrum) -> dict:
    consumers = consumer_inputs(target, orig_spectrum)
    diags: list = []
    a = run_module_job(original_repo, None, target.module, consumers, True, diags)
    b = run_module_job(patched_repo, None, target.module, consumers, True, diags)
    if a is None or b is None:
        return {"status": "unavailable", "why": "module import failed", "mode": "import_state"}
    c = compare_import_state(a, b, consumers)
    in_dist = [d for d in c["consumer_diffs"] if d["input"]["origin"] in ("recorded", "perturbed")]
    if in_dist:
        status = "differs"
    elif not c["state_keys"] and c["consumer_compared"] >= 3:
        status = "equal"
    else:
        status = "unavailable"
    return {"status": status, "mode": "import_state", "inputs": c["consumer_compared"], "state_keys": c["state_keys"],
            "consumers": [f["qualname"] for f in consumers], "n_diff": len(c["consumer_diffs"]),
            "n_diff_in_dist": len(in_dist), "n_diff_generated": 0, "generated_original_ok": False,
            "why": "module state differs but no consumer call shows it" if status == "unavailable" and c["state_keys"] else None,
            "example": (in_dist[0]["function"] + in_dist[0]["input"]["desc"]) if in_dist else None}


def classify_patch(original_repo: Path, patched_repo: Path, restored: bool, funcs_to_check: list, funcs: dict,
                   orig_spectrum, gen_budget: int = GEN_BUDGET, extra_repos=()) -> dict:
    if restored:
        return {"class": "restored", "details": {}}
    details = {q: behaviour_diff(original_repo, patched_repo, q, funcs, orig_spectrum, gen_budget, extra_repos)
               for q in funcs_to_check if q in funcs}
    if any(d.get("n_diff_in_dist") for d in details.values()):
        cls = "wrong"
    elif any(d.get("n_diff_generated") for d in details.values()):
        cls = "wrong_generated"
    elif details and all(d["status"] == "equal" for d in details.values()):
        cls = "equivalent"
    else:
        cls = "unknown"
    return {"class": cls, "details": details,
            "original_ok": any(d.get("generated_original_ok") for d in details.values())}
