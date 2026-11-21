"""Machine-readable summaries of DEV15 benchmark records and the pre-registered decision rules L1 and G1, implemented
exactly as written in benchmarks/preregistration/dev15_study.md. Pure functions of the records, so the results verifier
can recompute every published number."""
import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dev14_summaries as S14  # noqa: E402
from dev14_summaries import decoy_rows, is_correct, is_wrong, rate  # noqa: E402

L15_LOW = {"alternatives_disagree"}
L15_MEDIUM = {"underdetermined", "behaviour_unverified", "competing_patches_in_other_functions",
              "behavioural_deviation_persists"}


def label_l15(flags: list) -> str:
    f = set(flags or [])
    return "low" if f & L15_LOW else ("medium" if f & L15_MEDIUM else "high")


def label_dev14(flags: list) -> str:
    """The shipped DEV14 rule (R1 outcome: tied_localization informational)."""
    return S14.label_of(flags or [], True)


def _by_label(wrong: list, ctrl: list, rule) -> dict:
    out = {}
    for lab in ("high", "medium", "low"):
        w = sum(rule(x["flags"]) == lab for x in wrong)
        c = sum(rule(x["flags"]) == lab for x in ctrl)
        out[lab] = rate(w, w + c)
    return out


def _ordered(by: dict) -> bool:
    ps = [by[l]["p"] for l in ("high", "medium", "low")]
    return all(p is not None for p in ps) and ps[0] < ps[1] < ps[2]


def prereg_l1(records: list, sensitivity: bool = False) -> dict:
    rows = decoy_rows(records)
    wrong = [x for x in rows if x["kind"] == "decoy" and is_wrong(x, sensitivity)]
    ctrl = [x for x in rows if x["kind"] in ("true_fix", "single") and is_correct(x)]
    l15, d14 = _by_label(wrong, ctrl, label_l15), _by_label(wrong, ctrl, label_dev14)
    if len(wrong) < 10:
        decision, ship = "insufficient evidence (fewer than 10 WRONG decoys): keep the DEV14 rule", False
    elif _ordered(l15) and all(l15[l]["n"] >= 5 for l in l15):
        decision, ship = "L15 orders risk on the fresh decoys: ship L15", True
    else:
        decision, ship = "L15 ordering not confirmed: keep the DEV14 rule", False
    flags = sorted({f for x in rows for f in x["flags"]})
    return {"n_wrong_decoys": len(wrong), "n_correct_controls": len(ctrl),
            "p_wrong_given_label_L15": l15, "L15_ordered": _ordered(l15),
            "p_wrong_given_label_DEV14_rule": d14, "DEV14_rule_ordered": _ordered(d14),
            "flag_rates": {f: {"wrong": rate(sum(f in x["flags"] for x in wrong), len(wrong)),
                               "correct": rate(sum(f in x["flags"] for x in ctrl), len(ctrl))} for f in flags},
            "L1": decision, "ship_L15": ship}


def summarize_decoys(records: list) -> dict:
    rows = decoy_rows(records)
    return {"faults": len(records), "rows": len(rows),
            "decoy_classes": dict(sorted(collections.Counter(x["class"] for x in rows if x["kind"] == "decoy").items())),
            "control_classes": dict(sorted(collections.Counter(x["class"] for x in rows if x["kind"] != "decoy").items())),
            "L1": prereg_l1(records), "L1_sensitivity": prereg_l1(records, sensitivity=True)}


def _accepted(res: list) -> list:
    return [w for w in res if w.get("status") == "resolved" and "class" in w]


def summarize_calibration(records: list) -> dict:
    out = {"faults": len(records)}
    for s in ("half", "weak"):
        out[s] = {}
        for m in ("dev15", "dev14"):
            wfs = [r[s][m] for r in records if s in r and m in r[s]]
            acc = _accepted(wfs)
            judged = [w for w in acc if is_wrong(w) or is_correct(w)]
            out[s][m] = {"runs": len(wfs), "status": dict(sorted(collections.Counter(w["status"] for w in wfs).items())),
                         "accepted_classes": dict(sorted(collections.Counter(w["class"] for w in acc).items())),
                         "accepted_wrong": rate(sum(is_wrong(w) for w in judged), len(judged)),
                         "accepted_families": dict(sorted(collections.Counter("+".join(w.get("families") or []) for w in acc).items())),
                         "wrong_labels_dev14_rule": sorted(label_dev14(w.get("flags")) for w in judged if is_wrong(w)),
                         "wrong_labels_L15": sorted(label_l15(w.get("flags")) for w in judged if is_wrong(w)),
                         "W": sum(is_wrong(w) for w in judged), "A": len(judged)}
        # paired view: same fault, same suite
        pairs = [(r[s]["dev15"], r[s]["dev14"]) for r in records if s in r]
        out[s]["paired"] = dict(sorted(collections.Counter(
            f"{_cls(a)} | {_cls(b)}" for a, b in pairs).items()))
    h = out["half"]
    w15, a15, w14 = h["dev15"]["W"], h["dev15"]["A"], h["dev14"]["W"]
    keep = (a15 == 0 or w15 / a15 <= 0.10) and w15 <= w14 + 1
    out["G1"] = {"W15": w15, "A15": a15, "W14": w14,
                 "decision": "keep extended_ops on by default" if keep else "extended_ops becomes opt-in (default off)",
                 "keep_default_on": keep}
    return out


def _cls(w: dict) -> str:
    if w.get("status") != "resolved":
        return w.get("status", "?")
    return "WRONG" if is_wrong(w) else ("CORRECT" if is_correct(w) else w.get("class", "?"))


def summarize_realbugs(records: list) -> dict:
    base = S14.summarize_evaluate(records)
    res = [r for r in records if r.get("status") == "resolved"]
    base["resolved_families"] = dict(sorted(collections.Counter("+".join(r.get("families") or []) for r in res).items()))
    base["resolved_fixed_tests_pass"] = sum(1 for r in res if r.get("fixed_tests_on_patched") == "passed")
    base["resolved_wrong_primary"] = sum(1 for r in res if is_wrong({"class": r.get("oracle_class"), "original_ok": r.get("original_ok")}))
    base["resolved_correct"] = sum(1 for r in res if r.get("oracle_class") in ("restored", "equivalent"))
    base["resolved_list"] = [{k: r.get(k) for k in ("project", "bug", "desc", "families", "label", "flags", "oracle_class",
                                                    "original_ok", "fixed_tests_on_patched")} for r in res]
    base["labels_L15"] = dict(sorted(collections.Counter(label_l15(r.get("flags")) for r in res).items()))
    return base
