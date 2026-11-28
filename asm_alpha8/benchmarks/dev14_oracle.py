"""DEV14 ground-truth oracle: original (correct) program vs patched program on (a) the inputs the original program's own
tests use, (b) perturbations of them, and (c) GENERATED inputs beyond the test suite.

Independence from the workflow: the workflow's verification generates 100 inputs with seed 0; this oracle generates 200
with seed 7919, so it does not simply re-check the flags with the inputs the flags already saw.
Classes:
  restored             AST-equal to the original
  wrong                differs on a recorded or perturbed input (in-distribution evidence)
  wrong_generated      differs ONLY on generated inputs (weaker: may be outside the intended domain)
  equivalent           no difference on any compared input
  unknown              no replay possible
For wrong_generated, `original_ok` says whether the original program returned normally (did not raise) on at least one
differing input, i.e. the input was one the original handles.
Original-program replays are cached per (repo, function), since every candidate is compared with the same original.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from asm.coding.verification import _canon, build_inputs, generation_plan, run_versions, verification_target  # noqa: E402

GEN_BUDGET = 200
GEN_SEED = 7919
_ORIG_CACHE: dict = {}


def behaviour_diff(original_repo: Path, patched_repo: Path, qname: str, funcs: dict, orig_spectrum,
                   gen_budget: int = GEN_BUDGET) -> dict:
    target, via = verification_target(qname, funcs)
    if target is None:
        return {"status": "unavailable", "why": "enclosing function unresolved"}
    local = target.qname[len(target.module) + 1:]
    records = orig_spectrum.records.get(f"{target.path}:{local}", [])
    if not records:
        return {"status": "unavailable", "why": "no replayable calls recorded by the original program's tests"}
    inputs = build_inputs(records, orig_spectrum.outcomes,
                          generate=generation_plan(original_repo, target, gen_budget, GEN_SEED))
    diags: list = []
    key = (str(original_repo), target.qname, gen_budget)
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
    return {"status": "differs" if diff else "equal", "inputs": len(idx),
            "inputs_by_origin": {o: sum(1 for i in idx if inputs[i]["origin"] == o) for o in ("recorded", "perturbed", "generated")},
            "n_diff": len(diff), "n_diff_in_dist": len(in_dist), "n_diff_generated": len(gen),
            "generated_original_ok": any(not a[i]["exc"] for i in gen),
            "example": inputs[diff[0]]["desc"] if diff else None, "via_enclosing": via}


def classify_patch(original_repo: Path, patched_repo: Path, restored: bool, funcs_to_check: list, funcs: dict,
                   orig_spectrum, gen_budget: int = GEN_BUDGET) -> dict:
    if restored:
        return {"class": "restored", "details": {}}
    details = {q: behaviour_diff(original_repo, patched_repo, q, funcs, orig_spectrum, gen_budget)
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
