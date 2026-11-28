"""Machine-readable summaries of DEV14 benchmark records, and the pre-registered decision rules (R1, R2) implemented
exactly as written in benchmarks/preregistration/dev14_fresh_calibration.md. Pure functions of the records, so the
results verifier can recompute every published number."""
import collections
import math

CORRECT = {"restored", "equivalent"}


def is_wrong(row: dict, sensitivity: bool = False) -> bool:
    """Primary: `wrong`, or `wrong_generated` with original_ok. Sensitivity analysis: `wrong` only."""
    if row["class"] == "wrong":
        return True
    return (not sensitivity) and row["class"] == "wrong_generated" and bool(row.get("original_ok"))


def is_correct(row: dict) -> bool:
    return row["class"] in CORRECT


def label_of(flags: list, demote_tie: bool) -> str:
    n = len([f for f in flags if not (demote_tie and f == "tied_localization")])
    return "low" if n >= 2 else ("medium" if n else "high")


def wilson(k, n, z=1.96):
    if n == 0:
        return [None, None]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)]


def rate(k, n):
    return {"k": k, "n": n, "p": round(k / n, 4) if n else None, "ci95": wilson(k, n)}


def decoy_rows(records: list) -> list:
    return [dict(row, subject=r["subject"], suite=s, abs_index=r["abs_index"])
            for r in records for s in ("half", "weak") if "rows" in r.get(s, {}) for row in r[s]["rows"]]


def prereg_rules(records: list, sensitivity: bool = False) -> dict:
    rows = decoy_rows(records)
    wrong = [x for x in rows if x["kind"] == "decoy" and is_wrong(x, sensitivity)]
    ctrl = [x for x in rows if x["kind"] in ("true_fix", "single") and is_correct(x)]
    tpr = rate(sum("tied_localization" in x["flags"] for x in wrong), len(wrong))
    fpr = rate(sum("tied_localization" in x["flags"] for x in ctrl), len(ctrl))
    lr = (tpr["p"] / fpr["p"]) if (tpr["p"] is not None and fpr["p"]) else (math.inf if tpr["p"] else None)
    if len(wrong) < 10:
        r1 = "insufficient evidence (fewer than 10 WRONG decoys): label rule unchanged"
        demote = False
    elif lr is not None and lr >= 2.0 and tpr["p"] >= 0.20:
        r1, demote = "keep tied_localization in the label", False
    else:
        r1, demote = "demote tied_localization to informational", True
    by_label = {}
    for lab in ("high", "medium", "low"):
        w = sum(label_of(x["flags"], demote) == lab for x in wrong)
        c = sum(label_of(x["flags"], demote) == lab for x in ctrl)
        by_label[lab] = rate(w, w + c)
    ps = [by_label[l]["p"] for l in ("high", "medium", "low")]
    ordered = all(p is not None for p in ps) and ps[0] < ps[1] < ps[2]
    return {"n_wrong_decoys": len(wrong), "n_correct_controls": len(ctrl), "tied_tpr": tpr, "tied_fpr": fpr,
            "tied_lr_plus": (None if lr is None else (round(lr, 3) if lr != math.inf else "inf")),
            "R1": r1, "R1_demote": demote, "p_wrong_given_label": by_label,
            "R2": "labels order risk" if ordered else "ordering not confirmed"}


def summarize_decoys(records: list) -> dict:
    rows = decoy_rows(records)
    decoys = [x for x in rows if x["kind"] == "decoy"]
    out = {"faults": len(records), "rows": len(rows),
           "decoy_classes": dict(sorted(collections.Counter(x["class"] for x in decoys).items())),
           "control_classes": dict(sorted(collections.Counter(x["class"] for x in rows if x["kind"] != "decoy").items())),
           "decoys_constructed": sum(r[s].get("tried_decoys", 0) for r in records for s in ("half", "weak") if "rows" in r.get(s, {})),
           "decoys_kept": len(decoys),
           "distinct_decoy_programs": len({x["patch_sha256"] for x in decoys}),
           "primary": prereg_rules(records), "sensitivity_wrong_only": prereg_rules(records, sensitivity=True)}
    wrong = [x for x in decoys if is_wrong(x)]
    ctrl = [x for x in rows if x["kind"] != "decoy" and is_correct(x)]
    out["flag_rates"] = {f: {"on_wrong": rate(sum(f in x["flags"] for x in wrong), len(wrong)),
                             "on_correct": rate(sum(f in x["flags"] for x in ctrl), len(ctrl))}
                         for f in sorted({f for x in wrong + ctrl for f in x["flags"]})}
    out["any_flag"] = {"on_wrong": rate(sum(bool(x["flags"]) for x in wrong), len(wrong)),
                       "on_correct": rate(sum(bool(x["flags"]) for x in ctrl), len(ctrl))}
    return out


def summarize_calibration(records: list) -> dict:
    out = {"faults": len(records)}
    for s in ("half", "weak"):
        ok = [r[s] for r in records if s in r and "skipped" not in r[s]]
        pats = [p for x in ok for p in x["patches"]]
        wfs = [x["workflow"] for x in ok if "workflow" in x]
        res = [w for w in wfs if w["status"] == "resolved"]
        out[s] = {"analysed": len(ok), "skipped": sum(1 for r in records if "skipped" in r.get(s, {})),
                  "plausible_classes": dict(sorted(collections.Counter(p["class"] for p in pats).items())),
                  "plausible_wrong": rate(sum(is_wrong(p) for p in pats), sum(is_wrong(p) or is_correct(p) for p in pats)),
                  "verification_available": rate(sum(p["verified"] for p in pats), len(pats)),
                  "workflow_status": dict(sorted(collections.Counter(w["status"] for w in wfs).items())),
                  "workflow_accepted_classes": dict(sorted(collections.Counter(w.get("class") for w in res).items())),
                  "workflow_accepted_wrong": rate(sum(is_wrong(w) for w in res if "class" in w),
                                                  sum(is_wrong(w) or is_correct(w) for w in res if "class" in w)),
                  "workflow_wrong_labels": sorted(w.get("label") for w in res if "class" in w and is_wrong(w)),
                  "top1": sum(1 for x in ok if x["rank"] and x["rank"][1] <= 1),
                  "top3": sum(1 for x in ok if x["rank"] and x["rank"][1] <= 3)}
    return out


def _status_family(s: str) -> str:
    return s.split("(", 1)[0]


def summarize_validate(records: list) -> dict:
    by_project = {}
    for r in records:
        by_project.setdefault(r["project"], collections.Counter())[_status_family(r["status"])] += 1
    return {"bugs": len(records),
            "status": dict(sorted(collections.Counter(_status_family(r["status"]) for r in records).items())),
            "status_detail": dict(sorted(collections.Counter(r["status"] for r in records).items())),
            "by_project": {p: dict(sorted(c.items())) for p, c in sorted(by_project.items())},
            "env_augmented_bugs": sum(1 for r in records if r.get("env_augmented")),
            "valid": sorted(f'{r["project"]}-{r["bug"]}' for r in records if r["status"] == "valid")}


def summarize_evaluate(records: list) -> dict:
    loc = [r for r in records if "best_rank" in r]
    ranked = [r for r in loc if r["best_rank"]]
    res = [r for r in records if r.get("status") == "resolved"]
    return {"evaluated": len(records), "localized": len(loc), "truth_unmapped": sum(1 for r in loc if not r["truth"]),
            "top1": sum(1 for r in ranked if r["best_rank"][1] <= 1), "top3": sum(1 for r in ranked if r["best_rank"][1] <= 3),
            "top5": sum(1 for r in ranked if r["best_rank"][1] <= 5), "truth_not_ranked": len(loc) - len(ranked),
            "workflow_status": dict(sorted(collections.Counter(r.get("status") for r in records).items())),
            "resolved_oracle_class": dict(sorted(collections.Counter(r.get("oracle_class") for r in res).items())),
            "resolved_labels": dict(sorted(collections.Counter(r.get("label") for r in res).items())),
            "resolved_wrong_by_label": dict(sorted(collections.Counter(r.get("label") for r in res if is_wrong(
                {"class": r.get("oracle_class"), "original_ok": r.get("original_ok")})).items())),
            "per_bug": [{k: r.get(k) for k in ("project", "bug", "best_rank", "status", "label", "oracle_class")} for r in records]}
