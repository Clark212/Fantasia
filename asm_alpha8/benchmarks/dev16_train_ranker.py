"""DEV16: train and evaluate the learned candidate ranker on training data from dev16_build_training.py.

Evaluation is leave-one-PROJECT-out: for each subject, a model is trained on every other subject and scored on the
held-out subject's pairs only, so nothing about a project is learned from the project being tested. Per pair, the block
that matters is the candidate list in which the true fix appears (its suspect and phase): the workflow tries that list in
order, so the true fix's position in it is what a ranker changes. Reported beside the fixed (DEV15) order:
  - within-block rank of the true fix (top-1 / top-5 / top-20 / MRR / mean), learned vs given;
  - candidates tried before the true fix in the WHOLE search (earlier blocks + position), learned vs given: this is what
    turns into time budget.
Pairs whose fix is not in any generated list cannot be helped by ranking and are counted separately.
Finally, a model trained on ALL subjects is saved (sealed) with its provenance.
Usage: python benchmarks/dev16_train_ranker.py <training.jsonl> <model_out.json> <report_out.json> [--kind=logistic]
"""
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from asm.coding.integrity import file_sha256, read_records  # noqa: E402
from asm.learning.engine import CountModel, LearnedModel, LogisticModel, dataset_hash, evaluate_ranking  # noqa: E402


def blocks_of(pair: dict) -> dict:
    out: dict = {}
    for r in pair["rows"]:
        out.setdefault((r["suspect_rank"], r["phase"]), []).append(r)
    return out


def global_order(blocks: dict) -> list:
    """The workflow's block order: phase 1 over every suspect, then phase 2 over every suspect."""
    return sorted(blocks, key=lambda k: (k[1], k[0]))


def make_model(kind: str, seed: int = 0):
    return LogisticModel(seed=seed, epochs=6) if kind == "logistic" else CountModel()


def evaluate_fold(model, pairs: list) -> tuple:
    groups, tried_given, tried_learned = [], [], []
    for p in pairs:
        blocks = blocks_of(p)
        hit = next((k for k in global_order(blocks) if any(r["label"] for r in blocks[k])), None)
        if hit is None:
            continue
        g = [(model.decision(r["features"]), bool(r["label"]), r["position"]) for r in blocks[hit]]
        groups.append(g)
        before = sum(len(blocks[k]) for k in global_order(blocks)[: global_order(blocks).index(hit)])
        given = next(r["position"] for r in blocks[hit] if r["label"]) + 1
        learned = 1 + sum(1 for s, t, pos in g if (s, -pos) > next((s2, -p2) for s2, t2, p2 in g if t2))
        tried_given.append(before + given)
        tried_learned.append(before + learned)
    return groups, tried_given, tried_learned


def summary_tried(xs):
    return {"pairs": len(xs), "median": statistics.median(xs) if xs else None, "mean": round(statistics.mean(xs), 1) if xs else None,
            "within_80": sum(x <= 80 for x in xs), "within_40": sum(x <= 40 for x in xs)}


def main():
    src, model_out, report_out = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    kind = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--kind=")), "logistic")
    manifest, recs = {}, []
    for part in str(src).split(","):  # several training files (shards) may be given, comma-separated
        m, r = read_records(part)
        manifest, recs = manifest or m, recs + r
    pairs = [r for r in recs if r.get("status") == "ok"]
    subjects = sorted({p["subject"] for p in pairs})
    folds, all_groups, all_given, all_learned = {}, [], [], []
    for held in subjects:
        train = [p for p in pairs if p["subject"] != held]
        test = [p for p in pairs if p["subject"] == held]
        rows = [r for p in train for r in p["rows"]]
        if not rows or not any(r["label"] for r in rows):
            continue
        m = make_model(kind).fit([r["features"] for r in rows], [r["label"] for r in rows])
        groups, given, learned = evaluate_fold(m, test)
        folds[held] = {"train_pairs": len(train), "test_pairs": len(test), "ranking": evaluate_ranking(groups),
                       "tried_given": summary_tried(given), "tried_learned": summary_tried(learned)}
        all_groups += groups
        all_given += given
        all_learned += learned
    rows = [r for p in pairs for r in p["rows"]]
    final = make_model(kind).fit([r["features"] for r in rows], [r["label"] for r in rows])
    reachable = sum(1 for p in pairs if p.get("true_candidate"))
    report = {"input_sha256": {Path(x).name: file_sha256(x) for x in src.split(",")}, "kind": kind, "pairs": len(pairs), "subjects": subjects,
              "generators": sorted({str(p.get("generator")) for p in pairs}),
              "fix_in_generated_lists": reachable, "fix_in_repair_space": sum(1 for p in pairs if p.get("in_repair_space")),
              "leave_one_project_out": {"ranking": evaluate_ranking(all_groups), "tried_given": summary_tried(all_given),
                                        "tried_learned": summary_tried(all_learned)},
              "folds": folds}
    lm = LearnedModel("dev16_candidate_ranker", final, None,
                      {"training_file_sha256": {Path(x).name: file_sha256(x) for x in src.split(",")}, "dataset_sha256": dataset_hash([r["features"] for r in rows],
                                                                                                [r["label"] for r in rows]),
                       "rows": len(rows), "groups": len(subjects), "kind": kind, "pairs": len(pairs),
                       "generators": report["generators"], "asm_coding_sha256_of_data": manifest.get("asm_coding_sha256")},
                      {"leave_one_project_out": report["leave_one_project_out"]})
    report["model_sha256"] = lm.save(model_out)
    report_out.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    print(json.dumps(report["leave_one_project_out"], indent=1))


if __name__ == "__main__":
    main()
