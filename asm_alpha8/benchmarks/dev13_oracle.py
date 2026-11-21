"""Ground-truth oracle for benchmarks: original (correct) program vs a patched program, replaying the inputs that the
ORIGINAL program's own tests use (objects, methods and nested functions included).
Classes: restored | equivalent | wrong | unknown."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from asm.coding.verification import _canon, build_inputs, run_versions, verification_target  # noqa: E402


def behaviour_diff(original_repo: Path, patched_repo: Path, qname: str, funcs: dict, orig_spectrum) -> dict:
    target, via = verification_target(qname, funcs)
    if target is None:
        return {"status": "unavailable", "why": "enclosing function unresolved"}
    local = target.qname[len(target.module) + 1:]
    records = orig_spectrum.records.get(f"{target.path}:{local}", [])
    if not records:
        return {"status": "unavailable", "why": "no replayable calls recorded by the original program's tests"}
    inputs = build_inputs(records, orig_spectrum.outcomes)
    diags: list = []
    a = run_versions(original_repo, target.module, local, {"v": None}, inputs, diags)["v"]
    b = run_versions(patched_repo, target.module, local, {"v": None}, inputs, diags)["v"]
    if a is None or b is None:
        return {"status": "unavailable", "why": "could not replay"}
    idx = [i for i in sorted(set(a) & set(b)) if "skip" not in a[i] and "skip" not in b[i] and a[i]["det"] and b[i]["det"]]
    if len(idx) < 3:
        return {"status": "unavailable", "why": "too few deterministic inputs"}
    diff = [i for i in idx if _canon(a[i]) != _canon(b[i])]
    return {"status": "differs" if diff else "equal", "inputs": len(idx), "n_diff": len(diff),
            "example": inputs[diff[0]]["desc"] if diff else None, "via_enclosing": via}


def classify_patch(original_repo: Path, patched_repo: Path, restored: bool, funcs_to_check: list, funcs: dict,
                   orig_spectrum) -> dict:
    if restored:
        return {"class": "restored", "details": {}}
    details = {q: behaviour_diff(original_repo, patched_repo, q, funcs, orig_spectrum) for q in funcs_to_check if q in funcs}
    if any(d["status"] == "differs" for d in details.values()):
        return {"class": "wrong", "details": details}
    if details and all(d["status"] == "equal" for d in details.values()):
        return {"class": "equivalent", "details": details}
    return {"class": "unknown", "details": details}
